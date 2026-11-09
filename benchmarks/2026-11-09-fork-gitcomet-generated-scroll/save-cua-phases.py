#!/usr/bin/env python3
"""Map already-recorded CUA Date.now phases after capture; no app/input/native API calls."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
DRIFT_LIMIT_MS = 2.0
TIMING_TOLERANCE_MS = 200.0
SCHEMA = 'cua-scroll-timing-v1'
EVENT_ORDER = [('idle-before', 'begin'), ('idle-before', 'end'),
               ('scrolling', 'begin'), ('scrolling', 'end'),
               ('idle-after', 'begin'), ('idle-after', 'end')]
EVENT_TARGET_MS = [0, 10000, 10000, 30000, 30000, 45000]


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def read_lines(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert(capture, cua_path, required_revision=None):
    capture, cua_path = capture.resolve(), cua_path.resolve()
    rows = read_lines(capture)
    data = json.loads(cua_path.read_text())
    headers = [x for x in rows if x.get('event') == 'header']
    footers = [x for x in rows if x.get('event') == 'footer']
    if len(headers) != 1 or len(footers) != 1 or rows[0] is not headers[0] or rows[-1] is not footers[0]:
        raise ValueError('Require one initial header and one final footer; stop the observer first')
    header, footer = headers[0], footers[0]
    if header.get('schema') != 'fork-gitcomet-energy-v1' or data.get('schema') != SCHEMA:
        raise ValueError('Unexpected capture or CUA schema')
    revision = data.get('plan_revision', 1)
    if revision not in [1, 2] or isinstance(revision, bool):
        raise ValueError('Unsupported generated-workload plan revision')
    if required_revision is not None and revision != required_revision:
        raise ValueError('CUA plan revision differs from required revision')
    if data.get('label') != header.get('label'):
        raise ValueError('CUA label must match captured app label')
    if data.get('run_id', header['run_id']) != header['run_id']:
        raise ValueError('CUA run_id, when supplied, must match capture header')
    spec = importlib.util.spec_from_file_location('comparison_analysis_for_clock', HERE/'analyze.py')
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    integrity = analyzer.analyze_capture(capture)['integrity']
    if not integrity['valid']:
        raise ValueError('Incomplete raw capture: ' + repr(integrity['failures']))
    if not all(finite(x.get(k)) for x in [header, footer] for k in ['monotonic_s', 'unix_ms']):
        raise ValueError('Header/footer clock anchors unavailable')
    if footer['monotonic_s'] <= header['monotonic_s']:
        raise ValueError('Capture clock anchors are not increasing')
    events, commands = data.get('events'), data.get('commands')
    if not isinstance(events, list) or [(x.get('name'), x.get('state')) for x in events] != EVENT_ORDER:
        raise ValueError('Require the six frozen phase events in order')
    if not all(finite(x.get('unix_ms')) for x in events):
        raise ValueError('Phase timestamps must be finite host Unix milliseconds')
    if any(b['unix_ms'] < a['unix_ms'] for a, b in zip(events, events[1:])):
        raise ValueError('CUA phase event timestamps are not ordered')
    if not isinstance(commands, list) or len(commands) != 16 or [x.get('index') for x in commands] != list(range(16)):
        raise ValueError('Require ordered command indices 0..15')
    fields = ['scheduled_unix_ms', 'begin_unix_ms', 'end_unix_ms']
    for command in commands:
        if not all(finite(command.get(k)) for k in fields):
            raise ValueError('Command timestamps must be finite')
        if command.get('direction') not in ['down', 'up'] or command.get('requested_pages') != 1 or isinstance(command.get('requested_pages'), bool):
            raise ValueError('Require a down/up command requesting exactly one page')
        if command['end_unix_ms'] < command['begin_unix_ms']:
            raise ValueError('Command return timestamp precedes command begin')
        if revision == 2:
            children = command.get('subcalls')
            if (command.get('subcall_count') != 10 or command.get('subcall_pages') != .1
                    or command.get('planned_spacing_ms') != 50
                    or not isinstance(children, list) or len(children) != 10
                    or [x.get('index') for x in children] != list(range(10))):
                raise ValueError('Revision2 requires ten ordered0.1-page subcalls planned50 ms apart')
            for child in children:
                if not all(finite(child.get(k)) for k in fields) or child.get('requested_pages') != .1:
                    raise ValueError('Invalid subcall timestamps/page amount')
                if child['end_unix_ms'] < child['begin_unix_ms']:
                    raise ValueError('Subcall return precedes begin')
    started, ended = data.get('started_unix_ms'), data.get('ended_unix_ms')
    if not finite(started) or not finite(ended) or ended < started:
        raise ValueError('CUA overall start/end timestamps unavailable or reversed')
    offsets = [x['unix_ms'] - x['monotonic_s'] * 1000 for x in [header, footer]]
    offset = statistics.median(offsets)
    drift = abs(offsets[1] - offsets[0])
    clock_failures = []
    if drift > DRIFT_LIMIT_MS:
        clock_failures.append('header/footer offset drift exceeds 2 ms')
    row_clock_checks = []
    for row in rows:
        if row.get('event') != 'sample':
            continue
        if not all(finite(row.get(k)) for k in ['unix_ms', 'monotonic_s', 'total_acquisition_s']):
            clock_failures.append('sample lacks fields needed to bound sequential-read clock skew')
            continue
        residual = row['unix_ms'] - row['monotonic_s'] * 1000 - offset
        upper = row['total_acquisition_s'] * 1000
        # Row Unix timestamps occur after IOReport midpoint and remaining queries.
        # Use their acquisition-span interval as a consistency check, never as an anchor.
        passed = -DRIFT_LIMIT_MS <= residual <= upper + DRIFT_LIMIT_MS
        row_clock_checks.append({'seq': row['seq'], 'residual_ms': residual,
                                 'allowed_ms': [-DRIFT_LIMIT_MS, upper + DRIFT_LIMIT_MS], 'passed': passed})
        if not passed:
            clock_failures.append('sample host-clock residual exceeds its acquisition-span allowance: seq ' + str(row['seq']))
    markers = [{'event': 'phase', 'run_id': header['run_id'],
                'name': x['name'], 'state': x['state'], 'unix_ms': x['unix_ms'],
                'monotonic_s': (x['unix_ms'] - offset) / 1000,
                'source': 'retrospective-cua-Date.now-map', 'cua_json_sha256': digest(cua_path)} for x in events]
    if any(not header['monotonic_s'] <= x['monotonic_s'] <= footer['monotonic_s'] for x in markers):
        clock_failures.append('CUA phase timestamps map outside completed capture lifetime')
    violations = []
    def require(value, message):
        if not value:
            violations.append(message)
    for event, target in zip(events, EVENT_TARGET_MS):
        require(abs(event['unix_ms'] - started - target) <= TIMING_TOLERANCE_MS,
                'phase event misses frozen absolute schedule: ' + event['name'] + '/' + event['state'])
    expected_duration = {'idle-before': 10000, 'scrolling': 20000, 'idle-after': 15000}
    durations = {}
    for i in range(0, 6, 2):
        name = events[i]['name'];duration = events[i+1]['unix_ms'] - events[i]['unix_ms']
        durations[name] = duration
        require(abs(duration - expected_duration[name]) <= TIMING_TOLERANCE_MS, name + ' duration differs by more than 200 ms')
    require(abs(ended - started - 45000) <= TIMING_TOLERANCE_MS, 'overall duration differs from 45 s by more than 200 ms')
    require(ended >= events[-1]['unix_ms'], 'CUA overall end precedes last phase event')
    command_results = []
    for command in commands:
        target = started + 12000 + command['index'] * 1000
        late = command['begin_unix_ms'] - command['scheduled_unix_ms']
        require(command['direction'] == ['down', 'down', 'up', 'up'][command['index'] % 4],
                'command direction differs from frozen down/down/up/up plan: ' + str(command['index']))
        require(abs(command['scheduled_unix_ms'] - target) <= 2, 'command scheduled target differs from frozen plan: ' + str(command['index']))
        require(-2 <= late <= TIMING_TOLERANCE_MS, 'command begins early or more than 200 ms late: ' + str(command['index']))
        require(events[2]['unix_ms'] <= command['begin_unix_ms'] <= command['end_unix_ms'] <= events[3]['unix_ms'],
                'command lies outside scrolling phase: ' + str(command['index']))
        detail = {**command, 'start_lateness_ms': late,
                  'call_duration_ms': command['end_unix_ms'] - command['begin_unix_ms']}
        if revision == 2:
            children = command['subcalls']
            child_lateness = []
            for child in children:
                child_target = target + child['index'] * 50
                child_late = child['begin_unix_ms'] - child['scheduled_unix_ms']
                child_lateness.append(child_late)
                require(abs(child['scheduled_unix_ms'] - child_target) <= 2,
                        'subcall scheduled target differs from frozen plan: ' + str(command['index']) + '/' + str(child['index']))
                require(-2 <= child_late <= TIMING_TOLERANCE_MS,
                        'subcall begins early or more than200 ms late: ' + str(command['index']) + '/' + str(child['index']))
                require(command['begin_unix_ms'] <= child['begin_unix_ms'] <= child['end_unix_ms'] <= command['end_unix_ms'],
                        'subcall lies outside group: ' + str(command['index']) + '/' + str(child['index']))
            require(all(a['end_unix_ms'] <= b['begin_unix_ms'] for a, b in zip(children, children[1:])),
                    'subcalls overlap in group: ' + str(command['index']))
            spacings = [b['begin_unix_ms'] - a['begin_unix_ms'] for a, b in zip(children, children[1:])]
            computed = {'actual_spacing_min_ms': min(spacings), 'actual_spacing_max_ms': max(spacings),
                        'max_lateness_ms': max(child_lateness)}
            for key, value in computed.items():
                if key in command:
                    require(finite(command[key]) and abs(command[key] - value) <= 1,
                            'reported subcall summary disagrees with raw timestamps: ' + str(command['index']) + '/' + key)
            detail['recomputed_subcall_summary'] = computed
        command_results.append(detail)
    require(all(a['end_unix_ms'] <= b['begin_unix_ms'] for a, b in zip(commands, commands[1:])), 'commands overlap in a supposedly sequential batch')
    require(commands[-1]['end_unix_ms'] <= started + 28000 + TIMING_TOLERANCE_MS, 'last command returns after 28 s + 200 ms')
    plan_keys = ['index', 'direction', 'requested_pages'] + (['subcall_count', 'subcall_pages', 'planned_spacing_ms'] if revision == 2 else [])
    planned = [{k: command[k] for k in plan_keys} for command in commands]
    boundary_distances = []
    samples = [x for x in rows if x.get('event') == 'sample']
    uncertainty_floor = 1.001 + drift / 2
    for marker in markers:
        distance = min(abs(x['monotonic_s'] - marker['monotonic_s']) * 1000 for x in samples)
        boundary_distances.append({'name': marker['name'], 'state': marker['state'],
                                   'nearest_sample_distance_ms': distance,
                                   'sample_within_uncertainty_floor': distance <= uncertainty_floor})
    report = {'schema': 'cua-phase-clock-map-v1', 'capture': str(capture), 'cua_timing': str(cua_path),
              'run_id': header['run_id'], 'label': header['label'], 'plan_revision': revision,
              'capture_sha256': digest(capture), 'cua_json_sha256': digest(cua_path),
              'converter_sha256': digest(Path(__file__)), 'analyzer_sha256': digest(HERE/'analyze.py'),
              'recorded_collector_sources': {k: header.get(k) for k in ['helper_sha256', 'observer_sha256']},
              'clock_mapping': {'valid': not clock_failures, 'failures': clock_failures,
                  'anchor_offsets_unix_minus_monotonic_ms': offsets,
                  'median_offset_ms': offset, 'endpoint_offset_drift_ms': drift,
                  'maximum_allowed_endpoint_drift_ms': DRIFT_LIMIT_MS,
                  'Date_now_resolution_allowance_ms': 1.0,
                  'alignment_uncertainty_floor_ms': uncertainty_floor,
                  'uncertainty_is_certified_upper_bound': False,
                  'additional_unbounded_limits': ['Header/footer two-call pairing spans were not recorded',
                      'CUA Date.now is assumed to use the same Mac host wall clock; converter cannot independently establish host-clock identity',
                      'Row acquisition-span checks can detect large inconsistent host-clock changes, not every transient clock adjustment'],
                  'rows_are_consistency_checks_not_anchors': row_clock_checks,
                  'phase_sample_boundary_proximity': boundary_distances},
              'workload_validation': {'passed': not violations, 'violations': violations,
                  'phase_duration_ms': durations, 'overall_duration_ms': ended - started,
                  'timing_tolerance_ms': TIMING_TOLERANCE_MS,
                  'leading_scroll_padding_ms': commands[0]['begin_unix_ms'] - events[2]['unix_ms'],
                  'trailing_scroll_padding_ms': events[3]['unix_ms'] - commands[-1]['end_unix_ms'],
                  'commands': command_results},
              'requested_direction_page_plan_sha256': hashlib.sha256(json.dumps({'revision': revision, 'groups': planned}, sort_keys=True).encode()).hexdigest(),
              'mapped_markers': markers,
              'scope': 'Generated CUA wheel-pulse/burst host phase envelope only; no native packet frequency,120Hz physical glide, actual presented frame, AX-inactive, equal-output or total-energy-efficiency claim'}
    return report, markers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('cua_json', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--require-plan-revision', type=int, choices=[1, 2])
    args = parser.parse_args()
    output = args.out or args.capture.with_name(args.capture.name + '.cua-mapping.json')
    if output.exists():
        parser.error('Mapping output exists; never overwrite an earlier conversion')
    report, markers = convert(args.capture, args.cua_json, args.require_plan_revision)
    events = args.capture.with_name(args.capture.name + '.events.jsonl')
    existing = read_lines(events) if events.exists() else []
    if any(x.get('event') == 'phase' for x in existing):
        parser.error('Phase markers already exist; refusing duplicate/overlapping retrospective phases')
    if any(x.get('run_id') != report['run_id'] for x in existing):
        parser.error('Existing marker/control file belongs to another capture')
    report['existing_event_file_sha256'] = digest(events) if events.exists() else None
    report['markers_appended'] = False
    if report['clock_mapping']['valid']:
        payload = ''.join(json.dumps(x, allow_nan=False) + '\n' for x in markers).encode()
        fd = os.open(events, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            if os.write(fd, payload) != len(payload):
                raise OSError('Short marker write; retain partial file as an invalid attempt')
        finally:
            os.close(fd)
        report['markers_appended'] = True
    with output.open('x') as stream:
        os.chmod(output, 0o600)
        json.dump(report, stream, indent=2, allow_nan=False);stream.write('\n')
    passed = report['clock_mapping']['valid'] and report['workload_validation']['passed']
    print(json.dumps({'mapping': str(output.resolve()), 'clock_mapping_valid': report['clock_mapping']['valid'],
                      'workload_validation_passed': report['workload_validation']['passed'],
                      'markers_appended': report['markers_appended'], 'validation_passed': passed}))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
