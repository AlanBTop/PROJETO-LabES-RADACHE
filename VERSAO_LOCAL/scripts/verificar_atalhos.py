"""Testa os atalhos reais e reutilização de servidor com banco descartável."""
from pathlib import Path
import json
import os
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, RADACHE_SEM_PAUSA='1', RADACHE_DB=str(Path(temp) / 'atalhos.db'))
    env.pop('RADACHE_USERS', None)
    processo = subprocess.Popen(['cmd.exe', '/c', str(ROOT / 'INICIAR_LOCAL.bat'), '--no-browser', '--port', str(port)],
                                env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(80):
            try:
                with urlopen(f'http://127.0.0.1:{port}/healthz', timeout=1) as response:
                    assert json.load(response)['servico'] == 'radache-local'
                break
            except OSError:
                if processo.poll() is not None:
                    raise RuntimeError(processo.communicate()[0].decode(errors='replace'))
                time.sleep(.1)
        else:
            raise RuntimeError('Servidor não iniciou.')
        for nome in ['INICIAR_RADACHE.bat', 'INICIAR_GESTAO_POR_CURSO.bat', 'INICIAR_MENSAGENS.bat']:
            retorno = subprocess.run(['cmd.exe', '/c', str(ROOT / nome), '--no-browser', '--port', str(port)],
                                     env=env, cwd=ROOT, capture_output=True, timeout=10,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            assert retorno.returncode == 0, retorno.stdout.decode(errors='replace')
            assert 'ativo' in retorno.stdout.decode(errors='replace')
            print('OK:', nome, 'reutiliza servidor existente.', flush=True)
        for path in ['/', '/alunos/', '/gestao/', '/painel-demo/', '/mensagens/']:
            with urlopen(f'http://127.0.0.1:{port}' + path, timeout=3) as response:
                assert response.status == 200
        print('OK: cinco entradas servidas pelos atalhos com Python padrão.', flush=True)
    finally:
        if processo.poll() is None:
            subprocess.run(['taskkill', '/PID', str(processo.pid), '/T', '/F'], capture_output=True,
                           check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        processo.communicate(timeout=5)
