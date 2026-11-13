"""Executa os cenários de navegador existentes e preserva os logs desta auditoria."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validacao/auditoria_20261111'
SCENARIOS = ('verify_local_simulation_browser.py', 'verify_staff_ui.py',
             'verify_attendance_ui.py', 'verify_analytics_browser.py', 'verify_institutional_browser.py')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    selected = tuple(sys.argv[1:]) or SCENARIOS
    if not set(selected) <= set(SCENARIOS):
        raise ValueError('Cenário de auditoria desconhecido.')
    results = json.loads((OUT / 'browser_flows.json').read_text(encoding='utf-8')) if sys.argv[1:] and (OUT / 'browser_flows.json').exists() else []
    for script in selected:
        with tempfile.TemporaryDirectory(prefix='radache-flow-') as tmp:
            env = {**os.environ, 'RADACHE_DB': str(Path(tmp) / 'legacy.db'),
                   'RADACHE_MOCK_DB': str(Path(tmp) / 'academic.db'),
                   'RADACHE_SIM_DB': str(Path(tmp) / 'operational.db'),
                   'RADACHE_USERS': '{}', 'PYTHONIOENCODING': 'utf-8',
                   'PYTHONPATH': str(ROOT / 'RADACHE_Modulo_Alunos/backend')}
            start = time.perf_counter()
            with (OUT / (script + '.log')).open('w', encoding='utf-8') as log:
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script)], cwd=ROOT,
                                        env=env, stdout=log, stderr=subprocess.STDOUT)
            entry = dict(script=script, exit_code=result.returncode, seconds=round(time.perf_counter() - start, 2))
            results = [r for r in results if r['script'] != script] + [entry]
            print(json.dumps(entry), flush=True)
            (OUT / 'browser_flows.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
