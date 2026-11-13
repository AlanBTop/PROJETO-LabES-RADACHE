"""Inicia o launcher real com bancos temporários e valida execução independente."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env={**os.environ,'RADACHE_DB':str(folder/'legacy.db'),'RADACHE_MOCK_DB':str(folder/'mock_sigaa.db'),'RADACHE_SIM_DB':str(folder/'radache.db')}
    with (folder/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,str(ROOT/'RADACHE_Modulo_Alunos/backend/run_local.py'),'--no-browser','--port',str(port)],
            cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(50):
                try:
                    with urlopen(f'http://127.0.0.1:{port}/healthz',timeout=1) as r:health=json.load(r)
                    break
                except OSError:time.sleep(.1)
            else:raise AssertionError('Servidor não iniciou: '+(folder/'server.log').read_text())
            assert health['moduloAlunos']=='sqlite-simulacao'
            assert (folder/'mock_sigaa.db').stat().st_size>0
            assert (folder/'radache.db').stat().st_size>0
            print('OK launcher real: dois bancos SQLite criados, sem iniciar PostgreSQL ou integração externa.')
        finally:
            process.terminate();process.wait(timeout=5)
