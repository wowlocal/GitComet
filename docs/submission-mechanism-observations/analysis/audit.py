"""Independent saved-file joins for the frozen submission mechanism probe."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib,json,math,statistics

ROOT=Path(__file__).resolve().parent.parent
PLAN=ROOT/'analysis/input-plan.json'
plan=json.loads(PLAN.read_text())

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def quantiles(values):
    s=sorted(values)
    if not s:return {'n':0}
    def q(p):
        k=(len(s)-1)*p;i=int(k);j=math.ceil(k);return s[i]+(s[j]-s[i])*(k-i)
    return {'n':len(s),'min':s[0],'median':q(.5),'p95':q(.95),'max':s[-1]}

def audit(series):
    folder=ROOT/'runs'/series; native_path=folder/'native.jsonl';frames_path=folder/'frames.jsonl'
    raw=[json.loads(line)for line in native_path.read_text().splitlines()]
    frames=[json.loads(line)for line in frames_path.read_text().splitlines()]
    registered=json.loads((folder/'submission-mechanism-analysis.json').read_text())
    def select(kind):return [row for row in raw if row['event']==kind]
    records=[r for r in raw if 'seq'in r]
    assert [r['seq']for r in records]==list(range(1,len(records)+1))
    assert raw[-1]['records']==len(records) and raw[-1]['dropped']==raw[-1]['marker_overflow']==0
    assert raw[0]['event']=='capture_status' and raw[1]['event']=='capture_armed'
    assert raw[-1]['event']=='capture_status' and raw[-1]['reason']=='duration'
    kinds={kind:select(kind)for kind in ['metal_update','frame_decision','submit_begin','submit_end','gpu_completed','presented','history_offset','scenario_scroll']}
    indexes={}
    for kind,rows in kinds.items():
        if kind=='history_offset':indexes[kind]={r['seq']:r for r in rows};continue
        if kind=='scenario_scroll':continue
        key=lambda r:(r['window'],r['drawable'])if kind in ['metal_update','frame_decision']else(r['window'],r['call'])
        assert len({key(r)for r in rows})==len(rows),(series,kind,'duplicate join keys')
        indexes[kind]={key(r):r for r in rows}
    assert len(indexes['metal_update'])==len(indexes['frame_decision'])
    assert len(indexes['submit_begin'])==len(indexes['submit_end'])==len(indexes['gpu_completed'])==len(indexes['presented'])
    assert set(indexes['submit_begin'])==set(indexes['submit_end'])==set(indexes['gpu_completed'])==set(indexes['presented'])
    targets=Counter((r['window'],r['target_presentation_s'])for r in kinds['metal_update'])
    inputs=[r for r in frames if r['event']=='scenario_input']; packets=kinds['scenario_scroll'];assert len(inputs)==1442 and len(packets)==1440
    offset=statistics.median(n['at_s']-a['unix_ms']/1000 for n,a in zip(packets,inputs[2:]))
    for c in range(6):assert all(p['dy']==q['delta_px']*(1 if c%2==0 else -1)for p,q in zip(packets[c*240:(c+1)*240],plan['packets']))
    phases={(r['detail']['name'],r['detail']['state']):r['unix_ms']/1000+offset for r in frames if r['event']=='scenario_phase'}
    scopes={'full_scrolling':[(phases['replay-0','begin']+.3,phases['replay-3','end']-.3)],'source_active_cores':[(packets[(c+2)*240]['at_s']+w['start_us']/1e6,packets[(c+2)*240]['at_s']+w['end_us']/1e6)for c in range(4)for w in plan['motion_core_windows']]}
    report={'series':series,'capture_sha256':sha(native_path),'frames_sha256':sha(frames_path),'registered_analyzer_sha256':registered['analyzer_sha256'],'integrity_contiguous_count':len(records),'all_raw_assigned_targets':len(targets),'duplicate_raw_assigned_target_groups':sum(v>1 for v in targets.values()),'all_join_keys_unique_and_complete':True,'scopes':{}}
    for name,spans in scopes.items():
        inside=lambda t:any(lo<=t<=hi for lo,hi in spans)
        sums=Counter(); outcomes=defaultdict(list); targetlist=[]
        for b in kinds['submit_begin']:
            if not inside(b['at_s']):continue
            key=(b['window'],b['call']);e=indexes['submit_end'][key];g=indexes['gpu_completed'][key];p=indexes['presented'][key];u=indexes['metal_update'][b['window'],b['drawable']];d=indexes['frame_decision'][b['window'],b['drawable']]
            assert all(row['drawable']==b['drawable']for row in [e,g,p]) and d['used_drawable']
            assert g['status']==4 and g['gpu_end_s']>=g['gpu_start_s']>0
            assert (p['did_present']and p['presented_s']>0)or(not p['did_present']and p['presented_s']==0)
            outcome='positive'if p['did_present']else'zero_or_not_presented';sums[outcome]+=1;sums['new_scene_'+str(b['new_scene'])+'_'+outcome]+=1
            cpu=(e['at_s']-u['deadline_s'])*1000;gpu_cpu=(g['gpu_end_s']-u['deadline_s'])*1000;gpu_target=(g['gpu_end_s']-u['target_presentation_s'])*1000
            sums['cpu_return_after_deadline']+=cpu>0;sums['gpu_end_after_cpu_deadline']+=gpu_cpu>0;sums['gpu_end_after_estimated_target']+=gpu_target>0
            outcomes[outcome].append({'cpu_return_minus_deadline_ms':cpu,'gpu_end_minus_cpu_deadline_ms':gpu_cpu,'gpu_end_minus_target_ms':gpu_target,'gpu_duration_ms':(g['gpu_end_s']-g['gpu_start_s'])*1000})
            targetlist.append(u['target_presentation_s'])
        selected_updates=[u for u in kinds['metal_update']if inside(u['at_s'])]
        per_update=[]
        for lo,hi in spans:
            items=sorted([u for u in kinds['metal_update']if lo<=u['at_s']<=hi],key=lambda u:u['seq'])
            per_update.extend((b['target_presentation_s']-a['target_presentation_s'])*1000 for a,b in zip(items,items[1:]))
        exposure=sum(hi-lo for lo,hi in spans)
        positive_display=[];gaps=[];known=held=changed=reused_new=0
        for lo,hi in spans:
            display=defaultdict(list)
            for p in kinds['presented']:
                if p['did_present']and lo<=p['presented_s']<=hi:display[p['window'],p['presented_s']].append(p)
            assert all(len(rows)==1 for rows in display.values()),'actual timestamp collision'
            shown=[v[0]for k,v in sorted(display.items())];positive_display.extend(shown)
            for a,b in zip(shown,shown[1:]):
                assert a['window']==b['window'];gaps.append((b['presented_s']-a['presented_s'])*1000);changed+=a['scene_revision']!=b['scene_revision']
                reused_new+=a['scene_revision']!=b['scene_revision']and not indexes['submit_begin'][b['window'],b['call']]['new_scene']
                ma=indexes['history_offset'].get(a['history_marker']);mb=indexes['history_offset'].get(b['history_marker'])
                if ma and mb:
                    assert ma['window']==a['window'] and mb['window']==b['window'];assert ma['at_s']<=a['presented_s'] and mb['at_s']<=b['presented_s'];known+=1;held+=abs((mb['top']*mb['row_height']+mb['within'])-(ma['top']*ma['row_height']+ma['within']))<=.01
        summary={'exposure_s':exposure,'updates_by_callback_time':len(selected_updates),'submissions_by_begin_time':sums['positive']+sums['zero_or_not_presented'],'submission_counts':dict(sums),'duplicate_targets_among_selected_submissions':len(targetlist)-len(set(targetlist)),'assigned_target_step_ms':quantiles(per_update),'actual_displays_by_display_time':len(positive_display),'actual_display_gaps_ms':quantiles(gaps),'known_pose_pairs':known,'held_pose_pairs':held,'changed_scene_pairs':changed,'reused_submit_first_seen_display_pairs':reused_new,'by_outcome_relative_timing':{out:{k:quantiles(v[k]for v in values)for k in values[0]}for out,values in outcomes.items()}}
        expected=registered['summaries'][name]
        assert summary['submissions_by_begin_time']==expected['submissions_by_begin_time']
        assert sums['positive']==expected['outcomes']['positive']and sums['zero_or_not_presented']==expected['outcomes']['zero_or_not_presented']
        assert summary['actual_displays_by_display_time']==expected['actual_unique_displays']
        assert known==expected['known_actual_pose_pairs'] and held==expected['held_actual_pose_pairs'] and changed==expected['changed_actual_scene_pairs']
        report['scopes'][name]=summary
    return report

if __name__=='__main__':
    result={'scope':'Independent joins of saved raw records; no acquisition or causal/presentation-deadline inference','audit_script_sha256':sha(Path(__file__)),'plan_sha256':sha(PLAN),'captures':[audit(s)for s in ['pilot-excluded','confirmation']]}
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'independent-raw-audit.json');args=parser.parse_args()
    destination=args.output;destination.write_text(json.dumps(result,indent=2)+'\n');print(destination)
