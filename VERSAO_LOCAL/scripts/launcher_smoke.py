"""Confere o .bat real sem abrir o navegador nem tocar no banco existente."""
from pathlib import Path
import http.client
import json
import os
import socket
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ, RADACHE_DB=str(Path(temp) / "launcher.db"), RADACHE_PORT=str(port))
    env.pop("RADACHE_USERS", None)
    launcher = root / "RADACHE_Modulo_Alunos/iniciar_modulo.bat"
    process = subprocess.Popen(["cmd.exe", "/c", str(launcher), "--no-browser"],
                               cwd=root, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for attempt in range(80):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                conn.request("POST", "/api/login", json.dumps({"usuario": "coord", "senha": "admin123"}),
                             {"Content-Type": "application/json"})
                response = conn.getresponse()
                payload = json.loads(response.read())
                conn.close()
                assert response.status == 200, payload
                assert payload["usuario"]["role"] == "coordenacao"
                print("OK: inicializador .bat inicia Python, configura contas locais e autentica coord.")
                break
            except (ConnectionError, OSError):
                if process.poll() is not None:
                    raise RuntimeError(process.communicate()[0].decode(errors="replace"))
                time.sleep(.1)
        else:
            raise RuntimeError("Servidor não iniciou a tempo.")
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        process.communicate(timeout=5)
