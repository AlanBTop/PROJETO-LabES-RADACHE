"""Inicializador da versão local, com portal, SQLite e todas as interfaces."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.request import urlopen
import webbrowser

from auth import gerar_hash_senha


ALL_PAGES = (
    '/', '/gestao/#chamados', '/gestao/#usuarios', '/gestao/#alunos',
    '/alunos/', '/painel-demo/', '/institucional/', '/mensagens/',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=int(os.environ.get('RADACHE_PORT', '8080')))
    parser.add_argument('--page', choices=['/', '/alunos/', '/gestao/', '/mensagens/', '/painel-demo/'], default='/')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--all-pages', action='store_true', help='Abre o portal e todas as areas em abas.')
    args = parser.parse_args()
    os.environ['RADACHE_HOST'] = '127.0.0.1'
    url = f'http://localhost:{args.port}{args.page}'
    pages = ALL_PAGES if args.all_pages else (args.page,)
    # Reabrir um atalho reutiliza somente um servidor desta versão/pasta.
    try:
        with urlopen(f'http://127.0.0.1:{args.port}/healthz', timeout=1) as response:
            estado = json.load(response)
        if estado.get('servico') == 'radache-local' and estado.get('moduloAlunos') == 'sqlite-simulacao' and estado.get('pasta') == str(Path(__file__).resolve().parents[2]):
            print('Servidor local já está ativo:', url, flush=True)
            if not args.no_browser:
                for page in pages:
                    webbrowser.open(f'http://localhost:{args.port}{page}', new=2)
            return 0
    except (OSError, ValueError):
        pass
    if not os.environ.get('RADACHE_USERS'):
        os.environ['RADACHE_USERS']='{}'
    print('Portal local:', url, flush=True)
    print('Gestão por curso: admin@radache.local / admin123.', flush=True)
    print('Técnico: admin@radache.local. Analista: analista@radache.local. Senha de demonstração: admin123.',flush=True)
    import app
    try:
        app.run_server(args.port, open_browser=not args.no_browser, start_page=args.page,
                       start_pages=pages if args.all_pages else None)
    except OSError as erro:
        print('Não foi possível iniciar o servidor:', erro, flush=True)
        print('Tente outra porta: INICIAR_LOCAL.bat --port 8082', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
