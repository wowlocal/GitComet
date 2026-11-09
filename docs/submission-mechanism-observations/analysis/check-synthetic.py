"""Tiny saved-data checks; never launches the application or compiler."""
from pathlib import Path
import runpy,json,hashlib,datetime,math
HERE=Path(__file__).resolve().parent
module=runpy.run_path(str(HERE/'analyze.py'));analyze=module['analyze'];summarize=module['scope_summary']
data=[]
def add(event,at,**fields):
    r=dict(event=event,seq=len(data)+1,at_s=at,window=1,**fields);data.append(r);return r
def update(draw,at,deadline,target):return add('metal_update',at,drawable=draw,deadline_s=deadline,target_presentation_s=target,preferred_latency=2,minimum_hz=0,maximum_hz=0,preferred_hz=0)
def begin(draw,call,at,rev,new,marker):return add('submit_begin',at,drawable=draw,call=call,scene_revision=rev,new_scene=new,history_marker=marker)
def end(draw,call,at):return add('submit_end',at,drawable=draw,call=call)
def gpu(draw,call,at,start,finish,rev,marker):return add('gpu_completed',at,drawable=draw,call=call,status=4,gpu_start_s=start,gpu_end_s=finish,scene_revision=rev,history_marker=marker)
def show(draw,call,at,display,rev,marker):return add('presented',at,drawable=draw,call=call,did_present=display>0,presented_s=display,scene_revision=rev,history_marker=marker)
mark0=add('history_offset',.99,top=0,within=0,row_height=36,viewport=600)['seq']
update(10,1.,1.005,1.016);begin(10,0,1.001,0,True,mark0);end(10,0,1.003)
add('frame_decision',1.0031,drawable=10,used_drawable=True,paused=False);gpu(10,0,1.010,1.004,1.009,0,mark0);show(10,0,1.017,1.016,0,mark0)
mark1=add('history_offset',1.018,top=0,within=10,row_height=36,viewport=600)['seq']
update(11,1.020,1.025,1.033);begin(11,1,1.021,1,True,mark1);end(11,1,1.024)
add('frame_decision',1.0241,drawable=11,used_drawable=True,paused=False);gpu(11,1,1.030,1.024,1.029,1,mark1);show(11,1,1.034,0,1,mark1)
update(12,1.028,1.030,1.033);begin(12,2,1.0285,1,False,mark1);end(12,2,1.0305)
add('frame_decision',1.0306,drawable=12,used_drawable=True,paused=False);gpu(12,2,1.0325,1.031,1.032,1,mark1);show(12,2,1.034,1.0333,1,mark1)
update(13,1.040,1.045,1.050);add('frame_decision',1.041,drawable=13,used_drawable=False,paused=True)
update(14,1.060,1.065,1.070)
# This actual positive callback has no captured submit/marker; preserve it.
show(15,99,1.071,1.070,2,None)
joined=analyze(data);summary=summarize(joined,[(.99,1.08)])
assert len(joined['actual_displays'])==3 and summary['actual_unique_displays']==3 and summary['unknown_displayed_poses']==1
assert len(joined['orphan_present_callbacks'])==1
first=joined['submissions'][0];assert first['outcome']=='positive'and first['timing_ms']['gpu_end_minus_cpu_present_deadline']>0 and first['timing_ms']['gpu_end_minus_estimated_target']<0
assert summary['duplicate_assigned_target_groups']==1 and summary['reused_submission_but_changed_actual_scene_pairs']==1
assert summary['update_decisions']['slot_unused']==1 and summary['update_decisions']['pause_decision']==1 and summary['update_decisions']['decision_unavailable_or_ambiguous']==1
assert summary['outcomes']=={'positive':2,'zero_or_not_presented':1}
tests=['Distinct CPU deadline versus estimated target; GPU after deadline but before target remains valid positive.','Zero and positive callbacks preserved distinctly.','Repeated estimated target grouped exactly across two assigned drawables.','A reused previous-submit revision can be a new actual displayed revision.','Orphan positive display retained for cadence with unknown logical pose.','Unused paused update and missing decision remain distinct, with no fabricated success.']
# Ambiguous update identity cannot inherit a unique decision arbitrarily.
ambiguous=list(data);ambiguous.append(dict(data[1],seq=100,at_s=1.0001))
j=analyze(ambiguous);assert j['submissions'][0]['update_seq']is None
assert all(r['slot_consumed']is None for r in j['updates']if r['drawable']==10)
tests.append('Duplicate window/drawable updates mark update and decision association ambiguous.')
# Conflicting actual timestamp revisions/poses remain one ambiguous display.
conflict=list(data);conflict.append(dict(event='presented',seq=101,at_s=1.017,window=1,drawable=99,call=100,did_present=True,presented_s=1.016,scene_revision=7,history_marker=mark1))
j=analyze(conflict);sample=next(r for r in j['actual_displays']if r['at_s']==1.016);assert sample['scene_ambiguous']and sample['scene_revision']is None and sample['logical_position']is None
tests.append('Conflicting positive callbacks at one timestamp deduplicate to one ambiguous displayed pose/revision.')
# Acquisition completeness requires actual records and contiguous unique seqs,
# even when a retained footer claims no drops.
header={'event':'capture_status','status':'recording','duration_s':1,'pid':42};arm={'event':'capture_armed','ca_anchor_s':.5};footer={'event':'capture_status','status':'complete','reason':'duration','records':len(data),'dropped':0,'marker_overflow':0,'flushed_at_s':1.6}
complete=[header,arm,*data,footer];integrity=module['capture_integrity']
assert integrity(complete)['complete_without_drops']
missing=complete[:5]+complete[6:];check=integrity(missing);assert not check['complete_without_drops']and not check['checks']['footer_record_count_matches_actual']and not check['checks']['contiguous_ordered_sequences_from_one']
tests.append('Missing interior record with retained zero-drop footer fails count and sequence acquisition integrity.')
duplicate=[dict(r)for r in complete];duplicate[5]['seq']=duplicate[4]['seq'];check=integrity(duplicate);assert not check['complete_without_drops']and check['checks']['footer_record_count_matches_actual']and not check['checks']['unique_sequences']
tests.append('Duplicate record sequence fails acquisition integrity even when footer count matches.')
wrong_count=[*complete[:-1],dict(footer,records=len(data)+1)];assert not integrity(wrong_count)['complete_without_drops']
tests.append('Wrong footer record count cannot label a capture complete.')
# Native Number serialization emits null for a nonfinite presentedTime. This
# must remain an unavailable outcome, not crash or silently become zero.
null_time=[dict(r)for r in data]
for r in null_time:
    if r['event']=='presented'and r['call']==0:r['presented_s']=None;r['did_present']=False
j=analyze(null_time);first=j['submissions'][0];assert first['outcome']=='unavailable_presented_timestamp'and first['timing_ms']['positive_display_minus_estimated_target']is None and len(j['actual_displays'])==2
tests.append('Null/nonfinite-serialized presented timestamp stays explicitly unavailable and is excluded from positive cadence only.')
# A marker with a serialized nonfinite coordinate remains an unknown pose.
null_pose=[dict(r)for r in data];null_pose[0]['within']=None;j=analyze(null_pose);assert j['submissions'][0]['logical_position']is None and j['actual_displays'][0]['logical_position']is None
tests.append('Null logical marker coordinate remains an explicit unknown displayed pose.')
(HERE/'synthetic-native.jsonl').write_text(''.join(json.dumps(r)+'\n'for r in data))
for name,fixture in [('synthetic-complete-native',complete),('synthetic-missing-native',missing),('synthetic-duplicate-native',duplicate),('synthetic-null-time-native',[header,arm,*null_time,footer])]:
    (HERE/(name+'.jsonl')).write_text(''.join(json.dumps(r)+'\n'for r in fixture))
report={'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'tests':tests,'analyzer_sha256':hashlib.sha256((HERE/'analyze.py').read_bytes()).hexdigest(),'scope':'Tiny numeric fixtures only; no application/compiler/UI/runtime interaction.'}
(HERE/'synthetic-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
