#!/usr/bin/env python3
"""SOURCE ONLY: separate explicit-invocation raw CLPC/native-GPU collector.

No app/input/load/permission/privilege/network/settings APIs. All4channels are
required in main and diagnostics. No source switch or guessed/default unit.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

BINDING_SHA256 = 'a02c5d1312ebca2ab422864bb5d7e1114a744888995d4c0d8556f4530592ebd5'
PRIMARY_NAMES = ('CPU Energy', 'GPU Energy')
MAX_CALL_NS = 50_000_000
MAX_START_LATENESS_NS = 50_000_000
WINDOWS = {'idle_before': (5, 15), 'active_core': (35, 95), 'idle_after': (115, 125)}


def load_binding():
    path = Path(__file__).resolve().parent.parent / 'clpc-binding-v1.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != BINDING_SHA256:
        raise RuntimeError('Frozen CLPC binding changed; no substitution')
    spec = importlib.util.spec_from_file_location('frozen_clpc_raw_binding', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class Invalid(RuntimeError):
    pass


def stamp():
    before = time.monotonic_ns()
    unix = time.time_ns()
    after = time.monotonic_ns()
    return {'monotonic_before_ns': before, 'unix_ns': unix,
            'monotonic_after_ns': after}


def midpoint(mark):
    return (mark['monotonic_before_ns'] + mark['monotonic_after_ns']) // 2


def write(fd, row):
    payload = (json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    offset = 0
    while offset < len(payload):
        offset += os.write(fd, payload[offset:])


def bounds(row):
    return row['call_before']['monotonic_before_ns'], row['call_after']['monotonic_after_ns']


def snapshot_checks(row, deadline, anchor_offset):
    low, high = bounds(row)
    if high < low or high - low > MAX_CALL_NS:
        raise Invalid('Snapshot call latency exceeds frozen50ms bound')
    if low < deadline or low - deadline > MAX_START_LATENESS_NS:
        raise Invalid('Snapshot absolute start exceeds frozen50ms lateness bound')
    for mark in (row['call_before'], row['call_after']):
        offset = mark['unix_ns'] - midpoint(mark)
        if abs(offset - anchor_offset) > 50_000_000:
            raise Invalid('Host Unix/monotonic discontinuity over50ms; possible sleep/clock change')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--origin-monotonic-ns', type=int,
                      help='Run mode: exact native driver origin, common mach_absolute_time clock')
    mode.add_argument('--validation-samples', type=int,
                      help='Diagnostic mode only: finite1Hz intervals10..180;4 CLPC/native validation channels')
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.geteuid() == 0:
        parser.error('Run later as ordinary macOS user only; no root path')
    clock = time.get_clock_info('monotonic')
    if 'mach_absolute_time' not in clock.implementation or not clock.monotonic or clock.adjustable:
        parser.error('Python monotonic clock must use same nonadjustable mach_absolute_time as native driver')
    diagnostics = args.validation_samples is not None
    if diagnostics and not 10 <= args.validation_samples <= 180:
        parser.error('Diagnostic sample count must be finite10..180')
    if not diagnostics and (args.origin_monotonic_ns is None or args.origin_monotonic_ns <= 0):
        parser.error('Run mode requires positive native origin')
    if not diagnostics and not 0 <= time.monotonic_ns() - args.origin_monotonic_ns <= 1_000_000_000:
        parser.error('Main origin must be0..1s before this launch; no future/wrong-unit origin or shifted wait')
    path = args.output.absolute()
    if any(parent.is_symlink() for parent in [path.parent, *path.parents]):
        parser.error('No symlink output-directory components')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    observer_cpu_start = time.process_time_ns()
    observer_start = time.monotonic_ns()
    model = None
    previous_native = None
    current_native = None
    owned_samples = []
    collected = 0
    reason = None
    try:
        model = load_binding().CLPCBinding()
        if diagnostics:
            origin = time.monotonic_ns() + 1_000_000_000
            offsets = list(range(args.validation_samples + 1))
        else:
            origin = args.origin_monotonic_ns
            offsets = list(range(3, 128))
        if time.monotonic_ns() >= origin + offsets[0] * 1_000_000_000:
            raise Invalid('Collector setup missed first absolute snapshot; no shifted schedule')
        anchor = stamp()
        anchor_offset = anchor['unix_ns'] - midpoint(anchor)
        expected = len(offsets)
        write(fd, {'kind': 'header', 'schema': 'ioreport-clpc-energy-v1', 'stamp': anchor,
                   'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'binding_sha256': BINDING_SHA256, 'binding_provenance': model.provenance,
                   'unit_provenance': 'CLPC names/nJ descriptors assigned from pinned macmon firmware analysis; native GPU API nJ metadata. No independent CPU absolute calibration or physical/system/app energy claim.',
                   'mode': 'diagnostics' if diagnostics else 'main',
                   'scope': 'Machine-wide named CLPC CPU + native Energy Model GPU model counters, separately and literal sum; ANE0 secondary; CLPC GPU diagnostic only',
                   'primary_names': PRIMARY_NAMES, 'specs': model.specs, 'metadata': model.expected,
                   'expected_snapshots': expected, 'snapshot_offsets_s': offsets,
                   'origin_monotonic_ns': origin, 'windows_s': None if diagnostics else WINDOWS,
                   'max_call_ns': MAX_CALL_NS, 'max_start_lateness_ns': MAX_START_LATENESS_NS,
                   'monotonic_implementation': clock.implementation})
        for index, offset in enumerate(offsets):
            deadline = origin + offset * 1_000_000_000
            remaining = deadline - time.monotonic_ns()
            if remaining > 0:
                time.sleep(remaining / 1e9)
            current_native, current = model.sample()
            owned_samples.append(current_native)
            snapshot_checks(current, deadline, anchor_offset)
            row = {'kind': 'snapshot', 'index': index, 'offset_s': offset,
                   'scheduled_monotonic_ns': deadline, 'sample': current}
            if previous_native is not None:
                channels = model.delta(previous_native, current_native, previous, current)
                low0, high0 = bounds(previous)
                low1, high1 = bounds(current)
                exposure = (low1 + high1 - low0 - high0) // 2
                if exposure <= 0:
                    raise Invalid('Nonpositive snapshot midpoint exposure')
                primary_nj = sum(channels[name]['delta_nj'] for name in PRIMARY_NAMES)
                row['delta_from_previous'] = {'channels': channels,
                     'midpoint_exposure_ns': exposure,
                     'exposure_bounds_ns': [low1 - high0, high1 - low0],
                     'primary_sum_nj': primary_nj, 'primary_sum_j': primary_nj / 1e9,
                     'ane0_secondary_nj': channels['ANE0']['delta_nj']}
            write(fd, row)
            collected += 1
            if previous_native is not None:
                # Remove ownership before release; interrupt cannot double-free
                # an old alias during the following previous/current handoff.
                model.release(owned_samples.pop(0))
            previous_native, previous = current_native, current
            current_native = None
    except (Exception, KeyboardInterrupt) as error:
        reason = type(error).__name__ + ': ' + str(error)
    finally:
        if model:
            while owned_samples:
                model.release(owned_samples.pop())
            try: model.close()
            except Exception as error:
                reason = (reason + '; ' if reason else '') + 'Binding cleanup: ' + str(error)
        write(fd, {'kind': 'footer', 'stamp': stamp(), 'complete': reason is None and 'offsets' in locals() and collected == len(offsets),
                   'snapshots': collected, 'expected_snapshots': len(offsets) if 'offsets' in locals() else None,
                   'reason': reason, 'observer_cpu_ns': time.process_time_ns() - observer_cpu_start,
                   'observer_elapsed_ns': time.monotonic_ns() - observer_start})
        os.close(fd)
    return 0 if reason is None and collected == len(offsets) else 2


if __name__ == '__main__':
    sys.exit(main())
