#!/usr/bin/env python3
"""Energy v9 startup-readiness lifecycle SOURCE ONLY. Do not run until later gates are satisfied.

Direct owned app PIDs, native posting-only driver, separate named IOReport
collector, private profiles, retained attempts and guarded Fork restoration.
No AX, screenshots, app input fallback, privileges or permission requests.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ORDER = ['gitcomet','fork','fork','gitcomet','fork','gitcomet','gitcomet','fork'] * 2
FORBIDDEN_ENV = ('GITCOMET_', 'GPUI_', 'GIT_', 'DYLD_', 'MTL_', 'METAL_', 'RUST_')
BUSY = {'cargo','rustc','swiftc','swift-frontend','xcodebuild','bazel','make','ninja',
        'world of warcraft','sample','xctrace','instruments','screencapture','ffmpeg'}


class FatalTrial(RuntimeError):
    pass


def need(ok, message):
    if not ok: raise RuntimeError(message)


def fatal(ok, message):
    if not ok: raise FatalTrial(message)


def load(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def cpu(): return time.process_time_ns()


def save(path, value):
    path=Path(path)
    temporary=path.with_name(path.name+'.pending-'+str(os.getpid()))
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()


def command(argv, timeout=10, env=None):
    return subprocess.check_output([str(x) for x in argv],text=True,timeout=timeout,env=env)


def processes():
    result={}
    for line in command(['/bin/ps','-axo','pid=,comm=']).splitlines():
        pair=line.strip().split(None,1)
        if len(pair)==2: result[int(pair[0])]=pair[1]
    return result


def apps():
    return {pid:path for pid,path in processes().items() if Path(path).name.lower() in ('gitcomet','fork')}


def quiet(expected=None):
    found=processes()
    fatal(not [path for path in found.values() if Path(path).name.lower() in BUSY], 'Competing build/game/profiler/video process')
    measured={pid:path for pid,path in found.items() if Path(path).name.lower() in ('gitcomet','fork')}
    if expected is not None: need(measured==expected,'Unexpected app PID/executable during owned trial')
    return {'unix_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'load_average':os.getloadavg(),
            'app_processes':measured,'busy_found':False}


def tree_hash(root):
    root=Path(root)
    need(root.is_dir() and not root.is_symlink(),'Missing regular profile template')
    entries=[]
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink(),'Profile symlink not allowed')
        if path.is_file(): entries.append([str(path.relative_to(root)),sha(path)])
    need(entries,'Empty profile template')
    return hashlib.sha256(json.dumps(entries,separators=(',',':')).encode()).hexdigest()


def identity(pid):
    line=command(['/bin/ps','-p',pid,'-o','lstart=,comm=']).strip()
    need(line,'Owned process missing')
    return line


def repository(path):
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env['GIT_OPTIONAL_LOCKS']='0'
    def git(*args): return subprocess.check_output(['/usr/bin/git','-C',path,*args],env=env,timeout=30)
    index=Path(git('rev-parse','--git-path','index').decode().strip())
    if not index.is_absolute(): index=Path(path)/index
    return {'head':git('rev-parse','HEAD').decode().strip(),
            'status_sha256':hashlib.sha256(git('status','--porcelain=v1','-z')).hexdigest(),
            'index_sha256':sha(index) if index.exists() else None}


def profile_identity(value, condition):
    if condition=='gitcomet':
        return {'paths':value['open_repos'],'active':value['active_repo'],
                'workspace_ids':[row.get('id') for row in value.get('workspaces',[])]}
    wi=value['activeWorkspaceIndex']; workspace=value['workspaces'][wi]
    window=workspace['windows'][workspace.get('activeWindowIndex',0)]
    paths=window['tabs']
    return {'paths':paths,'active':paths[window['activeTabIndex']],
            'workspace_ids':[row['id'] for row in value['workspaces']]}


def fork_changes(before, after, allowed, path=()):
    key='/'.join(str(x) for x in path)
    if isinstance(before,dict):
        need(type(after) is dict and set(before)==set(after),'Fork keys/type changed: '+key)
        return sum((fork_changes(before[k],after[k],allowed,path+(k,)) for k in before),[])
    if isinstance(before,list):
        need(type(after) is list and len(before)==len(after),'Fork list/repository count/type changed: '+key)
        return sum((fork_changes(a,b,allowed,path+(i,)) for i,(a,b) in enumerate(zip(before,after))),[])
    if type(before) is type(after) and before==after: return []
    # Only explicit existing frame-coordinate leaves, exact calibrated value.
    frame_leaf=(path and path[-1] in ('x','y','width','height') and
                ('frame' in path or 'lastWindowFrame' in path))
    if key in allowed:
        need(frame_leaf and type(before) in (int,float) and type(after) in (int,float) and
             math.isfinite(after) and after==allowed[key],'Unexpected/uncalibrated Fork runtime field: '+key)
        return [key]
    raise RuntimeError('Unexpected Fork state/repository/order/ID/type change: '+key)


def guarded_replace(path, expected_sha, data):
    path=Path(path)
    need(path.is_file() and not path.is_symlink(),'Session is not a regular file')
    before=path.stat()
    need(before.st_uid==os.getuid() and sha(path)==expected_sha,'Session changed; refusing overwrite')
    temp=path.with_name(path.name+'.energy-'+str(os.getpid()))
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream: stream.write(data);stream.flush();os.fsync(stream.fileno())
        now=path.stat()
        need((now.st_dev,now.st_ino)==(before.st_dev,before.st_ino) and sha(path)==expected_sha,
             'Session changed during guarded replacement')
        os.replace(temp,path)
    finally:
        if temp.exists(): temp.unlink()
    need(path.read_bytes()==data,'Guarded session replacement verification failed')


def environment(cfg, pid):
    value=load_json_output([cfg['environment_helper'],str(pid)])
    battery=command(['/usr/bin/pmset','-g','batt'])
    value['power']={'source':'AC' if 'AC Power' in battery else 'Battery' if 'Battery Power' in battery else 'unknown',
                    'charging':'not charging' not in battery.lower() and 'charging' in battery.lower(),
                    'percent':int(re.search(r'(\d+)%;',battery).group(1)) if re.search(r'(\d+)%;',battery) else None}
    return value


def load_json_output(argv, timeout=10): return json.loads(command(argv,timeout=timeout))


def environment_check(value, reference, pid):
    need(value['frontmost_pid']==pid,'Target is not foreground')
    fatal(value['thermal_state']==0,'Thermal state is not nominal')
    for key in ('screens','target_windows','low_power_mode','reduce_motion','frontmost_bundle'):
        fatal(value[key]==reference[key],'Calibrated environment changed: '+key)
    for key in ('source','charging'):
        fatal(value['power'][key]==reference['power'][key],'Power/charge state changed')


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


def frozen(cfg):
    need(cfg.get('ready') is True,'Configuration is source-only/uncharacterized; stop')
    required={str(Path(__file__).resolve()),cfg['protocol'],cfg['collector'],cfg['driver'],cfg['driver_source'],
              cfg['native_control'],cfg['native_control_source'],cfg['environment_helper'],cfg['environment_source'],cfg['fork_template'],cfg['repository_set'],cfg['io_source_lock'],
              cfg['capability_checker'],cfg['capability_capture'],cfg['capability_markers'],cfg['clpc_binding'],
              *cfg['environment_references'].values(),*cfg['characterization'].values()}
    need(required <= set(cfg['frozen_files']),'Every source/binary/profile/evidence file must be explicitly frozen')
    for path, expected in cfg['frozen_files'].items(): need(sha(path)==expected,'Frozen source/binary/input changed: '+path)
    io_lock=load(cfg['io_source_lock'])
    for name,expected in io_lock['source_hashes'].items():
        need(sha(Path(cfg['io_source_lock']).parent/name)==expected,'Frozen IOReport source/validation packet changed')
    need(tree_hash(cfg['gc_template'])==cfg['gc_template_tree_sha256'],'Copied GC40 template changed')
    protocol=load(cfg['protocol'])
    need(protocol['schema']=='energy-identical-pixel-event-stream-v9-clpc' and protocol['order']==ORDER,'Wrong v8 protocol/order')
    for condition, spec in protocol['conditions'].items():
        bundle=Path(spec['app']); info=plistlib.loads((bundle/'Contents/Info.plist').read_bytes())
        binary=bundle/'Contents/MacOS'/info['CFBundleExecutable']
        need(str(binary)==cfg['executables'][condition] and sha(binary)==spec['binary_sha256'],'Installed app identity changed')
        if condition=='fork': need(info['CFBundleShortVersionString']==spec['version'],'Fork version changed')
    need(type(cfg['fork_startup_settle_seconds']) in (int,float) and 0<=cfg['fork_startup_settle_seconds']<=60,'Invalid frozen Fork settle')
    need(type(cfg['pixels']) is int and 1<=cfg['pixels']<=64,'Calibrated integer pixel magnitude missing')
    for condition in ORDER[:2]:
        point=cfg['points'][condition]
        need(len(point)==2 and all(type(x) in (int,float) and math.isfinite(x) and abs(x)<=32768 for x in point),'Invalid calibrated point')
        reference=load(cfg['environment_references'][condition])
        need(reference['thermal_state']==0,'Calibration environment not nominal')
        need(type(reference.get('power')) is dict and reference['power'].get('source') in ('AC','Battery') and
             type(reference['power'].get('charging')) is bool,'Frozen environment must include actual source/charging witness')
    report=load_json_output([sys.executable,'-B',cfg['capability_checker'],cfg['capability_capture'],cfg['capability_markers']],timeout=20)
    need(report['validation_passed'] is True,'Named-counter capability gate has not passed')
    need(set(cfg['characterization'])=={'gitcomet','fork'},'Both output characterization records required')
    for condition,evidence_path in cfg['characterization'].items():
        evidence=load(evidence_path)
        need(condition in ('gitcomet','fork') and evidence['passed'] is True and evidence['repeat_count']>=2 and
             evidence['motion'] is True and evidence['no_edge'] is True and evidence['return_error_rows']<=1 and
             evidence['distance_repeat_fraction']<=.10,'Output characterization missing/failed')
        need(evidence['driver_source_sha256']==sha(cfg['driver_source']) and evidence['pixels']==cfg['pixels'] and
             evidence['point']==cfg['points'][condition],'Characterization differs from frozen stream')
    return {'config_source_contract':'v8','tree_sha256':cfg['gc_template_tree_sha256'],
            'files_sha256':cfg['frozen_files'],'app_identities':protocol['conditions']}


ROUTE='CGEvent.post cgSessionEventTap plus one CGWarpMouseCursorPosition; no delivery acknowledgement'


def frozen_bounds(cfg,condition):
    reference=load(cfg['environment_references'][condition]);windows=reference['target_windows']
    need(len(windows)==1 and windows[0]['alpha']==1 and windows[0]['onscreen'] is True,'Need one frozen opaque onscreen window reference')
    bounds=windows[0]['bounds']
    need(set(bounds)=={'X','Y','Width','Height'} and all(type(v) in (int,float) and math.isfinite(v) for v in bounds.values()) and
         bounds['Width']>0 and bounds['Height']>0,'Invalid frozen public window rectangle')
    return bounds


def window_arguments(cfg,condition):
    bounds=frozen_bounds(cfg,condition)
    return sum(([flag,str(bounds[key])] for flag,key in [('--window-x','X'),('--window-y','Y'),('--window-width','Width'),('--window-height','Height')]),[])


def verify_description(cfg,condition,pid,description):
    point=cfg['points'][condition];bounds=frozen_bounds(cfg,condition);window=description['window']
    need(description['kind']=='target_description' and description['schema']=='native-scroll-target-description-v1' and
         description['no_warp_or_posts'] is True and description['pid']==description['frontmost_pid']==pid and
         description['x']==point[0] and description['y']==point[1] and type(window['id']) is int and window['id']>0 and
         window=={'id':window['id'],'x':bounds['X'],'y':bounds['Y'],'width':bounds['Width'],'height':bounds['Height']},
         'Fresh target metadata differs from owned PID/frozen rectangle/point')



def describe_target_ready(cfg, app, app_token, argv, run_dir):
    # Identical pre-input readiness contract for both conditions. No activation,
    # input, cursor warp, geometry relaxation or energy-result inspection here.
    start=time.monotonic();deadline=start+2
    attempts=[]
    def remaining():
        left=deadline-time.monotonic()
        need(left>0,'Target metadata readiness did not pass within absolute2s')
        return left
    try:
        while True:
            need(app.poll() is None,'Owned app exited before metadata readiness')
            token=command(['/bin/ps','-p',app.pid,'-o','lstart=,comm='],timeout=remaining()).strip()
            need(token==app_token,'Owned app identity changed before metadata readiness')
            foreground=load_json_output([cfg['native_control'],'--clock'],timeout=remaining())
            need(foreground['frontmost_pid']==app.pid,'Foreign foreground during metadata readiness; no reactivation/input')
            attempt={'index':len(attempts),'begin_monotonic_ns':time.monotonic_ns(),
                     'frontmost_pid':foreground['frontmost_pid'],'identity_matches':True}
            attempts.append(attempt)
            try:
                description=load_json_output(argv,timeout=remaining())
                remaining()
                attempt.update(passed=True,end_monotonic_ns=time.monotonic_ns())
                return description
            except subprocess.CalledProcessError as error:
                attempt.update(passed=False,end_monotonic_ns=time.monotonic_ns(),
                               returncode=error.returncode,output=error.output)
                # Only metadata command rejection is retried. Identity/foreign
                # foreground/timeouts/malformed output fail this attempt outright.
                time.sleep(min(.05,remaining()))
    finally:
        save(Path(run_dir)/'target-description-attempts.json',
             {'schema':'energy-v9-target-readiness-v1','limit_seconds':2,
              'started_monotonic_ns':int(start*1e9),'ended_monotonic_ns':time.monotonic_ns(),
              'attempts':attempts})


def verify_route_header(cfg,condition,pid,header,description):
    verify_description(cfg,condition,pid,description);point=cfg['points'][condition]
    need(header['schema']=='native-pixel-session-energy-v1' and header['route']==ROUTE and
         header['pid']==pid and header['window_id']==description['window']['id'] and header['frozen_window']==description['window'] and
         header['x']==point[0] and header['y']==point[1] and header['pixels']==cfg['pixels'],
         'Native route/header no longer matches described owned target')


def verify_cursor_completion(raw):
    restored=[row for row in raw if row['kind']=='cursor_restoration']
    need(len(restored)==1 and restored[0]['attempted'] is True and restored[0]['result_code']==0,
         'Native cursor restore state is unavailable/changed/failed')
    accounting=[row for row in raw if row['kind']=='driver_accounting']
    need(len(accounting)==1,'Driver own-CPU accounting missing/duplicated')
    record=accounting[0]
    need(record['run_id']==raw[0]['run_id'] and all(type(record[k]) is int and record[k]>=0 for k in ('cpu_start_ns','cpu_end_ns','cpu_ns')) and
         record['cpu_end_ns']>=record['cpu_start_ns'] and record['cpu_ns']==record['cpu_end_ns']-record['cpu_start_ns'],
         'Driver own-CPU metadata arithmetic invalid')
    for mark in (record['observer_start'],record['observer_end']):
        need(all(type(mark[k]) in (int,float) and math.isfinite(mark[k]) for k in ('monotonic_ns','unix_s','pair_bracket_ns')) and
             0<=mark['pair_bracket_ns']<=50e6,'Driver CPU scope clock metadata invalid')
    need(record['observer_start']['monotonic_ns']<=raw[0]['origin_monotonic_ns']<record['observer_end']['monotonic_ns'],
         'Driver CPU scope clocks do not bracket timed origin')


def cleanup_child(child):
    if child is None or child.poll() is not None: return
    child.terminate()
    try: child.wait(timeout=3)
    except subprocess.TimeoutExpired: child.kill();child.wait(timeout=3)


def read_header(child, timeout, sink):
    os.set_blocking(child.stdout.fileno(),False)
    sel=selectors.DefaultSelector();sel.register(child.stdout,selectors.EVENT_READ)
    until=time.monotonic()+timeout; data=b''
    try:
        while b'\n' not in data:
            need(time.monotonic()<until,'Driver header timeout')
            for key,_ in sel.select(max(0,min(.05,until-time.monotonic()))):
                block=os.read(key.fd,65536)
                need(block,'Driver exited without complete header')
                data+=block;sink.write(block);sink.flush()
            need(len(data)<=65536,'Driver header unexpectedly large')
        header=json.loads(data.split(b'\n',1)[0])
        need(header['kind']=='header' and header['schema']=='native-pixel-session-energy-v1','Wrong driver header')
        return header,data
    finally: sel.close()


def slot_ordinal(manifest, slot):
    need(slot==len(manifest['runs'])+1,'Slots must be serial; pending/failed attempts retained')
    if slot<=16: return slot
    need(len(manifest['runs'])>=16 and slot<=20,'At most2 pair replacements after16planned runs')
    failed=[i for i in range(1,17,2) if not all(manifest['runs'][j-1]['valid'] for j in (i,i+1))]
    need(len(failed)<=2,'More than2 failed pairs; no further main attempts')
    plan=sum(([i,i+1] for i in failed),[])
    if 'replacement_ordinals' in manifest: need(manifest['replacement_ordinals']==plan,'Replacement plan changed')
    manifest['replacement_ordinals']=plan
    need(slot-17<len(plan),'No failed pair to replace')
    return plan[slot-17]


def run(cfg, config_path, series, slot):
    # All of this is read-only until existing-post access and gates pass.
    frozen(cfg)
    gate=subprocess.run([cfg['driver'],'--check-access'],capture_output=True,text=True,timeout=5)
    need(gate.returncode==0,'Native post access absent; no profile/ledger/lock modification and no permission request')
    lock_path=Path(cfg['lock']).resolve(strict=True)
    with lock_path.open('r+') as lock:
        need([os.fstat(lock.fileno()).st_dev,os.fstat(lock.fileno()).st_ino]==cfg['lock_identity'],'Shared mutex identity changed')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        quiet({})
        series=Path(series).absolute()
        need(not series.is_symlink(),'Series symlink refused')
        series.mkdir(parents=True,exist_ok=True,mode=0o700)
        need(series.stat().st_uid==os.getuid() and stat.S_IMODE(series.stat().st_mode)&0o077==0,'Series must be private user directory')
        manifest_path=series/'manifest.json'
        current_gc=sha(cfg['real_gc_session']);current_fork=sha(cfg['real_fork_session'])
        if manifest_path.exists():
            manifest=load(manifest_path)
            need(not manifest.get('series_stopped'),'Series is stopped; no reset/relaunch/profile write allowed')
            need(manifest['config_sha256']==sha(config_path),'Frozen config changed during series')
            need(manifest['real_gc_sha256']==current_gc and manifest['real_fork_sha256']==current_fork,'Real sessions changed between trials')
        else:
            need(slot==1,'First slot must be1')
            shutil.copyfile(config_path,series/'config.local-only.json');os.chmod(series/'config.local-only.json',0o600)
            manifest={'schema':'energy-v4-series','series_stopped':False,'config_sha256':sha(config_path),'order':ORDER,'runs':[],
                      'real_gc_sha256':current_gc,'real_fork_sha256':current_fork,
                      'repository':repository(cfg['active_repository']),'created_unix_ns':time.time_ns()}
        ordinal=slot_ordinal(manifest,slot);condition=ORDER[ordinal-1]
        need(repository(cfg['active_repository'])==manifest['repository'],'Active repo HEAD/status/index changed')
        run_dir=series/f'{slot:02d}-{condition}-ordinal{ordinal}'
        run_dir.mkdir(mode=0o700)
        entry={'slot':slot,'original_ordinal':ordinal,'condition':condition,'valid':False,'status':'pending-before-launch',
               'run':str(run_dir),'failures':['pending'],'ax_state':'Unverified; instrumentation source makes noAXqueries'}
        manifest['runs'].append(entry);save(manifest_path,manifest)
        app=driver=collector=None; app_token=None; transaction=None; failures=[]; files=[]; fatal_failure=False
        started=time.monotonic();parent_cpu=cpu()
        try:
            def watchdog(signum,frame): raise TimeoutError('Finite300s owned-trial watchdog expired')
            signal.signal(signal.SIGALRM,watchdog);signal.setitimer(signal.ITIMER_REAL,300)
            shutil.copyfile(cfg['real_gc_session'],run_dir/'real-gc-before.local-only.json')
            os.chmod(run_dir/'real-gc-before.local-only.json',0o600)
            save(run_dir/'controls-before.local-only.json',frozen(cfg))
            before_repo=repository(cfg['active_repository']);save(run_dir/'repository-before.local-only.json',before_repo)
            env={k:v for k,v in os.environ.items() if not k.startswith(FORBIDDEN_ENV)}
            env['LC_ALL']='C'
            entry['launch_env_names']=sorted(env)
            if condition=='gitcomet':
                shutil.copytree(cfg['gc_template'],run_dir/'profile')
                env.update(GITCOMET_PROFILE_ROOT=str(run_dir/'profile'),GITCOMET_STARTUP_TRACE=str(run_dir/'startup.jsonl'),
                           GITCOMET_PERF_STARTUP_PROBE='1')
                session=run_dir/'profile/state/gitcomet/session.json'
            else:
                session=Path(cfg['real_fork_session'])
                backup=session.read_bytes();backup_path=run_dir/'fork-before.local-only.json'
                fd=os.open(backup_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as stream: stream.write(backup)
                replacement=Path(cfg['fork_template']).read_bytes()
                transaction={'path':str(session),'backup':str(backup_path),'backup_sha256':hashlib.sha256(backup).hexdigest(),
                             'installed_sha256':hashlib.sha256(replacement).hexdigest(),'installation_started':True,'installed':False,'restored':False}
                save(run_dir/'fork-transaction.local-only.json',transaction)
                guarded_replace(session,transaction['backup_sha256'],replacement)
                transaction['installed']=True;save(run_dir/'fork-transaction.local-only.json',transaction)
            entry['profile_before_sha256']=sha(session)
            initial_profile=load(session);save(run_dir/'profile-before.local-only.json',initial_profile)
            initial_id=profile_identity(initial_profile,condition)
            expected_paths=load(cfg['repository_set'])['repository_paths']
            fatal(initial_id['paths']==expected_paths and len(set(expected_paths))==40 and initial_id['active']==cfg['active_repository'],'Prepared profile is not common40/active repo')
            stdout=(run_dir/'app.stdout').open('xb');stderr=(run_dir/'app.stderr').open('xb');files += [stdout,stderr]
            app=subprocess.Popen([cfg['executables'][condition]],env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            app_token=identity(app.pid);entry['pid']=app.pid;entry['identity']=app_token;save(manifest_path,manifest)
            app_expected={app.pid:cfg['executables'][condition]}
            ready_until=time.monotonic()+90
            if condition=='gitcomet':
                while time.monotonic()<ready_until:
                    need(app.poll() is None,'GC exited before readiness')
                    events=[]
                    startup_raw=(run_dir/'app.stderr').read_bytes()
                    startup_complete=startup_raw[:startup_raw.rfind(b'\n')+1]
                    for line in startup_complete.decode('utf-8',errors='strict').splitlines():
                        if 'GITCOMET_PERF_STARTUP_EVENT ' in line:
                            events.append(json.loads(line.split('GITCOMET_PERF_STARTUP_EVENT ',1)[1]))
                    if any(x.get('name')=='active_repo_ready' for x in events) and any(x.get('repos_total')==40 for x in events): break
                    time.sleep(.1)
                else: raise RuntimeError('GC40 active repo not ready within90s')
            else:
                time.sleep(cfg['fork_startup_settle_seconds'])
                need(app.poll() is None,'Fork exited during frozen settle')
            quiet(app_expected)
            activation=load_json_output([cfg['native_control'],'--activate',str(app.pid)])
            need(activation['frontmost_pid']==app.pid,'Activation did not reach owned PID')
            # One identical2s/240request interior initializer before warmup;
            # every fresh app starts this prerequisite outside numeric phases.
            point=cfg['points'][condition]
            bounds_args=window_arguments(cfg,condition)
            description=describe_target_ready(cfg,app,app_token,
                 [cfg['driver'],'--describe-target','--pid',str(app.pid),
                  '--x',str(point[0]),'--y',str(point[1]),*bounds_args],run_dir)
            verify_description(cfg,condition,app.pid,description)
            save(run_dir/'target-description.json',description)
            argv=[cfg['driver'],'--run-id',run_dir.name,'--pid',str(app.pid),'--window-id',str(description['window']['id']),
                 '--x',str(point[0]),'--y',str(point[1]),'--pixels',str(cfg['pixels']),*bounds_args]
            with (run_dir/'initializer.jsonl').open('xb') as stream, (run_dir/'initializer.stderr').open('xb') as errors:
                subprocess.run(argv+['--initialize'],stdout=stream,stderr=errors,check=True,timeout=7)
            verify_initializer(cfg,run_dir,app.pid,condition)
            # Existing identical10s warmup cycle is unchanged.
            with (run_dir/'warmup.jsonl').open('xb') as stream:
                subprocess.run(argv+['--characterize'],stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=15)
            warmup=load_lines(run_dir/'warmup.jsonl')
            verify_route_header(cfg,condition,app.pid,warmup[0],description)
            need(warmup[0]['characterize'] is True and warmup[0]['initialize'] is False and warmup[0]['expected_events']==1200 and warmup[-1]['kind']=='complete','Warmup route/mode/completion mismatch')
            verify_cursor_completion(warmup)
            time.sleep(3)
            need(time.monotonic()-started<=120,'Frozen120s setup budget exceeded')
            reference=load(cfg['environment_references'][condition])
            before=environment(cfg,app.pid);environment_check(before,reference,app.pid)
            save(run_dir/'environment-before.json',before);save(run_dir/'interference-before.json',quiet(app_expected))
            entry.update(status='capturing',failures=['pending']);save(manifest_path,manifest)
            driver_err=(run_dir/'driver.stderr').open('xb');files.append(driver_err)
            driver_out=(run_dir/'driver.jsonl').open('xb');files.append(driver_out)
            driver=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=driver_err,start_new_session=True)
            header,line=read_header(driver,2,driver_out)
            need(header['pid']==app.pid and header['pixels']==cfg['pixels'] and header['x']==point[0] and header['y']==point[1] and
                 header['expected_events']==10800 and header['rate_hz']==120 and not header['characterize'] and header['initialize'] is False,'Driver header mismatch')
            verify_route_header(cfg,condition,app.pid,header,description)
            origin=int(header['origin_monotonic_ns'])
            need(0<=time.monotonic_ns()-origin<=1_000_000_000,'Driver header/collector startup missed1s; no shifted sampling')
            collector_log=(run_dir/'collector.stderr').open('xb');files.append(collector_log)
            collector=subprocess.Popen([sys.executable,'-B',cfg['collector'],'--origin-monotonic-ns',str(origin),
                                         '--output',str(run_dir/'energy.jsonl')],stdout=subprocess.DEVNULL,stderr=collector_log,start_new_session=True)
            os.set_blocking(driver.stdout.fileno(),False)
            sel=selectors.DefaultSelector();sel.register(driver.stdout,selectors.EVENT_READ)
            deadline=time.monotonic()+145;next_check=0
            try:
                while driver.poll() is None or collector.poll() is None:
                    fatal(time.monotonic()<deadline,'Finite145s capture watchdog expired; unexplained incomplete capture')
                    need(app.poll() is None,'Owned app exited')
                    if collector.poll() is not None and collector.returncode!=0: raise_collector_failure(run_dir)
                    if driver.poll() is not None: need(driver.returncode==0,'Native input driver failed')
                    if time.monotonic()>=next_check:
                        quiet(app_expected);need(identity(app.pid)==app_token,'Owned app identity changed');next_check=time.monotonic()+1
                    for key,_ in sel.select(.05):
                        data=os.read(key.fd,65536)
                        if data: driver_out.write(data)
                        else: sel.unregister(driver.stdout)
                while True:
                    data=os.read(driver.stdout.fileno(),65536)
                    if not data: break
                    driver_out.write(data)
            finally: sel.close();driver_out.flush()
            if collector.returncode!=0: raise_collector_failure(run_dir)
            need(driver.returncode==0,'Owned native input child failed')
            verify_raw(cfg,run_dir,header,app.pid)
            save(run_dir/'interference-after.json',quiet(app_expected))
            after=environment(cfg,app.pid);save(run_dir/'environment-after.json',after);environment_check(after,reference,app.pid)
            fatal(before['power']['source']==after['power']['source'] and before['power']['charging']==after['power']['charging'],'Power state changed')
            after_repo=repository(cfg['active_repository']);save(run_dir/'repository-after.local-only.json',after_repo)
            fatal(after_repo==before_repo==manifest['repository'],'Active repo changed')
            fatal(sha(cfg['real_gc_session'])==manifest['real_gc_sha256'],'Real GC session changed')
            try: save(run_dir/'controls-after.local-only.json',frozen(cfg))
            except Exception as error: raise FatalTrial('Frozen controls changed after capture: '+str(error))
        except BaseException as error:
            fatal_failure=isinstance(error,(FatalTrial,KeyboardInterrupt))
            failures.append(type(error).__name__+': '+str(error))
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
            # A second signal must not skip best-effort owned cleanup/transaction record.
            signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN)
            # Preserve an already-failed collector's fatal classification even
            # if an app/input error was observed in the same polling interval.
            if collector is not None and collector.poll() is not None and collector.returncode!=0:
                try: raise_collector_failure(run_dir)
                except FatalTrial as error:
                    fatal_failure=True;failures.append(str(error))
                except RuntimeError: pass
            for child,name in ((driver,'driver'),(collector,'collector')):
                try: cleanup_child(child)
                except BaseException as error:
                    fatal_failure=True;failures.append(name+' cleanup: '+str(error))
            # Close the poll/termination race: a model failure footer may have
            # arrived after the pre-cleanup poll. Never mask that reported cause.
            if collector is not None and (run_dir/'energy.jsonl').exists():
                try:
                    retained=load_lines(run_dir/'energy.jsonl')
                    footer=retained[-1] if retained else {}
                    if footer.get('kind')=='footer' and footer.get('reason') is not None:
                        try: raise_collector_failure(run_dir)
                        except FatalTrial as error:
                            fatal_failure=True;failures.append('Postcleanup counter failure: '+str(error))
                        except RuntimeError: pass
                except (ValueError,RuntimeError,KeyError):
                    pass  # Known app/input cancellation can leave a partial file.
            # App is a direct Popen child; only this verified live identity is terminated.
            if app is not None and app.poll() is None:
                try:
                    need(identity(app.pid)==app_token,'Refusing cleanup of changed PID identity')
                    cleanup_child(app)
                except BaseException as error:
                    fatal_failure=True;failures.append('Owned app cleanup: '+str(error))
            try:
                quiet({})
                final_owned_profile=None
                if transaction and transaction['installation_started']:
                    current=Path(transaction['path']);post=current.read_bytes();post_sha=hashlib.sha256(post).hexdigest()
                    transaction['closed_current_sha256']=post_sha
                    save(run_dir/'fork-transaction.local-only.json',transaction)
                    closed_fd=os.open(run_dir/'fork-closed.local-only.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                    with os.fdopen(closed_fd,'wb') as stream: stream.write(post)
                    if not transaction['installed']:
                        need(post_sha in (transaction['backup_sha256'],transaction['installed_sha256']),
                             'Incomplete install and unexpected session bytes; preserve without overwrite')
                    changes=[] if post_sha==transaction['backup_sha256'] and not transaction['installed'] else fork_changes(
                        load(cfg['fork_template']),json.loads(post),cfg['fork_runtime_frame_allowlist'])
                    final_owned_profile=json.loads(post) if transaction['installed'] else None
                    transaction['closed_current_sha256']=post_sha;transaction['allowed_runtime_changes']=changes
                    need(sha(transaction['backup'])==transaction['backup_sha256'],'Fork backup changed')
                    if post_sha!=transaction['backup_sha256']:
                        guarded_replace(current,post_sha,Path(transaction['backup']).read_bytes())
                    transaction['restored']=True;save(run_dir/'fork-transaction.local-only.json',transaction)
                if app is not None:
                    final_profile=load(run_dir/'profile/state/gitcomet/session.json') if condition=='gitcomet' else final_owned_profile
                    need(final_profile is not None,'No validated closed owned profile')
                    entry['profile_after_sha256']=sha(run_dir/'profile/state/gitcomet/session.json') if condition=='gitcomet' else transaction['closed_current_sha256']
                    final_id=profile_identity(final_profile,condition)
                    need(final_id==initial_id,'Saved40 profile repository/order/IDs changed')
                need(sha(cfg['real_gc_session'])==manifest['real_gc_sha256'] and sha(cfg['real_fork_session'])==manifest['real_fork_sha256'],'Real sessions were not preserved')
            except BaseException as error:
                fatal_failure=True;failures.append('Guarded restoration/profile check: '+str(error))
            for stream in files: stream.close()
            if fatal_failure:
                manifest['series_stopped']={'slot':slot,'failures':failures,'unix_ns':time.time_ns()}
            entry.update(valid=not failures,fatal_series_stop=fatal_failure,status='finished' if not failures else 'failed',failures=failures,
                         observer_cpu_ns=cpu()-parent_cpu,observer_elapsed_ns=int((time.monotonic()-started)*1e9),
                         ended_unix_ns=time.time_ns(),fork_transaction=transaction,
                         environment_scope='Before/after native metadata only; transient thermal/power changes not independently sampled')
            save(manifest_path,manifest)
        print(json.dumps(entry,indent=2))
        return 0 if entry['valid'] else 2


def raise_collector_failure(run_dir):
    try:
        rows=load_lines(run_dir/'energy.jsonl')
        reason=rows[-1].get('reason','') if rows[-1].get('kind')=='footer' else ''
    except Exception:
        reason=''
    text=str(reason)
    allowed=('Snapshot call latency exceeds','Snapshot absolute start exceeds',
             'Collector setup missed first absolute snapshot')
    if any(token in text for token in allowed):
        raise RuntimeError('Replaceable bounded collector timing failure: '+text)
    # A rejected startup-origin contract produces no capture file; exact stderr
    # identifies this known setup failure without accepting an arbitrary error.
    stderr=(run_dir/'collector.stderr').read_text(errors='replace')
    if not (run_dir/'energy.jsonl').exists() and 'Main origin must be0..1s' in stderr:
        raise RuntimeError('Replaceable collector startup origin lateness')
    raise FatalTrial('Named-model schema/unit/clock/integrity failure: '+(text or stderr[-2000:]))


def verify_initializer(cfg, run_dir, pid, condition):
    raw=load_lines(run_dir/'initializer.jsonl')
    need(raw and raw[0]['kind']=='header' and raw[-1]['kind']=='complete','Initializer header/completion missing')
    need(sum(row['kind']=='header' for row in raw)==1 and sum(row['kind']=='complete' for row in raw)==1 and
         not any(row['kind']=='failed' for row in raw),'Initializer mixed/failed capture')
    head=raw[0];origin=head['origin_monotonic_ns'];point=cfg['points'][condition]
    verify_route_header(cfg,condition,pid,head,load(run_dir/'target-description.json'))
    verify_cursor_completion(raw)
    need(head['schema']=='native-pixel-session-energy-v1' and head['run_id']==run_dir.name and
         head['pid']==pid and head['x']==point[0] and head['y']==point[1] and head['pixels']==cfg['pixels'] and
         head['initialize'] is True and head['characterize'] is False and head['rate_hz']==120 and head['expected_events']==240,
         'Initializer mode/target/stream identity mismatch')
    need(abs(head['active_start_monotonic_ns']-origin)<=1000 and
         abs(head['active_end_monotonic_ns']-origin-2e9)<=1000 and
         abs(head['finish_monotonic_ns']-origin-2e9)<=1000,'Initializer changed fixed2s plan')
    events=[row for row in raw if row['kind']=='posted_scroll_request']
    need(len(events)==240,'Missing initializer requests')
    for index,row in enumerate(events):
        scheduled=row['scheduled_monotonic_ns']
        need(row['index']==index and row['run_id']==head['run_id'] and row['pixel_delta_y']==-cfg['pixels'] and
             abs(scheduled-origin-index/120*1e9)<=1000,'Initializer index/polarity/deadline mismatch')
        begin=row['begin']['monotonic_ns'];end=row['end']['monotonic_ns']
        need(row['creation_begin']['monotonic_ns']<=begin<=end and
             -1000<=row['creation_begin']['monotonic_ns']-scheduled<=50e6 and
             -1000<=begin-scheduled<=50e6 and end-scheduled<=50e6,'Initializer posting clock/lateness failure')
        for stamp in (row['creation_begin'],row['begin'],row['end']):
            need(0<=stamp['pair_bracket_ns']<=50e6,'Initializer paired clock bracket invalid')
    need(origin+2e9<=raw[-1]['stamp']['monotonic_ns']<=origin+4e9,'Initializer did not finish before subsequent phases')


def verify_raw(cfg, run_dir, header, pid):
    raw=load_lines(run_dir/'driver.jsonl')
    verify_cursor_completion(raw)
    need(raw[0]==header and raw[-1]['kind']=='complete','Incomplete native header/footer')
    events=[row for row in raw if row['kind']=='posted_scroll_request']
    need(len(events)==10800,'Missing native event records')
    start=header['active_start_monotonic_ns']
    origin=header['origin_monotonic_ns']
    need(abs(start-origin-20e9)<=1000 and abs(header['active_end_monotonic_ns']-origin-110e9)<=1000 and
         abs(header['finish_monotonic_ns']-origin-130e9)<=1000,'Changed20/90/20 phase schedule')
    for index,row in enumerate(events):
        need(row['index']==index and row['run_id']==header['run_id'],'Duplicated/reordered native events')
        expected_delta=-cfg['pixels'] if index%1200<600 else cfg['pixels']
        scheduled=row['scheduled_monotonic_ns']
        need(row['pixel_delta_y']==expected_delta and abs(scheduled-start-index/120*1e9)<=1000,'Changed native pixel/deadline stream')
        need(row['creation_begin']['monotonic_ns']<=row['begin']['monotonic_ns']<=row['end']['monotonic_ns'],'Reordered posting clock')
        need(-1000<=row['begin']['monotonic_ns']-scheduled<=50e6 and row['end']['monotonic_ns']-scheduled<=50e6,'Native post schedule late')
        for mark in (row['creation_begin'],row['begin'],row['end']):
            need(0<=mark['pair_bracket_ns']<=50e6,'Invalid native paired clock bracket')
    try: verify_energy(cfg,run_dir,header)
    except FatalTrial: raise
    except Exception as error: raise FatalTrial('Malformed/inconsistent counter record: '+str(error))


def primary_liveness(samples):
    """Per-run instrument liveness only; still GPU/ANE may legitimately be zero."""
    indexed = {row['offset_s']: row['sample']['counters'] for row in samples}
    for start, end in ((5, 15), (35, 95), (115, 125)):
        if indexed[end]['CPU Energy']['raw'] - indexed[start]['CPU Energy']['raw'] <= 0:
            raise ValueError('CPU Energy stalled in fixed window ' + str(start) + '..' + str(end))
    for name in ('GPU Energy', 'CLPC GPU Energy'):
        if indexed[95][name]['raw'] - indexed[35][name]['raw'] <= 0:
            raise ValueError(name + ' stalled in active fixed window 35..95')


def verify_energy(cfg,run_dir,header):
    origin=header['origin_monotonic_ns']
    try: energy=load_lines(run_dir/'energy.jsonl')
    except Exception as error: raise FatalTrial('Unexplained counter capture truncation: '+str(error))
    head=energy[0];foot=energy[-1];samples=energy[1:-1]
    fatal(head['kind']=='header' and head['schema']=='ioreport-clpc-energy-v1' and head['mode']=='main' and
         abs(head['origin_monotonic_ns']-origin)<=1000,'Collector mode/origin mismatch')
    fatal(foot['kind']=='footer' and foot['complete'] is True and foot['reason'] is None and
         foot['snapshots']==foot['expected_snapshots']==len(samples)==125,'Incomplete named-model capture')
    fatal(head['primary_names']==['CPU Energy','GPU Energy'] and head['snapshot_offsets_s']==list(range(3,128)),
         'Changed primary channels/absolute snapshot plan')
    fatal(head['source_sha256']==cfg['frozen_files'][cfg['collector']] and head['binding_sha256']==cfg['frozen_files'][cfg['clpc_binding']], 'Collector/binding source identity mismatch')
    provenance=head['binding_provenance']
    fatal(provenance['os_version']=='27.2' and provenance['os_build']=='26B123' and provenance['clpc_bundle']=='com.apple.driver.AppleT6050CLPC' and provenance['clpc_registry_id']==0x1000005ce and provenance['upstream_commit']=='08653ddeb3c1206b6cc35d5a2bb442b4c64ad810','CLPC mapping provenance changed')
    identities={}
    anchor=head['stamp'];anchor_offset=anchor['unix_ns']-(anchor['monotonic_before_ns']+anchor['monotonic_after_ns'])//2
    for index,row in enumerate(samples):
        fatal(row['kind']=='snapshot' and row['index']==index and row['offset_s']==index+3,'Snapshot index/order mismatch')
        fatal(row['scheduled_monotonic_ns']==head['origin_monotonic_ns']+(index+3)*1_000_000_000,'Shifted snapshot schedule')
        sample=row['sample'];low=sample['call_before']['monotonic_before_ns'];high=sample['call_after']['monotonic_after_ns']
        fatal(0<=high-low<=50e6 and 0<=low-row['scheduled_monotonic_ns']<=50e6,'Snapshot call span/start bound violated')
        for mark in (sample['call_before'],sample['call_after']):
            fatal(0<=mark['monotonic_after_ns']-mark['monotonic_before_ns']<=50e6 and abs(mark['unix_ns']-(mark['monotonic_before_ns']+mark['monotonic_after_ns'])//2-anchor_offset)<=50e6,'Invalid host paired clock/drift')
        fatal(set(sample['counters'])=={'CPU Energy','GPU Energy','ANE0','CLPC GPU Energy'},'Main subscribed channels changed')
        if index:
            fatal(set(row['delta_from_previous']['channels'])=={'CPU Energy','GPU Energy','ANE0','CLPC GPU Energy'},'Delta channel set changed')
        for name,counter in sample['counters'].items():
            meta=counter['metadata']
            try: metadata_contract(meta,name)
            except (ValueError,KeyError) as error: raise FatalTrial('Strict CLPC/native metadata mismatch: '+str(error))
            if not index: identities[name]=meta
            fatal(meta==identities[name]==head['metadata'][name]['metadata'],'Counter identity changed')
            fatal(type(counter['raw']) is int and counter['raw']>=0,'Invalid cumulative scalar')
            if index:
                before=samples[index-1]['sample']['counters'][name]['raw'];delta=row['delta_from_previous']['channels'][name]
                factor=1
                fatal(counter['raw']>=before and delta['metadata']==meta and delta['before_raw']==before and
                     delta['after_raw']==counter['raw'] and delta['api_delta_raw']==counter['raw']-before and
                     delta['delta_nj']==(counter['raw']-before)*factor,'Raw/API interval counter mismatch')
        if index:
            prior=samples[index-1]['sample'];low0=prior['call_before']['monotonic_before_ns'];high0=prior['call_after']['monotonic_after_ns']
            expected_exposure=(low+high-low0-high0)//2;delta=row['delta_from_previous']
            fatal(expected_exposure>0 and delta['midpoint_exposure_ns']==expected_exposure and
                  delta['exposure_bounds_ns']==[low-high0,high-low0],'Interval exposure/brackets inconsistent')
            expected_sum=sum(delta['channels'][name]['delta_nj'] for name in ('CPU Energy','GPU Energy'))
            fatal(delta['primary_sum_nj']==expected_sum and math.isclose(delta['primary_sum_j'],expected_sum/1e9,rel_tol=1e-12,abs_tol=1e-12),
                  'Primary interval sum/J arithmetic inconsistent')
            fatal(delta['ane0_secondary_nj']==delta['channels']['ANE0']['delta_nj'],'ANE0 secondary arithmetic inconsistent')
    fatal({row['offset_s'] for row in samples}>={5,15,35,95,115,125},'Primary/still endpoints missing')
    try: primary_liveness(samples)
    except ValueError as error: raise FatalTrial('Per-run instrument liveness failure: '+str(error))


def load_lines(path):
    raw=Path(path).read_bytes();need(raw.endswith(b'\n'),'Truncated JSONL')
    return [json.loads(line) for line in raw.splitlines() if line]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--series',type=Path,required=True)
    parser.add_argument('--slot',type=int,choices=range(1,21),required=True)
    args=parser.parse_args()
    cfg=load(args.config)
    # SIGTERM follows the same owned-child/session finally paths as Ctrl+C.
    def interrupt(signum,frame): raise KeyboardInterrupt('Signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupt)
    return run(cfg,args.config,args.series,args.slot)


if __name__=='__main__':
    raise SystemExit(main())
