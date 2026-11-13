"""Verifica cadastro → chat existente → painel em Edge, com rede externa bloqueada."""
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import app,database,simulation_store as store,gestao_local
from auth import SessionManager,gerar_hash_senha

OUT=ROOT/'validacao/simulacao_local';OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    store.ACADEMIC=Path(tmp)/'mock_sigaa.db';store.OPERATIONAL=Path(tmp)/'radache.db';database.DB_PATH=Path(tmp)/'legacy.db'
    store.init();database.init_db();gestao_local.iniciar()
    app.auth=SessionManager({'coord':{'role':'coordenacao',**gerar_hash_senha('admin123')}})
    server=ThreadingHTTPServer(('127.0.0.1',0),app.RadacheRequestHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    errors=[];externals=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            def route(r):
                if r.request.url.startswith(base+'/'):r.continue_()
                else:externals.append(r.request.url);r.abort()
            context.route('**/*',route)
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/alunos/')
            page.locator('#password').fill('admin123');page.locator('#login-form button').click()
            expect(page.locator('#workspace')).to_be_visible()
            page.locator('#new-student').click()
            for selector,value in [('#name','TESTE Navegador Alfa'),('#registration','20260001'),('#course','Curso de Simulação'),('#average','8'),('#attendance','90')]:page.locator(selector).fill(value)
            page.locator('#period').select_option('4')
            page.locator('#save-student').click()
            expect(page.locator('#students')).to_contain_text('TESTE Navegador Alfa')
            page.get_by_role('button',name='Detalhes / editar TESTE Navegador Alfa',exact=True).click()
            page.locator('#name').fill('TESTE Navegador Editado');page.locator('#save-student').click()
            expect(page.locator('#students')).to_contain_text('TESTE Navegador Editado')
            page.screenshot(path=str(OUT/'cadastro.png'),full_page=True)
            print('OK cadastro e edição na interface',flush=True)
            page.goto(base+'/mensagens/')
            expect(page.locator('.contact')).to_have_count(1)
            for value,stage in [('1','financeira'),('4','emocional'),('1','concluido')]:
                page.locator(f'[data-answer="{value}"]').click()
                expect(page.locator('#simulation-stage')).to_have_attribute('data-stage',stage)
            expect(page.locator('.message')).to_have_count(7)
            page.reload();expect(page.locator('#simulation-stage')).to_have_attribute('data-stage','concluido')
            expect(page.locator('.message')).to_have_count(7)
            page.screenshot(path=str(OUT/'whatsapp.png'),full_page=True)
            page.locator('[data-simulation-action="mes"]').click()
            expect(page.locator('#simulation-stage')).to_have_attribute('data-stage','aguardando_inicio')
            for value,stage in [('1','financeira'),('1','emocional'),('5','concluido')]:
                page.locator(f'[data-answer="{value}"]').click()
                expect(page.locator('#simulation-stage')).to_have_attribute('data-stage',stage)
            print('OK chat persistente, recarga e segunda sessão',flush=True)
            page.goto(base+'/painel-demo/')
            expect(page.locator('#workspace')).to_be_visible()
            page.locator('#overview-course').select_option(label='Curso de Simulação')
            page.get_by_role('button',name='Ver perfil de TESTE Navegador Editado',exact=True).click()
            expect(page.locator('#student-modal-content')).to_contain_text('Questionários e respostas do WhatsApp')
            expect(page.locator('#student-modal-content')).to_contain_text('7,5 / 100')
            page.screenshot(path=str(OUT/'acompanhamento.png'),full_page=True)
            print('OK painel com respostas, duas sessões e risco recalculado',flush=True)
            page.goto(base+'/alunos/')
            expect(page.locator('#workspace')).to_be_visible()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(OUT/'cadastro-mobile.png'),full_page=True)
            page.goto(base+'/mensagens/')
            expect(page.locator('.contact')).to_have_count(1)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(OUT/'whatsapp-mobile.png'),full_page=True)
            assert not errors,errors
            assert not externals,externals
            print('OK mobile sem overflow, sem erros JavaScript e sem requisições externas',flush=True)
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
