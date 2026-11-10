"""Portable saved-data verification; no native APIs or acquisition."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, math

ROOT = Path(__file__).resolve().parent

def require(value, message):
    if not value: raise ValueError(message)

def equivalent(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if type(a) is float or type(b) is float:
        return type(a) in (int, float) and type(b) in (int, float) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    return type(a) is type(b) and a == b

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(__debug__, 'Do not run optimized Python')
    import sys
    sys.dont_write_bytecode = True
    inventory = {}
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        file = ROOT/name
        require(not file.is_symlink() and file.resolve().is_relative_to(ROOT), 'Unsafe inventory path')
        require(hashlib.sha256(file.read_bytes()).hexdigest() == digest, 'Inventory mismatch: '+name)
        inventory[name] = digest
    actual = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p != ROOT/'SHA256SUMS'}
    require(actual == set(inventory), 'Unexpected/missing dataset files')
    spec = importlib.util.spec_from_file_location('frozen_analyzer', ROOT/'analyzer/analyze-exact.py')
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    plan = json.loads((ROOT/'stock-vs-fix/input-plan.json').read_text())
    export = json.loads((ROOT/'export-manifest.json').read_text())
    if args.output:
        args.output = args.output.resolve()
        require(not args.output.exists() and not args.output.is_relative_to(ROOT), 'Output must be a new directory outside dataset')
        args.output.mkdir(parents=True)
    for arm in export['arms']:
        manifest = json.loads((ROOT/arm/'manifest.json').read_text())
        published = json.loads((ROOT/arm/'analysis.json').read_text())
        runs = []
        for entry in manifest['runs']:
            run = (ROOT/entry['path']).resolve()
            require(run.is_relative_to(ROOT), 'Unsafe run path')
            value = analyzer.analyze_run(run, plan)
            value.update(condition=entry['condition'], ordinal=entry['ordinal'], path=entry['path'])
            runs.append(value)
        pairs, summaries = analyzer.contrasts(runs)
        result = dict(published, runs=runs, paired_contrasts=pairs, summaries=summaries)
        require(equivalent(result, published), 'Recomputed analysis differs: '+arm)
        if args.output:
            destination = args.output/arm
            destination.mkdir()
            (destination/'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
            analyzer.plot(runs, destination, arm)
        print(json.dumps({'arm':arm, 'verified_runs':len(runs), 'adjacent_pairs':len(pairs), 'saved_data_parity':'passed'}))

if __name__ == '__main__': main()
