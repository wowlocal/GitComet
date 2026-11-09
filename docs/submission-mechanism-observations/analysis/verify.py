"""Verify published saved data without native calls, builds or network access."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    listed = set()
    for line in (ROOT / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        relative = PurePosixPath(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert name not in listed
        listed.add(name)
        path = ROOT / name
        assert path.is_file() and not path.is_symlink()
        assert digest(path) == expected, name
    actual = {str(path.relative_to(ROOT)) for path in ROOT.rglob('*')
              if path.is_file() and path.name != 'SHA256SUMS'}
    assert actual == listed, (actual - listed, listed - actual)
    lock = load(ROOT / 'analysis/prepilot-lock.json')
    for name, expected in lock['files'].items():
        assert digest(ROOT / 'analysis' / name) == expected, name
    source = load(ROOT / 'source/source-manifest.json')
    for component in ['framework', 'app']:
        for role in ['baseline', 'delta', 'full']:
            path = ROOT / 'source' / f'{component}-{role}.patch'
            assert digest(path) == source['roots'][component][f'{role}_patch_sha256']
    with tempfile.TemporaryDirectory(prefix='submission-saved-check-') as temporary:
        temp = Path(temporary)
        for label in ['pilot-excluded', 'confirmation']:
            output = temp / f'{label}.json'
            subprocess.run([sys.executable, '-B', 'analysis/analyze.py',
                            f'runs/{label}/native.jsonl', '--frames',
                            f'runs/{label}/frames.jsonl', '--output', str(output)],
                           cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
            assert load(output) == load(ROOT / 'runs' / label / 'submission-mechanism-analysis.json'), label
        audit = temp / 'audit.json'
        subprocess.run([sys.executable, '-B', 'analysis/audit.py', '--output', str(audit)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        assert load(audit) == load(ROOT / 'independent-raw-audit.json')
    print(f'PASS: {len(listed)} file hashes, both registered analyses and independent raw audit')


if __name__ == '__main__':
    main()
