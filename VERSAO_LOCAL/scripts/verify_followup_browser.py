"""Demonstra WhatsApp → quadro automático → atendimento e resolução em Edge real."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import app,database,simulation_store as store,gestao_local
from auth import SessionManager,gerar_hash_senha

OUT=ROOT/'validacao/acompanhamento_integrado';OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    store.ACADEMIC=Path(tmp)/'mock_sigaa.db';store.OPERATIONAL=Path(tmp)/'radache.db';database.DB_PATH=Path(tmp)/'legacy.db'
    store.init();database.init_db();gestao_local.iniciar()
    aid=store.save(dict(nome='TESTE Jornada Acadêmica',matricula='DEMO-ACOMP-001',curso='Ciência da Computação',periodo=4,nota_media=8,frequencia=90))
    app.auth=SessionManager({'coord':{'role':'coordenacao',**gerar_hash_senha('admin123')}})
    server=ThreadingHTTPServer(('127.0.0.1',0),app.RadacheRequestHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    errors=[];external=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            def route(r):
                if r.request.url.startswith(base+'/'):r.continue_()
                else:external.append(r.request.url);r.abort()
            context.route('**/*',route)
            board=context.new_page();chat=context.new_page()
            for page in (board,chat):page.on('pageerror',lambda e:errors.append(str(e)))
            board.goto(base+'/gestao/#chamados')
            board.locator('#login-email').fill('admin@radache.local');board.locator('#login-password').fill('admin123');board.locator('#login-submit').click()
            expect(board.locator('#app-shell')).to_be_visible()
            expect(board.locator('[data-ticket-id^="sim-"]')).to_have_count(0)
            chat.goto(base+f'/mensagens/?aluno={aid}')
            for value,stage in [('1','financeira'),('4','emocional'),('1','concluido')]:
                chat.locator(f'[data-answer="{value}"]').click();expect(chat.locator('#simulation-stage')).to_have_attribute('data-stage',stage)
            expect(chat.locator('#followup-link')).to_be_visible()
            board.bring_to_front()
            expect(board.locator('[data-ticket-id^="sim-"]')).to_have_count(1,timeout=15000)
            card=board.locator('[data-ticket-id^="sim-"]')
            expect(card).to_contain_text('TESTE Jornada Acadêmica')
            board.screenshot(path=str(OUT/'quadro-automatico.png'),full_page=True)
            card.click()
            expect(board.locator('#detail-checkins')).to_contain_text('Considerando trancar por motivo financeiro')
            expect(board.locator('#detail-checkins')).to_contain_text('Muito ruim')
            expect(board.locator('#detail-checkins')).to_contain_text('57,5 / 100')
            board.locator('#assume-ticket').click()
            expect(board.locator('#timeline')).to_contain_text('Responsável atribuído: Administração local')
            board.locator('#action-text').fill('Acolhimento realizado. Encaminhado para orientação acadêmica e apoio à permanência.')
            board.locator('#ticket-action-save').click()
            expect(board.locator('#timeline')).to_contain_text('Acolhimento realizado.')
            board.screenshot(path=str(OUT/'respostas-e-atendimento.png'),full_page=True)
            for status,label in [('em_andamento','Em andamento'),('aguardando_aluno','Aguardando aluno'),('resolvido','Resolvido')]:
                board.locator('#ticket-action-type').select_option('status');board.locator('#action-status').select_option(status)
                board.locator('#action-text').fill('Etapa demonstrada: '+label);board.locator('#ticket-action-save').click()
                expect(board.locator('#detail-badges')).to_contain_text(label)
            expect(board.locator('#ticket-resolved-note')).to_be_visible()
            expect(board.locator('#ticket-action-form')).to_have_attribute('aria-busy','false')
            board.get_by_role('button',name='Fechar atendimento',exact=True).click()
            expect(board.locator('#ticket-dialog')).not_to_be_visible()
            print('OK conclusão do WhatsApp abre chamado automático com nome e respostas; assumir, comentar e resolver funcionam.',flush=True)
            chat.bring_to_front();chat.locator('[data-simulation-action="mes"]').click()
            expect(chat.locator('#simulation-stage')).to_have_attribute('data-stage','aguardando_inicio')
            for value,stage in [('1','financeira'),('1','emocional'),('5','concluido')]:
                chat.locator(f'[data-answer="{value}"]').click();expect(chat.locator('#simulation-stage')).to_have_attribute('data-stage',stage)
            board.bring_to_front()
            expect(board.locator('[data-ticket-id^="sim-"]')).to_have_count(2,timeout=15000)
            expect(board.locator('[data-column-status="resolvido"]')).to_contain_text('TESTE Jornada Acadêmica')
            expect(board.locator('[data-column-status="aberto"]')).to_contain_text('TESTE Jornada Acadêmica')
            board.set_viewport_size({'width':390,'height':844})
            assert board.evaluate('document.documentElement.scrollWidth<=innerWidth')
            board.screenshot(path=str(OUT/'quadro-mobile.png'),full_page=True)
            assert not errors,errors
            assert not external,external
            print('OK nova sessão após resolução abre outro chamado, preservando o anterior; layout mobile e rede exclusivamente local.',flush=True)
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
