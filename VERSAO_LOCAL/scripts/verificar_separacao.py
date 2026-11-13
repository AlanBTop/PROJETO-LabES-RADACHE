"""Percorre todas as interfaces locais em Edge, com rede externa bloqueada e SQLite temporário."""
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
import gestao_local
from auth import SessionManager, gerar_hash_senha

OUT = ROOT / 'validacao/separacao'
OUT.mkdir(parents=True, exist_ok=True)
checks, errors, externos, ausentes = [], [], [], []


def ok(nome):
    checks.append(nome)
    print('OK:', nome, flush=True)


def login(page, email='admin@radache.local'):
    expect(page.locator('#login-submit')).to_be_enabled()
    page.locator('#login-email').fill(email)
    page.locator('#login-password').fill('admin123')
    page.locator('#login-submit').click()
    expect(page.locator('#app-shell')).to_be_visible()
    expect(page.locator('#refresh-button')).to_be_enabled()


with tempfile.TemporaryDirectory() as temp:
    database.DB_PATH = Path(temp) / 'navegacao.db'
    database.init_db()
    gestao_local.iniciar()
    app.auth = SessionManager({'coord': {'role': 'coordenacao', **gerar_hash_senha('admin123')}})
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.RadacheRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
            def intercept(route):
                if not route.request.url.startswith(base):
                    externos.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()
            context.route('**/*', intercept)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: ausentes.append(response.url) if response.status >= 400 and '/api/' not in response.url else None)
            page.goto(base, wait_until='networkidle')
            expect(page.locator('.cards .card')).to_have_count(6)
            page.screenshot(path=str(OUT / 'portal-desktop.png'), full_page=True)
            for width in [320, 390, 768, 1440]:
                page.set_viewport_size({'width': width, 'height': 900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
            ok('Portal: seis áreas e layout de 320 a 1440 px')
            page.locator('a[href="/gestao/#usuarios"]').click()
            login(page)
            expect(page.locator('#users-page')).to_be_visible()
            expect(page.locator('#users-body tr')).to_have_count(2)
            page.locator('#create-user-button').click()
            page.locator('#user-form [name=nome]').fill('Pessoa teste')
            page.locator('#user-form [name=email]').fill('pessoa@radache.local')
            page.locator('#user-course').select_option('direito')
            page.locator('#user-save').click()
            expect(page.locator('#users-body')).to_contain_text('Pessoa teste')
            ok('Equipe: link direto após login e criação persistida')
            page.locator('[data-page=alunos]').click()
            expect(page.locator('#students-body tr')).to_have_count(8)
            page.locator('#students-body button[data-action=ver-aluno]').first.click()
            expect(page.locator('#student-detail-content')).to_be_visible()
            expect(page.locator('#student-assessment')).to_contain_text('Índice de risco')
            page.keyboard.press('Escape')
            page.locator('#create-student-button').click()
            for name, value in {'nome': 'Aluno navegação', 'matricula': 'NAV123', 'campus': 'Cáceres', 'periodo': '2', 'email': 'aluno@example.com', 'telefone': '65999990000'}.items():
                page.locator('#student-form [name=' + name + ']').fill(value)
            page.locator('#student-course').select_option('direito')
            page.locator('#student-save').click()
            expect(page.locator('#students-body')).to_contain_text('Aluno navegação')
            row = page.locator('#students-body tr').filter(has_text='Aluno navegação')
            row.locator('button[data-action=editar-aluno]').click()
            page.locator('#student-form [name=nome]').fill('Aluno atualizado')
            page.locator('#student-save').click()
            expect(page.locator('#students-body')).to_contain_text('Aluno atualizado')
            ok('Alunos: lista, ficha com avaliação, cadastro e edição no SQLite')
            page.locator('[data-page=chamados]').click()
            expect(page.locator('[data-ticket-id]')).to_have_count(4)
            page.locator('[data-ticket-id="exemplo-1"]').click()
            expect(page.locator('#detail-content')).to_be_visible()
            page.locator('#action-text').fill('Registro feito pelo teste do navegador.')
            page.locator('#ticket-action-save').click()
            expect(page.locator('#timeline')).to_contain_text('Registro feito pelo teste do navegador.')
            page.locator('#assume-ticket').click()
            expect(page.locator('#detail-metadata')).to_contain_text('Administração local')
            page.locator('#ticket-action-type').select_option('status')
            page.locator('#action-status').select_option('em_andamento')
            page.locator('#action-text').fill('Iniciar acompanhamento.')
            page.locator('#ticket-action-save').click()
            expect(page.locator('#detail-badges')).to_contain_text('Em andamento')
            expect(page.locator('#ticket-action-form')).to_have_attribute('aria-busy', 'false')
            page.locator('#ticket-dialog [data-close-dialog]').click()
            expect(page.locator('#ticket-dialog')).not_to_be_visible()
            page.screenshot(path=str(OUT / 'chamados-desktop.png'), full_page=True)
            for width in [320, 390, 768]:
                page.set_viewport_size({'width': width, 'height': 900})
                page.screenshot(path=str(OUT / ('chamados-' + str(width) + '.png')), full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('Array.from(document.querySelectorAll("body *")).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().width]).slice(0,25)')
                if width == 390: page.screenshot(path=str(OUT / 'chamados-mobile.png'), full_page=True)
            ok('Chamados: quadro, detalhe, comentário, responsável, status e layout móvel')
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.goto(base + '/gestao/#chamados', wait_until='domcontentloaded')
            page.reload(wait_until='domcontentloaded')
            login(page)
            page.locator('[data-ticket-id="exemplo-1"]').click()
            expect(page.locator('#timeline')).to_contain_text('Registro feito pelo teste do navegador.')
            page.keyboard.press('Escape')
            ok('Persistência dos registros após recarregar e autenticar novamente')
            page.goto(base + '/painel-demo/', wait_until='domcontentloaded')
            expect(page.locator('#panel-mode')).to_contain_text('Entre na gestão')
            page.locator('#btn-go-admin').click()
            expect(page).to_have_url(base + '/alunos/?destino=painel')
            page.locator('#login-usuario').fill('coord')
            page.locator('#login-senha').fill('admin123')
            page.locator('#login-form button').click()
            expect(page).to_have_url(base + '/painel-demo/')
            expect(page.locator('#campus-grid > button')).not_to_have_count(0)
            page.locator('#campus-grid > button').first.click()
            page.locator('#courses-grid > button').first.click()
            expect(page.locator('#student-table-body tr')).not_to_have_count(0)
            page.locator('#student-table-body tr').first.click()
            expect(page.locator('#student-modal')).to_be_visible()
            page.keyboard.press('Escape')
            ok('Painel: login guiado, câmpus, cursos, dashboard e ficha')
            page.locator('#btn-nav-home').click()
            expect(page.locator('#btn-go-student')).to_have_count(0)
            expect(page.locator('#screen-whatsapp')).to_have_count(0)
            expect(page.locator('body')).not_to_contain_text('Prévia RADACHE')
            ok('Prévia RADACHE removida do painel e da navegação')
            page.goto(base + '/alunos/', wait_until='networkidle')
            expect(page.locator('#alunos-tbody')).to_contain_text('Aluno atualizado')
            ok('Módulo original compartilha o aluno cadastrado na gestão')
            page.goto(base + '/mensagens/', wait_until='networkidle')
            expect(page.locator('#workspace')).to_be_visible()
            page.locator('a.brand-mark').click()
            expect(page.locator('.cards')).to_be_visible()
            ok('Mensagens acessíveis e retorno ao portal')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(OUT / 'portal-mobile.png'), full_page=True)
            assert not errors, errors
            assert not externos, externos
            assert not ausentes, ausentes
            ok('Sem erros JavaScript, recursos ausentes ou pedidos externos')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
(OUT / 'resultado.json').write_text(json.dumps({'checks': checks, 'errors': errors, 'external_requests': externos, 'missing_resources': ausentes}, ensure_ascii=False, indent=2), encoding='utf-8')
print('Concluído:', len(checks), 'verificações.', flush=True)
