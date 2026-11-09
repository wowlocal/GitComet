from pathlib import Path
import subprocess, os, json, hashlib, plistlib, shutil, sys, time

out = Path(__file__).resolve().parent
app = Path('/path/to/workspace/GitComet-framework-ab')
framework = Path('/path/to/workspace/gpui-ce-framework-ab')
mode = sys.argv[1]
assert mode in ('stock', 'fixed')

def snapshot(root):
    names = set(subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=root,text=True).splitlines())
    names.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines())
    return {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sorted(names)}

cores = int(subprocess.check_output(['sysctl','-n','hw.perflevel0.physicalcpu'],text=True))
jobs = min(4, max(1, cores-2))
env = os.environ.copy()
env.update(CARGO_BUILD_JOBS=str(jobs),CMAKE_BUILD_PARALLEL_LEVEL=str(jobs),MAKEFLAGS=f'-j{jobs}',CARGO_TARGET_DIR='/path/to/workspace/GitComet/target')
before = {'app':snapshot(app),'framework':snapshot(framework)}
record = {'condition':mode,'jobs':jobs,'profile':'release: opt3 fatLTO codegen-units1','sources':before,'started_unix_s':time.time()}
cmd = ['cargo','+1.99','build','--release','--locked','--offline','-j'+str(jobs),'-p','gitcomet','--features','ui-gpui,gix','--bin','gitcomet']
record['command'] = cmd
(out/(mode+'-build.json')).write_text(json.dumps(record,indent=2))
with (out/(mode+'-build.log')).open('w') as log:
    result = subprocess.run(cmd,cwd=app,env=env,stdout=log,stderr=subprocess.STDOUT)
record.update(exit_code=result.returncode,finished_unix_s=time.time())
(out/(mode+'-build.json')).write_text(json.dumps(record,indent=2))
assert result.returncode == 0, f'{mode} build failed; see log'
assert before == {'app':snapshot(app),'framework':snapshot(framework)}, 'Source changed during compilation'
source = Path(env['CARGO_TARGET_DIR'])/'release/gitcomet'
bundle = out/('GitComet-'+mode+'.app')
assert not bundle.exists()
template = out/'GitComet-stock.app' if mode=='fixed' else Path('/Applications/GitComet.app')
shutil.copytree(template,bundle,symlinks=True)
binary = bundle/'Contents/MacOS/gitcomet'
shutil.copy2(source,binary)
info_path = bundle/'Contents/Info.plist'
info = plistlib.loads(info_path.read_bytes())
info.update(GitCometSourceCommit='ad5df1d185c1a8805870bffcfde592d5e3ce355a',GitCometBenchmarkCondition=mode,GitCometFrameworkCommit=('c55d73659dd6560d3e70281056f841e6d366c0e5' if mode=='stock' else 'aad11809345380e3ae2d79f6cfcfc5aaf2af4edc'))
info_path.write_bytes(plistlib.dumps(info))
subprocess.run(['codesign','--force','--sign','Developer ID Application: <your signing identity>','--options','runtime','--timestamp',str(bundle)],check=True)
subprocess.run(['codesign','--verify','--strict',str(bundle)],check=True)
record.update(bundle=str(bundle),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),source_binary_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),packaged_unix_s=time.time())
(out/(mode+'-build.json')).write_text(json.dumps(record,indent=2))
print(json.dumps({'condition':mode,'bundle':str(bundle),'binary_sha256':record['binary_sha256'],'seconds':record['finished_unix_s']-record['started_unix_s']}),flush=True)
