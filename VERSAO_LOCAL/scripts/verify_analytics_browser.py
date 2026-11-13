"""QA dos dashboards em Edge real, SQLite temporário e requisições externas bloqueadas."""
from contextlib import closing
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from uuid import uuid4
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
sys.path.insert(0,str(ROOT/'scripts'))
import app,analytics,database,simulation_store as store,simulation_followup,gestao_local
from populate_simulation_students import populate
from auth import SessionManager,gerar_hash_senha

OUT=ROOT/'validacao/dashboard_analitico';OUT.mkdir(parents=True,exist_ok=True)


def answer(aid,values):
    session=store.session(aid)
    for text in values:
        store.session(aid,{'acao':'responder','texto':text,'id_cliente':str(uuid4()),'sessao_id':session['sessao_id']})


with tempfile.TemporaryDirectory() as tmp:
    store.ACADEMIC=Path(tmp)/'mock_sigaa.db';store.OPERATIONAL=Path(tmp)/'radache.db';database.DB_PATH=Path(tmp)/'legacy.db'
    store.init();database.init_db()
    with closing(database.get_connection()) as c,c:c.execute('DELETE FROM alunos')
    gestao_local.iniciar();populate()
    for i in range(6):store.save(dict(nome='TESTE Computação '+str(i+1),matricula='TESTE-BI-'+str(i),curso='Ciência da Computação',periodo=i+1,nota_media=8,frequencia=90))
    for aid in range(1,13):
        if aid%3==1:
            store.save({'nota_media':2,'frequencia':50},aid);answer(aid,['1','4','1'])
        elif aid%3==2:answer(aid,['1','4','1'])
        else:answer(aid,['1','1','5'])
    for action,values in [('mes',['1','1','5']),('mes',['1','4','1'])]:
        store.session(1,{'acao':action,'id_cliente':str(uuid4())});answer(1,values)
    simulation_followup.sync()
    app.auth=SessionManager({'coord':{'role':'coordenacao',**gerar_hash_senha('admin123')},'nae':{'role':'nae',**gerar_hash_senha('admin123')}})
    server=ThreadingHTTPServer(('127.0.0.1',0),app.RadacheRequestHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    errors=[];external=[];failed=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
            context=browser.new_context(viewport={'width':1512,'height':1050},timezone_id='America/Cuiaba')
            def route(r):
                if r.request.url.startswith(base+'/'):r.continue_()
                else:external.append(r.request.url);r.abort()
            context.route('**/*',route)
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            # Força a virada UTC antes da meia-noite local para testar os limites de datas.
            page.clock.set_fixed_time(datetime.now(timezone.utc).replace(hour=2,minute=0,second=0,microsecond=0))
            page.on('response',lambda r:failed.append((r.status,r.url)) if r.status>=400 else None)
            page.goto(base+'/painel-demo/')
            page.screenshot(path=str(OUT/'acesso.png'),full_page=True)
            page.locator('#login-password').fill('admin123');page.locator('#login-submit').click()
            expect(page.locator('#workspace')).to_be_visible()
            expect(page.locator('#overview-course option')).to_have_count(31)
            expect(page.locator('[data-metric="cadastrados"] strong')).to_have_text('22')
            expect(page.locator('#ranking-body tr')).to_have_count(30)
            assert analytics.overview({})['kpis']['cadastrados']==22
            with closing(store.connect(store.ACADEMIC,True)) as c:
                assert c.execute('SELECT COUNT(*) FROM alunos').fetchone()[0]==22
            page.screenshot(path=str(OUT/'geral-desktop.png'),full_page=True)
            page.locator('#rank-sort').select_option('nome')
            expect(page.locator('#ranking-body tr').first).to_contain_text('Administração')
            page.locator('#rank-sort').select_option('sem_avaliacao')
            expect(page.locator('#ranking-body tr').first).to_contain_text('Ciência da Computação')
            page.locator('#rank-sort').select_option('alto_pct')
            page.locator('#date-preset').select_option('30')
            expect(page.locator('[data-metric="checkins"] strong')).to_have_text('12')
            expect(page.locator('#filter-end')).to_have_value(datetime.now(timezone.utc).date().isoformat())
            page.locator('#date-preset').select_option('all')
            expect(page.locator('[data-metric="checkins"] strong')).to_have_text('14')
            page.get_by_role('button',name='Abrir curso Ciência da Computação',exact=True).click()
            expect(page.locator('#page-title')).to_contain_text('Ciência da Computação')
            expect(page.locator('#student-table-body tr')).to_have_count(8)
            page.locator('#student-order').select_option('nome')
            expect(page.locator('#student-table-body tr').first).to_contain_text('Ana Clara Monteiro')
            page.locator('#student-next').click();expect(page.locator('#student-page')).to_have_text('2 de 2')
            page.locator('#student-search').fill('DEMO-2026-001')
            expect(page.locator('#student-table-body tr')).to_have_count(1)
            page.get_by_role('button',name='Ver perfil de Ana Clara Monteiro',exact=True).click()
            expect(page.locator('#student-modal-content')).to_contain_text('Questionários e respostas do WhatsApp')
            expect(page.locator('#student-modal-content')).to_contain_text('Atendimentos e andamentos')
            expect(page.locator('#student-modal-content')).to_contain_text('SIM-')
            page.screenshot(path=str(OUT/'perfil-desktop.png'),full_page=True)
            page.keyboard.press('Escape')
            page.locator('#student-search').fill('estudante inexistente')
            expect(page.locator('#students-empty')).to_be_visible()
            page.locator('#student-search').fill('')
            page.locator('#filter-period').select_option('2')
            expect(page.locator('#student-table-body')).to_contain_text('2º')
            page.locator('#filter-period').select_option('')
            page.locator('#advanced-toggle').click();page.locator('#filter-risk').select_option('alto')
            expect(page.locator('#student-table-body .badge.alto').first).to_be_visible()
            page.screenshot(path=str(OUT/'curso-desktop.png'),full_page=True)
            page.locator('#clear-filters').click()
            expect(page.locator('#ranking-panel')).to_be_visible()
            page.locator('#definitions-button').click();expect(page.locator('#definitions-content')).to_contain_text('Alto risco no total');page.keyboard.press('Escape')
            page.goto(base+'/alunos/')
            expect(page.locator('#workspace')).to_be_visible()
            expect(page.locator('#courses option')).to_have_count(30)
            expect(page.locator('#course-filter option')).to_have_count(31)
            options=page.locator('#courses option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')
            assert len(set(options))==30
            assert options.count('Agronomia / Engenharia Agronômica')==1
            page.locator('#course-filter').select_option('Medicina')
            expect(page.locator('#students tr')).to_have_count(0)
            page.goto(base+'/gestao/')
            page.locator('#login-email').fill('admin@radache.local')
            page.locator('#login-password').fill('admin123')
            page.locator('#login-form button[type="submit"]').click()
            expect(page.locator('#course-filter option')).to_have_count(31)
            values=page.locator('#course-filter option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')
            assert len(values)==len(set(values))
            assert values.count('agronomia')==1
            page.goto(base+'/painel-demo/')
            expect(page.locator('#workspace')).to_be_visible()
            print('OK geral/curso/perfil, KPIs conferidos no SQLite, filtros, ordenação, paginação, busca e históricos.',flush=True)
            for width in (390,320):
                page.set_viewport_size({'width':width,'height':844})
                page.screenshot(path=str(OUT/f'geral-mobile-{width}.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
                page.screenshot(path=str(OUT/f'geral-mobile-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1512,'height':1050})
            page.goto(base+'/painel-demo/#curso=Curso%20sem%20alunos')
            expect(page.locator('[data-metric="cadastrados"] strong')).to_have_text('0')
            expect(page.locator('#students-empty')).to_be_visible()
            expect(page.locator('#evolution-chart')).to_contain_text('Histórico insuficiente')
            page.screenshot(path=str(OUT/'curso-sem-alunos.png'),full_page=True)
            page.locator('#logout').click()
            expect(page.locator('#access-panel')).to_be_visible()
            page.locator('#login-user').fill('nae');page.locator('#login-password').fill('admin123');page.locator('#login-submit').click()
            expect(page.locator('#workspace')).to_be_visible()
            page.locator('#clear-filters').click()
            expect(page.locator('#factors-chart')).not_to_contain_text('Situação financeira')
            assert not errors,errors
            assert not external,external
            assert not failed,failed
            print('OK curso vazio sem valores inventados, privacidade por perfil, telas 1512/390/320 px, sem erros JS ou acesso externo.',flush=True)
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
