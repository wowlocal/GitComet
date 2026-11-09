"""Read saved benchmark evidence; never starts or controls applications."""
from pathlib import Path
import json, hashlib, statistics as st, math, collections

ROOT=Path(__file__).resolve().parent
SERIES=ROOT/'balanced-20261109-203428'
manifest=json.loads((SERIES/'manifest.json').read_text())
published=json.loads((SERIES/'analysis.json').read_text())
plan=json.loads((ROOT/'input-plan.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x)for x in p.read_text().splitlines()]
def eq(a,b,atol=1e-7):
    assert math.isclose(a,b,rel_tol=1e-9,abs_tol=atol),(a,b)
def quant(v):
    q=st.quantiles(v,n=100,method='inclusive')
    return {'n':len(v),'median':st.median(v),'p95':q[94],'p99':q[98],'max':max(v),'min':min(v)}
def checkquant(v,s):
    actual=quant(v);assert actual['n']==s['n']
    for k in ['median','p95','p99','max','min']:eq(actual[k],s[k])
    return actual

assert manifest['pilot'] is False
entries=[r for r in manifest['runs'] if r['valid']]
assert [r['ordinal']for r in entries]==list(range(1,9))
assert [r['condition']for r in entries]==['stock','fixed','fixed','stock','fixed','stock','stock','fixed']
assert len(plan['packets'])==240
assert sha(ROOT/'input-plan.json')==manifest['input_plan_sha256']
assert sha(ROOT/'frozen-input-session.json')==manifest['input_profile_sha256']
assert sha(ROOT/'real-session-before.json')==manifest['real_session_sha256']
profile=load(ROOT/'frozen-input-session.json')
assert len(profile['open_repos'])==264
assert profile['active_repo'].endswith('/<workload-repository>')
builds={k:load(ROOT/(k+'-build.json'))for k in ['stock','fixed']}
sources={k:load(ROOT/(k+'-source.json'))for k in builds}
assert builds['stock']['command']==builds['fixed']['command']
assert builds['stock']['profile']==builds['fixed']['profile']
assert builds['stock']['sources']['app']==builds['fixed']['sources']['app']
assert sources['stock']['application_commit']==sources['fixed']['application_commit']=='ad5df1d185c1a8805870bffcfde592d5e3ce355a'
assert sources['stock']['timing_recorder_sha256']==sources['fixed']['timing_recorder_sha256']
assert sources['stock']['common_app_patch_sha256']==sources['fixed']['common_app_patch_sha256']==sha(ROOT/'common-app.patch')
for c in builds:
    assert builds[c]['exit_code']==0
    assert sha(Path(builds[c]['bundle'])/'Contents/MacOS/gitcomet')==builds[c]['binary_sha256']
    assert sha(ROOT/(c+'-framework.patch'))==sources[c]['framework_tracked_patch_sha256']

results=[];scenarios=set()
cutoffs=[1000*n/120+.25 for n in [2,3,4]]
for entry in entries:
    run=Path(entry['path']);m=load(run/'measurement.json');a=load(run/'analysis.json')
    f=lines(run/'frames.jsonl');n=lines(run/'native.jsonl')
    assert m['verification']['valid'] and not m['verification']['failures']
    assert m['exit_code']==0 and 'error'not in m and m['observer_interval_s']==1
    assert m['real_session_unchanged'] and m['repository_unchanged']
    assert m['condition']==entry['condition']and m['ordinal']==entry['ordinal']
    assert m['build_binary_sha256']==builds[entry['condition']]['binary_sha256']
    assert sha(run/'scenario.json')==m['scenario_sha256'];scenarios.add(m['scenario_sha256'])
    assert len(m['environment'])==2
    for e in m['environment']:
        assert e['frontmost_pid']==m['pid']and e['thermal_state']==0
        assert e['screens']==manifest['expected_environment']['screens']
        assert e['low_power_mode'] is False and 'AC Power'in e['power_source']
        assert [w['bounds']for w in e['target_windows']]==manifest['expected_environment']['window_bounds']
        assert all(w['onscreen']and w['alpha']==1 for w in e['target_windows'])
    inputs=[r for r in f if r['event']=='scenario_input']
    scrolls=[r for r in n if r['event']=='scenario_scroll']
    assert len(inputs)==1442 and len(scrolls)==1440
    assert not any(r['event']=='native_scroll'for r in n)
    for c in range(6):
        for p,r in zip(plan['packets'],scrolls[c*240:(c+1)*240]):
            eq(r['dx'],0);eq(r['dy'],p['delta_px']*(-1 if c%2 else 1))
    stages={r['op']:r for r in f if r['event']=='stage'and r.get('stage')=='input'and r.get('label')=='scenario'}
    assert len(inputs[482:])==960
    assert all(i['detail']['op']in stages for i in inputs[482:])
    late=[stages[i['detail']['op']]['at_ms']-stages[i['detail']['op']]['a']/1e6 for i in inputs[482:]]
    checkquant(late,a['dispatch_lateness_ms'])
    positions=[r for r in f if r['event']=='benchmark_position'];assert len(positions)==12
    for c in range(6):
        assert [r['detail']['state']for r in positions[c*2:c*2+2]]==['before','after']
        expected=[2000,5468]if c%2==0 else[5468,2000]
        for r,value in zip(positions[c*2:c*2+2],expected):eq(r['detail']['offset'],value,.01)
    ready=next(r for r in f if r['event']=='scenario_ready')
    assert ready['detail']['viewport']==manifest['expected_viewport']
    witnesses=[r for r in f if r['event']=='scenario_windows'];assert len(witnesses)==16
    assert all(len(r['detail']['windows'])==1 and all(w['active']and w['ready']and w['repository']==profile['active_repo']for w in r['detail']['windows'])for r in witnesses)
    progress=m['verification']['repository_progress'][-1];assert progress['repos_total']==264 and progress['repos_loaded']==1
    end=next(r for r in reversed(f)if r['event']=='scenario_end');assert end['detail']['outcome']=='passed'
    footer=n[-1];assert footer['event']=='capture_status'and footer['status']=='complete'and footer['reason']=='duration'and footer['dropped']==0 and footer['marker_overflow']==0
    assert footer['records']==len([r for r in n if 'seq'in r])
    offsets=[r['at_s']-i['unix_ms']/1000 for r,i in zip(scrolls,inputs[2:])]
    clock=st.median(offsets);eq(clock,a['clock_mapping_offset_s'])
    residual=[1000*(x-clock)for x in offsets];checkquant(residual,a['clock_mapping_residual_ms'])
    native_arm=next(r for r in n if r['event']=='capture_armed')['ca_anchor_s']
    capture_duration=n[0]['duration_s'];assert capture_duration==50
    phases={state:{r['detail']['name']:r for r in f if r['event']=='scenario_phase'and r['detail']['state']==state}for state in ['begin','end']}
    start=phases['begin']['replay-0'];end=phases['end']['replay-3']
    assert native_arm<scrolls[0]['at_s']<scrolls[-1]['at_s']<native_arm+capture_duration
    assert end['unix_ms']/1000+clock+12.5<native_arm+capture_duration
    positive=[r['presented_s']for r in n if r['event']=='presented'and r['did_present']and r['presented_s']>0]
    allgaps=[];count=0;exposure=0;duplicates=0;core_counts=[]
    for c in range(4):
        origin=scrolls[(c+2)*240]['at_s']
        for ix,w in enumerate(plan['motion_core_windows']):
            lo=origin+w['start_us']/1e6;hi=origin+w['end_us']/1e6
            assert native_arm<lo<hi<native_arm+capture_duration
            raw=[t for t in positive if lo<=t<=hi];unique=sorted(set(raw))
            duplicates+=len(raw)-len(unique);count+=len(unique);core_counts.append(len(unique));exposure+=hi-lo
            allgaps.extend((y-x)*1000 for x,y in zip(unique,unique[1:]))
            saved=a['cores'][c*2+ix];assert len(unique)==saved['presentations']and len(raw)-len(unique)==saved['duplicate_timestamps']
    assert len(core_counts)==8 and min(core_counts)>1
    assert count==a['core']['presentations'];eq(exposure,a['core']['exposure_s']);eq(count/exposure,a['core']['presentation_rate_hz'])
    cadence=checkquant(allgaps,a['core']['interval_ms'])
    longgaps=[sum(x>t for x in allgaps)for t in cutoffs];assert longgaps==a['core']['long_gap_counts']
    for actual,saved in zip(longgaps,a['core']['long_gap_rates_per_second']):eq(actual/exposure,saved)
    lo=start['unix_ms']/1000+clock+.3;hi=end['unix_ms']/1000+clock-.3
    selected=[r for r in n if r['event']=='submit_begin'and lo<=r['at_s']<=hi]
    presents={(r['window'],r['call']):r for r in n if r['event']=='presented'}
    completed={(r['window'],r['call']):r for r in n if r['event']=='gpu_completed'}
    outcomes=dict(submissions=len(selected),missing_present_callback=0,zero_or_not_presented=0,missing_gpu_callback=0,gpu_errors=0)
    for s in selected:
        key=(s['window'],s['call']);p=presents.get(key);g=completed.get(key)
        outcomes['missing_present_callback']+=p is None
        outcomes['zero_or_not_presented']+=bool(p is not None and(not p['did_present']or p['presented_s']<=0))
        outcomes['missing_gpu_callback']+=g is None
        outcomes['gpu_errors']+=bool(g is not None and g['status']!=4)
    assert outcomes==a['submission_outcomes']
    fulltimes=sorted(set(t for t in positive if lo<=t<=hi));fullgaps=[(y-x)*1000 for x,y in zip(fulltimes,fulltimes[1:])]
    assert len(fulltimes)==a['full_phase_descriptive']['presentations'];checkquant(fullgaps,a['full_phase_descriptive']['interval_ms'])
    eq(len(fulltimes)/(hi-lo),a['full_phase_descriptive']['presentation_rate_hz'],.00001)
    submit=[r['duration_ms']for r in f if r['event']=='submit'and start['at_ms']+300<=r['start_ms']<=end['at_ms']-300]
    checkquant(submit,a['cpu_submit_including_drawable_acquisition_ms'])
    windows={'idle_before':(ready['unix_ms']+2500,phases['begin']['prefill']['unix_ms']-800),'scrolling':(start['unix_ms']+300,end['unix_ms']-300),'idle_after':(end['unix_ms']+2500,end['unix_ms']+12500)}
    telemetry={}
    for name,(lo_ms,hi_ms)in windows.items():
        ids=[i for i,r in enumerate(m['samples'])if lo_ms<=r['unix_ms']<=hi_ms]
        assert ids==list(range(min(ids),max(ids)+1))and len(ids)>=4
        rows=[m['samples'][i]for i in ids];dt=rows[-1]['monotonic_s']-rows[0]['monotonic_s'];eq(sum(r['interval_s']for r in rows[1:]),dt)
        pid=str(m['pid']);ws=str(m['windowserver_pid'])
        assert all(r['app_cpu']and r['app_cpu']['pid']==m['pid']and all(k in r['gpu_times_ns']for k in[pid,ws])for r in rows)
        assert all(r['soc']and r['soc']['gpu_energy_nj']is not None and r['soc']['gpu_energy_nj']>=0 for r in rows[1:])
        assert all(b['app_cpu']['cpu_s']>=a_['app_cpu']['cpu_s']and all(b['gpu_times_ns'][k]>=a_['gpu_times_ns'][k]for k in[pid,ws])for a_,b in zip(rows,rows[1:]))
        energy=sum(r['soc']['gpu_energy_nj']for r in rows[1:])/1e9
        states=collections.Counter()
        for r in rows[1:]:states.update(r['soc']['gpu_states'])
        assert all(v>=0 for v in states.values())
        computed={'elapsed_s':dt,'whole_gpu_modeled_j':energy,'whole_gpu_modeled_w':energy/dt,'app_cpu_percent_one_core':100*(rows[-1]['app_cpu']['cpu_s']-rows[0]['app_cpu']['cpu_s'])/dt,'app_gpu_ms_per_wall_second':(rows[-1]['gpu_times_ns'][pid]-rows[0]['gpu_times_ns'][pid])/1e6/dt,'windowserver_gpu_ms_per_wall_second':(rows[-1]['gpu_times_ns'][ws]-rows[0]['gpu_times_ns'][ws])/1e6/dt,'gpu_residency_vs_wall_ratio':sum(states.values())/24e6/dt}
        assert a['telemetry'][name]['available']and not a['telemetry'][name]['counter_reset']
        for k,v in computed.items():eq(v,a['telemetry'][name][k])
        assert abs(computed['gpu_residency_vs_wall_ratio']-1)<.001
        for state,ticks in states.items():
            if ticks:eq(ticks/sum(states.values())*100,a['telemetry'][name]['gpu_state_percent'][state])
        computed['samples']=len(rows);computed['raw_sample_indices']=[min(ids),max(ids)];computed['states_percent']={k:100*v/sum(states.values())for k,v in states.items()if v}
        telemetry[name]=computed
    observer=100*(m['observer_cpu_after']['cpu_s']-m['observer_cpu_before']['cpu_s'])/(m['end_unix_s']-m['start_unix_s']);eq(observer,a['observer_parent_cpu_percent_one_core'])
    results.append({'ordinal':entry['ordinal'],'condition':entry['condition'],'core_presentations':count,'core_exposure_s':exposure,'core_unique_hz':count/exposure,'core_interval_ms':cadence,'core_long_gap_counts':longgaps,'core_duplicates':duplicates,'per_core_counts':core_counts,'full_phase_unique_hz':len(fulltimes)/(hi-lo),'submission_outcomes_full_phase':outcomes,'full_submit_median_ms':st.median(submit),'dispatch_lateness_p95_ms':quant(late)['p95'],'max_abs_clock_residual_ms':max(map(abs,residual)),'input_stages':len(late),'observer_parent_cpu_percent_one_core':observer,'telemetry':telemetry,'capture_records':footer['records'],'capture_dropped':footer['dropped'],'environment_snapshots':len(m['environment'])})
assert len(scenarios)==1

# Reconstruct condition summaries and adjacent contrasts independently from raw-derived records.
metrics={
 'core_presentation_hz':lambda r:r['core_unique_hz'],
 'core_interval_median_ms':lambda r:r['core_interval_ms']['median'],
 'core_interval_p95_ms':lambda r:r['core_interval_ms']['p95'],
 'core_interval_p99_ms':lambda r:r['core_interval_ms']['p99'],
 'core_max_gap_ms':lambda r:r['core_interval_ms']['max'],
 'app_cpu_percent_one_core':lambda r:r['telemetry']['scrolling']['app_cpu_percent_one_core'],
 'app_gpu_ms_per_wall_second':lambda r:r['telemetry']['scrolling']['app_gpu_ms_per_wall_second'],
 'whole_gpu_modeled_w':lambda r:r['telemetry']['scrolling']['whole_gpu_modeled_w'],
 'idle_before_whole_gpu_modeled_w':lambda r:r['telemetry']['idle_before']['whole_gpu_modeled_w'],
 'idle_after_app_gpu_ms_per_wall_second':lambda r:r['telemetry']['idle_after']['app_gpu_ms_per_wall_second'],
 'windowserver_gpu_ms_per_wall_second':lambda r:r['telemetry']['scrolling']['windowserver_gpu_ms_per_wall_second'],
 'cpu_submit_median_ms':lambda r:r['full_submit_median_ms'],
 'dispatch_lateness_p95_ms':lambda r:r['dispatch_lateness_p95_ms']}
summaries={}
for condition in builds:
    rows=[r for r in results if r['condition']==condition]
    summaries[condition]={name:checkquant([fn(r)for r in rows],published['conditions'][condition][name])for name,fn in metrics.items()}
    extras={'observer_parent_cpu_percent_one_core':lambda r:r['observer_parent_cpu_percent_one_core'],'zero_or_not_presented_fullphase':lambda r:r['submission_outcomes_full_phase']['zero_or_not_presented'],'submissions_fullphase':lambda r:r['submission_outcomes_full_phase']['submissions'],'full_phase_unique_hz':lambda r:r['full_phase_unique_hz'],'idle_after_whole_gpu_modeled_w':lambda r:r['telemetry']['idle_after']['whole_gpu_modeled_w'],'idle_after_app_cpu_percent_one_core':lambda r:r['telemetry']['idle_after']['app_cpu_percent_one_core'],'idle_after_windowserver_gpu_ms_per_wall_second':lambda r:r['telemetry']['idle_after']['windowserver_gpu_ms_per_wall_second']}
    summaries[condition].update({k:quant([fn(r)for r in rows])for k,fn in extras.items()})
pairs=[]
for pair,saved in zip([results[i:i+2]for i in range(0,8,2)],published['paired_contrasts']):
    stock=next(r for r in pair if r['condition']=='stock');fixed=next(r for r in pair if r['condition']=='fixed')
    contrast={name:fn(fixed)-fn(stock)for name,fn in metrics.items()}
    assert saved['ordinals']==[stock['ordinal'],fixed['ordinal']]
    for k,v in contrast.items():eq(v,saved['fixed_minus_stock'][k])
    pairs.append({'ordinals':saved['ordinals'],'fixed_minus_stock':contrast})

failures=[]
badpaths=[Path(r['path'])for r in manifest['runs']if not r['valid']]
badpaths+=[ROOT/'pilot-fixed-20261109-202952/01-fixed']
for run in badpaths:
    m=load(run/'measurement.json');f=lines(run/'frames.jsonl')
    scenario_end=[r for r in f if r['event']=='scenario_end']
    phases=[r['detail']for r in f if r['event']=='scenario_phase']
    assert not m['verification']['valid']and not phases
    assert scenario_end and scenario_end[-1]['detail']['outcome']!='passed'
    failures.append({'path':str(run.relative_to(ROOT)),'condition':m['condition'],'ordinal':m['ordinal'],'verification_failures':m['verification']['failures'],'scenario_end':scenario_end[-1]['detail'],'scenario_phase_count':len(phases),'exit_code':m.get('exit_code'),'timing_footer':m['verification']['timing_footer']})
assert len(failures)==2 and all(x['condition']=='fixed'for x in failures)
report={'verdict':'Raw arithmetic and recorded controls pass. This workload does not demonstrate smoother presentation or equal-output energy efficiency for PR47.','series':str(SERIES),'auditor_sha256':sha(Path(__file__)),'analyzer_sha256':sha(ROOT/'analyze.py'),'runner_sha256':sha(ROOT/'run.py'),'analysis_sha256':sha(SERIES/'analysis.json'),'source_metadata':sources,'build_profile':builds['stock']['profile'],'source_isolation_reference':'instrumentation-review.md and instrumentation-parity.json (independent source reconstruction review)','checks':{'valid_runs':8,'order':'ABBA BAAB','pilots_in_comparison':0,'retained_main_invalid_attempts':1,'prior_invalid_pilot_attempts':1,'measured_input_stages_per_run':960,'core_exposure_s_per_run':4.601196,'identical_scenario_sha256':next(iter(scenarios)),'display_ready_and_after_scroll_match':True,'both_build_binary_hashes_match':True,'all_phase_counter_integrals_match':True,'all_pairwise_counter_monotonic':True,'all_residency_sums_match_wall_time_with_rounding':True,'all_presentations_and_gap_quantiles_match':True,'all_paired_contrasts_match':True,'no_native_hardware_input_in_replay':True},'summary':summaries,'paired_contrasts':pairs,'runs':results,'failed_attempts':failures,'caveats':['Instrumented stock versus instrumented PR47 at one exact upstream app commit on one Mac and built-in 120Hz display; four valid runs per condition, not independent per-frame replicates.','Absolute-schedule synthetic GPUI packet replay; it does not reproduce every physical trackpad/momentum path. Primary cadence covers fixed sustained-motion source windows, 4.601196s/run; tails/full-phase results are separate.','Foreground readiness is conditional; two fixed startup focus failures were retained, one pilot and one main-series attempt, with no proven PR47 attribution.','Positive unique drawable presentedTime is the measured output. Lower GPU energy with fewer presentations does not establish energy efficiency at equal output. CPU activity increased in all four adjacent pairs.','GPU Energy is the whole-device IOReport Energy Model in nJ, not app-specific, wall/socket, battery discharge, or total-system watts. WindowServer and other desktop workloads share it.','Per-process IOKit accumulatedGPUTime is accounted execution time, not GPU utilization or peak load. GPU command-buffer elapsed durations are different counters.','Telemetry windows are broader than primary cadence cores; do not divide full-window energy by core-only frame count.','Observer parent CPU is approximately 1.25–1.32 percent of one core; its children CPU includes the app and must not be added as observer overhead.','Idle-after app GPU was essentially zero, while whole-device energy and WindowServer activity remained variable; no pure per-app watts can be inferred from idle subtraction.']}
report['caveats'][7]='Observer parent CPU was 1.251–1.307 percent of one core; its children CPU includes the app and must not be added as observer overhead.'
report['caveats'] += ['Recorded display/power/geometry/thermal controls and the runner game/compiler guard matched. They cannot exclude every background GPU consumer; WindowServer is a shared compositor.','A zero/not-presented drawable callback means that particular submitted drawable was not positively reported displayed. It is retained as an outcome and must not automatically be described as a perceptible dropped animation frame.','GPU performance-state residency and driver utilization are separate from shader occupancy or thermal/power saturation. This experiment does not establish saturation.']
(ROOT/'final-data-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'verdict':report['verdict'],'summary':{c:{k:{q:v[q]for q in ['median','min','max']}for k,v in z.items()}for c,z in summaries.items()},'runs':[{'ordinal':r['ordinal'],'condition':r['condition'],'core_hz':r['core_unique_hz'],'max_gap':r['core_interval_ms']['max'],'long':r['core_long_gap_counts'],'zero':r['submission_outcomes_full_phase']['zero_or_not_presented'],'observer':r['observer_parent_cpu_percent_one_core'],'clockmax':r['max_abs_clock_residual_ms'],'residencyratios':[v['gpu_residency_vs_wall_ratio']for v in r['telemetry'].values()]}for r in results],'failed_attempts':failures},indent=2))
