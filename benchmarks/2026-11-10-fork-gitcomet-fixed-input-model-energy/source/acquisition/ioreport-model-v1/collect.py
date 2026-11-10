#!/usr/bin/env python3
"""Separate unprivileged IOReport named-model collector. SOURCE PREPARATION ONLY.

No app control, CPU load, subprocess, network, privilege or permission requests.
Only a reviewed later explicit invocation takes samples. Does not import old collectors.
"""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import sys
import time

UTF8 = 0x08000100
# IOReportTypes.h: quantity Energy=3; milli exponent=-3, nano=-9;
# __IOR_MAKEUNIT(quantity,scale), ExpZeroOffset=127, SIShift=32.
MJ_UNIT = (3 << 56) | ((127 - 3) << 32)
NJ_UNIT = (3 << 56) | ((127 - 9) << 32)
PRIMARY_NAMES = ('CPU Energy', 'GPU Energy')
SPECS = {
    'CPU Energy': {'unit': 'mJ', 'unit_code': MJ_UNIT, 'to_nj': 1_000_000},
    'GPU Energy': {'unit': 'nJ', 'unit_code': NJ_UNIT, 'to_nj': 1},
    'ANE0': {'unit': 'mJ', 'unit_code': MJ_UNIT, 'to_nj': 1_000_000},
}
DIAGNOSTIC_SPECS = {**SPECS, **{name: {'unit': 'mJ', 'unit_code': MJ_UNIT, 'to_nj': 1_000_000}
                         for name in ('GPU0', 'MCPU0', 'MCPU1', 'PCPU')}}
MAX_CALL_NS = 50_000_000
MAX_START_LATENESS_NS = 50_000_000
WINDOWS = {'idle_before': (5, 15), 'active_core': (35, 95), 'idle_after': (115, 125)}


class Invalid(RuntimeError):
    pass


class CFArrayCallBacks(c.Structure):
    _fields_ = [('version', c.c_long), ('retain', c.c_void_p),
                ('release', c.c_void_p), ('copyDescription', c.c_void_p),
                ('equal', c.c_void_p)]


def stamp():
    before = time.monotonic_ns()
    unix = time.time_ns()
    after = time.monotonic_ns()
    return {'monotonic_before_ns': before, 'unix_ns': unix,
            'monotonic_after_ns': after}


def midpoint(mark):
    return (mark['monotonic_before_ns'] + mark['monotonic_after_ns']) // 2


class NamedModel:
    """One subscription,3 main or7 diagnostic channels, no missing-unit or unknown-unit defaults."""
    def __init__(self, diagnostics=False):
        self.specs = DIAGNOSTIC_SPECS if diagnostics else SPECS
        if sys.platform != 'darwin':
            raise Invalid('This source requires the reviewed macOS IOReport ABI')
        self.cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.ior = c.CDLL('/usr/lib/libIOReport.dylib')
        ptr = c.c_void_p
        self._bind(self.cf, 'CFStringCreateWithCString', [ptr, c.c_char_p, c.c_uint32], ptr)
        self._bind(self.cf, 'CFStringGetCString', [ptr, c.c_char_p, c.c_long, c.c_uint32], c.c_bool)
        self._bind(self.cf, 'CFGetTypeID', [ptr], c.c_ulong)
        for name in ('CFDictionaryGetTypeID', 'CFArrayGetTypeID', 'CFStringGetTypeID'):
            self._bind(self.cf, name, [], c.c_ulong)
        self._bind(self.cf, 'CFDictionaryGetValue', [ptr, ptr], ptr)
        self._bind(self.cf, 'CFDictionarySetValue', [ptr, ptr, ptr], None)
        self._bind(self.cf, 'CFDictionaryCreateMutableCopy', [ptr, c.c_long, ptr], ptr)
        self._bind(self.cf, 'CFArrayGetCount', [ptr], c.c_long)
        self._bind(self.cf, 'CFArrayGetValueAtIndex', [ptr, c.c_long], ptr)
        self._bind(self.cf, 'CFArrayCreateMutable', [ptr, c.c_long, c.POINTER(CFArrayCallBacks)], ptr)
        self._bind(self.cf, 'CFArrayAppendValue', [ptr, ptr], None)
        self._bind(self.cf, 'CFRelease', [ptr], None)
        self._bind(self.ior, 'IOReportCopyChannelsInGroup', [ptr, ptr, c.c_uint64, c.c_uint64, c.c_uint64], ptr)
        self._bind(self.ior, 'IOReportCreateSubscription', [ptr, ptr, c.POINTER(ptr), c.c_uint64, ptr], ptr)
        self._bind(self.ior, 'IOReportCreateSamples', [ptr, ptr, ptr], ptr)
        self._bind(self.ior, 'IOReportCreateSamplesDelta', [ptr, ptr, ptr], ptr)
        for name in ('IOReportChannelGetGroup', 'IOReportChannelGetSubGroup',
                     'IOReportChannelGetChannelName', 'IOReportChannelGetUnitLabel'):
            self._bind(self.ior, name, [ptr], ptr)
        self._bind(self.ior, 'IOReportChannelGetFormat', [ptr], c.c_uint8)
        for name in ('IOReportChannelGetUnit', 'IOReportChannelGetChannelID', 'IOReportChannelGetDriverID'):
            self._bind(self.ior, name, [ptr], c.c_uint64)
        self._bind(self.ior, 'IOReportSimpleGetIntegerValue', [ptr, c.c_int32], c.c_int64)
        self.key = self._string('IOReportChannels')
        group = self._string('Energy Model')
        original = None
        array = None
        try:
            original = self.ior.IOReportCopyChannelsInGroup(group, None, 0, 0, 0)
            choices = {}
            for channel in self._channels(original):
                name = self._text(self.ior.IOReportChannelGetChannelName(channel))
                if name in self.specs:
                    if name in choices:
                        raise Invalid('Duplicate selected channel: ' + name)
                    self._metadata(channel)
                    choices[name] = channel
            if set(choices) != set(self.specs):
                raise Invalid('Required named model channels are not uniquely available')
            self.desired = self.cf.CFDictionaryCreateMutableCopy(None, 0, original)
            if not self.desired:
                raise Invalid('Cannot create filtered channel dictionary')
            callbacks = CFArrayCallBacks.in_dll(self.cf, 'kCFTypeArrayCallBacks')
            array = self.cf.CFArrayCreateMutable(None, len(self.specs), c.byref(callbacks))
            if not array:
                raise Invalid('Cannot createselected-channel array')
            for name in self.specs:
                self.cf.CFArrayAppendValue(array, choices[name])
            self.cf.CFDictionarySetValue(self.desired, self.key, array)
            self.subscribed = ptr()
            self.subscription = self.ior.IOReportCreateSubscription(None, self.desired,
                                          c.byref(self.subscribed), 0, None)
            if not self.subscription or not self.subscribed:
                raise Invalid('Unprivilegedselected-channel subscription unavailable; no auth workaround')
            self.expected = self._read(self.subscribed, values=False)
            if set(self.expected) != set(self.specs):
                raise Invalid('Subscribed channels do not match exactselected-channel schema')
        finally:
            self.release(array)
            self.release(original)
            self.release(group)
        # subscription/subscribed/desired/key retained once for process lifetime.
        # No unverified private destructor is called; OS reclaims on process exit.
        # Per-sample and delta Create objects are released in all paths below.

    @staticmethod
    def _bind(lib, name, arguments, result):
        fn = getattr(lib, name)
        fn.argtypes = arguments
        fn.restype = result

    def _string(self, text):
        value = self.cf.CFStringCreateWithCString(None, text.encode(), UTF8)
        if not value:
            raise Invalid('Cannot create channel key')
        return value

    def _text(self, value):
        if not value:
            return None
        if self.cf.CFGetTypeID(value) != self.cf.CFStringGetTypeID():
            raise Invalid('Nonstring native channel metadata')
        data = c.create_string_buffer(4096)
        if not self.cf.CFStringGetCString(value, data, len(data), UTF8):
            raise Invalid('Unreadable channel metadata')
        return data.value.decode('utf-8', errors='strict')

    def _channels(self, sample):
        if not sample or self.cf.CFGetTypeID(sample) != self.cf.CFDictionaryGetTypeID():
            raise Invalid('Native channel dictionary unavailable')
        array = self.cf.CFDictionaryGetValue(sample, self.key)
        if not array or self.cf.CFGetTypeID(array) != self.cf.CFArrayGetTypeID():
            raise Invalid('Native channel array unavailable')
        count = self.cf.CFArrayGetCount(array)
        if not 1 <= count <= 4096:
            raise Invalid('Unexpected channel array size')
        for index in range(count):
            value = self.cf.CFArrayGetValueAtIndex(array, index)
            if not value or self.cf.CFGetTypeID(value) != self.cf.CFDictionaryGetTypeID():
                raise Invalid('Native channel entry unavailable')
            yield value

    def _metadata(self, channel):
        ior = self.ior
        name = self._text(ior.IOReportChannelGetChannelName(channel))
        if name not in self.specs:
            raise Invalid('Unexpected subscribed model channel')
        result = {'name': name, 'group': self._text(ior.IOReportChannelGetGroup(channel)),
                  'subgroup': self._text(ior.IOReportChannelGetSubGroup(channel)),
                  'unit': self._text(ior.IOReportChannelGetUnitLabel(channel)),
                  'unit_code': int(ior.IOReportChannelGetUnit(channel)),
                  'format': int(ior.IOReportChannelGetFormat(channel)),
                  'driver_id': int(ior.IOReportChannelGetDriverID(channel)),
                  'channel_id': int(ior.IOReportChannelGetChannelID(channel))}
        spec = self.specs[name]
        if result['group'] != 'Energy Model' or result['subgroup'] is not None or \
           result['unit'] != spec['unit'] or result['unit_code'] != spec['unit_code'] or result['format'] != 1:
            raise Invalid('Exact model name/group/subgroup/format/unit schema mismatch: ' + name)
        return result

    def _read(self, native, values):
        result = {}
        for channel in self._channels(native):
            meta = self._metadata(channel)
            name = meta['name']
            if name in result:
                raise Invalid('Duplicate subscribed/sample channel: ' + name)
            row = {'metadata': meta}
            if values:
                row['raw'] = int(self.ior.IOReportSimpleGetIntegerValue(channel, 0))
                if row['raw'] < 0:
                    raise Invalid('Negative model counter value: ' + name)
            result[name] = row
        if set(result) != set(self.specs):
            raise Invalid('Missing/extra selected channel; no zero substitution')
        return result

    def sample(self):
        before = stamp()
        native = self.ior.IOReportCreateSamples(self.subscription, self.subscribed, None)
        after = stamp()
        try:
            readings = self._read(native, values=True)
            for name, row in readings.items():
                if row['metadata'] != self.expected[name]['metadata']:
                    raise Invalid('Model channel identity changed: ' + name)
            return native, {'call_before': before, 'call_after': after, 'counters': readings}
        except BaseException:
            self.release(native)
            raise

    def delta(self, before_native, after_native, before_row, after_row):
        native = self.ior.IOReportCreateSamplesDelta(before_native, after_native, None)
        try:
            readings = self._read(native, values=True)
            result = {}
            for name in self.specs:
                previous = before_row['counters'][name]
                current = after_row['counters'][name]
                delta = readings[name]
                if delta['metadata'] != previous['metadata'] or delta['metadata'] != current['metadata']:
                    raise Invalid('Counter identity changed inside delta: ' + name)
                direct = current['raw'] - previous['raw']
                if direct < 0 or delta['raw'] != direct:
                    raise Invalid('Reset, noncumulative or inconsistent delta: ' + name)
                result[name] = {'metadata': delta['metadata'],
                                'before_raw': previous['raw'], 'after_raw': current['raw'],
                                'api_delta_raw': delta['raw'],
                                'delta_nj': direct * self.specs[name]['to_nj']}
            return result
        finally:
            self.release(native)

    def release(self, native):
        if native:
            self.cf.CFRelease(native)


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
                      help='Diagnostic mode only: finite1Hz intervals10..180;7 validation channels')
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
    collected = 0
    reason = None
    try:
        model = NamedModel(diagnostics=diagnostics)
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
        write(fd, {'kind': 'header', 'schema': 'ioreport-named-model-energy-v2', 'stamp': anchor,
                   'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'mode': 'diagnostics' if diagnostics else 'main',
                   'scope': 'Machine-wide IOReport Energy Model CPU Energy and GPU Energy, separately and sum; ANE0 secondary',
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
            model.release(previous_native)
            previous_native, previous = current_native, current
            current_native = None
    except (Exception, KeyboardInterrupt) as error:
        reason = type(error).__name__ + ': ' + str(error)
    finally:
        if model:
            model.release(previous_native)
            model.release(current_native)
        write(fd, {'kind': 'footer', 'stamp': stamp(), 'complete': reason is None and 'offsets' in locals() and collected == len(offsets),
                   'snapshots': collected, 'expected_snapshots': len(offsets) if 'offsets' in locals() else None,
                   'reason': reason, 'observer_cpu_ns': time.process_time_ns() - observer_cpu_start,
                   'observer_elapsed_ns': time.monotonic_ns() - observer_start})
        os.close(fd)
    return 0 if reason is None and collected == len(offsets) else 2


if __name__ == '__main__':
    sys.exit(main())
