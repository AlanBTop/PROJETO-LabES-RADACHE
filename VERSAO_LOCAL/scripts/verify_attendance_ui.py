"""Conferência curta da interface de gestor e atendente, com dados temporários."""
from pathlib import Path
import sys
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend/tests'))
import test_attendance
import simulation_store as store

fixture=test_attendance.AttendanceFlow('test_complete_flow_and_access_boundaries')
fixture.setUp()
out=ROOT/'validacao/atendimentos';out.mkdir(parents=True,exist_ok=True)
try:
    aid=store.save(dict(nome='TESTE Atendimento UI',matricula='ATEND-UI',curso='Ciência da Computação',nota_media=8,frequencia=90))
    fixture.complete(aid)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(fixture.base+'/') else r.abort())
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def login(name):
            page.goto(fixture.base+'/gestao/')
            page.locator('#login-email').fill(name+'@radache.local');page.locator('#login-password').fill('admin123');page.locator('#login-submit').click()
            expect(page.locator('#app-shell')).to_be_visible()
        login('coord')
        expect(page.locator('#page-title')).to_have_text('Gestão de Atendimentos e Equipe')
        page.locator('[data-page="usuarios"]').click();page.locator('#create-user-button').click()
        page.locator('#user-form input[name="nome"]').fill('Ana UI');page.locator('#user-form input[name="email"]').fill('ana-ui@radache.local')
        page.locator('#user-initial-password').fill('admin123')
        page.locator('#user-course').select_option('ciencia-da-computacao');page.locator('#user-save').click()
        expect(page.locator('#user-dialog')).not_to_be_visible()
        expect(page.locator('#users-body')).to_contain_text('Ana UI')
        page.locator('[data-page="chamados"]').click()
        expect(page.locator('[data-ticket-id]').filter(has_text='TESTE Atendimento UI')).to_have_count(1)
        page.locator('[data-ticket-id]').filter(has_text='TESTE Atendimento UI').click()
        expect(page.locator('#detail-content')).to_be_visible()
        page.locator('#ticket-action-type').select_option('responsavel')
        uid=page.locator('#action-responsible option').filter(has_text='Ana UI').get_attribute('value')
        page.locator('#action-responsible').select_option(uid)
        page.locator('#action-text').fill('Distribuição inicial para Ana UI');page.locator('#ticket-action-save').click()
        expect(page.locator('#timeline')).to_contain_text('Distribuição inicial para Ana UI')
        expect(page.locator('#ticket-action-form')).to_have_attribute('aria-busy','false')
        page.locator('#ticket-dialog [data-close-dialog]').click()
        expect(page.locator('#ticket-dialog')).not_to_be_visible()
        expect(page.locator('#refresh-button')).to_be_enabled()
        page.screenshot(path=str(out/'gestor.png'),full_page=True)
        page.locator('#logout-button').click();login('ana-ui')
        expect(page.locator('#page-title')).to_have_text('Meus Atendimentos')
        expect(page.locator('#attendance-rows')).to_contain_text('TESTE Atendimento UI')
        expect(page.locator('#management-nav')).not_to_be_visible()
        page.locator('#attendance-rows button').click()
        expect(page.locator('#detail-content')).to_be_visible()
        expect(page.locator('#ticket-action-type option[value="responsavel"]')).to_have_count(0)
        page.locator('#ticket-action-type').select_option('status');page.locator('#action-status').select_option('resolvido')
        page.locator('#action-text').fill('Orientação acadêmica concluída');page.locator('#ticket-action-save').click()
        expect(page.locator('#ticket-resolved-note')).to_be_visible()
        expect(page.locator('#ticket-action-form')).to_have_attribute('aria-busy','false')
        page.locator('#ticket-dialog [data-close-dialog]').click()
        expect(page.locator('#ticket-dialog')).not_to_be_visible()
        expect(page.locator('#refresh-button')).to_be_enabled()
        expect(page.locator('[data-attendance-metric="totalResolvidos"] strong')).to_have_text('1')
        page.screenshot(path=str(out/'atendente.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'atendente-celular.png'),full_page=True)
        assert not errors,errors
        browser.close()
    print('OK: gestor cria atendente e atribui; atendente consulta e resolve; interface sem erros JavaScript.')
finally:
    fixture.tearDown()
