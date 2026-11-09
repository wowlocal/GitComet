#!/usr/bin/env python3
"""Saved-data arithmetic only. Missing counters stay unavailable; no app interaction."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

SCHEMA = 'fork-gitcomet-energy-v1'
METRICS = ['app_cpu_percent_one_core', 'windowserver_cpu_percent_one_core',
           'observer_cpu_percent_one_core', 'app_gpu_ms_per_wall_second',
           'windowserver_gpu_ms_per_wall_second', 'whole_gpu_modeled_w',
           'whole_gpu_modeled_j', 'gpu_residency_vs_wall_ratio']


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def stats(values):
    valid = sorted(x for x in values if finite(x))
    def quantile(p):
        f = (len(valid) - 1) * p
        lo, hi = math.floor(f), math.ceil(f)
        return valid[lo] + (valid[hi] - valid[lo]) * (f - lo)
    return {'n': len(valid), 'unavailable': len(values) - len(valid),
            **({k: quantile(p) for k, p in [('min', 0), ('median', .5), ('p95', .95), ('max', 1)]}
               if valid else {k: None for k in ['min', 'median', 'p95', 'max']})}


def load_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_units(witness):
    channels = witness.get('channels') or []
    energy = [x for x in channels if x.get('name') == 'GPU Energy']
    states = [x for x in channels if x.get('name') == 'GPUPH']
    result = dict(witness)
    result['energy_unit_supported'] = (len(energy) == 1 and energy[0].get('format') == 1
                                       and (energy[0].get('unit') or '').strip() in ['nJ', 'uJ', 'mJ'])
    result['gpu_state_24mhz_unit_verified'] = (len(states) == 1 and states[0].get('format') == 2
                                             and (states[0].get('unit') or '').strip() == '24Mticks')
    return result


def process_metric(rows, header, alias, field, exposure):
    pid = header.get('watched_pids', {}).get(alias)
    if pid is None:
        return None, 'process not watched'
    expected = header.get('initial_process_identities', {}).get(alias)
    values = []
    for row in rows:
        process = (row.get('processes') or {}).get(alias) or {}
        counters = process.get('counters') or {}
        if process.get('pid') != pid or not expected or process.get('identity') != expected:
            return None, 'process identity unavailable or changed'
        values.append(counters.get(field))
    if not all(finite(x) and x >= 0 for x in values):
        return None, 'counter unavailable or invalid inside phase'
    if any(b < a for a, b in zip(values, values[1:])):
        return None, 'counter decreased inside phase'
    return (values[-1] - values[0]) / exposure, None


def gpu_metric(rows, header, alias, exposure):
    pid = header.get('watched_pids', {}).get(alias)
    if pid is None:
        return None, 'process not watched'
    expected = header.get('initial_process_identities', {}).get(alias)
    values = []
    for row in rows:
        process = (row.get('processes') or {}).get(alias) or {}
        if not expected or process.get('identity') != expected:
            return None, 'process identity unavailable or changed'
        values.append((row.get('gpu_times_ns') or {}).get(str(pid)))
    if not all(finite(x) and x >= 0 for x in values):
        return None, 'GPU client/counter missing, unreadable or partial: unavailable attribution, not zero'
    if any(b < a for a, b in zip(values, values[1:])):
        return None, 'GPU counter decreased; Metal client lifetime/reset may change aggregate'
    return (values[-1] - values[0]) / 1e6 / exposure, None


def phase_summary(samples, header, units, name, lo, hi):
    indices = [i for i, row in enumerate(samples) if lo <= row['monotonic_s'] <= hi]
    rows = [samples[i] for i in indices]
    result = {'name': name, 'requested_begin_monotonic_s': lo, 'requested_end_monotonic_s': hi,
              'requested_duration_s': hi - lo, 'raw_sample_indices': indices,
              'samples': len(rows), 'available': False,
              **{key: None for key in METRICS}, 'metric_unavailable_reasons': {}}
    if hi <= lo:
        result['reason'] = 'phase endpoints are not increasing'
        return result
    if len(rows) < 4:
        result['reason'] = 'fewer than four samples (three complete intervals)'
        return result
    if indices != list(range(indices[0], indices[-1] + 1)):
        result['reason'] = 'noncontiguous raw sample indices'
        return result
    exposure = rows[-1]['monotonic_s'] - rows[0]['monotonic_s']
    intervals = [row.get('interval_s') for row in rows[1:]]
    seq = [row['seq'] for row in rows]
    if seq != list(range(seq[0], seq[0] + len(seq))):
        result['reason'] = 'missing or duplicated interior sample sequence'
        return result
    if not all(finite(x) and x > 0 for x in intervals):
        result['reason'] = 'invalid adjacent interval'
        return result
    if exposure <= 0 or abs(sum(intervals) - exposure) > 1e-6:
        result['reason'] = 'adjacent interval sum differs from exposure'
        return result
    if any(abs(row['interval_s'] - (row['monotonic_s'] - previous['monotonic_s'])) > 1e-6
           for previous, row in zip(rows, rows[1:])):
        result['reason'] = 'recorded interval does not match raw adjacent timestamps'
        return result
    result.update(available=True, elapsed_s=exposure,
                  integrated_begin_monotonic_s=rows[0]['monotonic_s'],
                  integrated_end_monotonic_s=rows[-1]['monotonic_s'],
                  left_sampling_loss_s=rows[0]['monotonic_s'] - lo,
                  right_sampling_loss_s=hi - rows[-1]['monotonic_s'],
                  interval_s=stats(intervals),
                  acquisition_ms=stats([r['total_acquisition_s'] * 1000 if finite(r.get('total_acquisition_s')) else None for r in rows]),
                  sample_start_lateness_ms=stats([r['start_lateness_s'] * 1000 if finite(r.get('start_lateness_s')) else None for r in rows]))
    unavailable = result['metric_unavailable_reasons']
    for alias in ['app', 'windowserver', 'observer']:
        value, reason = process_metric(rows, header, alias, 'cpu_s', exposure)
        key = alias + '_cpu_percent_one_core'
        result[key] = value * 100 if value is not None else None
        if reason:
            unavailable[key] = reason
    for alias in ['app', 'windowserver']:
        value, reason = gpu_metric(rows, header, alias, exposure)
        key = alias + '_gpu_ms_per_wall_second'
        result[key] = value
        if reason:
            unavailable[key] = reason
    result['extra_process_cpu_percent_one_core'] = {}
    for alias in header.get('watched_pids', {}):
        if alias in ['app', 'windowserver', 'observer']:
            continue
        value, reason = process_metric(rows, header, alias, 'cpu_s', exposure)
        result['extra_process_cpu_percent_one_core'][alias] = {
            'value': value * 100 if value is not None else None, 'reason': reason}
    energy = [(row.get('soc') or {}).get('gpu_energy_nj') for row in rows[1:]]
    if not units.get('energy_unit_supported'):
        unavailable['whole_gpu_modeled_w'] = 'actual energy unit/channel not verified'
    elif not all(finite(x) and x >= 0 for x in energy):
        unavailable['whole_gpu_modeled_w'] = 'energy delta missing/negative inside phase'
    else:
        result['whole_gpu_modeled_j'] = sum(energy) / 1e9
        result['whole_gpu_modeled_w'] = result['whole_gpu_modeled_j'] / exposure
    state_rows = [(row.get('soc') or {}).get('gpu_states') for row in rows[1:]]
    if not units.get('gpu_state_24mhz_unit_verified'):
        unavailable['gpu_residency_vs_wall_ratio'] = 'actual GPUPH 24Mticks unit/channel not verified'
    elif not all(isinstance(x, dict) and x for x in state_rows):
        unavailable['gpu_residency_vs_wall_ratio'] = 'state data missing inside phase'
    elif any(set(x) != set(state_rows[0]) for x in state_rows):
        unavailable['gpu_residency_vs_wall_ratio'] = 'state channel set changed inside phase'
    elif not all(finite(x) and x >= 0 for state in state_rows for x in state.values()):
        unavailable['gpu_residency_vs_wall_ratio'] = 'negative/unavailable state residency'
    else:
        states = {k: sum(x[k] for x in state_rows) for k in state_rows[0]}
        total_s = sum(states.values()) / 24e6
        result['gpu_residency_vs_wall_ratio'] = total_s / exposure
        result['gpu_state_percent_of_wall'] = {k: v / 24e6 / exposure * 100 for k, v in states.items()}
        result['gpu_residency_matches_wall_within_5_percent'] = abs(total_s / exposure - 1) <= .05
    result['driver_utilization_point_samples_percent'] = stats([
        (row.get('device') or {}).get('device_utilization_percent') for row in rows])
    result['cpu_energy_status'] = 'raw counters retained; not validated or analyzed'
    result['total_system_energy_status'] = 'not measured'
    result['gpu_client_lifetime_continuity'] = 'not established: registry client identities are not recorded; an aggregate may recompose without decreasing'
    return result


def analyze_capture(path, events=None):
    path = path.resolve()
    data = load_lines(path)
    headers = [r for r in data if r.get('event') == 'header']
    footers = [r for r in data if r.get('event') == 'footer']
    samples = [r for r in data if r.get('event') == 'sample']
    unit_rows = [r for r in data if r.get('event') == 'units']
    failures = []
    if len(headers) != 1 or data[0] is not headers[0] or headers[0].get('schema') != SCHEMA:
        raise ValueError('Invalid or ambiguous capture header')
    header = headers[0]
    if not samples:
        failures.append('no raw samples')
    if len(footers) != 1 or data[-1] is not footers[0]:
        failures.append('missing/ambiguous/nonfinal footer')
    footer = footers[0] if len(footers) == 1 else {}
    if footer.get('samples') != len(samples):
        failures.append('footer sample count mismatch')
    if footer.get('error'):
        failures.append('observer error: ' + str(footer['error']))
    seq = [r.get('seq') for r in samples]
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in seq) or seq != list(range(1, len(seq) + 1)):
        failures.append('sample sequence is not unique, ordered and contiguous from one')
    if any(r.get('run_id') != header['run_id'] for r in data):
        failures.append('capture run identity mismatch')
    if not all(finite(r.get('monotonic_s')) for r in samples):
        raise ValueError('Invalid sample timestamp')
    if any(b['monotonic_s'] <= a['monotonic_s'] for a, b in zip(samples, samples[1:])):
        failures.append('sample timestamps not strictly increasing')
    if len(unit_rows) != 1:
        failures.append('missing or ambiguous unit witness')
    units = verify_units(unit_rows[0]) if len(unit_rows) == 1 else {}
    event_file = events.resolve() if events else path.with_name(path.name + '.events.jsonl')
    markers = load_lines(event_file) if event_file.exists() else []
    if any(r.get('run_id') != header['run_id'] for r in markers):
        failures.append('marker run identity mismatch')
    names = sorted(set(r['name'] for r in markers if r.get('event') == 'phase'))
    phases = []
    for name in names:
        points = [r for r in markers if r.get('event') == 'phase' and r['name'] == name]
        begins = [r for r in points if r.get('state') == 'begin']
        ends = [r for r in points if r.get('state') == 'end']
        if len(begins) != 1 or len(ends) != 1:
            failures.append('phase ' + name + ' lacks unique begin/end')
            continue
        lo, hi = begins[0]['monotonic_s'], ends[0]['monotonic_s']
        if not finite(lo) or not finite(hi):
            failures.append('phase ' + name + ' has invalid time')
            continue
        phase = phase_summary(samples, header, units, name, lo, hi)
        phase['within_capture_lifetime'] = finite(footer.get('monotonic_s')) and header['monotonic_s'] <= lo < hi <= footer['monotonic_s']
        if not phase['within_capture_lifetime']:
            failures.append('phase ' + name + ' outside capture lifetime')
        phases.append(phase)
    return {'schema': SCHEMA, 'capture': str(path), 'events': str(event_file),
            'capture_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'label': header['label'], 'run_id': header['run_id'],
            'recorded_sources': {k: header.get(k) for k in ['helper_sha256', 'observer_sha256']},
            'integrity': {'valid': not failures, 'failures': failures, 'samples': len(samples)},
            'unit_witness': units, 'phases': phases,
            'controls_verified_by_observer': ['watched process identities per sample', 'counter units where witnessed'],
            'controls_not_verified_by_observer': ['native AX state', 'physical/native momentum input',
                'history readiness/filter/viewport/repo count', 'equal visible motion or frame cadence',
                'background quiet/foreground/power/thermal state unless supplied independently'],
            'scope': ['Whole-GPU energy is modeled/shared, not app/battery/socket/total-system watts',
                'Per-process GPU execution accounting is not peak compute utilization',
                'Missing per-app GPU client is unavailable, not zero',
                'No helper-inclusive CPU total or total-system energy is computed',
                'Counter calls occur sequentially; acquisition spans quantify timing skew',
                'Phase windows integrate only complete adjacent raw intervals inside marker bounds']}


def analyze_series(path):
    manifest = json.loads(path.read_text())
    entries = manifest['runs']
    valid = [r for r in entries if r.get('valid') is True]
    results = []
    for entry in valid:
        capture = Path(entry['capture'])
        if not capture.is_absolute():
            capture = path.parent / capture
        result = analyze_capture(capture)
        if result['label'] != entry['condition']:
            raise ValueError('Manifest condition does not match the captured app label')
        result.update(condition=entry['condition'], ordinal=entry['ordinal'])
        if not result['integrity']['valid']:
            raise ValueError('A manifest-valid capture failed raw integrity checks')
        results.append(result)
    results.sort(key=lambda r: r['ordinal'])
    if len(set(r['run_id'] for r in results)) != len(results):
        raise ValueError('The same capture run identity is repeated as multiple replicates')
    if len(set(r['capture'] for r in results)) != len(results):
        raise ValueError('The same capture path is repeated as multiple replicates')
    source_keys = ['helper_sha256', 'observer_sha256']
    if any(not isinstance(r['recorded_sources'].get(k), str) or len(r['recorded_sources'][k]) != 64
           for r in results for k in source_keys):
        raise ValueError('Every valid comparison capture requires recorded helper/observer hashes')
    if len({tuple(r['recorded_sources'][k] for k in source_keys) for r in results}) > 1:
        raise ValueError('Valid comparison captures used mixed helper/observer source versions')
    expected = ['gitcomet', 'fork', 'fork', 'gitcomet', 'fork', 'gitcomet', 'gitcomet', 'fork']
    balanced = len(results) == 8 and [r['ordinal'] for r in results] == list(range(1, 9)) and [r['condition'] for r in results] == expected
    phase_names = sorted(set(p['name'] for r in results for p in r['phases']))
    summary = {}
    for condition in sorted(set(r['condition'] for r in results)):
        summary[condition] = {}
        group = [r for r in results if r['condition'] == condition]
        for name in phase_names:
            phases = [next((p for p in r['phases'] if p['name'] == name), {}) for r in group]
            summary[condition][name] = {key: stats([p.get(key) for p in phases]) for key in METRICS}
    pairs = []
    if balanced:
        for i in range(0, 8, 2):
            a = next(r for r in results[i:i + 2] if r['condition'] == 'gitcomet')
            b = next(r for r in results[i:i + 2] if r['condition'] == 'fork')
            contrasts = {}
            for name in phase_names:
                ap = next((p for p in a['phases'] if p['name'] == name), {})
                bp = next((p for p in b['phases'] if p['name'] == name), {})
                contrasts[name] = {k: bp[k] - ap[k] if finite(bp.get(k)) and finite(ap.get(k)) else None for k in METRICS}
            pairs.append({'ordinals': [a['ordinal'], b['ordinal']], 'fork_minus_gitcomet': contrasts})
    return {'manifest': str(path.resolve()), 'balanced_eight_run_order_verified': balanced,
            'common_recorded_sources': results[0]['recorded_sources'] if results else None,
            'comparison_controls': manifest.get('comparison_controls', {}),
            'equal_output_efficiency_established': False,
            'interpretation': 'Generated CUA workload; external controls/output calibration must be assessed. These resource counters alone cannot establish equal output or total energy efficiency.',
            'excluded_attempts': [r for r in entries if r.get('valid') is not True],
            'conditions': summary, 'paired_contrasts': pairs, 'runs': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    one = commands.add_parser('run')
    one.add_argument('capture', type=Path)
    one.add_argument('--events', type=Path)
    one.add_argument('--out', type=Path)
    series = commands.add_parser('series')
    series.add_argument('manifest', type=Path)
    series.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.command == 'run':
        result = analyze_capture(args.capture, args.events)
        dest = args.out or args.capture.with_name(args.capture.name + '.analysis.json')
    else:
        result = analyze_series(args.manifest.resolve())
        dest = args.out or args.manifest.with_name('analysis.json')
    with dest.open('w') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'analysis': str(dest.resolve()),
                      'integrity': result.get('integrity'),
                      'balanced_eight_run_order_verified': result.get('balanced_eight_run_order_verified')}))


if __name__ == '__main__':
    main()
