"""QA: risco preservado no atendimento e evolução por evidências no WhatsApp, offline."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import app,database,simulation_store as store,gestao_local,simulation_followup,analytics
from auth import SessionManager,gerar_hash_senha

OUT=ROOT/'validacao/evolucao_risco';OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    store.ACADEMIC=Path(tmp)/'academic.db';store.OPERATIONAL=Path(tmp)/'operations.db';database.DB_PATH=Path(tmp)/'legacy.db'
    store.init();database.init_db();gestao_local.iniciar()
    aid=store.save(dict(nome='TESTE Evolução Persistente',matricula='EV-BROWSER',curso='Ciência da Computação',nota_media=0,frequencia=0))
    app.auth=SessionManager({'coord':{'role':'coordenacao',**gerar_hash_senha('admin123')}})
    server=ThreadingHTTPServer(('127.0.0.1',0),app.RadacheRequestHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    errors=[];external=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
            context=browser.new_context(viewport={'width':1512,'height':1050})
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else (external.append(r.request.url),r.abort()))
            board=context.new_page();chat=context.new_page();panel=context.new_page()
            for page in (board,chat,panel):page.on('pageerror',lambda e:errors.append(str(e)))
            context.request.post(base+'/api/local/login',data={'email':'admin@radache.local','senha':'admin123'})
            chat.goto(base+f'/mensagens/?aluno={aid}')
            def respond(finance,emotion,new_month=False):
                chat.bring_to_front()
                if new_month:
                    chat.locator('[data-simulation-action="mes"]').click()
                    expect(chat.locator('#simulation-stage')).to_have_attribute('data-stage','aguardando_inicio')
                for value,stage in [('1','financeira'),(finance,'emocional'),(emotion,'concluido')]:
                    chat.locator(f'[data-answer="{value}"]').click()
                    expect(chat.locator('#simulation-stage')).to_have_attribute('data-stage',stage)
            respond('4','1')
            board.goto(base+'/gestao/#chamados')
            board.locator('#login-email').fill('admin@radache.local');board.locator('#login-password').fill('admin123');board.locator('#login-submit').click()
            expect(board.locator('[data-ticket-id^="sim-"]')).to_have_count(1)
            board.locator('[data-ticket-id^="sim-"]').click()
            expect(board.locator('#detail-risk')).to_contain_text('Índice 100 / 100')
            expect(board.locator('#detail-risk-evolution circle')).to_have_count(1)
            board.locator('#assume-ticket').click()
            expect(board.locator('#detail-risk')).to_contain_text('Índice 100 / 100')
            for status in ['em_andamento','aguardando_aluno','resolvido']:
                board.locator('#ticket-action-type').select_option('status');board.locator('#action-status').select_option(status)
                board.locator('#action-text').fill('Atendimento realizado, sem nova avaliação.');board.locator('#ticket-action-save').click()
                expect(board.locator('#detail-badges')).to_contain_text({'em_andamento':'Em andamento','aguardando_aluno':'Aguardando aluno','resolvido':'Resolvido'}[status])
                expect(board.locator('#detail-risk')).to_contain_text('Índice 100 / 100')
            board.screenshot(path=str(OUT/'resolvido-ainda-risco-alto.png'),animations='disabled')
            board.get_by_role('button',name='Fechar atendimento',exact=True).click()
            cases=[(0,80,'4','1',80,'Diminuiu'),(6,90,'2','4',27,'Diminuiu'),(9,100,'1','5',2.5,'Diminuiu'),(0,0,'4','1',100,'Aumentou'),(0,0,'4','1',100,'Risco estável')]
            for index,(grade,attendance,finance,emotion,score,label) in enumerate(cases,2):
                store.save({'nota_media':grade,'frequencia':attendance},aid)
                respond(finance,emotion,True)
                board.bring_to_front();board.locator('#refresh-button').click()
                expect(board.locator('#refresh-button')).to_be_enabled()
                ticket=next(t for t in simulation_followup.tickets() if t['status']=='aberto')
                board.locator('[data-ticket-id="'+ticket['id']+'"]').click()
                expect(board.locator('#detail-risk-evolution circle')).to_have_count(index)
                expect(board.locator('#detail-risk-evolution')).to_contain_text(label)
                board.locator('#detail-risk-evolution summary').click()
                expect(board.locator('#detail-risk-evolution')).to_contain_text('WhatsApp simulado')
                assert analytics.detail(-aid)['indice']==score
                if index==4:board.screenshot(path=str(OUT/'melhora-com-fatores.png'),animations='disabled')
                if index==5:board.screenshot(path=str(OUT/'piora-em-acompanhamento.png'),animations='disabled')
                board.get_by_role('button',name='Fechar atendimento',exact=True).click()
            panel.goto(base+'/painel-demo/')
            panel.locator('#login-password').fill('admin123');panel.locator('#login-submit').click()
            expect(panel.locator('#observed-evolution')).to_contain_text('1 estáveis')
            panel.locator('#overview-course').select_option('Ciência da Computação')
            panel.locator('#student-search').fill('EV-BROWSER')
            expect(panel.locator('#student-table-body')).to_contain_text('Risco estável')
            panel.get_by_role('button',name='Ver perfil de TESTE Evolução Persistente',exact=True).click()
            expect(panel.locator('#student-modal-content circle')).to_have_count(6)
            expect(panel.locator('#student-modal-content')).to_contain_text('Risco inicial')
            expect(panel.locator('#student-modal-content')).to_contain_text('Risco atual')
            panel.screenshot(path=str(OUT/'perfil-com-historico.png'),animations='disabled')
            for width in [390,320]:
                panel.set_viewport_size({'width':width,'height':844})
                assert panel.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
                panel.screenshot(path=str(OUT/f'perfil-mobile-{width}.png'),animations='disabled')
            assert not errors,errors
            assert not external,external
            browser.close()
            print('OK atendimento resolvido mantém risco 100; novas evidências: 100 -> 80 -> 27 -> 2,5 -> 100 -> 100.')
            print('OK gráficos e fatores no atendimento/perfil, resumo geral/curso, mobile 390/320 px, zero erros JS e acesso externo.')
    finally:
        server.shutdown();server.server_close();thread.join()
