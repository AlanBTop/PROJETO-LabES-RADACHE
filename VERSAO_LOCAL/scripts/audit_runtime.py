"""Medições e revisão de seis interfaces em SQLite descartável e Edge headless."""
from contextlib import closing
import http.client
import json
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'RADACHE_Modulo_Alunos/backend'))
import app
import database
import gestao_local
import simulation_store as store
from playwright.sync_api import sync_playwright, expect

OUT = ROOT / 'validacao/auditoria_20261111'


def run(stage):
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = {'stage': stage, 'layouts': [], 'errors': [], 'failed_resources': [], 'external_requests': []}
    with tempfile.TemporaryDirectory(prefix='radache-runtime-') as tmp:
        database.DB_PATH = Path(tmp) / 'legacy.db'
        store.ACADEMIC = Path(tmp) / 'academic.db'
        store.OPERATIONAL = Path(tmp) / 'operational.db'
        store.init(); database.init_db(); gestao_local.iniciar()
        for i in range(400):
            store.save(dict(nome=f'TESTE Auditoria {i:03}', matricula=f'AUD-{i}', curso='Ciência da Computação', periodo=3, nota_media=8, frequencia=90))
        for aid in range(1, 5):
            session = store.session(aid)
            for n, text in enumerate(('1', '4', '1')):
                store.session(aid, dict(acao='responder', texto=text, sessao_id=session['sessao_id'], id_cliente=f'audit-{aid}-{n}'))
        original_connect = store.connect
        queries = []
        def traced(*args, **kwargs):
            conn = original_connect(*args, **kwargs)
            conn.set_trace_callback(queries.append)
            return conn
        durations = []
        with patch.object(store, 'connect', traced):
            for _ in range(7):
                queries.clear()
                started = time.perf_counter()
                rows = store.projected()
                durations.append((time.perf_counter() - started) * 1000)
        evidence['projection'] = {'students': len(rows), 'selects': sum(q.lstrip().upper().startswith('SELECT') for q in queries),
                                  'median_ms': round(statistics.median(durations), 3), 'samples_ms': durations}
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.RadacheRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            conn.request('GET', '/assets/radache-theme.css'); response = conn.getresponse()
            content = response.read(); headers = dict(response.getheaders()); conn.close()
            conditional = {'If-None-Match': headers.get('ETag', '"audit-no-validator"')}
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            conn.request('GET', '/assets/radache-theme.css', headers=conditional)
            response = conn.getresponse()
            evidence['static'] = {'initial_bytes': len(content), 'repeat_status': response.status,
                                  'repeat_bytes': len(response.read()), 'cache_control': headers.get('Cache-Control')}
            conn.close()
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
                context = browser.new_context(reduced_motion='reduce')
                def restrict(route):
                    if route.request.url.startswith(base + '/'):
                        route.continue_()
                    else:
                        evidence['external_requests'].append(route.request.url); route.abort()
                context.route('**/*', restrict)
                page = context.new_page()
                page.on('pageerror', lambda e: evidence['errors'].append(str(e)))
                page.on('response', lambda r: evidence['failed_resources'].append({'url': r.url.replace(base, ''), 'status': r.status}) if r.status >= 400 and not any(prefix in r.url for prefix in ('/api/', '/simulation-api/', '/mock-api/')) else None)
                paths = ('/', '/gestao/', '/alunos/', '/painel-demo/', '/institucional/', '/mensagens/')
                for authenticated in (False, True):
                    if authenticated:
                        response = context.request.post(base + '/api/login', data={'usuario': 'admin@radache.local', 'senha': 'admin123'})
                        assert response.status == 200, response.status
                        token = response.json()['token']
                        context.add_init_script('sessionStorage.setItem("radache_token", ' + json.dumps(token) + ');')
                    for width in (320, 390, 768, 1366, 1920):
                        page.set_viewport_size({'width': width, 'height': 900})
                        for path in paths:
                            page.goto(base + path, wait_until='networkidle')
                            if authenticated and path == '/gestao/':
                                page.locator('#login-email').fill('admin@radache.local')
                                page.locator('#login-password').fill('admin123')
                                page.locator('#login-submit').click()
                                expect(page.locator('#app-shell')).to_be_visible()
                                expect(page.locator('#refresh-button')).to_be_enabled()
                            if authenticated and path in ('/alunos/', '/painel-demo/', '/institucional/'):
                                expect(page.locator('#workspace')).to_be_visible()
                            layout = page.evaluate('''() => ({width: innerWidth, scroll: document.documentElement.scrollWidth,
                              overflow: [...document.querySelectorAll('body *')].filter(e => {
                                const r=e.getBoundingClientRect(); return r.width && r.right>innerWidth+1 &&
                                getComputedStyle(e).position!=='fixed' && !e.closest('.table-scroll, .table-wrapper, .kanban-board');
                              }).slice(0,8).map(e=>e.tagName+'.'+e.className)})''')
                            evidence['layouts'].append({'path': path, 'authenticated': authenticated, **layout})
                            if authenticated and width in (320, 1366):
                                page.screenshot(path=str(OUT / f'{stage}_{path.strip("/") or "portal"}_{width}.png'), full_page=True)
                evidence['error_messages'] = page.evaluate('''async () => {
                  const {ApiService} = await import('/gestao/js/services/api-service.js');
                  const savedFetch = window.fetch, messages = [];
                  try {
                    const api = new ApiService({token: async () => 'fixture'}, {apiBase:'/api/local/',timeoutMs:1000});
                    for (const erro of ['Mensagem textual preservada.', {mensagem:'Mensagem estruturada preservada.'}]) {
                      window.fetch = async () => ({status:400,ok:false,json:async()=>({sucesso:false,erro})});
                      try {await api.requisitar('fixture');} catch(e) {messages.push(e.message);}
                    }
                    return messages;
                  } finally {window.fetch=savedFetch;}
                }''')
                if stage == 'after':
                    assert evidence['error_messages'] == ['Mensagem textual preservada.', 'Mensagem estruturada preservada.']
                    page.goto(base + '/')
                    page.keyboard.press('Tab')
                    expect(page.locator('.skip-link')).to_be_focused()
                    page.keyboard.press('Enter')
                    expect(page.locator('#main-content')).to_be_focused()
                    page.set_viewport_size({'width':320, 'height':900})
                    page.goto(base + '/institucional/', wait_until='networkidle')
                    expect(page.locator('.sidebar nav')).to_be_visible()
                    evidence['mobile_navigation'] = page.locator('.sidebar nav a').count()
                    assert page.locator('#course').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)') >= 16
                browser.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
    (OUT / f'{stage}_runtime.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    overflows = [r for r in evidence['layouts'] if r['scroll'] > r['width']]
    print(json.dumps({k: v for k, v in evidence.items() if k != 'layouts'}, ensure_ascii=False, indent=2))
    print('Overflows:', json.dumps(overflows, ensure_ascii=False))
    if stage == 'after':
        assert not overflows, overflows
        assert not evidence['errors'], evidence['errors']
        assert not evidence['failed_resources'], evidence['failed_resources']
        assert not evidence['external_requests'], evidence['external_requests']
        assert evidence['projection']['selects'] == 4
        assert evidence['static']['repeat_status'] == 304


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else 'after')
