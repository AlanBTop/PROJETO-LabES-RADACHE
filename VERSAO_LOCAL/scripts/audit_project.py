"""Auditoria reproduzível, sem escrever nos bancos da instalação.

Uso: python scripts/audit_project.py baseline|after
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validacao/auditoria_20261111'
BACKEND = ROOT / 'RADACHE_Modulo_Alunos/backend'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(stage):
    OUT.mkdir(parents=True, exist_ok=True)
    # A impressão digital permite verificar que os testes não alteraram dados reais.
    databases = {str(p.relative_to(ROOT)): digest(p)
                 for p in ROOT.rglob('*.db') if 'validacao' not in p.parts}
    sources = {}
    for folder in ('portal', 'gestao', 'institucional', 'painel-demo', 'assets', 'RADACHE_Modulo_Alunos', 'scripts'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.js', '.css', '.html', '.sql', '.svg', '.bat', '.md') and '__pycache__' not in path.parts:
                relative = path.relative_to(ROOT)
                sources[str(relative)] = {'sha256': digest(path), 'bytes': path.stat().st_size}
                if stage == 'baseline':
                    target = OUT / 'original' / relative
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, target)
    (OUT / f'{stage}_inventory.json').write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='radache-audit-') as tmp:
        env = {**os.environ, 'RADACHE_DB': str(Path(tmp) / 'legacy.db'),
               'RADACHE_MOCK_DB': str(Path(tmp) / 'academic.db'),
               'RADACHE_SIM_DB': str(Path(tmp) / 'operational.db'),
               'RADACHE_USERS': '{}', 'PYTHONPATH': str(BACKEND), 'PYTHONIOENCODING': 'utf-8'}
        start = time.perf_counter()
        with (OUT / f'{stage}_tests.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                                    cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
        elapsed = time.perf_counter() - start
    unchanged = databases == {str(p.relative_to(ROOT)): digest(p)
                             for p in ROOT.rglob('*.db') if 'validacao' not in p.parts}
    summary = {'stage': stage, 'exit_code': result.returncode, 'seconds': round(elapsed, 2),
               'installation_databases_unchanged': unchanged, 'source_files': len(sources)}
    (OUT / f'{stage}_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)
    print('\n'.join((OUT / f'{stage}_tests.log').read_text(encoding='utf-8').splitlines()[-8:]))
    return result.returncode or (0 if unchanged else 1)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else 'after'))
