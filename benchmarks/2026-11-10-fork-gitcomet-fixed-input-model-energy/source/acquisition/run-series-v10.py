#!/usr/bin/env python3
"""Explicitly armed, serial outer runner. No energy reads or app/UI/counter APIs.

Preparing/importing this source does nothing. Runtime process metadata is local-only.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import time

ORDER = ['gitcomet','fork','fork','gitcomet','fork','gitcomet','gitcomet','fork']*2
PER_RUN_SECONDS = 420  # runner has its own300s watchdog plus guarded cleanup
GRACE_SECONDS = 90
POLL_SECONDS = .25
BUSY = {'cargo','rustc','rustdoc','swift','swiftc','swift-frontend','xcodebuild','bazel','make','gmake','ninja',
        'cmake','clang','clang++','cc','c++','ld','ld64','lto','ffmpeg','ffplay','sample','spindump','xctrace',
        'instruments','powermetrics','world of warcraft','world of warcraft classic','wow','gitcomet','fork'}
SCREEN_MARKERS = ('screenkite','screen-kite','sk-mcp-server')
SPINDUMP_PATH = '/usr/sbin/spindump'
SPINDUMP_SERVICE = 'system/com.apple.spindump'
DAEMON_IDLE_INTERVAL_S = 1


def need(ok, text):
    if not ok: raise RuntimeError(text)


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text())


def save_new(path, value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def planned_next(manifest):
    """Pure ledger policy; never consult energy/output values."""
    need(manifest['schema']=='energy-v4-series' and manifest['order']==ORDER, 'Wrong ledger/order')
    need(not manifest.get('series_stopped'), 'Persisted series stop; no reset or next slot')
    runs=manifest['runs'];need(len(runs)<=20,'Too many attempts')
    for i,e in enumerate(runs):
        need(e['slot']==i+1 and type(e['valid']) is bool and e['status'] in ('finished','failed'), 'Pending/nonserial slot')
        need(not e.get('fatal_series_stop',False), 'Fatal attempt; no next slot')
        need((e['valid'] and e['status']=='finished' and not e['failures']) or
             (not e['valid'] and e['status']=='failed' and bool(e['failures'])), 'Ledger validity conflict')
        if i<16:need(e['original_ordinal']==i+1,'Main ordinal changed')
        need(1<=e['original_ordinal']<=16 and e['condition']==ORDER[e['original_ordinal']-1], 'Condition changed')
    if len(runs)<16:return len(runs)+1
    failed=[i for i in range(1,17,2) if not all(runs[j-1]['valid'] for j in (i,i+1))]
    need(len(failed)<=2,'More than two failed original pairs; incomplete series')
    plan=[j for i in failed for j in (i,i+1)]
    need([e['original_ordinal'] for e in runs[16:]]==plan[:len(runs)-16], 'Replacement order changed')
    if 'replacement_ordinals' in manifest:need(manifest['replacement_ordinals']==plan,'Replacement ledger changed')
    return len(runs)+1 if len(runs)-16<len(plan) else None


def cpu_centiseconds(text):
    """Exact ps cumulative TIME conversion; no floating-point CPU threshold."""
    match=re.fullmatch(r'(?:(\d+)-)?(\d+):(\d{2})(?::(\d{2}))?\.(\d{2})',text)
    need(match is not None,'Unknown ps CPU TIME format')
    days,first,second,third,fraction=match.groups()
    need(int(second)<60 and (third is None or int(third)<60),'Invalid ps CPU TIME')
    seconds=int(first)*60+int(second) if third is None else int(first)*3600+int(second)*60+int(third)
    return ((int(days or 0)*86400+seconds)*100)+int(fraction)


def launchd_spindump_pid(text):
    """Accept only the exact running system service and its single no-argument argv."""
    lines=text.splitlines()
    need(lines and lines[0]==SPINDUMP_SERVICE+' = {','Wrong launchd service')
    for key,value in [('program',SPINDUMP_PATH),('type','LaunchDaemon'),('state','running'),('domain','system')]:
        need([line for line in lines if line.startswith('\t'+key+' = ')]==['\t'+key+' = '+value],
             'Uncorroborated launchd '+key)
    starts=[i for i,line in enumerate(lines) if line=='\targuments = {']
    need(len(starts)==1 and lines[starts[0]+1:starts[0]+3]==['\t\t'+SPINDUMP_PATH,'\t}'],
         'Launchd spindump has arguments or unknown argv')
    pids=[line for line in lines if line.startswith('\tpid = ')]
    need(len(pids)==1 and re.fullmatch(r'\tpid = [1-9]\d*',pids[0]) is not None,'Unknown launchd PID')
    return int(pids[0].split(' = ')[1])


def daemon_ps_row(text, pid):
    rows=[line.split() for line in text.splitlines() if line.strip()]
    need(len(rows)==1 and len(rows[0])==11,'Unknown daemon ps identity/argv')
    row=rows[0]
    need(int(row[0])==pid and row[1]=='1' and row[9:]==[SPINDUMP_PATH,SPINDUMP_PATH],
         'Daemon PID/parent/executable/argv mismatch')
    birth=' '.join(row[4:9])
    need(re.fullmatch(r'[A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2} \d{2}:\d{2}:\d{2} \d{4}',birth) is not None,
         'Unknown daemon birth identity')
    return {'pid':pid,'ppid':1,'birth_ps':birth,'executable':row[9],'command':row[10],
            'cumulative_cpu_time_ps':row[3],'cpu_centiseconds':cpu_centiseconds(row[3])}


def daemon_snapshot():
    """Metadata only; no sampling, app mutation or energy/counter access."""
    start=time.monotonic_ns()
    try:
        service=subprocess.check_output(['/bin/launchctl','print',SPINDUMP_SERVICE],text=True,timeout=2)
        pid=launchd_spindump_pid(service)
        # macOS truncates nonlast comm columns even with -ww; keep each path column last.
        raw=subprocess.check_output(['/bin/ps','-p',str(pid),'-o','pid=,ppid=,etime=,time=,lstart=,comm='],
                                    text=True,timeout=2)
        argv=subprocess.check_output(['/bin/ps','-p',str(pid),'-o','command='],text=True,timeout=2)
        result=daemon_ps_row(raw.rstrip('\n')+' '+argv.strip()+'\n',pid)
        result.update(status='corroborated',service=SPINDUMP_SERVICE)
    except Exception as error:
        result={'status':'unknown','reason':type(error).__name__+': '+str(error)}
    result['call_monotonic_ns']=[start,time.monotonic_ns()]
    return result


def same_daemon(before, after):
    return (before.get('status')=='corroborated' and after.get('status')=='corroborated' and
            all(before.get(key)==after.get(key) for key in ('pid','ppid','birth_ps','executable','command','service')))


def idle_daemon(before, after):
    """Strict preflight gate: stable identity and exactly zero centisecond increase."""
    valid=(same_daemon(before,after) and before['cpu_centiseconds']==after['cpu_centiseconds'] and
           after['call_monotonic_ns'][0]-before['call_monotonic_ns'][1]>=DAEMON_IDLE_INTERVAL_S*1_000_000_000)
    return {'status':'idle-verified' if valid else 'not-exempt','before':before,'after':after,
            'pid':after.get('pid') if valid else None,'cpu_increase_centiseconds':0 if valid else None,
            'policy':'Exact launchd no-argument daemon, same PID/birth and zero ps CPU centiseconds across at least1s.'}


def daemon_preflight():
    before=daemon_snapshot()
    if before['status']!='corroborated':return {'status':'not-exempt','before':before,'pid':None}
    time.sleep(DAEMON_IDLE_INTERVAL_S)
    return idle_daemon(before,daemon_snapshot())


def blocked_processes(executable_rows, command_rows, daemon=None):
    """Only the currently corroborated idle daemon PID may bypass the spindump block."""
    found=[];commands={pid:command for pid,command in command_rows}
    for pid, executable in executable_rows:
        name=Path(executable).name.lower()
        exempt=(name=='spindump' and daemon is not None and daemon.get('status')=='idle-verified' and
                pid==daemon['pid'] and executable==SPINDUMP_PATH and commands.get(pid)==SPINDUMP_PATH)
        if not exempt and (name in BUSY or any(token in executable.lower() for token in SCREEN_MARKERS)):
            found.append({'pid':pid,'executable':executable})
    for pid, command in command_rows:
        if any(token in command.lower() for token in SCREEN_MARKERS):
            found.append({'pid':pid,'reason':'ScreenKite GUI/MCP command path present'})
    return found


def daemon_run_delta(before, after):
    initial=before.get('after',{})
    if same_daemon(initial,after) and after['cpu_centiseconds']>=initial['cpu_centiseconds']:
        return {'status':'recorded','cpu_increase_centiseconds':after['cpu_centiseconds']-initial['cpu_centiseconds']}
    return {'status':'unknown-identity-changed-or-unavailable','cpu_increase_centiseconds':None}


def run_with_daemon_metadata(runner, config, series, slot, cancelled, before):
    """Snapshots bracket the whole runner, outside every energy endpoint; report only."""
    save_new(series/f'controller-slot-{slot:02d}.daemon-before.json',before)
    try:
        return run_one(runner,config,series,slot,cancelled)
    finally:
        after={'status':'unknown-runner-cleanup-not-confirmed'}
        try:
            metadata=load(series/f'controller-slot-{slot:02d}.json')
            if type(metadata.get('returncode')) is int:after=daemon_snapshot()
        except Exception as error:after={'status':'unknown','reason':type(error).__name__+': '+str(error)}
        save_new(series/f'controller-slot-{slot:02d}.daemon.json',
                 {'before':before,'after':after,'delta':daemon_run_delta(before,after),
                  'scope':'System daemon cumulative CPU across full runner setup/capture/cleanup, outside energy endpoints. Wake/restart/unknown is reported, never exclusion, replacement, subtraction or app attribution.'})


def ps_pairs(column):
    raw=subprocess.check_output(['/bin/ps','-axo','pid=,'+column+'='],text=True,timeout=2)
    return [(int(p[0]),p[1]) for line in raw.splitlines() if len(p:=line.strip().split(None,1))==2]


def preflight(config, config_hash, controller, controller_hash, runner, runner_hash):
    need(digest(config)==config_hash and digest(controller)==controller_hash and digest(runner)==runner_hash,
         'Frozen config/controller/runner changed; stop before app/profile mutation')
    cfg=load(config);need(cfg.get('ready') is True,'Config not READY')
    need(cfg['frozen_files'][str(controller)]==controller_hash and
         cfg['frozen_files'][str(runner)]==runner_hash, 'Controller/runner absent from frozen config')
    daemon=daemon_preflight()
    found=blocked_processes(ps_pairs('comm'),ps_pairs('command'),daemon)
    need(not found,'Competing ScreenKite/MCP, app, build, game, video or profiler process: '+repr(found))
    return daemon


def descendants(rows, app_pid):
    keep={app_pid}
    while True:
        expanded=keep|{r['pid'] for r in rows if r['ppid'] in keep}
        if expanded==keep:break
        keep=expanded
    return [r for r in rows if r['pid'] in keep]


def process_snapshot(app_pid):
    start=time.monotonic_ns()
    raw=subprocess.check_output(['/bin/ps','-axo','pid=,ppid=,time=,pri=,comm='],text=True,timeout=1)
    rows=[]
    for line in raw.splitlines():
        p=line.strip().split(None,4)
        if len(p)==5:
            rows.append({'pid':int(p[0]),'ppid':int(p[1]),'cumulative_cpu_time_ps':p[2],
                         'priority_ps':p[3],'executable_name':Path(p[4]).name})
    selected=descendants(rows,app_pid)
    return {'status':'recorded' if any(r['pid']==app_pid for r in selected) else 'unknown-app-not-present',
            'call_monotonic_ns':[start,time.monotonic_ns()], 'processes':selected,
            'scope':'Two point-in-time app/descendant snapshots; cumulative process CPU time in ps TIME format and raw priority. Not CPU attribution, delivery, per-run integrated child CPU, energy or an exclusion gate.'}


def snapshot_due(now, origin, target, taken):
    if taken:return 'done'
    # Firstcall between+1..+3s leaves at least1s before endpoint5 after1s timeout.
    # Secondcall+128..+129s follows endpoint125 and precedes driver finish130; no new validity criterion.
    late=3 if target==1 else 129
    if now>origin+late:return 'unknown-missed-window'
    return 'take' if now>=origin+target else 'wait'


def run_one(runner, config, series, slot, cancelled):
    own_start=time.process_time_ns();wall_start=time.monotonic_ns()
    meta={'slot':slot,'snapshots':{},'runner_pid':None,'cancellation':None}
    with (series/f'controller-slot-{slot:02d}.stdout').open('xb') as out, (series/f'controller-slot-{slot:02d}.stderr').open('xb') as err:
        child=subprocess.Popen([sys.executable,'-B',str(runner),'--config',str(config),'--series',str(series),'--slot',str(slot)],
                               stdout=out,stderr=err,start_new_session=True)
        meta['runner_pid']=child.pid;origin=None;app_pid=None;term_at=None
        try:
            while child.poll() is None:
                now=time.monotonic()
                if term_at is None and (cancelled[0] or now-wall_start/1e9>PER_RUN_SECONDS):
                    meta['cancellation']='user-signal' if cancelled[0] else 'outer-watchdog'
                    # Only our Popen child receives SIGINT: default KeyboardInterrupt enters runner's guarded finally.
                    child.send_signal(signal.SIGINT);term_at=now
                if term_at is not None:
                    if now-term_at>GRACE_SECONDS:
                        meta['cleanup']='unknown-runner-still-alive; no further slots; no blind group/app kill'
                        raise RuntimeError('Owned runner cleanup not confirmed after90s; inspect retained PID '+str(child.pid))
                elif origin is None:
                    try:
                        ledger=load(series/'manifest.json');entry=ledger['runs'][slot-1]
                        # Only the first driver line is read; never energy.jsonl or buffered event outcomes.
                        with (Path(entry['run'])/'driver.jsonl').open('rb') as stream:line=stream.readline(65537)
                        if line.endswith(b'\n') and len(line)<=65536:
                            header=json.loads(line);need(header['kind']=='header','Unexpected native header')
                            origin=header['origin_monotonic_ns']/1e9;app_pid=entry['pid']
                    except (FileNotFoundError,IndexError,json.JSONDecodeError,KeyError):pass
                if origin is not None and term_at is None:
                    for target in (1,128):
                        key=str(target);decision=snapshot_due(time.monotonic(),origin,target,key in meta['snapshots'])
                        if decision=='take':
                            try:
                                snapshot=process_snapshot(app_pid)
                                end_limit=origin+(5 if target==1 else 130)
                                snapshot['timing_status']='inside-planned-endpoint-margin' if snapshot['call_monotonic_ns'][1]/1e9<end_limit else 'unknown-overran-metadata-margin'
                                meta['snapshots'][key]=snapshot
                            except Exception as error:meta['snapshots'][key]={'status':'unknown','reason':type(error).__name__+': '+str(error)}
                        elif decision=='unknown-missed-window':meta['snapshots'][key]={'status':'unknown-missed-window'}
                time.sleep(POLL_SECONDS)
            meta['returncode']=child.returncode
            if meta['cancellation']:raise RuntimeError('Controller canceled; no further slots')
            return child.returncode
        except BaseException:
            if child.poll() is None and 'cleanup' not in meta:
                child.send_signal(signal.SIGINT)
                try:child.wait(timeout=GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    meta['cleanup']='unknown-runner-still-alive; no blind group/app kill; no further slots'
            raise
        finally:
            for target in ('1','128'):meta['snapshots'].setdefault(target,{'status':'unknown-no-opportunity'})
            meta['outer_controller_own_cpu_ns']=time.process_time_ns()-own_start
            meta['outer_controller_elapsed_ns']=time.monotonic_ns()-wall_start
            meta['scope']='Outer controller own process only, including bounded ps waits and ledger polling; excludes runner/app/helper children. Metadata only; no subtraction or energy conversion.'
            save_new(series/f'controller-slot-{slot:02d}.json',meta)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true')
    parser.add_argument('--runner',required=True,type=Path,help='Explicit reviewed runner source; no autodetect or fallback')
    parser.add_argument('--config',required=True,type=Path);parser.add_argument('--series',required=True,type=Path);args=parser.parse_args()
    if not args.run:parser.error('Explicit --run required; source preparation never launches trials')
    controller=Path(__file__).resolve();runner=args.runner.resolve();config=args.config.resolve();series=args.series.absolute()
    need(not series.exists() and not series.is_symlink(),'NEW series only; no implicit resume/reset')
    hashes=[digest(config),digest(controller),digest(runner)]
    initial_daemon=preflight(config,hashes[0],controller,hashes[1],runner,hashes[2])
    series.mkdir(mode=0o700);cancelled=[False]
    def cancel(signum,frame):cancelled[0]=True
    signal.signal(signal.SIGINT,cancel);signal.signal(signal.SIGTERM,cancel)
    record={'schema':'energy-serial-controller-v9','initial_daemon_preflight':initial_daemon,'config_sha256':hashes[0],'controller_sha256':hashes[1],
            'runner_sha256':hashes[2],'snapshot_targets_s':[1,128],'snapshot_misses_are_unknown_not_exclusions':True,
            'per_run_watchdog_s':PER_RUN_SECONDS,'cleanup_grace_s':GRACE_SECONDS,'status':'running'}
    start=time.monotonic_ns();cpu_start=time.process_time_ns()
    try:
        slot=1
        while slot is not None:
            need(not cancelled[0],'Controller canceled before next trial')
            daemon=preflight(config,hashes[0],controller,hashes[1],runner,hashes[2])
            code=run_with_daemon_metadata(runner,config,series,slot,cancelled,daemon)
            manifest=load(series/'manifest.json')
            need(len(manifest['runs'])==slot,'Runner did not retain expected slot; stop')
            need(code==(0 if manifest['runs'][-1]['valid'] else 2),'Runner exit/validity mismatch')
            slot=planned_next(manifest)
        record['status']='finished';record['attempt_count']=len(manifest['runs'])
        # Failed replacement pairs stay incomplete; never rerun again or inspect energy.
        record['replacement_failures']=any(not e['valid'] for e in manifest['runs'][16:])
        record['complete_valid_eight_pairs']=not record['replacement_failures']
    except Exception as error:
        record.update(status='stopped',reason=type(error).__name__+': '+str(error));raise
    finally:
        record.update(own_cpu_ns=time.process_time_ns()-cpu_start,elapsed_ns=time.monotonic_ns()-start,
                      scope='Outer controller own CPU, not child CPU or app energy; no subtraction')
        save_new(series/'controller-summary.json',record)


if __name__=='__main__':main()
