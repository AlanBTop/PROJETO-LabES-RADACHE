"""Executa toda a suíte e registra o resultado em UTF-8."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
backend=ROOT/'RADACHE_Modulo_Alunos/backend'
sys.path.insert(0,str(backend))
out=ROOT/'validacao/simulacao_local/regressao.log'
out.parent.mkdir(parents=True,exist_ok=True)
suite=unittest.defaultTestLoader.discover(str(backend/'tests'))
with out.open('w',encoding='utf-8') as log:
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
print(f'Testes: {result.testsRun}; falhas: {len(result.failures)}; erros: {len(result.errors)}; ignorados: {len(result.skipped)}')
raise SystemExit(not result.wasSuccessful())
