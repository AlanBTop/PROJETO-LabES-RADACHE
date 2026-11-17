"""Inicializador da avaliação no Render Free; não envia mensagens externas."""
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
import io
import os
from pathlib import Path
import re
import signal
import sys
import threading


class EvaluationServer(ThreadingHTTPServer):
    """Limita conexões simultâneas; os handlers já usam timeout de leitura."""
    daemon_threads = True

    def __init__(self, address, handler, max_connections=24):
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def configure():
    hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip().lower()
    hosts = os.environ.get('RADACHE_ALLOWED_HOSTS', hostname).split(',')
    hosts = [h.strip().lower() for h in hosts if h.strip()]
    if not hosts or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', h) or '..' in h for h in hosts):
        raise ValueError('Configure RADACHE_ALLOWED_HOSTS ou RENDER_EXTERNAL_HOSTNAME com nomes de host válidos.')
    from credential_policy import EVALUATION_ACCOUNTS
    values = [os.environ.get(key, '') for key in EVALUATION_ACCOUNTS.values()]
    if any(len(v) < 16 or v == 'admin123' for v in values) or len(set(values)) != len(values):
        raise ValueError('Configure quatro senhas iniciais privadas e diferentes, com pelo menos 16 caracteres.')
    port = int(os.environ.get('PORT', '10000'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT deve ser uma porta TCP válida.')
    data = Path(os.environ.get('RADACHE_DATA_DIR', '/tmp/radache02-26labes')).resolve()
    static = Path(__file__).resolve().parents[2]
    if data == static or static in data.parents:
        raise ValueError('RADACHE_DATA_DIR deve ficar fora das pastas da aplicação.')
    data.mkdir(parents=True, exist_ok=True)
    os.environ.update(RADACHE_PUBLIC_EVALUATION='1', RADACHE_DEMO='0', RADACHE_ENV='evaluation',
                      RADACHE_HOST='0.0.0.0', RADACHE_ALLOWED_HOSTS=','.join(hosts), RADACHE_HTTPS='1',
                      RADACHE_USERS='{}', RADACHE_WHATSAPP_LEMBRETES='0',
                      RADACHE_DB=str(data/'legacy.db'), RADACHE_MOCK_DB=str(data/'academic.db'),
                      RADACHE_SIM_DB=str(data/'operational.db'))
    for key in tuple(os.environ):
        if key.startswith('WHATSAPP_'):
            del os.environ[key]
    return port


def prepare_data():
    import app
    import database
    import gestao_local
    import simulation_store
    # O povoamento faz conferências internas e é idempotente. Não imprimir seus dados.
    with redirect_stdout(io.StringIO()):
        database.init_db(); simulation_store.init(); gestao_local.iniciar()
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
        from populate_universities import populate
        populate()
    return app.RadacheRequestHandler


def main():
    try:
        port = configure()
        handler = prepare_data()
    except (ValueError, OSError):
        print('Inicialização recusada. Verifique hosts, porta, diretório privado e senhas de avaliação.', flush=True)
        return 1
    server = EvaluationServer(('0.0.0.0', port), handler)
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    print('RADACHE02/26LabES: avaliação iniciada; dados fictícios compartilhados e descartáveis.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
