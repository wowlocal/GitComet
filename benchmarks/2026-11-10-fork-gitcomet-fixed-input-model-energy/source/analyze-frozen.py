#!/usr/bin/env python3
"""Saved files only. No collector/runner imports, FFI, subprocess or app access."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

ORDER = ['gitcomet', 'fork', 'fork', 'gitcomet', 'fork', 'gitcomet', 'gitcomet', 'fork'] * 2
WINDOWS = {'idle_before': (5, 15), 'active_core': (35, 95), 'idle_after': (115, 125)}
FACTORS = {'CPU Energy': 1, 'GPU Energy': 1, 'ANE0': 1, 'CLPC GPU Energy': 1}
COMPONENTS = ('CPU Energy', 'GPU Energy', 'CPU+GPU named sum')
APP_SHA256 = {'gitcomet': 'f3172102f1b0b9722424ea991ee229a51396ee43a87cffaabcd4adc36b9455c3',
              'fork': '5e2a769758b352aad2e66d1c8607642b1d3b9f37b09475694cdfed9c3eedf8e1'}
V8_PROTOCOL = 'energy-identical-pixel-event-stream-v9-clpc'
V5_PROTOCOL = 'energy-identical-pixel-event-stream-v5-ioreport'
V8_ROUTE = 'CGEvent.post cgSessionEventTap plus one CGWarpMouseCursorPosition; no delivery acknowledgement'
T95 = {1: 12.706204736432095, 2: 4.302652729696142, 3: 3.182446305284263,
       4: 2.7764451051977987, 5: 2.570581835636314, 6: 2.4469118487916806,
       7: 2.3646242515927844}


def need(ok, text):
    if not ok:
        raise ValueError(text)


def integer(value):
    need(type(value) is int, 'Expected exact integer, not float/bool')
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    obj = {}
    for k, v in pairs:
        need(k not in obj, 'Duplicate JSON key')
        obj[k] = v
    return obj


def decode(raw):
    def finite(text):
        value = float(text)
        need(math.isfinite(value), 'Nonfinite JSON float')
        return value
    return json.loads(raw, object_pairs_hook=unique,
                      parse_float=finite,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def midpoint(mark):
    lo, hi = integer(mark['monotonic_before_ns']), integer(mark['monotonic_after_ns'])
    need(0 <= hi - lo <= 50_000_000, 'Invalid paired clock bracket')
    integer(mark['unix_ns'])
    return (lo + hi) // 2


def bounds(sample):
    lo = integer(sample['call_before']['monotonic_before_ns'])
    hi = integer(sample['call_after']['monotonic_after_ns'])
    need(0 <= hi - lo <= 50_000_000, 'Native call span exceeds bound')
    need(sample['call_before']['monotonic_after_ns'] <= sample['call_after']['monotonic_before_ns'],
         'Reordered acquisition brackets')
    return lo, hi


def metadata_contract(meta, name):
    """Pure exact local map; assigned CLPC units are not API unit evidence."""
    integer_fields = ('format', 'unit_code', 'driver_id', 'channel_id')
    if not all(type(meta.get(k)) is int for k in integer_fields):
        raise ValueError('Noninteger model identity')
    common = {'name': name, 'format': 1, 'unit': 'nJ',
              'unit_code': (3 << 56) | (118 << 32)}
    if name == 'GPU Energy':
        expected = dict(common, native_name='GPU Energy', group='Energy Model', subgroup=None,
                        driver_id=4294969919, channel_id=76202472785753,
                        source_kind='Native Energy Model GPU',
                        unit_origin='Native legacy channel metadata; no constructed descriptor')
    else:
        native, report = {'CPU Energy': ('CPU Energy', 0x00000010d3ab60bb),
                          'ANE0': ('ANE', 0x000000188c0f1c59),
                          'CLPC GPU Energy': ('GPU Energy', 0x0000001927cd4ce5)}[name]
        expected = dict(common, native_name=native, group='CLPC', subgroup='Energy Counters',
                        driver_id=0x1000005ce, channel_id=report,
                        source_kind='AppleCLPC assigned descriptor',
                        unit_origin='Assigned nJ/name descriptor from macmonv0.11.0 firmware-derived mapping; not independent unit proof')
    if not all(meta.get(k) == v for k, v in expected.items()):
        raise ValueError('Exact CLPC/native GPU metadata/provenance mismatch')
    return True


def metadata(meta, name):
    return metadata_contract(meta,name)


def primary_liveness(samples):
    """Per-run instrument liveness only; still GPU/ANE may legitimately be zero."""
    indexed = {row['offset_s']: row['sample']['counters'] for row in samples}
    for start, end in ((5, 15), (35, 95), (115, 125)):
        if indexed[end]['CPU Energy']['raw'] - indexed[start]['CPU Energy']['raw'] <= 0:
            raise ValueError('CPU Energy stalled in fixed window ' + str(start) + '..' + str(end))
    for name in ('GPU Energy', 'CLPC GPU Energy'):
        if indexed[95][name]['raw'] - indexed[35][name]['raw'] <= 0:
            raise ValueError(name + ' stalled in active fixed window 35..95')


def validate_energy(rows, source_hash, driver_origin, binding_hash):
    need(len(rows) == 127, 'Expected header,125 snapshots,footer')
    head, foot, samples = rows[0], rows[-1], rows[1:-1]
    need(head['kind'] == 'header' and head['schema'] == 'ioreport-clpc-energy-v1'
         and head['mode'] == 'main' and head['source_sha256'] == source_hash, 'Collector identity/schema')
    need(foot['kind'] == 'footer' and foot['complete'] is True and foot['reason'] is None
         and foot['snapshots'] == foot['expected_snapshots'] == 125, 'Incomplete counter capture')
    need(head['binding_sha256'] == binding_hash, 'CLPC binding identity mismatch')
    provenance=head['binding_provenance']
    need(provenance['os_version']=='27.2' and provenance['os_build']=='26B123' and provenance['clpc_bundle']=='com.apple.driver.AppleT6050CLPC' and provenance['clpc_registry_id']==0x1000005ce and provenance['upstream_commit']=='08653ddeb3c1206b6cc35d5a2bb442b4c64ad810','CLPC firmware/OS/source provenance mismatch')
    origin = integer(head['origin_monotonic_ns'])
    need(abs(origin - driver_origin) <= 1000, 'Native/collector origins differ')
    need(head['primary_names'] == ['CPU Energy', 'GPU Energy']
         and head['snapshot_offsets_s'] == list(range(3, 128))
         and head['windows_s'] == {k: list(v) for k, v in WINDOWS.items()}
         and head['max_call_ns'] == head['max_start_lateness_ns'] == 50_000_000
         and 'mach_absolute_time' in head['monotonic_implementation'], 'Changed clock/window contract')
    expected_specs = {name: {'unit': 'nJ', 'unit_code': (3 << 56) | (118 << 32), 'to_nj': factor} for name, factor in FACTORS.items()}
    need(head['specs'] == expected_specs and set(head['metadata']) == set(FACTORS), 'Changed selected specs')
    anchor = head['stamp']['unix_ns'] - midpoint(head['stamp'])
    need(origin <= midpoint(head['stamp']) < origin + 3_000_000_000, 'Collector anchor outside startup')
    identities = {name: head['metadata'][name]['metadata'] for name in FACTORS}
    for i, row in enumerate(samples):
        need(row['kind'] == 'snapshot' and row['index'] == i and row['offset_s'] == i + 3,
             'Missing/duplicate/reordered snapshot')
        deadline = origin + (i + 3) * 1_000_000_000
        need(row['scheduled_monotonic_ns'] == deadline, 'Changed snapshot deadline')
        sample = row['sample']; lo, hi = bounds(sample)
        need(0 <= lo - deadline <= 50_000_000, 'Late/early snapshot')
        for mark in (sample['call_before'], sample['call_after']):
            need(abs(mark['unix_ns'] - midpoint(mark) - anchor) <= 50_000_000, 'Clock drift/discontinuity')
        need(set(sample['counters']) == set(FACTORS), 'Missing/extra counter; no zero substitution')
        for name, factor in FACTORS.items():
            counter = sample['counters'][name]; meta = counter['metadata']; metadata(meta, name)
            need(meta == identities[name], 'Provider/channel identity changed')
            value = integer(counter['raw']); need(value >= 0, 'Negative cumulative counter')
            if i:
                previous = samples[i-1]['sample']['counters'][name]['raw']
                delta = row['delta_from_previous']['channels'][name]
                need(value >= previous and delta == {'metadata': meta, 'before_raw': previous,
                     'after_raw': value, 'api_delta_raw': value-previous,
                     'delta_nj': (value-previous)*factor}, 'Reset/API/direct delta disagreement')
        if i:
            prior = samples[i-1]['sample']; low0, high0 = bounds(prior); d = row['delta_from_previous']
            need(set(d['channels']) == set(FACTORS), 'Delta channel set changed')
            need(d['midpoint_exposure_ns'] == (lo+hi-low0-high0)//2 > 0
                 and d['exposure_bounds_ns'] == [lo-high0, hi-low0], 'Delta exposure mismatch')
            total = sum(d['channels'][n]['delta_nj'] for n in ('CPU Energy', 'GPU Energy'))
            need(d['primary_sum_nj'] == total and math.isclose(d['primary_sum_j'], total/1e9, rel_tol=1e-12, abs_tol=1e-12)
                 and d['ane0_secondary_nj'] == d['channels']['ANE0']['delta_nj'], 'Delta conversion/sum mismatch')
        else:
            need('delta_from_previous' not in row, 'First snapshot has unexpected delta')
    for key in ('observer_cpu_ns', 'observer_elapsed_ns'):
        need(integer(foot[key]) >= 0, 'Invalid observer accounting')
    primary_liveness(samples)
    return samples


def window(samples, start, end):
    indexed = {r['offset_s']: r['sample'] for r in samples}
    a, b = indexed[start], indexed[end]; low0, high0 = bounds(a); low1, high1 = bounds(b)
    # Twice the midpoint exposure is an exact integer; do not round sub-ns half units.
    exposure_x2 = low1 + high1 - low0 - high0
    need(low1 - high0 > 0 and exposure_x2 > 0, 'Nonpositive endpoint exposure')
    ns = {n: (b['counters'][n]['raw'] - a['counters'][n]['raw']) * FACTORS[n] for n in FACTORS}
    ns['CPU+GPU named sum'] = ns['CPU Energy'] + ns['GPU Energy']
    return {'offsets_s': [start, end], 'exposure_ns_x2': exposure_x2,
            'exposure_seconds': exposure_x2 / 2e9, 'exposure_bounds_ns': [low1-high0, high1-low0],
            'endpoint_brackets_ns': [[low0, high0], [low1, high1]],
            'components': {n: {'raw_nj': v, 'raw_J': v/1e9, 'mean_model_W': 2*v/exposure_x2,
                                'normalized_J60': 120*v/exposure_x2} for n, v in ns.items()}}


def analyze_windows(samples):
    out = {name: window(samples, *limits) for name, limits in WINDOWS.items()}
    a, b, active = out['idle_before'], out['idle_after'], out['active_core']
    # Sum energy / sum actual exposures, not an unweighted mean of two rates.
    out['secondary_active_minus_exposure_weighted_still_J60'] = {
        name: active['components'][name]['normalized_J60'] -
        120*(a['components'][name]['raw_nj']+b['components'][name]['raw_nj']) /
        (a['exposure_ns_x2']+b['exposure_ns_x2']) for name in (*COMPONENTS, 'ANE0')}
    return out


def summary(values):
    return {'n': len(values), 'mean': statistics.mean(values), 'median': statistics.median(values),
            'range': [min(values), max(values)],
            'MAD': statistics.median(abs(x-statistics.median(values)) for x in values)} if values else None


def paired(gc, fork, complete):
    diffs = [b-a for a, b in zip(gc, fork)]
    out = {'gitcomet': summary(gc), 'fork': summary(fork), 'fork_minus_gitcomet': summary(diffs),
           'differences': diffs, 'ci95': None, 'directional_gate_passed': False}
    if len(diffs) >= 2:
        m = statistics.mean(diffs); half = T95[len(diffs)-1]*statistics.stdev(diffs)/math.sqrt(len(diffs))
        out['ci95'] = [m-half, m+half]
        threshold = max(out['gitcomet']['MAD'], out['fork']['MAD'])
        out['larger_within_app_MAD'] = threshold
        out['directional_gate_passed'] = bool(complete and len(diffs) == 8 and
            (m-half > 0 or m+half < 0) and abs(statistics.median(diffs)) > threshold)
    return out


def paired_ratio(gc, fork):
    if not gc or any(a <= 0 or b <= 0 for a,b in zip(gc,fork)):
        return {'available':False,'reason':'Missing/nonpositive paired value; no pair omitted'}
    logs=[math.log(b/a) for a,b in zip(gc,fork)]
    mean=statistics.mean(logs);ci=None
    if len(logs)>=2:
        half=T95[len(logs)-1]*statistics.stdev(logs)/math.sqrt(len(logs))
        ci=[math.exp(mean-half),math.exp(mean+half)]
    return {'available':True,'n':len(logs),'fork_over_gitcomet':[b/a for a,b in zip(gc,fork)],
            'geometric_mean':math.exp(mean),'ci95_log_paired':ci,
            'scope':'Ratio independent of a common positive CPU-unit scale; not physical energy calibration'}


def apply_scale_robust_gate(results):
    cpu,gpu,total=(results[k] for k in COMPONENTS)
    c,g=cpu['ci95'],gpu['ci95']
    same_sign=bool(c and g and ((c[0]>0 and g[0]>0) or (c[1]<0 and g[1]<0)))
    total['directional_gate_before_cpu_unit_limit']=total['directional_gate_passed']
    total['scale_robust_component_direction']=bool(cpu['directional_gate_passed'] and gpu['directional_gate_passed'] and same_sign)
    total['directional_gate_passed']=bool(total['directional_gate_passed'] and total['scale_robust_component_direction'])
    total['unit_limit']='Sum conditional on macmon CPU nJ mapping. Direction requires both component intervals exclude0 with same sign and individual predeclared gates; otherwise sum depends on unverified CPU scale.'


def select_pairs(entries, stopped=False):
    need(len(entries) <= 20, 'More than20 attempts')
    for i, e in enumerate(entries):
        need(e['slot'] == i+1 and type(e['valid']) is bool, 'Nonserial/ambiguous attempts')
        need(e['status'] in ('finished', 'failed') and isinstance(e['failures'], list), 'Unfinished attempt')
        need((e['status'] == 'finished' and not e['failures']) == e['valid'], 'Validity/failure conflict')
        if i < 16: need(e['original_ordinal'] == i+1, 'Changed main order')
        need(e['condition'] == ORDER[e['original_ordinal']-1], 'Condition/order mismatch')
    failed = [i for i in range(1, min(len(entries), 16), 2)
              if not all(entries[j-1]['valid'] for j in (i, i+1))]
    plan = [j for i in failed for j in (i, i+1)]
    need(len(entries) <= 16 or len(failed) <= 2, 'Too many failed pairs for replacements')
    need([e['original_ordinal'] for e in entries[16:]] == plan[:max(0,len(entries)-16)], 'Changed replacement pair/order')
    selected = []
    for first in range(1, 17, 2):
        candidates = entries[first-1:first+1]
        if len(candidates) < 2: continue
        if not all(e['valid'] for e in candidates):
            candidates = [e for e in entries[16:] if e['original_ordinal'] in (first, first+1)]
        if len(candidates) == 2 and all(e['valid'] and not e.get('fatal_series_stop',False) for e in candidates):
            selected.append(candidates)
    complete = len(entries) >= 16 and len(selected) == 8 and not stopped
    return selected, complete, plan


class Saved:
    def __init__(self, root, lock):
        self.root = root.resolve(); self.lock = lock; self.used = {}

    def raw(self, relative):
        p = self.root / relative
        need(not p.is_symlink() and p.resolve().is_relative_to(self.root), 'Input path escapes saved series')
        raw = p.read_bytes(); expected = self.lock['files'][relative]
        need(sha(raw) == expected, 'Saved input hash mismatch: '+relative)
        self.used[relative] = expected
        return raw

    def json(self, relative): return decode(self.raw(relative))

    def lines(self, relative):
        raw = self.raw(relative); need(raw.endswith(b'\n'), 'Truncated JSONL')
        need(all(line for line in raw.splitlines()), 'Blank JSONL row')
        return [decode(line) for line in raw.splitlines()]


def native_stamp(mark):
    for key in ('monotonic_ns', 'unix_s', 'pair_bracket_ns'):
        need(type(mark[key]) in (int, float) and math.isfinite(mark[key]), 'Invalid native scope clock')
    need(mark['monotonic_ns'] >= 0 and 0 <= mark['pair_bracket_ns'] <= 50e6, 'Native scope bracket')
    return mark['monotonic_ns']


def driver_metadata(rows, entry, cfg, description, reference):
    head = rows[0]; point = cfg['points'][entry['condition']]
    need(description['kind'] == 'target_description' and description['schema'] == 'native-scroll-target-description-v1'
         and description['no_warp_or_posts'] is True and description['pid'] == description['frontmost_pid'] == entry['pid']
         and [description['x'], description['y']] == point, 'Fresh target description identity mismatch')
    windows = reference['target_windows']
    need(len(windows) == 1 and windows[0]['alpha'] == 1 and windows[0]['onscreen'] is True,
         'Frozen reference is not one opaque onscreen window')
    rect = windows[0]['bounds']; window = description['window']
    need(set(rect) == {'X','Y','Width','Height'} and
         all(type(v) in (int,float) and math.isfinite(v) for v in rect.values())
         and rect['Width'] > 0 and rect['Height'] > 0, 'Invalid frozen rectangle')
    need(integer(window['id']) > 0 and window == {'id':window['id'], 'x':rect['X'], 'y':rect['Y'],
         'width':rect['Width'], 'height':rect['Height']} and head['window_id'] == window['id']
         and head['frozen_window'] == window and head['route'] == V8_ROUTE,
         'Native route/window no longer matches fresh description and frozen reference')
    need(native_stamp(description['stamp']) <= head['origin_monotonic_ns'], 'Target described after input origin')
    restored = [r for r in rows if r['kind'] == 'cursor_restoration']
    accounting = [r for r in rows if r['kind'] == 'driver_accounting']
    need(len(restored) == len(accounting) == 1, 'Missing/duplicate native completion metadata')
    restored = restored[0]; record = accounting[0]
    need(restored['run_id'] == head['run_id'] and restored['attempted'] is True
         and type(restored['result_code']) is int and restored['result_code'] == 0,
         'Cursor restoration did not complete successfully')
    need(record['run_id'] == head['run_id'], 'Driver CPU record run identity mismatch')
    for key in ('cpu_start_ns','cpu_end_ns','cpu_ns'):
        need(integer(record[key]) >= 0, 'Invalid own driver CPU accounting')
    need(record['cpu_end_ns'] >= record['cpu_start_ns'] and
         record['cpu_ns'] == record['cpu_end_ns'] - record['cpu_start_ns'], 'Own driver CPU arithmetic mismatch')
    start = native_stamp(record['observer_start']); end = native_stamp(record['observer_end'])
    restore = native_stamp(restored['stamp']); complete = native_stamp(rows[-1]['stamp'])
    need(start <= head['origin_monotonic_ns'] < head['finish_monotonic_ns'] <= restore <= end <= complete,
         'Driver CPU scope does not cover timed phases/final restoration')
    need(rows[-1]['run_id'] == head['run_id'] and isinstance(record['scope'], str), 'Completion identity/scope mismatch')
    # Accounting is metadata only: no CPU amount/rate selection, subtraction or energy conversion.
    return record


def driver(rows, entry, cfg, protocol_schema, description=None, reference=None):
    head = rows[0]
    need(protocol_schema == V8_PROTOCOL, 'Unsupported protocol version')
    expected_schema = 'native-pixel-session-energy-v1' if protocol_schema == V8_PROTOCOL else 'native-pixel-scroll-energy-v1'
    need(head['kind'] == 'header' and head['schema'] == expected_schema
         and rows[-1]['kind'] == 'complete' and not any(r['kind'] == 'failed' for r in rows), 'Incomplete input log')
    need(head['pid'] == entry['pid'] and head['run_id'] == Path(entry['run']).name
         and head['pixels'] == cfg['pixels'] and head['initialize'] is False and head['characterize'] is False,
         'Input identity/mode differs')
    need([head['x'], head['y']] == cfg['points'][entry['condition']], 'Changed frozen input point')
    origin = head['origin_monotonic_ns']; start = head['active_start_monotonic_ns']
    need(all(type(x) in (int,float) and math.isfinite(x) for x in [origin,start]), 'Invalid native clock')
    need(abs(start-origin-20e9) <= 1000 and abs(head['active_end_monotonic_ns']-origin-110e9) <= 1000
         and abs(head['finish_monotonic_ns']-origin-130e9) <= 1000, 'Changed input phase plan')
    events = [r for r in rows if r['kind'] == 'posted_scroll_request']; need(len(events) == 10800, 'Input count')
    for i, row in enumerate(events):
        scheduled = row['scheduled_monotonic_ns']
        need(row['index'] == i and row['run_id'] == head['run_id'] and
             row['pixel_delta_y'] == (-cfg['pixels'] if i%1200 < 600 else cfg['pixels'])
             and abs(scheduled-start-i/120*1e9) <= 1000, 'Input schedule/delta/order')
        times = [row[k]['monotonic_ns'] for k in ('creation_begin','begin','end')]
        need(times == sorted(times) and all(-1000 <= t-scheduled <= 50e6 for t in times), 'Input lateness')
        need(all(0 <= row[k]['pair_bracket_ns'] <= 50e6 for k in ('creation_begin','begin','end')), 'Input bracket')
    own_cpu = driver_metadata(rows,entry,cfg,description,reference) if protocol_schema == V8_PROTOCOL else None
    return origin, own_cpu


def analyze(root, lock):
    need(lock['schema'] == 'energy-analysis-input-lock-v1', 'Unknown input lock')
    saved = Saved(root, lock); manifest = saved.json(lock['manifest']); cfg = saved.json(lock['config'])
    protocol = saved.json(lock['protocol'])
    need(protocol['schema'] == V8_PROTOCOL, 'Unsupported frozen protocol')
    contract = 'v8' if protocol['schema'] == V8_PROTOCOL else 'v5'
    need(manifest['schema'] == 'energy-v4-series' and manifest['order'] == protocol['order'] == ORDER, 'Series/order mismatch')
    need(manifest['config_sha256'] == saved.used[lock['config']] and cfg['ready'] is True, 'Unfrozen/unready config')
    need(cfg['frozen_files'][cfg['protocol']] == saved.used[lock['protocol']], 'Protocol identity mismatch')
    need({app:spec['binary_sha256'] for app,spec in protocol['conditions'].items()} == APP_SHA256,
         'Selected app build identities changed')
    need(protocol['adjacent_pairs'] == [[i,i+1] for i in range(1,17,2)]
         and protocol['windows']['active_core_origin_offsets_s'] == [35,95]
         and protocol['windows']['idle_before_origin_offsets_s'] == [5,15]
         and protocol['windows']['idle_after_origin_offsets_s'] == [115,125], 'Numerical policy changed')
    entries = manifest['runs']; pairs, complete, plan = select_pairs(entries, bool(manifest.get('series_stopped')))
    need(not any(e.get('fatal_series_stop',False) for e in entries) or bool(manifest.get('series_stopped')),
         'Fatal attempt without persisted series stop')
    if 'replacement_ordinals' in manifest: need(manifest['replacement_ordinals'] == plan, 'Manifest replacement plan')
    results = []; all_series_ids = None
    for e in entries:
        attempt = {'slot':e['slot'], 'original_ordinal':e['original_ordinal'], 'condition':e['condition'],
                   'valid':e['valid'], 'failures':e['failures'], 'fatal_series_stop':e.get('fatal_series_stop',False)}
        parent_cpu = {k:e.get(k) for k in ('observer_cpu_ns','observer_elapsed_ns')}
        if e['valid']:
            need(all(type(v) is int and v >= 0 for v in parent_cpu.values()), 'Invalid runner own-CPU accounting')
        attempt['observers'] = {'runner_parent':dict(parent_cpu,
            scope='Runner own process CPU/elapsed across run setup, child monitoring and guarded cleanup; excludes child CPU; not app CPU or energy')}
        runpath = Path(e['run']); runpath = runpath if runpath.is_absolute() else root/runpath
        rel = str(runpath.resolve().relative_to(root.resolve()))
        # Hash all retained failed-attempt files named in the lock; don't interpret partial counters as complete.
        for name in lock['files']:
            if name.startswith(rel+'/'): saved.raw(name)
        if e['valid']:
            for stage in ('before','after'):
                controls = saved.json(rel+'/controls-'+stage+'.local-only.json')
                need(controls['config_source_contract'] == contract and controls['files_sha256'] == cfg['frozen_files'] and
                     controls['app_identities'] == protocol['conditions'], 'Before/after frozen app/source identity mismatch')
            need(isinstance(e['identity'],str) and e['identity'] and type(e['pid']) is int, 'Missing process identity')
            description = reference = None
            if contract == 'v8':
                description = saved.json(rel+'/target-description.json')
                ref_path = lock['environment_references'][e['condition']]
                reference = saved.json(ref_path)
                need(saved.used[ref_path] == cfg['frozen_files'][cfg['environment_references'][e['condition']]],
                     'Frozen environment reference hash mismatch')
            origin, own_cpu = driver(saved.lines(rel+'/driver.jsonl'), e, cfg, protocol['schema'], description, reference)
            rows = saved.lines(rel+'/energy.jsonl')
            samples = validate_energy(rows, cfg['frozen_files'][cfg['collector']], origin, cfg['frozen_files'][cfg['clpc_binding']])
            ids = rows[0]['metadata']
            if all_series_ids is None: all_series_ids = ids
            need(ids == all_series_ids, 'Provider/channel identity changed between runs')
            attempt['windows'] = analyze_windows(samples)
            attempt['observers']['collector'] = dict({k:rows[-1][k] for k in ('observer_cpu_ns','observer_elapsed_ns')},
                scope='Collector own process CPU/elapsed from before native subscription setup through last sample/release before footer; not app CPU or energy')
            attempt['observers']['native_driver'] = own_cpu
            attempt['trace'] = [{'offset_s':row['offset_s'], 'CPU Energy':row['delta_from_previous']['channels']['CPU Energy']['delta_nj']/row['delta_from_previous']['midpoint_exposure_ns'],
                                 'GPU Energy':row['delta_from_previous']['channels']['GPU Energy']['delta_nj']/row['delta_from_previous']['midpoint_exposure_ns']}
                                for row in samples[1:]]
        results.append(attempt)
    post = {}; post_passed = True
    for app in ('gitcomet','fork'):
        path = lock.get('post_characterization',{}).get(app)
        if path is None:
            post[app] = {'status':'missing; descriptive only'}; post_passed = False; continue
        record = saved.json(path); post[app] = record
        passed = record['passed'] is True and record['repeat_count'] >= 2 and record['motion'] is True and \
             record['no_edge'] is True and record['return_error_rows'] <= 1 and record['distance_repeat_fraction'] <= .10
        need(record['pixels'] == cfg['pixels'] and record['point'] == cfg['points'][app]
             and record['driver_source_sha256'] == cfg['frozen_files'][cfg['driver_source']], 'Post-main output identity mismatch')
        post_passed = post_passed and passed
    complete = complete and post_passed
    indexed = {r['slot']:r for r in results}; paired_results = {}; secondary_results = {}
    for component in COMPONENTS:
        gc, fork = [], []
        for pair in pairs:
            vals = {e['condition']:indexed[e['slot']]['windows']['active_core']['components'][component]['normalized_J60'] for e in pair}
            gc.append(vals['gitcomet']); fork.append(vals['fork'])
        paired_results[component] = paired(gc,fork,complete)
        if component == 'CPU Energy':
            paired_results[component]['ratio'] = paired_ratio(gc,fork)
        gc, fork = [], []
        for pair in pairs:
            vals = {e['condition']:indexed[e['slot']]['windows']['secondary_active_minus_exposure_weighted_still_J60'][component] for e in pair}
            gc.append(vals['gitcomet']);fork.append(vals['fork'])
        secondary_results[component] = paired(gc,fork,complete)
    apply_scale_robust_gate(paired_results);apply_scale_robust_gate(secondary_results)
    return {'schema':'energy-saved-analysis-clpc-v1','complete_eight_pairs':complete,
            'scope':'Machine-wide GPU model energy per posted stream; separate CPU model counter with nJ as mapped by macmon0.11.0 (unit not API-declared). Sum conditional on mapping; no physical/app/total energy or equivalent-output efficiency claim.',
            'all_attempts':results,'selected_pairs':[[e['slot'] for e in pair] for pair in pairs],
            'replacement_plan':plan,'paired_primary_normalized_J60':paired_results,
            'paired_secondary_active_minus_weighted_still_J60':secondary_results,
            'post_characterization_passed':post_passed,
            'output_characterization':post,'input_sha256':saved.used,
            'limits':['Post return is not delivery acknowledgment; pre/post output witnesses do not prove every main raster frame.',
                      'CPU units/names assigned using macmon0.11.0 firmware map, not independent CPU energy calibration. GPU/CPU components separate; sum conditional.',
                      'Model acquisition brackets do not prove physical integration freshness; no equivalent-output winner or app-specific energy attribution.',
                      'Secondary exposure-weighted still subtraction retains negative values; ANE0 excluded from primary sum.']}


def graphs(result, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    runs = [r for r in result['all_attempts'] if r['valid']]
    fig, axes = plt.subplots(3,1,figsize=(10,9),layout='constrained')
    for ax, name in zip(axes, COMPONENTS):
        for app, color in [('gitcomet','tab:blue'),('fork','tab:orange')]:
            group = [r for r in runs if r['condition']==app]
            ax.scatter([r['slot'] for r in group],[r['windows']['active_core']['components'][name]['normalized_J60'] for r in group],label=app,color=color)
        ax.set_ylabel(name+'\nmodel J / 60s'); ax.legend(); ax.set_xlabel('All retained valid attempt slots (failed slots listed in analysis)')
    fig.savefig(out/'all-runs.png',dpi=150); plt.close(fig)
    fig, axes = plt.subplots(1,3,figsize=(12,4),layout='constrained')
    for ax,name in zip(axes,COMPONENTS):
        data=result['paired_primary_normalized_J60'][name]
        for pair in result['selected_pairs']:
            rs=[next(r for r in runs if r['slot']==slot) for slot in pair];v={r['condition']:r['windows']['active_core']['components'][name]['normalized_J60'] for r in rs}
            ax.plot([0,1],[v['gitcomet'],v['fork']],marker='o',alpha=.7)
        ax.set_xticks([0,1],['GitComet','Fork']);ax.set_title(name);ax.set_ylabel('Named model J / 60s')
    fig.savefig(out/'paired-joules.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(12,7),layout='constrained')
    for ax,name in zip(axes,('CPU Energy','GPU Energy')):
        for r in runs:ax.plot([p['offset_s'] for p in r['trace']],[p[name] for p in r['trace']],alpha=.45,label=str(r['slot'])+' '+r['condition'])
        ax.set_xlabel('Seconds from native origin (interval ending at snapshot)');ax.set_ylabel(name+' model W')
        for a,b in WINDOWS.values():ax.axvspan(a,b,color='grey',alpha=.08)
    axes[0].legend(ncol=4,fontsize=7);fig.savefig(out/'model-power-traces.png',dpi=150);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--series',type=Path,required=True);p.add_argument('--input-lock',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    need(not args.output.exists() and not args.output.resolve().is_relative_to(args.series.resolve()),
         'Output must be a new directory outside saved series');args.output.mkdir(parents=False)
    try:
        raw=args.input_lock.read_bytes();result=analyze(args.series,decode(raw));result['input_lock_sha256']=sha(raw)
        result['analysis_source_sha256']=sha(Path(__file__).read_bytes())
        (args.output/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        graphs(result,args.output)
        (args.output/'REPORT.md').write_text('# Saved-data model-energy analysis\n\n'+result['scope']+'\n\nComplete eight-pair series: '+str(result['complete_eight_pairs'])+'.\n\nSee analysis.json for all attempts, replacements, raw pre/post still windows, exact nJ, exposures, paired intervals and gates. Components precede sum; no automatic winner claim.\n\n'+ '\n'.join('- '+x for x in result['limits'])+'\n')
    except Exception as error:
        (args.output/'failure.json').write_text(json.dumps({'status':'FAILED','reason':type(error).__name__+': '+str(error)},indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
