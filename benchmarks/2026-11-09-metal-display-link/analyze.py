from pathlib import Path
import json, sys, statistics, collections, math

out = Path(__file__).resolve().parent
manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text())
plan = json.loads((out/'input-plan.json').read_text())
cutoffs = [2/120*1000+.25,3/120*1000+.25,4/120*1000+.25]

def stats(values):
    v=sorted(x for x in values if x is not None)
    def q(p):
        x=(len(v)-1)*p;i=math.floor(x);j=math.ceil(x)
        return v[i]+(v[j]-v[i])*(x-i)
    return {'n':len(v),'missing':len(values)-len(v),'min':v[0],'median':q(.5),'p95':q(.95),'p99':q(.99),'max':v[-1]} if v else {'n':0,'missing':len(values),'min':None,'median':None,'p95':None,'p99':None,'max':None}

def presentation_window(visible, lo, hi):
    raw=[r['presented_s'] for r in visible if lo <= r['presented_s'] <= hi]
    times=sorted(set(raw))
    gaps=[(b-a)*1000 for a,b in zip(times,times[1:])]
    return {'lo_ca_s':lo,'hi_ca_s':hi,'exposure_s':hi-lo,'presentations':len(times),'raw_positive_callbacks':len(raw),'presentation_rate_hz':len(times)/(hi-lo),'interval_ms':stats(gaps),'duplicate_timestamps':len(raw)-len(times),'long_gap_counts':[sum(x>t for x in gaps) for t in cutoffs],'intervals_ms':gaps}

def telemetry(measurement, lo, hi):
    pid=str(measurement['pid']);ws=str(measurement['windowserver_pid'])
    indices=[i for i,r in enumerate(measurement['samples']) if lo<=r['unix_ms']<=hi]
    assert not indices or indices==list(range(indices[0],indices[-1]+1))
    rows=[measurement['samples'][i] for i in indices]
    if any(not r['app_cpu'] or pid not in r['gpu_times_ns'] or ws not in r['gpu_times_ns'] for r in rows):
        return {'available':False,'reason':'counter unavailable inside phase','samples':len(rows)}
    if any(not r['soc'] or r['soc']['gpu_energy_nj'] is None or r['soc']['gpu_energy_nj']<0 for r in rows[1:]):
        return {'available':False,'reason':'GPU energy interval missing or negative','samples':len(rows)}
    if len(rows)<4:return {'available':False,'samples':len(rows)}
    dt=rows[-1]['monotonic_s']-rows[0]['monotonic_s']
    assert abs(sum(r['interval_s'] for r in rows[1:])-dt)<1e-6
    energy=sum(r['soc']['gpu_energy_nj'] for r in rows[1:])/1e9
    states={k:sum(r['soc']['gpu_states'].get(k,0) for r in rows[1:]) for k in rows[-1]['soc']['gpu_states']}
    total=sum(states.values())
    assert all(b['app_cpu']['cpu_s']>=a['app_cpu']['cpu_s'] for a,b in zip(rows,rows[1:]))
    cpu=rows[-1]['app_cpu']['cpu_s']-rows[0]['app_cpu']['cpu_s']
    reset=any(b['gpu_times_ns'][k]<a['gpu_times_ns'][k] for a,b in zip(rows,rows[1:]) for k in [pid,ws])
    gpu={k:rows[-1]['gpu_times_ns'][k]-rows[0]['gpu_times_ns'][k] for k in [pid,ws]}
    return {'available':True,'samples':len(rows),'elapsed_s':dt,'lo_unix_ms':rows[0]['unix_ms'],'hi_unix_ms':rows[-1]['unix_ms'],'whole_gpu_modeled_w':energy/dt,'whole_gpu_modeled_j':energy,'app_cpu_percent_one_core':cpu/dt*100,'app_gpu_ms_per_wall_second':gpu[pid]/1e6/dt if not reset else None,'windowserver_gpu_ms_per_wall_second':gpu[ws]/1e6/dt if not reset else None,'counter_reset':reset,'gpu_state_percent':{k:v/total*100 for k,v in states.items() if v and total},'gpu_residency_vs_wall_ratio':total/24e6/dt,'driver_utilization_percent':stats([(r.get('device') or {}).get('device_utilization_percent') for r in rows]),'mean_app_rss_mib':statistics.mean(r['app_cpu']['rss_kib'] for r in rows)/1024}

runs=[]
for entry in manifest['runs']:
    if not entry['valid']: continue
    run=manifest_path.parent/entry['path'];m=json.loads((run/'measurement.json').read_text())
    assert m['verification']['valid'], entry
    frames=[json.loads(x) for x in (run/'frames.jsonl').read_text().splitlines()]
    native=[json.loads(x) for x in (run/'native.jsonl').read_text().splitlines()]
    app_inputs=[r for r in frames if r['event']=='scenario_input']
    scrolls=[r for r in native if r['event']=='scenario_scroll']
    assert len(app_inputs)==1442 and len(scrolls)==1440
    expected=[]
    for c in range(6):expected.extend(p['delta_px']*(1 if c%2==0 else -1) for p in plan['packets'])
    assert all(abs(r['dy']-d)<1e-6 and r['dx']==0 for r,d in zip(scrolls,expected))
    offsets=[r['at_s']-a['unix_ms']/1000 for r,a in zip(scrolls,app_inputs[2:])]
    clock=statistics.median(offsets)
    begins={r['detail']['name']:r for r in frames if r['event']=='scenario_phase' and r['detail']['state']=='begin'}
    ends={r['detail']['name']:r for r in frames if r['event']=='scenario_phase' and r['detail']['state']=='end'}
    ready=next(r for r in frames if r['event']=='scenario_ready')
    lo=begins['replay-0']['unix_ms']+300;hi=ends['replay-3']['unix_ms']-300
    visible=sorted([r for r in native if r['event']=='presented' and r['did_present'] and r['presented_s']>0],key=lambda r:r['presented_s'])
    cores=[]
    for c in range(4):
        origin=scrolls[(c+2)*240]['at_s']
        for ix,window in enumerate(plan['motion_core_windows']):
            core=presentation_window(visible,origin+window['start_us']/1e6,origin+window['end_us']/1e6)
            core.update(cycle=c,burst=ix)
            cores.append(core)
    exposure=sum(c['exposure_s'] for c in cores)
    gaps=[x for c in cores for x in c['intervals_ms']]
    core_summary={'exposure_s':exposure,'presentations':sum(c['presentations'] for c in cores),'presentation_rate_hz':sum(c['presentations'] for c in cores)/exposure,'interval_ms':stats(gaps),'long_gap_counts':[sum(c['long_gap_counts'][i] for c in cores) for i in range(3)],'long_gap_rates_per_second':[sum(c['long_gap_counts'][i] for c in cores)/exposure for i in range(3)],'empty_cores':sum(c['presentations']==0 for c in cores),'sparse_cores_lt2':sum(c['presentations']<2 for c in cores)}
    full=presentation_window(visible,lo/1000+clock,hi/1000+clock)
    selected=[r for r in native if r['event']=='submit_begin' and lo/1000+clock<=r['at_s']<=hi/1000+clock]
    present_by_call={(r['window'],r['call']):r for r in native if r['event']=='presented'}
    gpu_by_call={(r['window'],r['call']):r for r in native if r['event']=='gpu_completed'}
    outcomes=collections.Counter();gpu_durations=[]
    for s in selected:
        key=(s['window'],s['call']);p=present_by_call.get(key);g=gpu_by_call.get(key)
        outcomes['submissions']+=1
        outcomes['missing_present_callback']+=p is None
        outcomes['zero_or_not_presented']+=bool(p is not None and (not p['did_present'] or p['presented_s']<=0))
        outcomes['missing_gpu_callback']+=g is None
        outcomes['gpu_errors']+=bool(g is not None and g['status']!=4)
        if g is not None and g['gpu_start_s']>0 and g['gpu_end_s']>=g['gpu_start_s']:gpu_durations.append((g['gpu_end_s']-g['gpu_start_s'])*1000)
    stages={r['op']:r for r in frames if r['event']=='stage' and r.get('stage')=='input' and r.get('label')=='scenario'}
    late=[]
    for a in app_inputs[482:]:
        if a['detail']['op'] in stages:
            s=stages[a['detail']['op']];late.append(s['at_ms']-s['a']/1e6)
    dispatch=[]
    for c in range(4):
        group=scrolls[(c+2)*240:(c+3)*240];origin=group[0]['at_s']
        dispatch.extend((r['at_s']-origin)*1000-p['at_us']/1000 for r,p in zip(group,plan['packets']))
    frame_lo=begins['replay-0']['at_ms']+300;frame_hi=ends['replay-3']['at_ms']-300
    cpu_draw=stats([r['duration_ms'] for r in frames if r['event']=='draw' and frame_lo<=r['start_ms']<=frame_hi])
    cpu_submit=stats([r['duration_ms'] for r in frames if r['event']=='submit' and frame_lo<=r['start_ms']<=frame_hi])
    phases={'idle_before':telemetry(m,ready['unix_ms']+2500,begins['prefill']['unix_ms']-800),'scrolling':telemetry(m,lo,hi),'idle_after':telemetry(m,ends['replay-3']['unix_ms']+2500,ends['replay-3']['unix_ms']+12500)}
    obs=(m['observer_cpu_after']['cpu_s']-m['observer_cpu_before']['cpu_s'])/(m['end_unix_s']-m['start_unix_s'])*100
    result={'condition':entry['condition'],'ordinal':entry['ordinal'],'path':entry['path'],'core':core_summary,'cores':cores,'full_phase_descriptive':full,'submission_outcomes_scope':'full-phase descriptive window; primary core cadence separate','submission_outcomes':dict(outcomes),'gpu_command_interval_ms':stats(gpu_durations),'dispatch_lateness_ms':stats(late),'dispatch_lag_relative_first_ms':stats(dispatch),'clock_mapping_offset_s':clock,'clock_mapping_residual_ms':stats([(x-clock)*1000 for x in offsets]),'cpu_draw_ms':cpu_draw,'cpu_submit_including_drawable_acquisition_ms':cpu_submit,'telemetry':phases,'observer_parent_cpu_percent_one_core':obs,'verification':m['verification'],'environment':m['environment']}
    (run/'analysis.json').write_text(json.dumps(result,indent=2))
    runs.append(result)

def metric(r,path):
    for k in path:
        if not isinstance(r,dict) or k not in r:return None
        r=r[k]
    return r

paths={
    'core_presentation_hz':['core','presentation_rate_hz'],
    'core_interval_median_ms':['core','interval_ms','median'],
    'core_interval_p95_ms':['core','interval_ms','p95'],
    'core_interval_p99_ms':['core','interval_ms','p99'],
    'core_max_gap_ms':['core','interval_ms','max'],
    'app_cpu_percent_one_core':['telemetry','scrolling','app_cpu_percent_one_core'],
    'app_gpu_ms_per_wall_second':['telemetry','scrolling','app_gpu_ms_per_wall_second'],
    'whole_gpu_modeled_w':['telemetry','scrolling','whole_gpu_modeled_w'],
    'idle_before_whole_gpu_modeled_w':['telemetry','idle_before','whole_gpu_modeled_w'],
    'idle_after_app_gpu_ms_per_wall_second':['telemetry','idle_after','app_gpu_ms_per_wall_second'],
    'windowserver_gpu_ms_per_wall_second':['telemetry','scrolling','windowserver_gpu_ms_per_wall_second'],
    'cpu_submit_median_ms':['cpu_submit_including_drawable_acquisition_ms','median'],
    'dispatch_lateness_p95_ms':['dispatch_lateness_ms','p95']}
summary={condition:{name:stats([metric(r,path) for r in runs if r['condition']==condition]) for name,path in paths.items()} for condition in ['stock','fixed'] if any(r['condition']==condition for r in runs)}
pairs=[]
if not manifest['pilot']:
    assert len(runs)==8
    assert [r['ordinal'] for r in runs]==list(range(1,9))
    assert [r['condition'] for r in runs]==manifest['order']
    for i in range(0,8,2):
        a=next(r for r in runs[i:i+2] if r['condition']=='stock');b=next(r for r in runs[i:i+2] if r['condition']=='fixed')
        pairs.append({'ordinals':[a['ordinal'],b['ordinal']],'fixed_minus_stock':{name:metric(b,path)-metric(a,path) if metric(b,path) is not None and metric(a,path) is not None else None for name,path in paths.items()}})
result={'manifest':manifest_path.name,'pilot':manifest['pilot'],'invalid_attempts':[r for r in manifest['runs'] if not r['valid']],'long_gap_cutoffs_ms':cutoffs,'scope':'Primary cadence:8source-defined sustained-motion cores, all exposure retained. Full-phase/tails descriptive. Synthetic same-input replay, not fresh hardware input; actual drawable presentedTime. Whole-GPU modeled energy is not app or wall power. Four runs per condition are experimental replicates; frames are not. Timing comparison is conditional on matched foreground/ready controls; invalid startup attempts are separately retained.','conditions':summary,'paired_contrasts':pairs,'runs':runs}
dest=manifest_path.parent/'analysis.json';dest.write_text(json.dumps(result,indent=2))
print(json.dumps({'analysis':str(dest),'conditions':summary},indent=2))
