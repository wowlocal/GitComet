#!/usr/bin/env python3
"""Portable numeric replay only; saved JSON/JSONL, no acquisition or private config."""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode=True

ANALYZER_SHA256='59bb74d9c4e9da0f2119405f42d207817a187bcaf1bb6bd82e3872ef6193a4d4'
PROTOCOL_SHA256='45df462cfdc90c7c4351836ebb67b52650e8247113252c3fb92e23708fa9c8a9'
COLLECTOR_SHA256='45a5d38465f787ea818bc89fc42b9cb19d972420880c81cbd8962982f2fe53cc'
BINDING_SHA256='a02c5d1312ebca2ab422864bb5d7e1114a744888995d4c0d8556f4530592ebd5'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def checked(root,relative,expected):
    path=root/relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Input escapes packet')
    raw=path.read_bytes()
    if digest(raw)!=expected:raise ValueError('Input checksum mismatch: '+relative)
    return raw


def inventory(root):
    entries={}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        value,name=line.split('  ',1)
        if name in entries or len(value)!=64:raise ValueError('Invalid/duplicate inventory row')
        entries[name]=value
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    if actual!=set(entries):raise ValueError('Packet inventory changed')
    for name,value in entries.items():checked(root,name,value)
    return entries


def csv_rows(result):
    for run in result['all_attempts']:
        for window in ('idle_before','active_core','idle_after'):
            w=run['windows'][window]
            for name,component in w['components'].items():
                yield {'slot':run['slot'],'condition':run['condition'],'window':window,'component':name,
                       'raw_delta_nJ':component['raw_nj'],'exposure_ns_x2':w['exposure_ns_x2'],
                       'exposure_seconds':w['exposure_seconds'],'raw_J':component['raw_J'],
                       'mean_model_W':component['mean_model_W'],'normalized_J60':component['normalized_J60'],
                       'secondary_active_minus_exposure_weighted_still_J60':run['windows']['secondary_active_minus_exposure_weighted_still_J60'].get(name,'')}


def write_csv(result,path):
    rows=list(csv_rows(result))
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def reproduce(root,output):
    root=root.resolve();output=output.absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(root):raise ValueError('NEW output outside packet required')
    entries=inventory(root)
    raw=checked(root,'source/analyze-frozen.py',ANALYZER_SHA256)
    spec=importlib.util.spec_from_file_location('frozen_numeric_analysis',root/'source/analyze-frozen.py')
    a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    manifest=a.decode(checked(root,'manifest-public.json',entries['manifest-public.json']))
    protocol=a.decode(checked(root,'protocol-clpc-v1.json',PROTOCOL_SHA256))
    expected=a.decode(checked(root,'analysis-public.json',entries['analysis-public.json']))
    a.need(manifest['schema']=='public-energy-numeric-manifest-v1' and manifest['order']==a.ORDER==protocol['order'],'Order/schema changed')
    a.need(len(manifest['runs'])==16 and not manifest['series_stopped'],'Expected exact completed16-run series')
    a.need(manifest['analysis_source_sha256']==ANALYZER_SHA256 and manifest['protocol_sha256']==PROTOCOL_SHA256,'Source binding changed')
    a.need(protocol['schema']==a.V8_PROTOCOL and protocol['adjacent_pairs']==[[i,i+1] for i in range(1,17,2)],'Protocol/pairs changed')
    a.need({app:row['binary_sha256'] for app,row in protocol['conditions'].items()}==a.APP_SHA256,'App build identity changed')
    a.need(manifest['sources']['collector_sha256']==COLLECTOR_SHA256 and manifest['sources']['binding_sha256']==BINDING_SHA256,'Collector/binding source pin changed')
    pairs,complete,plan=a.select_pairs(manifest['runs'],manifest['series_stopped'])
    runs=[];identities=None
    for entry in manifest['runs']:
        a.need(entry['valid'] is True and entry['status']=='finished' and entry['failures']==[] and not entry['fatal_series_stop'],'Unexpected incomplete attempt')
        a.need(type(entry['driver_origin_monotonic_ns']) in (int,float) and math.isfinite(entry['driver_origin_monotonic_ns']) and entry['driver_origin_monotonic_ns']>=0 and entry['binary_sha256']==a.APP_SHA256[entry['condition']],'Origin/build metadata changed')
        raw=checked(root,entry['energy_file'],entry['energy_sha256'])
        a.need(raw.endswith(b'\n') and all(raw.splitlines()),'Truncated/blank raw JSONL')
        rows=[a.decode(line) for line in raw.splitlines()]
        samples=a.validate_energy(rows,manifest['sources']['collector_sha256'],entry['driver_origin_monotonic_ns'],manifest['sources']['binding_sha256'])
        if identities is None:identities=rows[0]['metadata']
        a.need(identities==rows[0]['metadata'],'Series channel/provider identity changed')
        observers=entry['observers']
        for kind in ('runner_parent','collector'):
            a.need(all(type(observers[kind][key]) is int and observers[kind][key]>=0 for key in ('observer_cpu_ns','observer_elapsed_ns')),'Invalid observer metadata')
        for key in ('observer_cpu_ns','observer_elapsed_ns'):
            a.need(observers['collector'][key]==rows[-1][key],'Collector observer/raw mismatch')
        driver=observers['native_driver']
        a.need(driver['cpu_end_ns']>=driver['cpu_start_ns']>=0 and driver['cpu_ns']==driver['cpu_end_ns']-driver['cpu_start_ns'],'Driver ownCPU arithmetic')
        a.need(a.native_stamp(driver['observer_start'])<=entry['driver_origin_monotonic_ns']<a.native_stamp(driver['observer_end']),'Driver metadata scope/origin')
        runs.append({key:entry[key] for key in ('slot','original_ordinal','condition','valid','failures','fatal_series_stop')})
        runs[-1].update(observers=observers,windows=a.analyze_windows(samples),trace=[{
            'offset_s':row['offset_s'],**{name:row['delta_from_previous']['channels'][name]['delta_nj']/row['delta_from_previous']['midpoint_exposure_ns'] for name in ('CPU Energy','GPU Energy')}} for row in samples[1:]])
    post=manifest['post_output_geometry'];post_passed=True
    for app in ('gitcomet','fork'):
        record=post[app]
        post_passed=post_passed and record['passed'] is True and record['repeat_count']>=2 and record['motion'] is True and record['no_edge'] is True and record['return_error_rows']<=1 and record['distance_repeat_fraction']<=.10
    complete=complete and post_passed;indexed={row['slot']:row for row in runs};primary={};secondary={}
    for component in a.COMPONENTS:
        values=[];still=[]
        for pair in pairs:
            values.append({e['condition']:indexed[e['slot']]['windows']['active_core']['components'][component]['normalized_J60'] for e in pair})
            still.append({e['condition']:indexed[e['slot']]['windows']['secondary_active_minus_exposure_weighted_still_J60'][component] for e in pair})
        gc,fork=([v[app] for v in values] for app in ('gitcomet','fork'))
        primary[component]=a.paired(gc,fork,complete)
        if component=='CPU Energy':primary[component]['ratio']=a.paired_ratio(gc,fork)
        secondary[component]=a.paired([v['gitcomet'] for v in still],[v['fork'] for v in still],complete)
    a.apply_scale_robust_gate(primary);a.apply_scale_robust_gate(secondary)
    actual=dict(expected,all_attempts=runs,complete_eight_pairs=complete,selected_pairs=[[e['slot'] for e in pair] for pair in pairs],
                replacement_plan=plan,paired_primary_normalized_J60=primary,paired_secondary_active_minus_weighted_still_J60=secondary,
                post_characterization_passed=post_passed,output_characterization=post)
    a.need(actual==expected,'Recomputed numeric result differs from analysis-public.json')
    # Compare the canonical CSV before writing a fresh independent output directory.
    import io
    stream=io.StringIO(newline='');rows=list(csv_rows(actual));writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    a.need(stream.getvalue().encode()==(root/'all-runs.csv').read_bytes(),'CSV differs from computed endpoints/exposures')
    output.mkdir(mode=0o700)
    (output/'analysis-recomputed.json').write_text(json.dumps(actual,indent=2,allow_nan=False)+'\n')
    write_csv(actual,output/'all-runs.csv');a.graphs(actual,output)
    # Run the exact presentation-only chart source against the newly recomputed JSON.
    checked(root,'source/make-component-summary.py',manifest['sources']['component_chart_sha256'])
    import runpy
    old_argv=sys.argv
    try:
        sys.argv=['make-component-summary.py','--analysis',str(output/'analysis-recomputed.json'),'--output',str(output/'component-summary.png')]
        runpy.run_path(str(root/'source/make-component-summary.py'),run_name='__main__')
    finally:sys.argv=old_argv
    report={'status':'PASS','raw_runs':16,'pairs':8,'raw_counter_bytes_and_source_hashes_verified':True,'exact_numeric_result_and_csv_parity':True,
            'scope':'Numeric reproducibility only. Private acquisition, native event logs, environment/profile/cleanup controls and video witnesses are not rerun or independently established by this wrapper.'}
    (output/'reproduction.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    print(json.dumps(reproduce(Path(__file__).resolve().parent,args.output),indent=2))


if __name__=='__main__':main()
