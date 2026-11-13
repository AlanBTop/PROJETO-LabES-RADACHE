"""Valida cálculos e filtros do painel com dados controlados, sem alterar o banco real."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'RADACHE_Modulo_Alunos/backend'))
import app
import database
from auth import SessionManager, gerar_hash_senha

checks = []


def ok(message):
    checks.append(message)
    print('OK:', message, flush=True)


with tempfile.TemporaryDirectory() as temp:
    database.DB_PATH = Path(temp) / 'painel.db'
    database.init_db()
    app.auth = SessionManager({'coord': {'role': 'coordenacao', **gerar_hash_senha('senha-teste')}})
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.RadacheRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    records = [
        {'id': i + 1, 'nome': 'Álvaro ' + str(i + 1), 'matricula': 'M' + str(i + 1),
         'campus': 'Câmpus A' if i < 4 or i == 7 else 'Câmpus B', 'curso': 'Curso comum',
         'status': 'inativo' if i == 7 else 'ativo', 'indice_risco': risk}
        for i, risk in enumerate([0, 33, 33.5, None, 66.9, 67, 100, 95])
    ]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/painel-demo/', wait_until='networkidle')
            expect(page.locator('#screen-home')).to_be_visible()
            expect(page.locator('#screen-campus')).not_to_be_visible()
            ok('Sem autenticação, o painel não apresenta registros privados')
            response = page.request.post(base + '/api/login', data={'usuario': 'coord', 'senha': 'senha-teste'})
            token = response.json()['token']
            page.evaluate('(token) => sessionStorage.setItem("radache_token", token)', token)
            page.route('**/api/alunos', lambda route: route.fulfill(json={'sucesso': True, 'dados': records}))
            page.reload(wait_until='networkidle')
            expect(page.locator('#screen-campus')).to_be_visible()
            expect(page.locator('#overview-active')).to_have_text('7')
            expect(page.locator('#overview-critical')).to_have_text('2')
            expect(page.locator('#overview-warning')).to_have_text('2')
            expect(page.locator('#overview-missing')).to_have_text('1')
            expect(page.locator('#coverage-note')).to_contain_text('6 de 7')
            expect(page.locator('#priority-list > button')).to_have_count(4)
            expect(page.locator('#priority-list')).not_to_contain_text('Álvaro 8')
            expect(page.locator('#risk-distribution')).to_have_attribute('aria-label', 'Crítico: 2; Moderado: 2; Estável: 2; Sem índice: 1')
            ok('Zero e 33 são estáveis; 33,5 e 66,9 moderados; 67 e 100 críticos; ausentes e inativos separados')
            expect(page.locator('#comparison-body tr')).to_have_count(2)
            expect(page.locator('#comparison-body tr').first).to_contain_text('Câmpus B')
            page.locator('#overview-campus').select_option('Câmpus A')
            expect(page.locator('#overview-active')).to_have_text('4')
            expect(page.locator('#overview-critical')).to_have_text('0')
            expect(page.locator('#overview-warning')).to_have_text('1')
            expect(page.locator('#overview-missing')).to_have_text('1')
            expect(page.locator('#comparison-body tr')).to_have_count(1)
            expect(page.locator('#priority-list > button')).to_have_count(1)
            ok('Cursos com mesmo nome em câmpus diferentes e filtros preservam os recortes')
            page.locator('#comparison-body button').click()
            expect(page.locator('#screen-dashboard')).to_be_visible()
            expect(page.locator('#card-total')).to_have_text('4')
            expect(page.locator('#card-chance')).to_have_text('22,2%')
            page.locator('#student-risk-filter').select_option('neutral')
            expect(page.locator('#student-table-body tr')).to_have_count(1)
            expect(page.locator('#student-table-body')).to_contain_text('Álvaro 4')
            page.locator('#student-risk-filter').select_option('stable')
            expect(page.locator('#student-table-body tr')).to_have_count(2)
            page.locator('#student-search').fill('alvaro 1')
            expect(page.locator('#student-table-body tr')).to_have_count(1)
            ok('Acesso direto ao curso, média sem ausentes/inativos, filtro de índice e pesquisa sem acento')
            page.locator('#btn-nav-home').click()
            page.locator('#clear-overview-filters').click()
            expect(page.locator('#overview-active')).to_have_text('7')
            expect(page.locator('#comparison-body tr')).to_have_count(2)
            for record in records:
                record['indice_risco'] = None
            page.evaluate('loadSharedStudents()')
            expect(page.locator('#overview-missing')).to_have_text('7')
            expect(page.locator('#overview-critical')).to_have_text('0')
            expect(page.locator('#priority-list > button')).to_have_count(0)
            page.locator('#comparison-body button').first.click()
            expect(page.locator('#card-chance')).to_have_text('—')
            ok('Uma base sem índices não gera média zero nem estudantes classificados como estáveis')
            records.clear()
            page.evaluate('loadSharedStudents()')
            expect(page.locator('#screen-campus')).to_be_visible()
            expect(page.locator('#overview-active')).to_have_text('0')
            expect(page.locator('#comparison-empty')).to_be_visible()
            expect(page.locator('#comparison-body')).to_be_empty()
            expect(page.locator('#priority-list')).to_be_empty()
            ok('Base vazia elimina a seleção obsoleta e não apresenta NaN ou dados anteriores')
            page.request.post(base + '/api/logout', headers={'Authorization': 'Bearer ' + token})
            page.evaluate('loadSharedStudents()')
            expect(page.locator('#screen-home')).to_be_visible()
            expect(page.locator('#overview-active')).to_have_text('—')
            expect(page.locator('#campus-grid')).to_be_empty()
            assert not errors, errors
            ok('Sessão revogada limpa resumos, seletores, tabelas e fichas; sem erros JavaScript')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

out = ROOT / 'validacao/painel'
out.mkdir(parents=True, exist_ok=True)
(out / 'resultado.json').write_text(json.dumps({'verificacoes': checks, 'erros': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print('Concluído:', len(checks), 'verificações.', flush=True)
