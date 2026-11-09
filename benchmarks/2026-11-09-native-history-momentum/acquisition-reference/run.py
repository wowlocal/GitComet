from pathlib import Path
import argparse, subprocess, json, time, os, sys, hashlib, datetime, shutil

out = Path(__file__).resolve().parent
sys.path.insert(0, '/path/to/workspace/GitComet/scripts/profiling')
import perf_macos as perf

parser = argparse.ArgumentParser()
parser.add_argument('--pilot', choices=['off','on'])
parser.add_argument('--resume', type=Path)
args = parser.parse_args()
assert not (args.pilot and args.resume)
order = [args.pilot] if args.pilot else ['off','on','on','off','on','off','off','on']
series = ('pilot-' + args.pilot if args.pilot else 'balanced') + '-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
series_dir = args.resume.resolve() if args.resume else out / series
if args.resume: series = series_dir.name
else: series_dir.mkdir()
real = Path('/path/to/normal/GitComet/session.json')
profile = (out / 'frozen-input-session.json').read_bytes()
session = json.loads(profile)
assert len(session['open_repos']) == 264 and session['active_repo'] == '/path/to/workload-repository'
active = session['active_repo']
real_sha = hashlib.sha256(real.read_bytes()).hexdigest()
plan_bytes = (out / 'input-plan.json').read_bytes()
plan = json.loads(plan_bytes)
packets = plan['packets']
assert len(packets) == 240

def repository_identity():
    head=subprocess.check_output(['git','-C',active,'rev-parse','HEAD'],text=True).strip()
    status=subprocess.check_output(['git','-C',active,'status','--porcelain=v1','-z'])
    index=Path(subprocess.check_output(['git','-C',active,'rev-parse','--git-path','index'],text=True).strip())
    if not index.is_absolute():index=Path(active)/index
    return {'head':head,'status_sha256':hashlib.sha256(status).hexdigest(),'index_sha256':hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None}

repo = repository_identity()
manifest = {'series':series,'pilot':bool(args.pilot),'order':order,'real_session_sha256':real_sha,'input_profile_sha256':hashlib.sha256(profile).hexdigest(),'input_plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),'repository':repo,'runs':[],'started_unix_s':time.time()}
manifest_path = series_dir / 'manifest.json'
if args.resume:
    prior = json.loads(manifest_path.read_text())
    for key in ['order','real_session_sha256','input_profile_sha256','input_plan_sha256','repository']:
        assert prior[key] == manifest[key], ('Resume control changed',key)
    manifest = prior
    manifest.setdefault('resumed_unix_s',[]).append(time.time())
manifest_path.write_text(json.dumps(manifest,indent=2))

def environment(pid):
    result = subprocess.run([str(out/'environment'),str(pid)],capture_output=True,text=True,check=True)
    data = json.loads(result.stdout)
    data['power_source'] = subprocess.check_output(['pmset','-g','batt'],text=True).strip()
    return data

def interference_check():
    names = [Path(x.strip()).name for x in subprocess.check_output(['ps','-axo','comm='],text=True).splitlines()]
    assert not any(x in names for x in ['cargo','rustc','swiftc','swift-frontend']), 'Compilation invalidates timing'
    assert 'World of Warcraft' not in names, 'Game must be closed before a clean GPU comparison'
    return names

class LaunchedApp:
    def __init__(self,pid,waiter): self.pid,self.waiter=pid,waiter
    def poll(self): return self.waiter.poll()
    def wait(self,timeout=None): return self.waiter.wait(timeout=timeout)
    def terminate(self):
        try: os.kill(self.pid,15)
        except ProcessLookupError: pass
    def kill(self):
        try: os.kill(self.pid,9)
        except ProcessLookupError: pass

def launch_app(bundle,env,run):
    command=['/usr/bin/open','-W','-n','-a',str(bundle),'--stdout',str(run/'app.stdout'),'--stderr',str(run/'app.stderr')]
    for key,value in sorted(env.items()):
        if key.startswith(('GPUI_NATIVE_TIMING_','GITCOMET_')) or key=='PATH':
            command += ['--env',key+'='+value]
    waiter=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=(run/'launcher.stderr').open('w'))
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        if waiter.poll() is not None: raise RuntimeError('LaunchServices exited before native recorder initialization')
        trace=run/'native.jsonl'
        if trace.exists():
            first=trace.read_text().splitlines()
            if first:
                header=json.loads(first[0]);return LaunchedApp(header['pid'],waiter)
        time.sleep(.05)
    waiter.terminate();raise TimeoutError('No native recorder header after LaunchServices launch')

for index, condition in enumerate(order):
    if any(r['ordinal']==index+1 and r['valid'] for r in manifest['runs']): continue
    attempts = sum(r['ordinal']==index+1 for r in manifest['runs'])
    suffix = f'-attempt{attempts+1}' if attempts else ''
    run = series_dir / f'{index+1:02d}-{condition}{suffix}'
    run.mkdir()
    names = interference_check()
    assert not any(x=='gitcomet' for x in names), 'Quit the prior app normally first'
    assert hashlib.sha256(real.read_bytes()).hexdigest()==real_sha
    assert repository_identity()==repo, 'Repository changed during comparison'
    assert (out/'input-plan.json').read_bytes()==plan_bytes
    state = run/'profile/state/gitcomet'
    state.mkdir(parents=True)
    (state/'session.json').write_bytes(profile)
    steps = [{'do':'wait_ready','indexed':True,'timeout_ms':90000},{'do':'scroll','target':'history','delta_px':1000000,'repeat':1,'interval_ms':0},{'do':'settle','ms':12000},{'do':'switch_window','name':'primary'}, {'do':'phase','name':'prefill'},{'do':'scroll','target':'history','delta_px':-2000,'repeat':1,'interval_ms':0},{'do':'settle','ms':500}]
    for cycle in range(2):
        sign = 1 if cycle%2==0 else -1
        steps += [{'do':'phase','name':f'warmup-{cycle}'},{'do':'scroll_packets','target':'history','packets':[dict(p,delta_px=p['delta_px']*sign) for p in packets]},{'do':'settle','ms':150}]
    steps += [{'do':'settle','ms':1000}]
    for cycle in range(4):
        sign = 1 if cycle%2==0 else -1
        steps += [{'do':'switch_window','name':'primary'},{'do':'phase','name':f'replay-{cycle}'},{'do':'scroll_packets','target':'history','packets':[dict(p,delta_px=p['delta_px']*sign) for p in packets]},{'do':'settle','ms':150},{'do':'phase','name':f'replay-{cycle}-end'}]
    steps += [{'do':'settle','ms':40000}]
    scenario = json.dumps({'steps':steps},indent=2).encode()
    scenario_path = run/'scenario.json'
    scenario_path.write_bytes(scenario)
    bundle = Path('/Applications/GitComet.app')
    binary = bundle/'Contents/MacOS/gitcomet'
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert binary_sha=='f3172102f1b0b9722424ea991ee229a51396ee43a87cffaabcd4adc36b9455c3'
    build = {'binary_sha256':binary_sha}
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('GPUI_NATIVE_TIMING_','GITCOMET_UI_PROBE','GITCOMET_PERF_STARTUP_')) or key in {'GITCOMET_UI_SCENARIO','GITCOMET_PROFILE_ROOT','GITCOMET_DISABLE_SESSION_PERSIST','GITCOMET_HISTORY_MOMENTUM_RESAMPLING','GITCOMET_STARTUP_TRACE'}:
            env.pop(key,None)
    env.update(GITCOMET_PROFILE_ROOT=str(run/'profile'),GITCOMET_UI_PROBE='1',GITCOMET_UI_PROBE_JSONL=str(run/'frames.jsonl'),GITCOMET_UI_SCENARIO=str(scenario_path),GITCOMET_STARTUP_TRACE=str(run/'startup.jsonl'),GPUI_NATIVE_TIMING_PATH=str(run/'native.jsonl'),GPUI_NATIVE_TIMING_SECONDS='60',GPUI_NATIVE_TIMING_ARM='immediate',GITCOMET_HISTORY_MOMENTUM_RESAMPLING=condition)
    record = {'condition':condition,'ordinal':index+1,'scenario_sha256':hashlib.sha256(scenario).hexdigest(),'build_binary_sha256':build['binary_sha256'],'start_unix_s':time.time(),'observer_interval_s':1,'samples':[],'environment':[]}
    ws = perf.window_server_pid()
    report = perf.IOReportSampler()
    assert report.ok and ws
    previous = report.sample()
    previous_at = time.monotonic()
    observer_before = perf.process_sample(os.getpid())
    native_started = time.monotonic()
    stdout = (run/'app.stderr').open('w')
    try:
        process = launch_app(bundle,env,run)
    except BaseException as error:
        stdout.close()
        report.release(previous)
        failure='LaunchServices startup failed: '+repr(error)
        record.update(error=repr(error),end_unix_s=time.time(),verification={'valid':False,'failures':[failure]})
        (run/'measurement.json').write_text(json.dumps(record,indent=2))
        manifest['runs'].append({'condition':condition,'ordinal':index+1,'path':str(run),'valid':False,'failures':[failure]})
        manifest_path.write_text(json.dumps(manifest,indent=2))
        raise SystemExit(failure)
    record.update(pid=process.pid,windowserver_pid=ws,launch_method='LaunchServices open -W -n --env',exit_code_scope='launcher only; native completion verified by scenario/capture')
    print(json.dumps({'event':'run_started','series':series,'ordinal':index+1,'condition':condition,'pid':process.pid,'path':str(run)}),flush=True)
    activated = False
    after_environment = False
    try:
        while process.poll() is None:
            loop = time.monotonic()
            assert loop-native_started < 165, 'Scenario exceeded watchdog'
            interference_check()
            frame_path = run/'frames.jsonl'
            frames = frame_path.read_text() if frame_path.exists() else ''
            if not activated and '"scenario_ready"' in frames:
                subprocess.run(['/usr/bin/open','-a',str(bundle)],check=True)
                record['environment'].append(dict(event='ready',**environment(process.pid)))
                activated = True
            if activated and not after_environment and '"replay-3-end"' in frames:
                record['environment'].append(dict(event='after_scroll',**environment(process.pid)))
                after_environment = True
            current = report.sample()
            at = time.monotonic()
            record['samples'].append({'unix_ms':time.time()*1000,'monotonic_s':at,'interval_s':at-previous_at,'soc':report.delta(previous,current),'gpu_times_ns':perf.gpu_times_ns({ws,process.pid}),'app_cpu':perf.process_sample(process.pid),'observer_cpu':perf.process_sample(os.getpid()),'device':perf.device_statistics()})
            report.release(previous)
            previous = current
            previous_at = at
            time.sleep(max(0,1-(time.monotonic()-loop)))
        record['exit_code'] = process.wait()
    except BaseException as error:
        record['error'] = repr(error)
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
    finally:
        stdout.close()
        report.release(previous)
        record.update(end_unix_s=time.time(),observer_cpu_before=observer_before,observer_cpu_after=perf.process_sample(os.getpid()),activated_via_launchservices=activated,real_session_unchanged=hashlib.sha256(real.read_bytes()).hexdigest()==real_sha,repository_unchanged=repository_identity()==repo)
        (run/'measurement.json').write_text(json.dumps(record,indent=2))
    failures = []
    def require(value, reason):
        if not value: failures.append(reason)
    require(record.get('exit_code')==0,'LaunchServices waiter failed')
    require(record.get('error') is None,'watchdog/observer error')
    require(record['real_session_unchanged'],'real session changed')
    require(record['repository_unchanged'],'repository changed')
    require(hashlib.sha256(binary.read_bytes()).hexdigest()==binary_sha,'installed binary changed during run')
    require([e['event'] for e in record['environment']]==['ready','after_scroll'],'missing environment snapshots')
    require(all(not e['reduce_motion'] for e in record['environment']),'Reduce Motion suppresses momentum path')
    require(all(e['frontmost_pid']==process.pid for e in record['environment']),'native foreground mismatch')
    frame_path = run/'frames.jsonl'
    require(frame_path.exists(),'missing application timing capture')
    rows = [json.loads(x) for x in frame_path.read_text().splitlines()] if frame_path.exists() else []
    ends = [r for r in rows if r['event']=='scenario_end']
    require(ends and ends[-1]['detail']['outcome']=='passed','scenario failed')
    witnesses = [w for r in rows if r['event']=='scenario_windows' for w in r['detail']['windows']]
    require(witnesses and all(w['active'] and w['ready'] and w['repository']==active for w in witnesses),'focus/readiness contamination')
    require(all(len(r['detail']['windows'])==1 for r in rows if r['event']=='scenario_windows'),'unexpected app window')
    ready = [r for r in rows if r['event']=='scenario_ready']
    require(len(ready)==1,'missing readiness geometry')
    positions = [r for r in rows if r['event']=='benchmark_position']
    # Installed binary has prepaint history markers rather than per-plan endpoint records.
    # The saved-data analyzer checks endpoints/path as product outcomes.
    if len(positions)==12:
        for c in range(6):
            start,end=(2000,5468) if c%2==0 else (5468,2000)
            require(abs(positions[c*2]['detail']['offset']-start)<.01 and abs(positions[c*2+1]['detail']['offset']-end)<.01,'unexpected logical endpoints')
    if ready:
        viewport=ready[0]['detail']['viewport']
        manifest.setdefault('expected_viewport',viewport)
        require(viewport==manifest['expected_viewport'],'history viewport changed')
    for e in record['environment']:
        controls={'screens':e['screens'],'low_power_mode':e['low_power_mode'],'reduce_motion':e['reduce_motion'],'power_source':'AC' if 'AC Power' in e['power_source'] else 'Battery','window_bounds':[w['bounds'] for w in e['target_windows']]}
        if e['event']=='after_scroll':
            require(e['frontmost_pid']==process.pid,'app was not foreground after replay')
            manifest.setdefault('expected_environment',controls)
            require(controls==manifest['expected_environment'],'display/power/window environment changed')
    record['verification'] = {'failures':failures,'focus_witnesses':len(witnesses),'ready_geometry':ready[0]['detail'] if ready else None,'logical_position_witnesses':positions}
    native_path = run/'native.jsonl'
    native = [json.loads(x) for x in native_path.read_text().splitlines()] if native_path.exists() else []
    footer = [r for r in native if r['event']=='capture_status' and r.get('status')=='complete']
    require(footer and footer[-1]['dropped']==0 and footer[-1]['marker_overflow']==0 and footer[-1]['reason']=='duration','incomplete/dropped timing capture')
    require(not any(r['event']=='native_scroll' for r in native),'real native input contaminated replay')
    # Presentation failures/zero callbacks and lateness are retained outcomes.
    require(sum(r['event']=='scenario_scroll' for r in native)==1442,'packet capture mismatch')
    prefix='GITCOMET_PERF_STARTUP_EVENT '
    progress=[]
    for line in ((run/'app.stderr').read_text()+(run/'app.stdout').read_text()).splitlines():
        if prefix in line:
            value=json.loads(line.split(prefix,1)[1])
            if value.get('name')=='repos_loaded':progress.append(value)
    require(progress and progress[-1]['repos_total']==264,'runtime repository-count mismatch')
    record['verification'].update(valid=not failures,timing_footer=footer[-1] if footer else None,repository_progress=progress)
    (run/'measurement.json').write_text(json.dumps(record,indent=2))
    manifest['runs'].append({'condition':condition,'ordinal':index+1,'path':str(run),'valid':not failures,'failures':failures})
    manifest_path.write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'event':'run_finished','condition':condition,'ordinal':index+1,'valid':not failures,'failures':failures}),flush=True)
    if failures: raise SystemExit('Invalid attempt retained; inspect before continuing')
manifest.update(completed_unix_s=time.time())
manifest_path.write_text(json.dumps(manifest,indent=2))
print(json.dumps({'event':'series_finished','manifest':str(manifest_path)}),flush=True)
