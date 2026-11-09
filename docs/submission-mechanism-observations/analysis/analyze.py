"""Saved numeric mechanism evidence only; no app, build or UI operations."""
from pathlib import Path
import argparse,collections,hashlib,json,math,statistics as st

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(x)for x in Path(p).read_text().splitlines()]
def finite(x):return isinstance(x,(int,float))and math.isfinite(x)
def stats(v):
    raw=list(v);s=sorted(x for x in raw if finite(x))
    def q(p):
        k=(len(s)-1)*p;i=math.floor(k);j=math.ceil(k)
        return s[i]+(s[j]-s[i])*(k-i)
    return {'n':len(s),'missing':len(raw)-len(s),'min':s[0],'median':q(.5),'p95':q(.95),'p99':q(.99),'max':s[-1]}if s else dict(n=0,missing=len(raw),min=None,median=None,p95=None,p99=None,max=None)
def difference(a,b):return(a-b)*1000 if finite(a)and finite(b)else None
def one(v):return v[0]if len(v)==1 else None
def outcome(p,candidates):
    if not candidates:return'missing_callback'
    if p is None:return'ambiguous_callback'
    if not finite(p['presented_s']):return'unavailable_presented_timestamp'
    return'positive'if p['did_present']and p['presented_s']>0 else'zero_or_not_presented'

def marker_position(marker):
    if marker is None or not all(finite(marker.get(k))for k in['top','within','row_height']):return None
    return marker['top']*marker['row_height']+marker['within']

def capture_integrity(native):
    """Acquisition integrity is independent of successful drawable outcomes."""
    records=[r for r in native if'seq'in r];sequences=[r['seq']for r in records]
    footers=[r for r in native if r['event']=='capture_status'and r.get('status')=='complete'];footer=one(footers)
    valid_sequence_types=all(isinstance(v,int)and not isinstance(v,bool)and v>0 for v in sequences)
    unique_sequences=len(set(sequences))==len(sequences)if valid_sequence_types else False
    contiguous_sequences=valid_sequence_types and sequences==list(range(1,len(sequences)+1))
    count_matches=bool(footer is not None and isinstance(footer.get('records'),int)and not isinstance(footer.get('records'),bool)and footer['records']==len(records))
    header_present=any(r['event']=='capture_status'and'duration_s'in r for r in native)
    arms=sum(r['event']=='capture_armed'for r in native)
    checks={'header_present':header_present,'exactly_one_arm':arms==1,'exactly_one_complete_footer':len(footers)==1,'footer_is_final_row':bool(footer is not None and native[-1]is footer),'footer_record_count_matches_actual':count_matches,'valid_sequence_types':valid_sequence_types,'unique_sequences':unique_sequences,'contiguous_ordered_sequences_from_one':contiguous_sequences,'duration_completion':bool(footer is not None and footer.get('reason')=='duration'),'zero_recorder_drops':bool(footer is not None and footer.get('dropped')==0),'zero_marker_overflow':bool(footer is not None and footer.get('marker_overflow')==0)}
    return {'complete_without_drops':bool(records)and all(checks.values()),'checks':checks,'actual_record_count':len(records),'footer_record_count':footer.get('records')if footer else None,'sequence_first':sequences[0]if sequences else None,'sequence_last':sequences[-1]if sequences else None,'failures':[k for k,v in checks.items()if not v]}

def analyze(native):
    grouped={kind:collections.defaultdict(list)for kind in['metal_update','frame_decision','submit_begin','submit_end','gpu_completed','presented']}
    by_drawable=collections.defaultdict(list);markers={r['seq']:r for r in native if r['event']=='history_offset'}
    for r in native:
        event=r['event']
        if event not in grouped:continue
        if event=='frame_decision'and'drawable'not in r:continue
        key=(r['window'],r['drawable'])if event in['metal_update','frame_decision']else(r['window'],r['call'])
        grouped[event][key].append(r)
        if event=='submit_begin':by_drawable[(r['window'],r['drawable'])].append(r)
    submissions=[];previous_revision={}
    for b in sorted((r for r in native if r['event']=='submit_begin'),key=lambda r:r['seq']):
        call=(b['window'],b['call']);draw=(b['window'],b['drawable']);update=one(grouped['metal_update'][draw]);end=one(grouped['submit_end'][call]);gpu=one(grouped['gpu_completed'][call]);present=one(grouped['presented'][call]);marker=markers.get(b['history_marker'])
        flags=[]
        for kind,key in[('metal_update',draw),('submit_begin',call),('submit_end',call),('gpu_completed',call),('presented',call)]:
            if len(grouped[kind][key])!=1:flags.append(kind+('_missing'if not grouped[kind][key]else'_ambiguous'))
        for kind,r in[('submit_end',end),('gpu_completed',gpu),('presented',present)]:
            if r is not None and r['drawable']!=b['drawable']:flags.append(kind+'_drawable_mismatch')
        identity_known=len(grouped['submit_begin'][call])==1
        end=end if identity_known and end is not None and end['drawable']==b['drawable']else None
        gpu=gpu if identity_known and gpu is not None and gpu['drawable']==b['drawable']else None
        present=present if identity_known and present is not None and present['drawable']==b['drawable']else None
        marker_valid=marker is not None and marker['window']==b['window']and finite(marker['at_s'])and marker['at_s']<=b['at_s']
        if marker is not None and not marker_valid:flags.append('marker_window_or_time_mismatch')
        position=marker_position(marker)if marker_valid else None
        if marker_valid and position is None:flags.append('marker_numeric_pose_unavailable')
        gpu_valid=gpu is not None and gpu['status']==4 and finite(gpu['gpu_start_s'])and finite(gpu['gpu_end_s'])and gpu['gpu_start_s']>0 and gpu['gpu_end_s']>=gpu['gpu_start_s']
        if gpu_valid and gpu['gpu_start_s']<b['at_s']-.001:flags.append('gpu_clock_before_observed_encoding')
        if gpu_valid and gpu['gpu_end_s']>gpu['at_s']+.001:flags.append('gpu_clock_after_completed_callback')
        positive_present=bool(present and present['did_present']and finite(present['presented_s'])and present['presented_s']>0)
        if present and finite(present['presented_s'])and finite(present['at_s'])and present['presented_s']>present['at_s']+.001:flags.append('display_clock_after_present_callback')
        target=update['target_presentation_s']if update else None;deadline=update['deadline_s']if update else None
        previous=previous_revision.get(b['window']);previous_revision[b['window']]=b['scene_revision']
        calculated_new=None if previous is None else b['scene_revision']!=previous
        submissions.append({'window':b['window'],'drawable':b['drawable'],'call':b['call'],'submit_seq':b['seq'],'submit_begin_at_s':b['at_s'],'submit_end_at_s':end['at_s']if end else None,'scene_revision':b['scene_revision'],'new_scene_since_previous_submit':b['new_scene'],'calculated_new_since_previous_captured_submit':calculated_new,'new_scene_flag_consistent':None if calculated_new is None else b['new_scene']==calculated_new,'history_marker':b['history_marker'],'logical_position':position,'marker_at_s':marker['at_s']if marker_valid else None,'update_seq':update['seq']if update else None,'update_recorded_at_s':update['at_s']if update else None,'cpu_present_deadline_s':deadline,'estimated_presentation_target_s':target,'outcome':outcome(present,grouped['presented'][call]),'presented_s':present['presented_s']if present else None,'present_callback_at_s':present['at_s']if present else None,'gpu_status':gpu['status']if gpu else None,'gpu_host_times_valid':gpu_valid,'gpu_start_s':gpu['gpu_start_s']if gpu_valid else None,'gpu_end_s':gpu['gpu_end_s']if gpu_valid else None,'gpu_callback_at_s':gpu['at_s']if gpu else None,'join_flags':flags,'timing_ms':{'recorded_update_to_submit_begin':difference(b['at_s'],update['at_s']if update else None),'submit_path_elapsed_excluding_acquisition':difference(end['at_s']if end else None,b['at_s']),'cpu_path_return_minus_cpu_present_deadline':difference(end['at_s']if end else None,deadline),'gpu_start_minus_cpu_present_deadline':difference(gpu['gpu_start_s']if gpu_valid else None,deadline),'gpu_end_minus_cpu_present_deadline':difference(gpu['gpu_end_s']if gpu_valid else None,deadline),'gpu_end_minus_estimated_target':difference(gpu['gpu_end_s']if gpu_valid else None,target),'gpu_start_minus_cpu_path_return':difference(gpu['gpu_start_s']if gpu_valid else None,end['at_s']if end else None),'gpu_command_host_interval':difference(gpu['gpu_end_s']if gpu_valid else None,gpu['gpu_start_s']if gpu_valid else None),'positive_display_minus_estimated_target':difference(present['presented_s']if positive_present else None,target),'prepaint_to_positive_display':difference(present['presented_s']if positive_present else None,marker['at_s']if marker_valid else None),'present_callback_after_reported_display':difference(present['at_s']if positive_present else None,present['presented_s']if positive_present else None)}})
    bycall=collections.defaultdict(list)
    for r in submissions:bycall[(r['window'],r['call'])].append(r)
    updates=[]
    for u in(r for r in native if r['event']=='metal_update'):
        draw=(u['window'],u['drawable']);decision=one(grouped['frame_decision'][draw])if len(grouped['metal_update'][draw])==1 else None;candidates=by_drawable[draw]
        updates.append({'window':u['window'],'drawable':u['drawable'],'update_seq':u['seq'],'at_s':u['at_s'],'cpu_present_deadline_s':u['deadline_s'],'estimated_presentation_target_s':u['target_presentation_s'],'preferred_latency':u['preferred_latency'],'frame_rate_range':[u['minimum_hz'],u['maximum_hz'],u['preferred_hz']],'update_key_candidates':len(grouped['metal_update'][draw]),'decision_candidates':len(grouped['frame_decision'][draw]),'decision_seq':decision['seq']if decision else None,'decision_at_s':decision['at_s']if decision else None,'slot_consumed':decision['used_drawable']if decision else None,'pause_decision':decision['paused']if decision else None,'submission_candidates':len(candidates),'submission_calls':[r['call']for r in candidates],'recorded_update_minus_cpu_deadline_ms':difference(u['at_s'],u['deadline_s']),'estimated_target_minus_cpu_deadline_ms':difference(u['target_presentation_s'],u['deadline_s'])})
    target_index=collections.defaultdict(list)
    for u in updates:
        if finite(u['estimated_presentation_target_s']):target_index[(u['window'],u['estimated_presentation_target_s'])].append(u)
    target_groups=[]
    for (window,target),items in sorted(target_index.items()):
        keys={(u['window'],call)for u in items for call in u['submission_calls']};calls=[r for key in sorted(keys)for r in bycall[key]];positions=[r['logical_position']for r in calls if r['logical_position']is not None]
        target_groups.append({'window':window,'target_s':target,'updates':len(items),'duplicate_assigned_target':len(items)>1,'update_seqs':[u['update_seq']for u in items],'drawables':[u['drawable']for u in items],'submission_records':len(calls),'submission_calls':[r['call']for r in calls],'outcomes':dict(collections.Counter(r['outcome']for r in calls)),'scene_revisions':sorted(set(r['scene_revision']for r in calls)),'known_pose_min':min(positions)if positions else None,'known_pose_max':max(positions)if positions else None,'known_pose_span_gt_0_01':max(positions)-min(positions)>.01 if len(positions)>=2 else None,'ambiguous_update_join':any(u['update_key_candidates']!=1 for u in items),'update_recording_span_ms':(max(u['at_s']for u in items)-min(u['at_s']for u in items))*1000})
    displayed_index=collections.defaultdict(list)
    # Actual presentation evidence does not require a captured submit. Missing
    # or ambiguous begin records affect joins, not whether a positive display
    # timestamp is retained for cadence/unknown-pose coverage.
    for r in native:
        if r['event']!='presented'or not r['did_present']or not finite(r['presented_s'])or r['presented_s']<=0:continue
        begin=one(bycall[(r['window'],r['call'])]);marker=markers.get(r['history_marker']);valid=marker is not None and marker['window']==r['window']and marker['at_s']<=r['presented_s']
        displayed_index[(r['window'],r['presented_s'])].append({'call':r['call'],'scene_revision':r['scene_revision'],'logical_position':marker_position(marker)if valid else None,'new_scene_since_previous_submit':begin['new_scene_since_previous_submit']if begin else None})
    displays=[]
    for (window,t),calls in sorted(displayed_index.items()):
        revisions=set(r['scene_revision']for r in calls);positions=[r['logical_position']for r in calls if r['logical_position']is not None];known=len(positions)==len(calls)and max(positions)-min(positions)<=.01
        displays.append({'window':window,'at_s':t,'calls':[r['call']for r in calls],'positive_callbacks':len(calls),'duplicate_actual_timestamp_callbacks':len(calls)-1,'scene_revision':next(iter(revisions))if len(revisions)==1 else None,'scene_ambiguous':len(revisions)>1,'logical_position':st.median(positions)if known else None,'all_reused_since_previous_submit':all(r['new_scene_since_previous_submit']is False for r in calls)})
    unmatched={'presented_without_begin':sum(r['event']=='presented'and not grouped['submit_begin'][(r['window'],r['call'])]for r in native),'gpu_completed_without_begin':sum(r['event']=='gpu_completed'and not grouped['submit_begin'][(r['window'],r['call'])]for r in native),'submit_end_without_begin':sum(r['event']=='submit_end'and not grouped['submit_begin'][(r['window'],r['call'])]for r in native),'decision_without_update':sum(r['event']=='frame_decision'and'drawable'in r and not grouped['metal_update'][(r['window'],r['drawable'])]for r in native),'decision_without_drawable_key':sum(r['event']=='frame_decision'and'drawable'not in r for r in native)}
    return {'submissions':submissions,'updates':updates,'exact_target_groups':target_groups,'actual_displays':displays,'unmatched_record_counts':unmatched,'orphan_present_callbacks':[{'window':r['window'],'call':r['call'],'seq':r['seq']}for r in native if r['event']=='presented'and not grouped['submit_begin'][(r['window'],r['call'])]],'orphan_gpu_callbacks':[{'window':r['window'],'call':r['call'],'seq':r['seq']}for r in native if r['event']=='gpu_completed'and not grouped['submit_begin'][(r['window'],r['call'])]]}

def scope_summary(joined,intervals):
    inside=lambda t:any(lo<=t<=hi for lo,hi in intervals)
    submissions=[r for r in joined['submissions']if inside(r['submit_begin_at_s'])];updates=[r for r in joined['updates']if inside(r['at_s'])];groups=[r for r in joined['exact_target_groups']if inside(r['target_s'])]
    gaps=[];display_count=unknown_poses=changed_scenes=repeated_scenes=known_pose_pairs=held_pose_pairs=reused_but_first_displayed_revision=duplicate_actual=0
    for lo,hi in intervals:
        windows=collections.defaultdict(list)
        for r in joined['actual_displays']:
            if lo<=r['at_s']<=hi:windows[r['window']].append(r)
        for samples in windows.values():
            display_count+=len(samples);unknown_poses+=sum(r['logical_position']is None for r in samples);duplicate_actual+=sum(r['duplicate_actual_timestamp_callbacks']for r in samples)
            for a,b in zip(samples,samples[1:]):
                gaps.append((b['at_s']-a['at_s'])*1000)
                if a['scene_revision']is not None and b['scene_revision']is not None:
                    changed=b['scene_revision']!=a['scene_revision'];changed_scenes+=changed;repeated_scenes+=not changed;reused_but_first_displayed_revision+=changed and b['all_reused_since_previous_submit']
                if a['logical_position']is not None and b['logical_position']is not None:known_pose_pairs+=1;held_pose_pairs+=abs(b['logical_position']-a['logical_position'])<=.01
    table=collections.Counter()
    for r in submissions:
        cpu=r['timing_ms']['cpu_path_return_minus_cpu_present_deadline'];gpu=r['timing_ms']['gpu_end_minus_estimated_target'];cpu_class='unavailable'if cpu is None else'return_at_or_before_deadline'if cpu<=0 else'return_after_deadline';gpu_class='unavailable'if gpu is None else'end_at_or_before_estimated_target'if gpu<=0 else'end_after_estimated_target';table[(r['outcome'],cpu_class,gpu_class)]+=1
    timing_keys=list(joined['submissions'][0]['timing_ms'])if joined['submissions']else[]
    exposure=sum(hi-lo for lo,hi in intervals)
    return {'intervals_ca_s':intervals,'exposure_s':exposure,'updates_by_recording_time':len(updates),'submissions_by_begin_time':len(submissions),'outcomes':dict(collections.Counter(r['outcome']for r in submissions)),'join_flags':dict(collections.Counter(flag for r in submissions for flag in r['join_flags'])),'gpu_status':dict(collections.Counter(str(r['gpu_status'])for r in submissions)),'gpu_host_time_unavailable':sum(not r['gpu_host_times_valid']for r in submissions),'cpu_deadline_scope':'CPU-path-return offsets only; no exact present-call/commit/scheduling stamp. GPU may finish after CPU deadline.','timing_ms':{key:stats(r['timing_ms'][key]for r in submissions)for key in timing_keys},'outcome_timing_contingency':[{'outcome':key[0],'cpu_path_return':key[1],'gpu_host_end':key[2],'submissions':count}for key,count in sorted(table.items())],'update_decisions':{'slot_consumed':sum(u['slot_consumed']is True for u in updates),'slot_unused':sum(u['slot_consumed']is False for u in updates),'decision_unavailable_or_ambiguous':sum(u['slot_consumed']is None for u in updates),'pause_decision':sum(u['pause_decision']is True for u in updates),'consumed_with_no_observed_submission':sum(u['slot_consumed']is True and u['submission_candidates']==0 for u in updates)},'exact_target_groups_by_assigned_target':len(groups),'duplicate_assigned_target_groups':sum(r['duplicate_assigned_target']for r in groups),'updates_in_duplicate_assigned_target_groups':sum(r['updates']for r in groups if r['duplicate_assigned_target']),'actual_unique_displays':display_count,'actual_display_windows':len({r['window']for r in joined['actual_displays']if inside(r['at_s'])}),'actual_display_events_per_second_selected_exposure':display_count/exposure if exposure else None,'actual_gap_ms':stats(gaps),'duplicate_actual_timestamp_callbacks':duplicate_actual,'unknown_displayed_poses':unknown_poses,'changed_actual_scene_pairs':changed_scenes,'repeated_actual_scene_pairs':repeated_scenes,'known_actual_pose_pairs':known_pose_pairs,'held_actual_pose_pairs':held_pose_pairs,'reused_submission_but_changed_actual_scene_pairs':reused_but_first_displayed_revision}

def scenario_intervals(native,frames,plan):
    inputs=[r for r in frames if r['event']=='scenario_input'];packets=[r for r in native if r['event']=='scenario_scroll']
    if len(inputs)!=1442 or len(packets)!=1440:return {'available':False,'reason':'Expected1442 app inputs and1440 native packet markers','app_inputs':len(inputs),'native_packets':len(packets)}
    for c in range(6):
        assert all(r['dx']==0 and r['dy']==p['delta_px']*(-1 if c%2 else 1)for r,p in zip(packets[c*240:(c+1)*240],plan['packets']))
    offset=st.median(r['at_s']-i['unix_ms']/1000 for r,i in zip(packets,inputs[2:]));residual=[(r['at_s']-i['unix_ms']/1000-offset)*1000 for r,i in zip(packets,inputs[2:])]
    phase={state:{r['detail']['name']:r for r in frames if r['event']=='scenario_phase'and r['detail']['state']==state}for state in['begin','end']}
    if'replay-0'not in phase['begin']or'replay-3'not in phase['end']:return {'available':False,'reason':'Missing four measured phase boundaries'}
    full=[(phase['begin']['replay-0']['unix_ms']/1000+offset+.3,phase['end']['replay-3']['unix_ms']/1000+offset-.3)]
    cores=[(packets[(c+2)*240]['at_s']+w['start_us']/1e6,packets[(c+2)*240]['at_s']+w['end_us']/1e6)for c in range(4)for w in plan['motion_core_windows']]
    return {'available':True,'clock_ca_minus_unix_s':offset,'clock_residual_ms':stats(residual),'full_scrolling':full,'source_active_cores':cores}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('capture',type=Path);parser.add_argument('--frames',type=Path);parser.add_argument('--plan',type=Path,default=HERE/'input-plan.json');parser.add_argument('--output',type=Path);args=parser.parse_args();native=rows(args.capture)
    footer=next((r for r in reversed(native)if r['event']=='capture_status'and r.get('status')=='complete'),None);records=[r for r in native if'seq'in r];assert records
    joined=analyze(native);capture_interval=[(min(r['at_s']for r in records),max(r['at_s']for r in records))];summaries={'full_capture_descriptive':scope_summary(joined,capture_interval)};frames_path=args.frames or args.capture.with_name('frames.jsonl');mapping={'available':False,'reason':'No adjacent application timing file'}
    if frames_path.exists():
        mapping=scenario_intervals(native,rows(frames_path),read(args.plan))
        if mapping['available']:
            for name in['full_scrolling','source_active_cores']:summaries[name]=scope_summary(joined,mapping[name])
    anchor=next((r for r in native if r['event']=='capture_armed'),None);header=next((r for r in native if r['event']=='capture_status'and'duration_s'in r),None)
    capture_lo=anchor['ca_anchor_s']if anchor else capture_interval[0][0];capture_hi=capture_lo+header['duration_s']if anchor and header and footer and footer.get('reason')=='duration'else capture_interval[0][1]
    for summary in summaries.values():
        summary['capture_covers_requested_intervals']=all(capture_lo<=lo<=hi<=capture_hi for lo,hi in summary['intervals_ca_s'])
        summary['wake_requests_by_recording_time']=sum(r['event']=='wake'and any(lo<=r['at_s']<=hi for lo,hi in summary['intervals_ca_s'])for r in native)
    report={'scope':'Single-arm observer mechanism diagnosis only; no efficacy/overhead/energy/physical-input claim. Deadline is CPU present-call deadline, estimated target is distinct. CPU commit/scheduled/present-call instants are not observed.','capture':str(args.capture),'capture_sha256':hashlib.sha256(args.capture.read_bytes()).hexdigest(),'analyzer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'footer':footer,'capture_integrity':capture_integrity(native),'capture_complete_without_drops':capture_integrity(native)['complete_without_drops'],'counts':dict(collections.Counter(r['event']for r in native)),'scenario_mapping':mapping,'summaries':summaries,'join_tables':joined,'limits':['submit_end after commit return is not the exact present-call or commit/scheduling timestamp.','GPU-end after CPU deadline is legitimate with preferred latency; compare the distinct estimated target and actual outcome.','Zero callback, missing callback and ambiguous callback remain distinct. Early GPU completion with zero presentation is an association, not proof of compositor cause.','new_scene compares previous submission; actual scene/pose changes compare unique positive displayed samples.','Exact target duplicates alone do not prove a bug, last-wins behavior, or observer neutrality.','Slot consumption/pause decision/wake requests are not GPU success/native pause readback/CPU execution counts.','Numeric observer work can perturb this arm; there is no matched overhead control.']}
    output=args.output or args.capture.with_name('submission-mechanism-analysis.json');output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(output),'capture_complete_without_drops':report['capture_complete_without_drops'],'summaries':summaries},indent=2))

if __name__=='__main__':main()
