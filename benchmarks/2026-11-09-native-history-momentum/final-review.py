"""Independent raw-data arithmetic review; no acquisition or UI operations."""
from pathlib import Path
import json,hashlib,statistics as st,math,bisect,collections

ROOT=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent
SERIES=ROOT/'balanced-20261109-213514'
load=lambda p:json.loads(p.read_text())
lines=lambda p:[json.loads(x)for x in p.read_text().splitlines()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=load(SERIES/'manifest.json');analysis=load(OUT/('analysis-'+SERIES.name+'.json'));plan=load(OUT/'input-plan.json')
def equal(a,b,tolerance=1e-7):assert math.isclose(a,b,rel_tol=1e-9,abs_tol=tolerance),(a,b)
def quant(v):
    q=st.quantiles(v,n=100,method='inclusive');return dict(n=len(v),median=st.median(v),p95=q[94],p99=q[98],max=max(v),min=min(v))
def verifyquant(v,reported):
    calculated=quant(v)
    for k,value in calculated.items():equal(value,reported[k])
    return calculated
def linear_at(times,positions,time):
    if time<=times[0]:return positions[0]
    if time>=times[-1]:return positions[-1]
    j=bisect.bisect_right(times,time)-1
    return positions[j]+(positions[j+1]-positions[j])*(time-times[j])/(times[j+1]-times[j])
def inverse_latest(times,positions,value,direction):
    oriented=[p*direction for p in positions];value*=direction
    assert oriented[0]-.01<=value<=oriented[-1]+.01
    value=max(oriented[0],min(oriented[-1],value));j=bisect.bisect_right(oriented,value)-1
    if j==len(times)-1:return times[j]
    return times[j]+(times[j+1]-times[j])*(value-oriented[j])/(oriented[j+1]-oriented[j])
assert not manifest['pilot']and len(manifest['runs'])==8
assert all(e['valid']and not e['failures']for e in manifest['runs'])
assert [e['condition']for e in manifest['runs']]==plan['order']
assert [e['ordinal']for e in manifest['runs']]==list(range(1,9))
assert sha(ROOT/'input-plan.json')==sha(OUT/'input-plan.json')==manifest['input_plan_sha256']
assert sha(ROOT/'frozen-input-session.json')==manifest['input_profile_sha256']
profile=load(ROOT/'frozen-input-session.json');assert len(profile['open_repos'])==264
assert profile['auto_fetch_enabled']is False and profile['check_for_updates_on_startup']is False
result=[];environment_controls=[];scenarios=set();binary_hashes=set()
for entry,a in zip(manifest['runs'],analysis['runs']):
    run=Path(entry['path']);m=load(run/'measurement.json');f=lines(run/'frames.jsonl');n=lines(run/'native.jsonl')
    assert m['verification']['valid']and m['repository_unchanged']and m['real_session_unchanged']and 'error'not in m
    assert m['condition']==entry['condition']==a['condition']and m['ordinal']==entry['ordinal']==a['ordinal']
    assert m['observer_interval_s']==1 and m['launch_method'].startswith('LaunchServices')
    scenarios.add(sha(run/'scenario.json'));assert m['scenario_sha256']in scenarios
    binary_hashes.add(m['build_binary_sha256'])
    assert len(m['environment'])==2 and [e['event']for e in m['environment']]==['ready','after_scroll']
    for e in m['environment']:
        assert e['reduce_motion']is False and e['low_power_mode']is False and e['thermal_state']==0 and e['frontmost_pid']==m['pid']
        controls={k:e[k]for k in['screens','low_power_mode','reduce_motion']};controls.update(power_source='AC'if'AC Power'in e['power_source']else'Battery',window_bounds=[w['bounds']for w in e['target_windows']]);assert controls==manifest['expected_environment'];environment_controls.append(controls)
    progress=m['verification']['repository_progress'][-1];assert progress['repos_total']==264 and progress['repos_loaded']==1
    assert m['verification']['ready_geometry']['viewport']==manifest['expected_viewport']
    witnesses=[r for r in f if r['event']=='scenario_windows'];assert len(witnesses)==16
    assert all(len(r['detail']['windows'])==1 and all(w['active']and w['ready']and w['repository']==profile['active_repo']for w in r['detail']['windows'])for r in witnesses)
    assert next(r for r in reversed(f)if r['event']=='scenario_end')['detail']['outcome']=='passed'
    inputs=[r for r in f if r['event']=='scenario_input'];packets=[r for r in n if r['event']=='scenario_scroll'];assert len(inputs)==len(packets)==1442
    stages={r['op']:r for r in f if r['event']=='stage'and r.get('stage')=='input'and r.get('label')=='scenario'};traces=[stages[i['detail']['op']]for i in inputs];assert len(traces[482:])==960
    scenario=load(run/'scenario.json');packet_plans=[r['packets']for r in scenario['steps']if r['do']=='scroll_packets'];assert len(packet_plans)==6
    for c,p in enumerate(packet_plans):
        assert len(p)==240
        for expected,actual,dispatched in zip(plan['packets'],p,packets[2+c*240:2+(c+1)*240]):
            assert expected['at_us']==actual['at_us']and expected['native']==actual['native']and expected['delta_px']*(-1 if c%2 else 1)==actual['delta_px']==dispatched['dy']and dispatched['dx']==0
    assert not any(r['event']=='native_scroll'for r in n)
    footer=n[-1];assert footer['status']=='complete'and footer['dropped']==footer['marker_overflow']==0 and footer['records']==len([r for r in n if'seq'in r])
    assert footer['records']<n[0]['max_records']==32768 and n[0]['duration_s']==60
    assert all(r['minimum_hz']==r['maximum_hz']==r['preferred_hz']==0 and r['preferred_latency']==2 for r in n if r['event']=='metal_update')
    offset=st.median(r['at_s']-t['at_ms']/1000 for r,t in zip(packets,traces));equal(offset,a['clock_mapping']['ca_minus_trace_s'])
    clock_residual=max(abs((r['at_s']-t['at_ms']/1000-offset)*1000)for r,t in zip(packets,traces));equal(clock_residual,a['clock_mapping']['max_abs_trace_residual_ms'])
    unix_offset=st.median(r['at_s']-i['unix_ms']/1000 for r,i in zip(packets,inputs));equal(unix_offset,a['clock_mapping']['ca_minus_unix_s'])
    markers={r['seq']:r for r in n if r['event']=='history_offset'}
    positive=[r for r in n if r['event']=='presented'and r['did_present']and r['presented_s']>0]
    bytime=collections.defaultdict(list)
    for r in positive:bytime[r['presented_s']].append(r)
    pose={}
    for t,rs in bytime.items():
        values=[markers[r['history_marker']]['top']*markers[r['history_marker']]['row_height']+markers[r['history_marker']]['within']for r in rs if r['history_marker']in markers]
        pose[t]=st.median(values)if len(values)==len(rs)and max(values)-min(values)<=.01 else None
    unique=sorted(bytime);count=held=known=0;known_time=held_time=exposure=0;gaps=[];lags=[];residual_totals={str(s):[0.,0.]for s in[0,12.5]};endpoints=[];source_ages=[];gesture_endpoints=[]
    for c in range(6):
        group=packets[2+c*240:2+(c+1)*240];trace=traces[2+c*240:2+(c+1)*240];origin=group[0]['at_s'];start=2000 if c%2==0 else 5468;direction=1 if c%2==0 else -1
        path=[start]
        for p in packet_plans[c]:path.append(path[-1]-p['delta_px'])
        source=[t['a']/1e9+offset-p['native']['age_us']/1e6 for t,p in zip(trace,packet_plans[c])]
        assert all(y>=x for x,y in zip(source,source[1:]))
        cutoff=packets[2+(c+1)*240]['at_s']if c<5 else group[-1]['at_s']+.5
        actual_times=[t for t in unique if group[0]['at_s']<=t<cutoff];final_t=actual_times[-1];final_pose=pose[final_t]
        # Final actual timestamp, including unknowns, is the endpoint witness.
        assert final_pose is not None;error=final_pose-path[-1];assert abs(error)<=.01
        saved=a['cycles'][c];equal(saved['last_displayed_at_s'],final_t);equal(saved['last_displayed_pose'],final_pose);equal(saved['endpoint_error_px'],error);assert saved['last_displayed_pose_status']=='known'and saved['endpoint_within_tolerance']is True
        endpoints.append(error)
        # Supplement the cycle checks with each original gesture's endpoint,
        # using the final actual timestamp before the next gesture/cycle.
        for gesture,(begin_packet,end_packet)in enumerate([(0,121),(122,239)]):
            boundary=group[122]['at_s']if gesture==0 else cutoff
            shown=[t for t in unique if group[begin_packet]['at_s']<=t<boundary];final=shown[-1];value=pose[final];expected=path[end_packet+1]
            assert value is not None and abs(value-expected)<=.01
            last_nonzero=next(r['at_s']for r in reversed(group[begin_packet:end_packet+1])if r['dy'])
            reached=[t for t in shown if t>=last_nonzero and pose[t]is not None and abs(pose[t]-expected)<=.01];assert reached
            gesture_endpoints.append({'cycle':c,'measured':c>=2,'gesture':gesture,'final_actual_display_known':True,'endpoint_error_px':value-expected,'first_endpoint_after_last_nonzero_dispatch_ms':(reached[0]-last_nonzero)*1000})
        arrivals=[r['at_s']for r in group]
        previous=start
        for marker in sorted((r for r in markers.values()if group[0]['at_s']<=r['at_s']<cutoff),key=lambda r:r['at_s']):
            value=marker['top']*marker['row_height']+marker['within'];k=bisect.bisect_right(arrivals,marker['at_s']);lo,hi=sorted((start,path[k]));assert lo-.01<=value<=hi+.01 and direction*(value-previous)>=-.01;previous=value
        if c<2:continue
        source_ages.extend((r['at_s']-t)*1000 for r,t in zip(group,source))
        for ix,core in enumerate(plan['momentum_core_windows']):
            lo=origin+core['start_us']/1e6;hi=origin+core['end_us']/1e6;times=[t for t in unique if lo<=t<=hi];exposure+=hi-lo;count+=len(times)
            assert all(pose[t]is not None for t in times)
            full=plan['full_momentum_windows'][ix];begin=next(i for i,p in enumerate(plan['packets'])if p['at_us']==full['start_us']);end=next(i for i,p in enumerate(plan['packets'])if p['at_us']==full['end_us']);tref=source[begin-1:end+1];pref=path[begin:end+2]
            for t in times:lags.append((t-inverse_latest(tref,pref,pose[t],direction))*1000)
            for x,y in zip(times,times[1:]):
                dt=y-x;step=pose[y]-pose[x];known+=1;known_time+=dt;gaps.append(dt*1000)
                if abs(step)<=.01:held+=1;held_time+=dt
                assert direction*step>=-.01
                for shift in[0,12.5]:
                    reference=linear_at(tref,pref,y-shift/1000)-linear_at(tref,pref,x-shift/1000);residual_totals[str(shift)][0]+=abs(step-reference);residual_totals[str(shift)][1]+=abs(reference)
    assert count==a['core']['presentations']and held==a['core']['held_pairs']and known==a['core']['known_pairs']
    assert a['core']['unknown_pairs']==a['core']['unknown_poses']==a['core']['ambiguous_poses']==a['core']['duplicates']==0
    equal(exposure,4.251708);equal(count/exposure,a['core']['presentation_rate_hz']);equal(held/known,a['core']['held_pair_fraction']);equal(held_time/known_time,a['core']['held_pair_time_fraction']);verifyquant(gaps,a['core']['gap_ms']);verifyquant(lags,a['core']['source_equivalent_pose_lag_ms']);verifyquant(source_ages,a['effective_source_age_ms']);assert max(source_ages)<100
    long=[sum(v>threshold for v in gaps)for threshold in[n/120*1000+.25 for n in[2,3,4]]];assert long==a['core']['long_gap_counts']==[0,0,0]
    for key,(num,den)in residual_totals.items():
        saved=a['core']['source_curve_residual_by_fixed_shift_ms'][key];equal(num,saved['sum_absolute_delta_error_px']);equal(den,saved['sum_absolute_reference_travel_px']);equal(num/den,saved['travel_normalized_absolute_delta_error'])
    phases={state:{r['detail']['name']:r for r in f if r['event']=='scenario_phase'and r['detail']['state']==state}for state in['begin','end']};ready=next(r for r in f if r['event']=='scenario_ready');first=phases['begin']['replay-0'];last=phases['end']['replay-3']
    windows={'idle_before':(ready['unix_ms']+2500,phases['begin']['prefill']['unix_ms']-800),'scrolling':(first['unix_ms']+300,last['unix_ms']-300),'idle_after':(last['unix_ms']+2500,last['unix_ms']+12500)}
    for name,(lo,hi)in windows.items():
        ids=[i for i,r in enumerate(m['samples'])if lo<=r['unix_ms']<=hi];assert ids==list(range(min(ids),max(ids)+1))and len(ids)>=4
        rows=[m['samples'][i]for i in ids];dt=rows[-1]['monotonic_s']-rows[0]['monotonic_s'];equal(sum(r['interval_s']for r in rows[1:]),dt);saved=a['telemetry'][name];assert saved['available']and not saved['cpu_counter_reset']and not saved['gpu_counter_reset']
        assert all(r['app_cpu']and r['app_cpu']['pid']==m['pid']for r in rows)
        cpu=100*(rows[-1]['app_cpu']['cpu_s']-rows[0]['app_cpu']['cpu_s'])/dt;energy=sum(r['soc']['gpu_energy_nj']for r in rows[1:])/1e9
        equal(cpu,saved['app_cpu_percent_one_core']);equal(energy,saved['whole_gpu_modeled_j']);equal(energy/dt,saved['whole_gpu_modeled_w'])
        assert all(b['app_cpu']['cpu_s']>=a_['app_cpu']['cpu_s']for a_,b in zip(rows,rows[1:]))
        for key,label in[(str(m['pid']),'app_gpu_ms_per_wall_second'),(str(m['windowserver_pid']),'windowserver_gpu_ms_per_wall_second')]:
            assert all(key in r['gpu_times_ns']for r in rows)and all(b['gpu_times_ns'][key]>=a_['gpu_times_ns'][key]for a_,b in zip(rows,rows[1:]));equal((rows[-1]['gpu_times_ns'][key]-rows[0]['gpu_times_ns'][key])/1e6/dt,saved[label])
        state=collections.Counter()
        for r in rows[1:]:state.update(r['soc']['gpu_states'])
        ratio=sum(state.values())/24e6/dt;equal(ratio,saved['gpu_residency_vs_wall_ratio']);assert abs(ratio-1)<.001
        for k,v in state.items():
            if v:equal(v/sum(state.values())*100,saved['gpu_state_percent'][k])
    arm=next(r['ca_anchor_s']for r in n if r['event']=='capture_armed');deadline=arm+60;assert a['capture_coverage']['all_core_windows_inside']and a['capture_coverage']['idle_after_inside']and last['unix_ms']/1000+unix_offset+12.5<deadline<footer['flushed_at_s']
    lo=first['unix_ms']/1000+unix_offset+.3;hi=last['unix_ms']/1000+unix_offset-.3
    selected=[r for r in n if r['event']=='submit_begin'and lo<=r['at_s']<=hi];present={(r['window'],r['call']):r for r in n if r['event']=='presented'};completed={(r['window'],r['call']):r for r in n if r['event']=='gpu_completed'};outcomes=dict(submissions=len(selected),missing_present_callback=0,zero_or_not_presented=0,missing_gpu_callback=0,gpu_errors=0)
    for r in selected:
        key=(r['window'],r['call']);p=present.get(key);g=completed.get(key);outcomes['missing_present_callback']+=p is None;outcomes['zero_or_not_presented']+=bool(p is not None and(not p['did_present']or p['presented_s']<=0));outcomes['missing_gpu_callback']+=g is None;outcomes['gpu_errors']+=bool(g is not None and g['status']!=4)
    assert outcomes==a['submission_outcomes_full_phase']and outcomes['missing_present_callback']==outcomes['missing_gpu_callback']==outcomes['gpu_errors']==0
    observer=100*(m['observer_cpu_after']['cpu_s']-m['observer_cpu_before']['cpu_s'])/(m['end_unix_s']-m['start_unix_s']);equal(observer,a['observer_parent_cpu_percent_one_core'])
    result.append({'ordinal':entry['ordinal'],'condition':entry['condition'],'core_presentations':count,'core_known_pairs':known,'core_held_pairs':held,'core_held_fraction':held/known,'core_held_time_fraction':held_time/known_time,'core_hz':count/exposure,'core_gap_ms':quant(gaps),'core_long_gap_counts':long,'source_equivalent_pose_lag_ms':quant(lags),'curve_residuals':{k:num/den for k,(num,den)in residual_totals.items()},'max_source_age_ms':max(source_ages),'max_abs_clock_residual_ms':clock_residual,'max_abs_endpoint_error_px':max(map(abs,endpoints)),'gesture_endpoints_supplement':gesture_endpoints,'unknown_or_ambiguous_final_endpoints':0,'capture_records':footer['records'],'capture_capacity_margin':32768-footer['records'],'submission_outcomes_full_phase':outcomes,'telemetry':a['telemetry'],'observer_parent_cpu_percent_one_core':observer})
assert len(scenarios)==len(binary_hashes)==1
assert next(iter(binary_hashes))=='f3172102f1b0b9722424ea991ee229a51396ee43a87cffaabcd4adc36b9455c3'
mapping={'core_hz':lambda r:r['core_hz'],'core_gap_p95_ms':lambda r:r['core_gap_ms']['p95'],'core_gap_p99_ms':lambda r:r['core_gap_ms']['p99'],'core_max_gap_ms':lambda r:r['core_gap_ms']['max'],'held_known_pair_fraction':lambda r:r['core_held_fraction'],'held_known_time_fraction':lambda r:r['core_held_time_fraction'],'source_equivalent_pose_lag_median_ms':lambda r:r['source_equivalent_pose_lag_ms']['median'],'source_equivalent_pose_lag_p95_ms':lambda r:r['source_equivalent_pose_lag_ms']['p95'],'curve_delta_error_shift0':lambda r:r['curve_residuals']['0'],'curve_delta_error_shift12_5':lambda r:r['curve_residuals']['12.5'],'app_cpu_percent_one_core':lambda r:r['telemetry']['scrolling']['app_cpu_percent_one_core'],'app_gpu_ms_per_wall_second':lambda r:r['telemetry']['scrolling']['app_gpu_ms_per_wall_second'],'whole_gpu_modeled_w':lambda r:r['telemetry']['scrolling']['whole_gpu_modeled_w'],'observer_parent_cpu_percent_one_core':lambda r:r['observer_parent_cpu_percent_one_core']}
summary={c:{k:verifyquant([fn(r)for r in result if r['condition']==c],analysis['conditions'][c][k])for k,fn in mapping.items()}for c in['off','on']}
for c in summary:
    rows=[r for r in result if r['condition']==c]
    for phase in['idle_before','scrolling','idle_after']:
        for k in['whole_gpu_modeled_w','app_cpu_percent_one_core','app_gpu_ms_per_wall_second','windowserver_gpu_ms_per_wall_second']:summary[c][phase+'_'+k]=quant([r['telemetry'][phase][k]for r in rows])
paired=[]
for i,saved in zip(range(0,8,2),analysis['paired_contrasts']):
    off=next(r for r in result[i:i+2]if r['condition']=='off');on=next(r for r in result[i:i+2]if r['condition']=='on');assert saved['ordinals_off_on']==[off['ordinal'],on['ordinal']];d={k:fn(on)-fn(off)for k,fn in mapping.items()}
    for k,v in d.items():equal(v,saved['on_minus_off'][k])
    paired.append({'ordinals_off_on':saved['ordinals_off_on'],'on_minus_off':d})
report={'verdict':'Recorded arithmetic and controls pass; supports logical pose retiming with a latency/CPU tradeoff, not a higher-frame-rate or physical-user-feel claim.','series':str(SERIES),'analysis_sha256':sha(OUT/('analysis-'+SERIES.name+'.json')),'reviewer_script_sha256':sha(Path(__file__)),'binary_sha256':next(iter(binary_hashes)),'scenario_sha256':next(iter(scenarios)),'checks':{'valid_balanced_runs':8,'pilot_runs_in_comparison':0,'main_failed_attempts':0,'paired_input_and_native_markers_per_run':1442,'measured_stages_per_run':960,'core_exposure_s_per_run':4.251708,'unique_cadence_held_duration_and_source_inverse_recomputed':True,'both_fixed_shift_curve_residuals_recomputed':True,'all24phase_integrals_and_monotonic_counters_recomputed':True,'final_actual_display_endpoint_status_verified':True,'cross_run_environment_binary_profile_scenario_control_matches':True,'all_paired_contrasts_reproduced':True},'summary':summary,'paired_contrasts':paired,'runs':result,'caveats':['Four serial runs per condition on one machine; per-frame observations are not independent experimental replicates.','Synthetic phase/timestamp metadata replay through GPUI; logical prepaint poses are not raster displacement or a physical trackpad/user-feel trial.','The algorithm deliberately uses12.5ms sample lookback. Source-equivalent displayed-pose lag is a compound modeled surrogate, not a physical end-to-end latency measurement.','Core frame cadence did not improve; sparse held logical pose pairs disappeared, a narrower objective finding.','The0/12.5ms source-normalized curve residuals are mixed across pairs; do not claim universal uneven-step improvement from held-pose counts.','Whole-GPU model watts include WindowServer/desktop work, are not app watts or total system/battery power, and use a broader window than primary motion cores.','CPU increases in all four adjacent pairs; app GPU execution-time contrasts are mixed; lower shared GPU modeled watts do not establish lower total energy or equal-output efficiency.','Successful pilots and retained failed On pilot are excluded. Normal activation after readiness was fixed identically for both main conditions before main acquisition.','Endpoint unknown-handling was corrected during acquisition without reading main results, preserving prior code/patch/test evidence; all actual final endpoints in this dataset are known.']}
(OUT/'final-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'verdict':report['verdict'],'runs':[{'ordinal':r['ordinal'],'mode':r['condition'],'hz':r['core_hz'],'held':[r['core_held_pairs'],r['core_known_pairs']],'lagmed':r['source_equivalent_pose_lag_ms']['median'],'cpu':r['telemetry']['scrolling']['app_cpu_percent_one_core'],'GPUW':r['telemetry']['scrolling']['whole_gpu_modeled_w'],'WSGPU':r['telemetry']['scrolling']['windowserver_gpu_ms_per_wall_second'],'records':r['capture_records']}for r in result],'summary':{c:{k:{q:v[q]for q in['median','min','max']}for k,v in s.items()}for c,s in summary.items()}},indent=2))
