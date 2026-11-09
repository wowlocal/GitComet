#!/usr/bin/env python3
"""Read-only 1 Hz process/GPU observer, plus external phase markers. Never launches or terminates apps."""
import argparse
import ctypes
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import uuid

SCHEMA = 'fork-gitcomet-energy-v1'
HERE = Path(__file__).resolve().parent


def stamp():
    return {'monotonic_s': time.monotonic(), 'unix_ms': time.time() * 1000}


def event_path(capture):
    return capture.with_name(capture.name + '.events.jsonl')


def read_header(path):
    with path.open() as stream:
        header = json.loads(stream.readline())
    if header.get('event') != 'header' or header.get('schema') != SCHEMA:
        raise ValueError('Not a comparison capture')
    return header


def marker(args):
    capture = args.capture.resolve()
    header = read_header(capture)
    value = {'event': 'control' if args.command == 'stop' else 'phase',
             'run_id': header['run_id'], **stamp()}
    if args.command == 'stop':
        value['action'] = 'stop_observer'
    else:
        value.update(name=args.name, state=args.state)
    data = (json.dumps(value, allow_nan=False) + '\n').encode()
    fd = os.open(event_path(capture), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise OSError('Short marker write')
    finally:
        os.close(fd)
    print(json.dumps(value), flush=True)


def unit_witness(perf, report, snapshot):
    """Read actual labels instead of trusting helper fallback-unit defaults."""
    if not snapshot:
        return {'available': False, 'reason': 'No IOReport sample'}
    cf = report.cf
    channels = cf.CFDictionaryGetValue(snapshot, report.channels_key)
    found = []
    for i in range(cf.CFArrayGetCount(channels) if channels else 0):
        channel = cf.CFArrayGetValueAtIndex(channels, i)
        name = report._text(report.ior.IOReportChannelGetChannelName(channel))
        if name in ['GPU Energy', 'GPUPH']:
            found.append({'name': name,
                          'group': report._text(report.ior.IOReportChannelGetGroup(channel)),
                          'subgroup': report._text(report.ior.IOReportChannelGetSubGroup(channel)),
                          'unit': report._text(report.ior.IOReportChannelGetUnitLabel(channel)),
                          'format': report.ior.IOReportChannelGetFormat(channel)})
    energy = [x for x in found if x['name'] == 'GPU Energy']
    states = [x for x in found if x['name'] == 'GPUPH']
    energy_ok = len(energy) == 1 and energy[0]['format'] == 1 and (energy[0]['unit'] or '').strip() in ['nJ', 'uJ', 'mJ']
    state_ok = len(states) == 1 and states[0]['format'] == 2 and (states[0]['unit'] or '').strip() == '24Mticks'
    return {'available': True, 'channels': found,
            'energy_unit_supported': energy_ok,
            'gpu_state_24mhz_unit_verified': state_ok}


def process_identity(perf, pid):
    libs = perf._load()
    if not libs:
        return None
    info = perf._RusageInfo()
    if libs['system'].proc_pid_rusage(pid, perf._RUSAGE_INFO_V6, ctypes.byref(info)):
        return None
    return {'uuid': bytes(info.uuid).hex(), 'start_abstime': int(info.proc_start_abstime)}


def record(args):
    capture = args.out.resolve()
    if capture.exists() or event_path(capture).exists():
        raise ValueError('Capture/events exist; choose a new path. Existing data are never overwritten.')
    capture.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    helper = args.helper.resolve()
    spec = importlib.util.spec_from_file_location('comparison_perf_macos', helper)
    perf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(perf)
    if not perf.available():
        raise RuntimeError('Native counter helper unavailable')
    ws = perf.window_server_pid()
    watches = {'observer': os.getpid()}
    if ws:
        watches['windowserver'] = ws
    if args.pid is not None:
        if args.pid <= 0:
            raise ValueError('App PID must be positive')
        watches['app'] = args.pid
    for extra in args.extra_pid:
        alias, text = extra.split('=', 1)
        if alias in watches or not alias or int(text) <= 0:
            raise ValueError('Extra PID alias must be unique and PID positive')
        watches[alias] = int(text)
    if len(set(watches.values())) != len(watches):
        raise ValueError('Aliases must refer to distinct processes')
    identities = {alias: process_identity(perf, pid) for alias, pid in watches.items()}
    if args.pid is not None and identities['app'] is None:
        raise ValueError('Target app PID is unavailable before capture')
    report = perf.IOReportSampler()
    previous = None
    run_id = uuid.uuid4().hex
    stop = {'reason': None}
    def on_signal(number, _frame):
        stop['reason'] = 'signal-' + str(number)
    old_handlers = {s: signal.signal(s, on_signal) for s in [signal.SIGINT, signal.SIGTERM]}
    header = {'event': 'header', 'schema': SCHEMA, 'run_id': run_id,
              'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'label': args.label, 'observer_pid': os.getpid(), 'app_pid': args.pid,
              'windowserver_pid': ws, 'watched_pids': watches,
              'initial_process_identities': identities, 'interval_s': args.interval,
              'duration_limit_s': args.duration,
              'helper_sha256': hashlib.sha256(helper.read_bytes()).hexdigest(),
              'observer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'ioreport_subscription_available': report.ok,
              'scope': ['Read-only observer; no launch/quit/activation/AX/screenshot/input calls',
                        'App GPU absence means unavailable attribution, not zero display-path GPU cost',
                        'WindowServer and modeled GPU energy are shared desktop/device scopes',
                        'CPU energy/billed counters retained but not validated or analyzed',
                        'Only explicitly watched processes; short-lived/helper work may be omitted',
                        'Phase markers are external host times, not native input or actual presentation times'],
              **stamp()}
    rows = 0
    error = None
    started = time.monotonic()
    previous_at = None
    next_at = started
    event_offset = 0
    try:
        with capture.open('x') as stream:
            os.chmod(capture, 0o600)
            def emit(value):
                stream.write(json.dumps(value, allow_nan=False) + '\n')
                stream.flush()
            emit(header)
            print(json.dumps({'event': 'observer_ready', 'capture': str(capture),
                              'events': str(event_path(capture)), 'run_id': run_id,
                              'observer_pid': os.getpid(), **stamp()}), flush=True)
            try:
                while not stop['reason']:
                    remaining = started + args.duration - time.monotonic()
                    if remaining <= 0:
                        stop['reason'] = 'duration'
                        break
                    time.sleep(max(0, min(next_at - time.monotonic(), remaining)))
                    query_start = time.monotonic()
                    sample_start = time.monotonic()
                    current = report.sample() if report.ok else None
                    sample_end = time.monotonic()
                    at = (sample_start + sample_end) / 2
                    try:
                        if rows == 0:
                            units = unit_witness(perf, report, current) if report.ok else {'available': False}
                            emit({'event': 'units', 'run_id': run_id, **units, **stamp()})
                        soc = report.delta(previous, current) if previous is not None and current is not None else None
                        processes = {alias: {'pid': pid, 'identity': process_identity(perf, pid),
                                             'counters': perf.process_sample(pid)}
                                     for alias, pid in watches.items()}
                        if hasattr(perf, 'gpu_times_snapshot'):
                            gpu_snapshot = perf.gpu_times_snapshot(set(watches.values()))
                            gpu = gpu_snapshot.get('times_ns') if gpu_snapshot else None
                            gpu_status = gpu_snapshot.get('client_status') if gpu_snapshot else None
                        else:
                            gpu = perf.gpu_times_ns(set(watches.values()))
                            gpu_status = None
                        device = perf.device_statistics()
                    except BaseException:
                        if current is not None:
                            report.release(current)
                        raise
                    if previous is not None:
                        report.release(previous)
                    previous = current
                    rows += 1
                    emit({'event': 'sample', 'seq': rows, 'run_id': run_id,
                          'monotonic_s': at, 'unix_ms': time.time() * 1000,
                          'interval_s': at - previous_at if previous_at is not None else None,
                          'soc': soc, 'processes': processes, 'gpu_times_ns': gpu,
                          'gpu_client_status': gpu_status,
                          'device': device, 'ioreport_query_s': sample_end - sample_start,
                          'total_acquisition_s': time.monotonic() - query_start,
                          'planned_sample_monotonic_s': next_at,
                          'start_lateness_s': max(0, query_start - next_at)})
                    previous_at = at
                    events = event_path(capture)
                    if events.exists():
                        with events.open() as control:
                            control.seek(event_offset)
                            for line in control:
                                value = json.loads(line)
                                if value.get('run_id') != run_id:
                                    raise ValueError('Marker file belongs to a different capture')
                                if value.get('event') == 'control' and value.get('action') == 'stop_observer':
                                    stop['reason'] = 'external-stop'
                            event_offset = control.tell()
                    next_at += args.interval
                    # Avoid bursts of catch-up samples; lateness stays in the raw data.
                    if next_at < time.monotonic():
                        next_at = started + math.ceil((time.monotonic() - started) / args.interval) * args.interval
            except BaseException as exc:
                error = repr(exc)
                stop['reason'] = 'error'
            finally:
                emit({'event': 'footer', 'schema': SCHEMA, 'run_id': run_id,
                      'samples': rows, 'stop_reason': stop['reason'], 'error': error,
                      'elapsed_s': time.monotonic() - started, **stamp()})
    finally:
        if previous is not None:
            report.release(previous)
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
    print(json.dumps({'event': 'observer_finished', 'capture': str(capture),
                      'samples': rows, 'stop_reason': stop['reason'], 'error': error}), flush=True)
    return 1 if error else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    rec = commands.add_parser('record', help='Observe existing processes without interacting with them')
    rec.add_argument('--pid', type=int, help='Already-running app PID; omit for desktop baseline')
    rec.add_argument('--label', required=True)
    rec.add_argument('--out', type=Path, required=True)
    rec.add_argument('--duration', type=float, default=90)
    rec.add_argument('--interval', type=float, choices=[1.0], default=1.0)
    rec.add_argument('--extra-pid', action='append', default=[], metavar='ALIAS=PID')
    rec.add_argument('--helper', type=Path, default=HERE / 'perf_macos.py')
    for name in ['mark', 'stop']:
        p = commands.add_parser(name)
        p.add_argument('capture', type=Path)
        if name == 'mark':
            p.add_argument('name')
            p.add_argument('state', choices=['begin', 'end'])
    args = parser.parse_args()
    if args.command == 'record':
        if not 5 <= args.duration <= 600:
            parser.error('Duration must be between 5 and 600 seconds')
        return record(args)
    marker(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
