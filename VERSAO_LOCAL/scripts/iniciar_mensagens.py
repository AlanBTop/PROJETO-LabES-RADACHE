"""Servidor isolado do chat e do mock. Usa apenas Python padrão; não abre o banco."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "RADACHE_Modulo_Alunos" / "backend"))
import mock_mensagens

FRONTEND = ROOT / "RADACHE_Modulo_Alunos" / "frontend"


class MensagensHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/assets/"):
            assets = (ROOT / "assets").resolve()
            resource = (assets / unquote(path[len("/assets/"):])).resolve()
            if not resource.is_relative_to(assets) or not resource.is_file():
                self.send_error(404, "Recurso inexistente.")
                return
            body = resource.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(str(resource)))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/mensagens/")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path == mock_mensagens.ENDPOINT:
            return mock_mensagens.responder(self)
        self.send_error(404, "Endpoint inexistente no servidor do prototipo.")

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        # O console não registra o conteúdo das mensagens.
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), MensagensHandler)
    except OSError as erro:
        print("Nao foi possivel iniciar o prototipo:", erro)
        return 1
    url = f"http://localhost:{server.server_port}/mensagens/"
    print("RADACHE Mensagens:", url, flush=True)
    print("API mock local: sem banco e sem envio ao WhatsApp. Ctrl+C para encerrar.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
