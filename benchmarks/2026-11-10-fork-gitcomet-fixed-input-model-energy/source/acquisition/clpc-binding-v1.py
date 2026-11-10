"""SOURCE ONLY: explicit-init CLPC raw binding; no native initialization on import.

Mirrors macmon v0.11.0 descriptors for this Mac/boot. Assigned names/nJ units
are firmware-derived upstream conventions, not independently discovered units.
No CLI, fallback, workload, application, permission, privilege or settings API.
"""
import ctypes as c
import hashlib
import importlib.util
import os
from pathlib import Path
import plistlib
import sys
from types import MethodType

BASE_SHA256 = 'd4b098c69a27319c866f16c1ef8cd7a03072f4f7bc25f2403766d827dc9ba9e2'
UPSTREAM_COMMIT = '08653ddeb3c1206b6cc35d5a2bb442b4c64ad810'
EXPECTED_OS = ('27.2', '26B123')
EXPECTED_BUNDLE = 'com.apple.driver.AppleT6050CLPC'
EXPECTED_REGISTRY_ID = 0x1000005ce
CLPC_IDS = {'CPU Energy': 0x00000010d3ab60bb,
            'GPU Energy': 0x0000001927cd4ce5, 'ANE': 0x000000188c0f1c59}
NJ_UNIT = (3 << 56) | (118 << 32)
CHANNEL_TYPE = 1 | (2 << 16) | (1 << 32)
SPECS = {name:{'unit':'nJ','unit_code':NJ_UNIT,'to_nj':1}
         for name in ('CPU Energy','GPU Energy','ANE0','CLPC GPU Energy')}


def descriptors(driver_id):
    if type(driver_id) is not int or driver_id != EXPECTED_REGISTRY_ID:
        raise RuntimeError('Unregistered local CLPC driver ID; no inferred mapping')
    return [{'DriverID': driver_id, 'DriverName': 'AppleCLPC',
             'IOReportGroupName': 'CLPC', 'IOReportSubGroupName': 'Energy Counters',
             'IOReportChannelInfo': {'IOReportChannelUnit': NJ_UNIT},
             'LegendChannel': [report_id, CHANNEL_TYPE, name]}
            for name, report_id in CLPC_IDS.items()]


class CLPCBinding:
    def __init__(self):
        self._owned = []; self._closed = False
        if sys.platform != 'darwin' or os.geteuid() == 0:
            raise RuntimeError('Ordinary macOS user required')
        with open('/System/Library/CoreServices/SystemVersion.plist', 'rb') as stream:
            version = plistlib.load(stream)
        if (version.get('ProductVersion'), version.get('ProductBuildVersion')) != EXPECTED_OS:
            raise RuntimeError('Unregistered OS/build; retained model protocol must be reviewed')
        path = Path(__file__).resolve().parent / 'ioreport-model-v1/collect.py'
        if hashlib.sha256(path.read_bytes()).hexdigest() != BASE_SHA256:
            raise RuntimeError('Frozen raw sample/delta implementation changed')
        spec = importlib.util.spec_from_file_location('frozen_named_model_for_clpc', path)
        self.base = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.base)
        for name in ('_string', '_text', '_channels', '_read', 'release'):
            setattr(self, name, MethodType(getattr(self.base.NamedModel, name), self))
        self.cf = c.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.ior = c.CDLL('/usr/lib/libIOReport.dylib')
        self.io = c.CDLL('/System/Library/Frameworks/IOKit.framework/IOKit')
        p = c.c_void_p; bind = self.base.NamedModel._bind
        for name, args, result in [
            ('CFStringCreateWithCString', [p,c.c_char_p,c.c_uint32], p),
            ('CFStringGetCString', [p,c.c_char_p,c.c_long,c.c_uint32], c.c_bool),
            ('CFGetTypeID', [p], c.c_ulong), ('CFDictionaryGetTypeID', [], c.c_ulong),
            ('CFArrayGetTypeID', [], c.c_ulong), ('CFStringGetTypeID', [], c.c_ulong),
            ('CFDictionaryGetValue', [p,p], p), ('CFDictionarySetValue', [p,p,p], None),
            ('CFDictionaryCreateMutableCopy', [p,c.c_long,p], p),
            ('CFArrayGetCount', [p], c.c_long), ('CFArrayGetValueAtIndex', [p,c.c_long], p),
            ('CFArrayCreateMutable', [p,c.c_long,c.POINTER(self.base.CFArrayCallBacks)], p),
            ('CFArrayAppendValue', [p,p], None), ('CFRelease', [p], None),
            ('CFDataCreate', [p,c.c_void_p,c.c_long], p),
            ('CFPropertyListCreateWithData', [p,p,c.c_ulong,c.POINTER(c.c_long),c.POINTER(p)], p)]:
            bind(self.cf, name, args, result)
        for name, args, result in [
            ('IOReportCopyChannelsInGroup', [p,p,c.c_uint64,c.c_uint64,c.c_uint64], p),
            ('IOReportCreateSubscription', [p,p,c.POINTER(p),c.c_uint64,p], p),
            ('IOReportCreateSamples', [p,p,p], p), ('IOReportCreateSamplesDelta', [p,p,p], p),
            ('IOReportSimpleGetIntegerValue', [p,c.c_int32], c.c_int64),
            ('IOReportChannelGetFormat', [p], c.c_uint8)]: bind(self.ior,name,args,result)
        for name in ('Group','SubGroup','ChannelName','UnitLabel'):
            bind(self.ior,'IOReportChannelGet'+name,[p],p)
        for name in ('Unit','ChannelID','DriverID'):
            bind(self.ior,'IOReportChannelGet'+name,[p],c.c_uint64)
        for name, args, result in [
            ('IOServiceMatching', [c.c_char_p], p),
            ('IOServiceGetMatchingServices', [c.c_uint32,p,c.POINTER(c.c_uint32)], c.c_int32),
            ('IOIteratorNext', [c.c_uint32], c.c_uint32),
            ('IORegistryEntryGetRegistryEntryID', [c.c_uint32,c.POINTER(c.c_uint64)], c.c_int32),
            ('IORegistryEntryCreateCFProperties', [c.c_uint32,c.POINTER(p),p,c.c_uint32], c.c_int32),
            ('IOObjectRelease', [c.c_uint32], c.c_int32)]: bind(self.io,name,args,result)
        self.specs = SPECS
        self.provenance = {'upstream':'macmonv0.11.0','upstream_commit':UPSTREAM_COMMIT,'os_version':EXPECTED_OS[0],
                           'os_build':EXPECTED_OS[1],'clpc_bundle':EXPECTED_BUNDLE,
                           'clpc_registry_id':EXPECTED_REGISTRY_ID,
                           'base_source_sha256':BASE_SHA256,
                           'scope':'Machine-wide named model counters; no physical/system/app energy claim',
                           'unit_assignment':'CLPC descriptors assigned nJ from upstream firmware analysis; not independent API unit proof'}
        self.key = self._keep(self._string('IOReportChannels'))
        group = original = array = encoded = None
        try:
            self._verify_registry()
            group = self._string('Energy Model')
            original = self.ior.IOReportCopyChannelsInGroup(group,None,0,0,0)
            gpu = [x for x in self._channels(original)
                   if self._text(self.ior.IOReportChannelGetChannelName(x)) == 'GPU Energy']
            if len(gpu) != 1: raise RuntimeError('Native legacy GPU channel not unique')
            self._metadata(gpu[0])
            encoded = self._plist({'IOReportChannels':descriptors(EXPECTED_REGISTRY_ID)})
            self.desired = self._keep(self.cf.CFDictionaryCreateMutableCopy(None,0,original))
            callbacks = self.base.CFArrayCallBacks.in_dll(self.cf,'kCFTypeArrayCallBacks')
            array = self.cf.CFArrayCreateMutable(None,4,c.byref(callbacks))
            if not array: raise RuntimeError('Cannot create CLPC selection array')
            for item in self._channels(encoded): self.cf.CFArrayAppendValue(array,item)
            self.cf.CFArrayAppendValue(array,gpu[0])
            self.cf.CFDictionarySetValue(self.desired,self.key,array)
            self.subscribed = p()
            self.subscription = self.ior.IOReportCreateSubscription(None,self.desired,c.byref(self.subscribed),0,None)
            if self.subscription: self._owned.append(self.subscription)
            if self.subscribed: self._owned.append(self.subscribed.value)
            if not self.subscription or not self.subscribed: raise RuntimeError('Unprivileged CLPC subscription unavailable')
            self.expected = self._read(self.subscribed,values=False)
        except BaseException:
            self.close(); raise
        finally:
            for value in (array,original,group,encoded): self.release(value)

    def _keep(self, value):
        if not value: raise RuntimeError('CF creation failed')
        self._owned.append(value); return value

    def _plist(self, value):
        payload = plistlib.dumps(value,fmt=plistlib.FMT_BINARY)
        data = self.cf.CFDataCreate(None,c.c_char_p(payload),len(payload)); error = c.c_void_p()
        if not data: raise RuntimeError('Cannot create descriptor data')
        try:
            # Public kCFPropertyListMutableContainersAndLeaves=2: IOReport caches metadata.
            result = self.cf.CFPropertyListCreateWithData(None,data,2,None,c.byref(error))
            if not result or error: self.release(result); raise RuntimeError('Cannot decode mutable descriptors')
            return result
        finally: self.release(data); self.release(error)

    def _verify_registry(self):
        iterator = c.c_uint32(); seen = []
        matching = self.io.IOServiceMatching(b'AppleCLPC')
        if not matching: raise RuntimeError('AppleCLPC matching dictionary unavailable')
        if self.io.IOServiceGetMatchingServices(0,matching,c.byref(iterator)) != 0:
            if iterator: self.io.IOObjectRelease(iterator)
            raise RuntimeError('AppleCLPC registry unavailable')
        try:
            while entry := self.io.IOIteratorNext(iterator):
                properties = c.c_void_p(); key = None
                try:
                    driver = c.c_uint64()
                    if self.io.IORegistryEntryGetRegistryEntryID(entry,c.byref(driver)) != 0 or self.io.IORegistryEntryCreateCFProperties(entry,c.byref(properties),None,0) != 0:
                        raise RuntimeError('CLPC registry identity unreadable')
                    if not properties or self.cf.CFGetTypeID(properties)!=self.cf.CFDictionaryGetTypeID():
                        raise RuntimeError('CLPC registry properties unavailable')
                    key = self._string('CFBundleIdentifier')
                    seen.append((driver.value,self._text(self.cf.CFDictionaryGetValue(properties,key))))
                finally: self.release(key); self.release(properties); self.io.IOObjectRelease(entry)
        finally: self.io.IOObjectRelease(iterator)
        if seen != [(EXPECTED_REGISTRY_ID,EXPECTED_BUNDLE)]: raise RuntimeError('Exact single CLPC provider identity changed')

    def _metadata(self, channel):
        i = self.ior
        m = {'native_name':self._text(i.IOReportChannelGetChannelName(channel)),
             'group':self._text(i.IOReportChannelGetGroup(channel)),
             'subgroup':self._text(i.IOReportChannelGetSubGroup(channel)),
             'unit':self._text(i.IOReportChannelGetUnitLabel(channel)), 'unit_code':int(i.IOReportChannelGetUnit(channel)),
             'format':int(i.IOReportChannelGetFormat(channel)), 'driver_id':int(i.IOReportChannelGetDriverID(channel)),
             'channel_id':int(i.IOReportChannelGetChannelID(channel))}
        if m['group']=='CLPC' and m['subgroup']=='Energy Counters' and m['native_name'] in CLPC_IDS:
            if m['driver_id']!=EXPECTED_REGISTRY_ID or m['channel_id']!=CLPC_IDS[m['native_name']]: raise RuntimeError('CLPC report/provider mismatch')
            m.update(name={'CPU Energy':'CPU Energy','GPU Energy':'CLPC GPU Energy','ANE':'ANE0'}[m['native_name']],source_kind='AppleCLPC assigned descriptor',unit_origin='Assigned nJ/name descriptor from macmonv0.11.0 firmware-derived mapping; not independent unit proof')
        elif m['group']=='Energy Model' and m['subgroup'] is None and m['native_name']=='GPU Energy':
            m.update(name='GPU Energy',source_kind='Native Energy Model GPU',unit_origin='Native legacy channel metadata; no constructed descriptor')
        else: raise RuntimeError('Unexpected selected CLPC/legacy GPU channel')
        if m['unit']!='nJ' or m['unit_code']!=NJ_UNIT or m['format']!=1: raise RuntimeError('Exact scalar/nJ schema mismatch')
        return m

    def sample(self):
        if self._closed: raise RuntimeError('Binding closed')
        return self.base.NamedModel.sample(self)

    def delta(self, *args):
        if self._closed: raise RuntimeError('Binding closed')
        return self.base.NamedModel.delta(self,*args)

    def close(self):
        if self._closed: return
        self._closed = True
        while self._owned: self.release(self._owned.pop())
