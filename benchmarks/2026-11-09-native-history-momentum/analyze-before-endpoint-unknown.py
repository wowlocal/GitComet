"""Saved-data only analysis of same-binary off/on metadata replay.

Writes a separate review report, never starts apps or alters source captures.
"""
from pathlib import Path
import argparse, bisect, collections, hashlib, json, math, statistics as st

HERE=Path(__file__).resolve().parent

def read(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(x)for x in Path(p).read_text().splitlines()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stats(values):
    all_values=list(values);v=sorted(x for x in all_values if x is not None and math.isfinite(x))
    def q(p):
        n=(len(v)-1)*p;lo=math.floor(n);hi=math.ceil(n)
        return v[lo]+(v[hi]-v[lo])*(n-lo)
    return {'n':len(v),'missing':len(all_values)-len(v),'min':v[0],'median':q(.5),'p95':q(.95),'p99':q(.99),'max':v[-1]}if v else dict(n=0,missing=len(all_values),min=None,median=None,p95=None,p99=None,max=None)

class Curve:
    """Piecewise-linear, endpoint-clamped source curve; plateaus invert latest."""
    def __init__(self,times,positions):
        assert len(times)==len(positions)>1
        assert all(b>=a for a,b in zip(times,times[1:])), 'Source timestamps not ordered'
        merged={}
        for t,p in zip(times,positions):merged[t]=p
        self.t=list(merged);self.p=list(merged.values())
        self.direction=1 if self.p[-1]>=self.p[0] else -1
        self.oriented=[x*self.direction for x in self.p]
        assert all(b>=a-.000001 for a,b in zip(self.oriented,self.oriented[1:])), 'Source direction reversal'
    def at(self,t):
        if t<=self.t[0]:return self.p[0]
        if t>=self.t[-1]:return self.p[-1]
        i=bisect.bisect_right(self.t,t)-1
        f=(t-self.t[i])/(self.t[i+1]-self.t[i])
        return self.p[i]+f*(self.p[i+1]-self.p[i])
    def inverse(self,p,tolerance=.01):
        x=p*self.direction
        if x<self.oriented[0]-tolerance or x>self.oriented[-1]+tolerance:return None
        x=max(self.oriented[0],min(x,self.oriented[-1]))
        i=bisect.bisect_right(self.oriented,x)-1
        if i==len(self.t)-1:return self.t[-1]
        span=self.oriented[i+1]-self.oriented[i]
        assert span>0
        return self.t[i]+(self.t[i+1]-self.t[i])*(x-self.oriented[i])/span

def displayed_samples(native,tolerance):
    markers={r['seq']:r for r in native if r['event']=='history_offset'}
    submissions={(r['window'],r['call']):r for r in native if r['event']=='submit_begin'}
    grouped=collections.defaultdict(list)
    for r in native:
        if r['event']=='presented'and r['did_present']and r['presented_s']>0:
            marker=markers.get(r['history_marker']);position=marker['top']*marker['row_height']+marker['within']if marker else None
            grouped[(r['window'],r['presented_s'])].append({'position':position,'marker_at_s':marker['at_s']if marker else None,'marker':r['history_marker'],'call':r['call'],'scene_revision':r['scene_revision'],'submit_found':(r['window'],r['call'])in submissions})
    result=[]
    for (window,t),rows in sorted(grouped.items()):
        poses=[r['position']for r in rows if r['position']is not None]
        ambiguous=bool(poses and max(poses)-min(poses)>tolerance)
        known=bool(len(poses)==len(rows)and not ambiguous)
        result.append({'window':window,'t':t,'position':st.median(poses)if known else None,'marker_at_s':max(r['marker_at_s']for r in rows)if known else None,'duplicate_callbacks':len(rows)-1,'ambiguous':ambiguous,'callbacks':rows})
    return result,markers

def window_metrics(samples,lo,hi,curve,shifts,tolerance):
    selected=[r for r in samples if lo<=r['t']<=hi]
    gaps=[(b['t']-a['t'])*1000 for a,b in zip(selected,selected[1:])]
    known=[];unknown_time=0;unknown_pairs=0;held_time=0;held_pairs=0;legacy_held=0;run_held=0;max_held=0;reversals=0
    changed_intervals=[];last_changed=None
    for a,b in zip(selected,selected[1:]):
        dt=b['t']-a['t']
        if a['position']is None or b['position']is None:
            unknown_pairs+=1;unknown_time+=dt;run_held=0;last_changed=None;continue
        step=b['position']-a['position'];known.append((a,b,dt,step))
        if abs(step)<=tolerance:
            held_pairs+=1;held_time+=dt;run_held+=dt;max_held=max(max_held,run_held)
        else:
            run_held=0
            if last_changed is not None:changed_intervals.append((b['t']-last_changed)*1000)
            last_changed=b['t']
        legacy_held+=abs(step)<1e-6
        reversals+=step*curve.direction < -tolerance
    known_time=sum(x[2]for x in known)
    residuals={}
    for shift_ms in shifts:
        errors=[];expected_travel=0
        for a,b,dt,step in known:
            expected=curve.at(b['t']-shift_ms/1000)-curve.at(a['t']-shift_ms/1000)
            errors.append(abs(step-expected));expected_travel+=abs(expected)
        residuals[str(shift_ms)]={'sum_absolute_delta_error_px':sum(errors),'sum_absolute_reference_travel_px':expected_travel,'travel_normalized_absolute_delta_error':sum(errors)/expected_travel if expected_travel else None,'absolute_delta_error_px':stats(errors)}
    lags=[];inverse_unavailable=0
    for r in selected:
        if r['position']is None:inverse_unavailable+=1;continue
        t=curve.inverse(r['position'])
        if t is None:inverse_unavailable+=1
        else:lags.append((r['t']-t)*1000)
    cutoffs=[n/120*1000+.25 for n in[2,3,4]]
    ages=[(r['t']-r['marker_at_s'])*1000 if r['marker_at_s']is not None else None for r in selected]
    return {'lo_ca_s':lo,'hi_ca_s':hi,'exposure_s':hi-lo,'presentations':len(selected),'presentation_rate_hz':len(selected)/(hi-lo),'duplicates':sum(r['duplicate_callbacks']for r in selected),'ambiguous_poses':sum(r['ambiguous']for r in selected),'unknown_poses':sum(r['position']is None for r in selected),'gap_ms':stats(gaps),'long_gap_counts':[sum(v>cutoff for v in gaps)for cutoff in cutoffs],'pairs':len(gaps),'known_pairs':len(known),'unknown_pairs':unknown_pairs,'known_pair_time_s':known_time,'unknown_pair_time_s':unknown_time,'held_pairs':held_pairs,'legacy_held_pairs_lt_1e6':legacy_held,'held_pair_fraction':held_pairs/len(known)if known else None,'held_pair_time_s':held_time,'held_pair_time_fraction':held_time/known_time if known_time else None,'max_consecutive_observed_hold_ms':max_held*1000,'direction_reversal_pairs':reversals,'absolute_step_px':stats(abs(x[3])for x in known),'direction_normalized_step_px':stats(x[3]*curve.direction for x in known),'absolute_speed_px_s':stats(abs(x[3])/x[2]for x in known),'changed_pose_interval_ms':stats(changed_intervals),'source_curve_residual_by_fixed_shift_ms':residuals,'source_equivalent_pose_lag_ms':stats(lags),'source_equivalent_pose_lag_unavailable':inverse_unavailable,'prepaint_to_display_age_ms':stats(ages),'raw_gaps_ms':gaps,'raw_known_pairs':[[x[0]['t'],x[1]['t'],x[3]]for x in known],'raw_source_lags_ms':lags,'raw_prepaint_ages_ms':ages}

def combine_windows(windows):
    count_keys=['presentations','duplicates','ambiguous_poses','unknown_poses','pairs','known_pairs','unknown_pairs','held_pairs','legacy_held_pairs_lt_1e6','direction_reversal_pairs','source_equivalent_pose_lag_unavailable']
    sum_keys=['exposure_s','known_pair_time_s','unknown_pair_time_s','held_pair_time_s']
    result={k:sum(w[k]for w in windows)for k in count_keys+sum_keys}
    result.update(presentation_rate_hz=result['presentations']/result['exposure_s'],gap_ms=stats(x for w in windows for x in w['raw_gaps_ms']),long_gap_counts=[sum(w['long_gap_counts'][i]for w in windows)for i in range(3)],held_pair_fraction=result['held_pairs']/result['known_pairs']if result['known_pairs']else None,held_pair_time_fraction=result['held_pair_time_s']/result['known_pair_time_s']if result['known_pair_time_s']else None,max_consecutive_observed_hold_ms=max(w['max_consecutive_observed_hold_ms']for w in windows),source_equivalent_pose_lag_ms=stats(x for w in windows for x in w['raw_source_lags_ms']))
    known=[pair for w in windows for pair in w['raw_known_pairs']]
    result.update(absolute_step_px=stats(abs(x[2])for x in known),absolute_speed_px_s=stats(abs(x[2])/(x[1]-x[0])for x in known),prepaint_to_display_age_ms=stats(x for w in windows for x in w['raw_prepaint_ages_ms']))
    result['source_curve_residual_by_fixed_shift_ms']={}
    for shift in windows[0]['source_curve_residual_by_fixed_shift_ms']:
        rows=[w['source_curve_residual_by_fixed_shift_ms'][shift]for w in windows];num=sum(r['sum_absolute_delta_error_px']for r in rows);den=sum(r['sum_absolute_reference_travel_px']for r in rows)
        result['source_curve_residual_by_fixed_shift_ms'][shift]={'sum_absolute_delta_error_px':num,'sum_absolute_reference_travel_px':den,'travel_normalized_absolute_delta_error':num/den if den else None}
    return result

def telemetry(m,lo,hi):
    ids=[i for i,r in enumerate(m['samples'])if lo<=r['unix_ms']<=hi]
    if len(ids)<4:return {'available':False,'reason':'fewer than four phase samples','samples':len(ids)}
    assert ids==list(range(min(ids),max(ids)+1))
    rows=[m['samples'][i]for i in ids];pid=str(m['pid']);ws=str(m['windowserver_pid'])
    if any(not r['app_cpu']or pid not in r['gpu_times_ns']or ws not in r['gpu_times_ns']for r in rows):return {'available':False,'reason':'missing interior process counter','samples':len(rows)}
    if any(not r['soc']or r['soc']['gpu_energy_nj']is None or r['soc']['gpu_energy_nj']<0 for r in rows[1:]):return {'available':False,'reason':'missing/negative energy interval','samples':len(rows)}
    dt=rows[-1]['monotonic_s']-rows[0]['monotonic_s'];assert abs(sum(r['interval_s']for r in rows[1:])-dt)<1e-6
    cpu_reset=any(b['app_cpu']['cpu_s']<a['app_cpu']['cpu_s']for a,b in zip(rows,rows[1:]));gpu_reset=any(b['gpu_times_ns'][k]<a['gpu_times_ns'][k]for a,b in zip(rows,rows[1:])for k in[pid,ws])
    states=collections.Counter()
    for r in rows[1:]:states.update(r['soc']['gpu_states'])
    energy=sum(r['soc']['gpu_energy_nj']for r in rows[1:])/1e9;total=sum(states.values())
    return {'available':True,'samples':len(rows),'raw_sample_indices':[min(ids),max(ids)],'elapsed_s':dt,'whole_gpu_modeled_j':energy,'whole_gpu_modeled_w':energy/dt,'app_cpu_percent_one_core':100*(rows[-1]['app_cpu']['cpu_s']-rows[0]['app_cpu']['cpu_s'])/dt if not cpu_reset else None,'app_gpu_ms_per_wall_second':(rows[-1]['gpu_times_ns'][pid]-rows[0]['gpu_times_ns'][pid])/1e6/dt if not gpu_reset else None,'windowserver_gpu_ms_per_wall_second':(rows[-1]['gpu_times_ns'][ws]-rows[0]['gpu_times_ns'][ws])/1e6/dt if not gpu_reset else None,'gpu_state_percent':{k:100*v/total for k,v in states.items()if v and total},'gpu_residency_vs_wall_ratio':total/24e6/dt,'cpu_counter_reset':cpu_reset,'gpu_counter_reset':gpu_reset}

def run_analysis(entry,plan):
    run=Path(entry['path']);m=read(run/'measurement.json');f=lines(run/'frames.jsonl');n=lines(run/'native.jsonl');scenario=read(run/'scenario.json')
    inputs=[r for r in f if r['event']=='scenario_input'];scrolls=[r for r in n if r['event']=='scenario_scroll']
    assert len(inputs)==len(scrolls)==1442
    packet_plans=[s['packets']for s in scenario['steps']if s['do']=='scroll_packets'];assert len(packet_plans)==6 and all(len(p)==240 for p in packet_plans)
    for c,packets in enumerate(packet_plans):
        for expected,actual,row in zip(plan['packets'],packets,scrolls[2+c*240:2+(c+1)*240]):
            assert actual['at_us']==expected['at_us']and actual['native']==expected['native']
            assert actual['delta_px']==expected['delta_px']*(-1 if c%2 else 1)==row['dy']and row['dx']==0
    assert not any(r['event']=='native_scroll'for r in n)
    footer=n[-1];assert footer['event']=='capture_status'and footer['status']=='complete'and footer['dropped']==footer['marker_overflow']==0
    assert footer['records']==len([r for r in n if 'seq'in r])
    policy=[r for r in n if r['event']=='metal_update'];assert policy and all(r['minimum_hz']==r['maximum_hz']==r['preferred_hz']==0 and r['preferred_latency']==2 for r in policy)
    stages={r['op']:r for r in f if r['event']=='stage'and r.get('stage')=='input'and r.get('label')=='scenario'}
    assert all(r['detail']['op']in stages for r in inputs)
    stage_rows=[stages[r['detail']['op']]for r in inputs]
    ca_to_trace=st.median(s['at_s']-t['at_ms']/1000 for s,t in zip(scrolls,stage_rows))
    residual=[1000*(s['at_s']-t['at_ms']/1000-ca_to_trace)for s,t in zip(scrolls,stage_rows)]
    clock_unix=st.median(s['at_s']-t['unix_ms']/1000 for s,t in zip(scrolls,inputs))
    samples,markers=displayed_samples(n,plan['held_logical_tolerance_px'])
    windows_set={r['window']for r in samples};assert len(windows_set)==1
    cores=[];momentums=[];tails=[];cycle_checks=[];effective_ages=[];lateness=[];engagement=0;engagement_known=0
    core_defs=plan['momentum_core_windows'];full_defs=plan['full_momentum_windows']
    for c in range(6):
        group=scrolls[2+c*240:2+(c+1)*240];trace=stage_rows[2+c*240:2+(c+1)*240];packets=packet_plans[c];anchor=group[0]['at_s']
        start=2000 if c%2==0 else 5468;path=[start]
        for r in packets:path.append(path[-1]-r['delta_px'])
        expected=path[-1];planned_ca=[r['a']/1e9+ca_to_trace for r in trace]
        source_ca=[t-p['native']['age_us']/1e6 for t,p in zip(planned_ca,packets)]
        curve=Curve(source_ca,path[1:])
        source_known=sorted(set(path))
        measured=c>=2
        if measured:
            effective_ages.extend((r['at_s']-source)*1000 for r,source in zip(group,source_ca))
            lateness.extend((r['at_s']-planned)*1000 for r,planned in zip(group,planned_ca))
            for i,definition in enumerate(core_defs):
                # Limit inverse plateaus to this gesture, never to a later touch.
                begin_index=next(j for j,p in enumerate(packets)if p['at_us']==full_defs[i]['start_us'])
                end_index=next(j for j,p in enumerate(packets)if p['at_us']==full_defs[i]['end_us'])
                gesture_curve=Curve(source_ca[begin_index-1:end_index+1],path[begin_index:end_index+2])
                for kind,definition2,destination in [('core',definition,cores),('momentum',full_defs[i],momentums),('tail',{'start_us':full_defs[i]['end_us'],'end_us':full_defs[i]['end_us']+plan['fixed_tail_us']},tails)]:
                    lo=anchor+definition2['start_us']/1e6;hi=anchor+definition2['end_us']/1e6
                    metric=window_metrics(samples,lo,hi,gesture_curve,plan['curve_reference_shifts_ms'],plan['held_logical_tolerance_px']);metric.update(cycle=c-2,gesture=i,kind=kind)
                    destination.append(metric)
                for sample in samples:
                    if anchor+definition['start_us']/1e6<=sample['t']<=anchor+definition['end_us']/1e6 and sample['position']is not None:
                        engagement_known+=1;pos=sample['position'];j=bisect.bisect_left(source_known,pos);neighbors=source_known[max(0,j-1):j+1]
                        engagement+=bool(neighbors)and min(abs(pos-q)for q in neighbors)>.001
        cutoff=scrolls[2+(c+1)*240]['at_s']if c<5 else group[-1]['at_s']+.5
        relevant=[r for r in markers.values()if group[0]['at_s']<=r['at_s']<cutoff]
        actual_times=[r['at_s']for r in group];bounds=[];reversals=[];previous=start;direction=1 if expected>=start else -1
        for marker in relevant:
            k=bisect.bisect_right(actual_times,marker['at_s']);received=path[k];pos=marker['top']*marker['row_height']+marker['within'];low,high=sorted((start,received))
            if not low-.01<=pos<=high+.01:bounds.append({'marker':marker['seq'],'pose':pos,'bounds':[low,high]})
            if direction*(pos-previous)<-.01:reversals.append({'marker':marker['seq'],'pose':pos,'previous':previous})
            previous=pos
        displayed=[r for r in samples if group[0]['at_s']<=r['t']<cutoff and r['position']is not None]
        last_nonzero=next(r['at_s']for r in reversed(group)if r['dy'])
        reached=[r for r in displayed if r['t']>=last_nonzero and abs(r['position']-expected)<=.01]
        last=displayed[-1]if displayed else None
        cycle_checks.append({'cycle':c,'measured':measured,'start_expected':start,'end_expected':expected,'last_displayed_pose':last['position']if last else None,'endpoint_error_px':last['position']-expected if last else None,'endpoint_within_tolerance':bool(last and abs(last['position']-expected)<=.01),'first_endpoint_after_final_nonzero_dispatch_ms':(reached[0]['t']-last_nonzero)*1000 if reached else None,'received_path_bound_violations':bounds,'marker_direction_reversals':reversals,'marker_count':len(relevant),'displayed_pose_count':len(displayed)})
    assert len(cores)==len(momentums)==len(tails)==8
    combined=combine_windows(cores)
    assert math.isclose(combined['exposure_s'],plan['core_exposure_s_per_run'],abs_tol=1e-8)
    phase={state:{r['detail']['name']:r for r in f if r['event']=='scenario_phase'and r['detail']['state']==state}for state in['begin','end']}
    first=phase['begin']['replay-0'];last=phase['end']['replay-3'];ready=next(r for r in f if r['event']=='scenario_ready')
    lo=first['unix_ms']+300;hi=last['unix_ms']-300
    arm=next(r for r in n if r['event']=='capture_armed')['ca_anchor_s'];deadline=arm+n[0]['duration_s']
    capture_coverage={'capture_start_ca_s':arm,'capture_deadline_ca_s':deadline,'idle_after_end_ca_s':last['unix_ms']/1000+clock_unix+12.5,'all_core_windows_inside':all(arm<w['lo_ca_s']<w['hi_ca_s']<deadline for w in cores),'idle_after_inside':arm<last['unix_ms']/1000+clock_unix+2.5<last['unix_ms']/1000+clock_unix+12.5<deadline}
    assert capture_coverage['all_core_windows_inside']and capture_coverage['idle_after_inside']
    selected=[r for r in n if r['event']=='submit_begin'and lo/1000+clock_unix<=r['at_s']<=hi/1000+clock_unix]
    presentation={(r['window'],r['call']):r for r in n if r['event']=='presented'};completed={(r['window'],r['call']):r for r in n if r['event']=='gpu_completed'}
    outcomes=collections.Counter(submissions=len(selected),missing_present_callback=0,zero_or_not_presented=0,missing_gpu_callback=0,gpu_errors=0)
    for r in selected:
        key=(r['window'],r['call']);p=presentation.get(key);g=completed.get(key)
        outcomes['missing_present_callback']+=p is None;outcomes['zero_or_not_presented']+=bool(p is not None and(not p['did_present']or p['presented_s']<=0));outcomes['missing_gpu_callback']+=g is None;outcomes['gpu_errors']+=bool(g is not None and g['status']!=4)
    full_selected=[r for r in samples if lo/1000+clock_unix<=r['t']<=hi/1000+clock_unix];full_gaps=[(b['t']-a['t'])*1000 for a,b in zip(full_selected,full_selected[1:])]
    t={'idle_before':telemetry(m,ready['unix_ms']+2500,phase['begin']['prefill']['unix_ms']-800),'scrolling':telemetry(m,lo,hi),'idle_after':telemetry(m,last['unix_ms']+2500,last['unix_ms']+12500)}
    observer=100*(m['observer_cpu_after']['cpu_s']-m['observer_cpu_before']['cpu_s'])/(m['end_unix_s']-m['start_unix_s'])
    input_stages=[r['at_ms']-r['a']/1e6 for r in stage_rows[482:]]
    submit=stats(r['duration_ms']for r in f if r['event']=='submit'and first['at_ms']+300<=r['start_ms']<=last['at_ms']-300)
    wakes={phase_name:sum(r['event']=='wake'and bounds[0]<=r['at_s']<=bounds[1]for r in n)for phase_name,bounds in {'full_scrolling':(lo/1000+clock_unix,hi/1000+clock_unix),'idle_after':(last['unix_ms']/1000+clock_unix+2.5,last['unix_ms']/1000+clock_unix+12.5)}.items()}
    return {'ordinal':entry['ordinal'],'condition':entry['condition'],'path':str(run),'binary_sha256':m['build_binary_sha256'],'scenario_sha256':sha(run/'scenario.json'),'core':combined,'cores':cores,'full_momentum':combine_windows(momentums),'full_momentum_windows':momentums,'fixed_tails':combine_windows(tails),'fixed_tail_windows':tails,'full_phase_descriptive':{'presentation_rate_hz':len(full_selected)/((hi-lo)/1000),'presentations':len(full_selected),'gap_ms':stats(full_gaps)},'submission_outcomes_full_phase':dict(outcomes),'submit_elapsed_including_drawable_acquisition_ms':submit,'wake_request_counts':wakes,'wake_request_scope':'Requests only, not executions/frames/CPU cost.','source_timestamp_lateness_ms':stats(lateness),'effective_source_age_ms':stats(effective_ages),'effective_age_over_100ms_packets':sum(v>100 for v in effective_ages),'measured_input_stages':len(input_stages),'traced_input_lateness_ms':stats(input_stages),'clock_mapping':{'ca_minus_trace_s':ca_to_trace,'ca_minus_unix_s':clock_unix,'trace_residual_ms':stats(residual),'max_abs_trace_residual_ms':max(map(abs,residual))},'correctness':{'all_cycle_endpoints':all(r['endpoint_within_tolerance']for r in cycle_checks),'no_received_path_bound_violation':all(not r['received_path_bound_violations']for r in cycle_checks),'no_marker_direction_reversal':all(not r['marker_direction_reversals']for r in cycle_checks)},'cycles':cycle_checks,'engagement':{'between_discrete_source_endpoint_presentations':engagement,'known_core_poses':engagement_known,'tolerance_px':.001,'scope':'Witness of interpolation, not physical effectiveness/new information.'},'telemetry':t,'observer_parent_cpu_percent_one_core':observer,'capture_records':footer['records'],'capture_capacity':n[0]['max_records'],'capture_coverage':capture_coverage,'environment':m['environment'],'verification':m['verification']}

def get(r,path):
    for k in path:
        if not isinstance(r,dict)or k not in r:return None
        r=r[k]
    return r

def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('--plan',type=Path,default=HERE/'input-plan.json');p.add_argument('--allow-partial',action='store_true');args=p.parse_args()
    manifest=read(args.manifest);plan=read(args.plan);entries=[r for r in manifest['runs']if r['valid']]
    if not args.allow_partial and not manifest.get('pilot'):
        assert len(entries)==8 and [r['ordinal']for r in entries]==list(range(1,9))and [r['condition']for r in entries]==plan['order']
    runs=[run_analysis(e,plan)for e in entries]
    assert len({r['binary_sha256']for r in runs})==1 and len({r['scenario_sha256']for r in runs})==1
    metrics={'core_hz':['core','presentation_rate_hz'],'core_gap_p95_ms':['core','gap_ms','p95'],'core_gap_p99_ms':['core','gap_ms','p99'],'core_max_gap_ms':['core','gap_ms','max'],'held_known_pair_fraction':['core','held_pair_fraction'],'held_known_time_fraction':['core','held_pair_time_fraction'],'max_observed_hold_ms':['core','max_consecutive_observed_hold_ms'],'source_equivalent_pose_lag_median_ms':['core','source_equivalent_pose_lag_ms','median'],'source_equivalent_pose_lag_p95_ms':['core','source_equivalent_pose_lag_ms','p95'],'curve_delta_error_shift0':['core','source_curve_residual_by_fixed_shift_ms','0','travel_normalized_absolute_delta_error'],'curve_delta_error_shift12_5':['core','source_curve_residual_by_fixed_shift_ms','12.5','travel_normalized_absolute_delta_error'],'app_cpu_percent_one_core':['telemetry','scrolling','app_cpu_percent_one_core'],'app_gpu_ms_per_wall_second':['telemetry','scrolling','app_gpu_ms_per_wall_second'],'whole_gpu_modeled_w':['telemetry','scrolling','whole_gpu_modeled_w'],'observer_parent_cpu_percent_one_core':['observer_parent_cpu_percent_one_core']}
    summaries={c:{name:stats(get(r,path)for r in runs if r['condition']==c)for name,path in metrics.items()}for c in['off','on']}
    pairs=[]
    if len(runs)==8:
        for i in range(0,8,2):
            off=next(r for r in runs[i:i+2]if r['condition']=='off');on=next(r for r in runs[i:i+2]if r['condition']=='on');contrast={}
            for name,path in metrics.items():
                a=get(off,path);b=get(on,path);contrast[name]=b-a if a is not None and b is not None else None
            pairs.append({'ordinals_off_on':[off['ordinal'],on['ordinal']],'on_minus_off':contrast})
    report={'protocol_sha256':sha(HERE/'PROTOCOL.md'),'plan_sha256':sha(args.plan),'analyzer_sha256':sha(Path(__file__)),'manifest':str(args.manifest),'scope':'Same installed instrumented binary; synthetic metadata replay, not physical hardware input or user feel. Primary momentum-only cadence/pose cores; energy uses broader scrolling phase. Logical pose is not raster displacement. Deliberate12.5ms source delay disclosed; equal-output energy efficiency not inferred.','pilot':manifest.get('pilot',False),'conditions':summaries,'paired_contrasts':pairs,'invalid_attempts':[r for r in manifest['runs']if not r['valid']],'runs':runs}
    output=HERE/('analysis-'+args.manifest.parent.name+'.json');output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(output),'conditions':summaries,'runs':[{'ordinal':r['ordinal'],'condition':r['condition'],'core_hz':r['core']['presentation_rate_hz'],'held_fraction':r['core']['held_pair_fraction'],'source_lag_median':r['core']['source_equivalent_pose_lag_ms']['median'],'correctness':r['correctness'],'engagement':r['engagement'],'records':r['capture_records']}for r in runs]},indent=2))

if __name__=='__main__':main()
