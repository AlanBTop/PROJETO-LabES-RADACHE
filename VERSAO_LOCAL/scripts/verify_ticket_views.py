"""Aceitação do quadro geral, status, paginação, contadores e destaques de risco."""
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import sys
import tempfile
import threading
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import app,database,simulation_store as store,simulation_followup,gestao_local

OUT=ROOT/'validacao/chamados_status_risco';OUT.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    store.ACADEMIC=Path(tmp)/'academic.db';store.OPERATIONAL=Path(tmp)/'operations.db';database.DB_PATH=Path(tmp)/'legacy.db'
    store.init();database.init_db();gestao_local.iniciar()
    cases=[('Alto',0,0,'4','1','aberto'),('Médio',8,90,'4','1','em_andamento'),
           ('Baixo',10,100,'1','5','aguardando_aluno'),('Sem avaliação',None,None,'1','5','resolvido')]
    for i,(name,grade,attendance,finance,emotion,status) in enumerate(cases):
        aid=store.save(dict(nome='TESTE Risco '+name,matricula='STATUS-'+str(i),curso='Ciência da Computação',nota_media=grade,frequencia=attendance))
        session=store.session(aid)
        for text in ['1',finance,emotion]:
            store.session(aid,dict(acao='responder',texto=text,sessao_id=session['sessao_id'],id_cliente=str(uuid4())))
    simulation_followup.sync()
    with closing(store.connect(store.OPERATIONAL)) as c,c:
        for row in c.execute('SELECT id,aluno_id,dados FROM gestao_chamados').fetchall():
            ticket=json.loads(row['dados']);ticket['status']=cases[row['aluno_id']-1][-1]
            c.execute('UPDATE gestao_chamados SET dados=? WHERE id=?',(json.dumps(ticket),row['id']))
        # Mais de uma página: os botões devem contar 26 abertos, não só os 20 carregados.
        template=json.loads(c.execute('SELECT dados FROM gestao_chamados WHERE aluno_id=1').fetchone()[0])
        for i in range(24):
            ticket={**template,'id':'qa-page-'+str(i),'protocolo':'QA-'+str(i),'origem':'equipe'}
            c.execute('INSERT INTO gestao_chamados VALUES (?,?,?)',(ticket['id'],1,json.dumps(ticket)))
    server=ThreadingHTTPServer(('127.0.0.1',0),app.RadacheRequestHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    errors=[];external=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
            context=browser.new_context(viewport={'width':1512,'height':1050})
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else (external.append(r.request.url),r.abort()))
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/gestao/#chamados')
            page.locator('#login-email').fill('admin@radache.local');page.locator('#login-password').fill('admin123');page.locator('#login-submit').click()
            expect(page.locator('[data-status-count="geral"]')).to_have_text('32')
            expect(page.locator('[data-column-status]:visible')).to_have_count(4)
            def assert_priority():
                groups=page.locator('[data-column-status]:visible').evaluate_all('(nodes)=>nodes.map(n=>[...n.querySelectorAll(".ticket-card")].map(c=>c.dataset.risk))')
                priorities={'alto':0,'medio':1,'baixo':2,'sem_avaliacao':3}
                for group in groups:
                    values=[priorities[level] for level in group]
                    assert values==sorted(values),group
            assert_priority()
            for level in ['alto','medio','baixo','sem_avaliacao']:
                expect(page.locator(f'.ticket-card[data-risk="{level}"]').first).to_be_visible()
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(OUT/'quadro-geral.png'),full_page=True,animations='disabled')
            for status in ['aberto','em_andamento','aguardando_aluno','resolvido']:
                page.locator(f'[data-ticket-status="{status}"]').click()
                expect(page.locator('[data-column-status]:visible')).to_have_count(1)
                expect(page.locator(f'[data-column-status="{status}"]')).to_be_visible()
                expect(page.locator(f'[data-ticket-status="{status}"]')).to_have_attribute('aria-pressed','true')
                expect(page.locator('[data-ticket-status][aria-pressed="true"]')).to_have_count(1)
                assert_priority()
            page.locator('[data-ticket-status="aberto"]').click()
            expect(page.locator('[data-status-count="aberto"]')).to_have_text('26')
            expect(page.locator('[data-column-status="aberto"] .ticket-card')).to_have_count(20)
            page.locator('[data-more-status="aberto"]').click()
            expect(page.locator('[data-column-status="aberto"] .ticket-card')).to_have_count(26)
            assert_priority()
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(OUT/'somente-abertos.png'),full_page=True,animations='disabled')
            page.locator('.ticket-card[data-risk="alto"]').first.click()
            expect(page.locator('#detail-risk')).to_contain_text('Risco alto')
            expect(page.locator('#detail-risk')).to_contain_text('Índice 100 / 100')
            contact=page.locator('#detail-risk .whatsapp-contact')
            expect(contact).to_have_attribute('href','/mensagens/?aluno=1')
            risk_box=page.locator('#detail-risk .risk-detail').bounding_box();contact_box=contact.bounding_box()
            assert contact_box['x']>=risk_box['x']+risk_box['width']
            with page.expect_popup() as popup:
                contact.click()
            chat=popup.value
            expect(chat.locator('#simulation-student')).to_contain_text('TESTE Risco Alto')
            chat.close()
            page.screenshot(path=str(OUT/'risco-no-atendimento.png'),full_page=True,animations='disabled')
            page.get_by_role('button',name='Fechar atendimento',exact=True).click()
            expect(page.locator('[data-ticket-status="aberto"]')).to_have_attribute('aria-pressed','true')
            page.locator('#category-filter').select_option('ti')
            expect(page.locator('[data-status-count="geral"]')).to_have_text('1')
            expect(page.locator('[data-status-count="aberto"]')).to_have_text('0')
            expect(page.locator('[data-column-status="aberto"]')).to_contain_text('Nenhum chamado')
            page.locator('#clear-ticket-filters').click()
            expect(page.locator('[data-status-count="geral"]')).to_have_text('32')
            page.goto(base+'/gestao/#chamados/exemplo-1')
            expect(page.locator('#detail-risk .whatsapp-contact')).to_have_attribute('href','/mensagens/?aluno=-1')
            legacy_name=page.locator('#detail-metadata dd').nth(1).inner_text()
            with page.expect_popup() as popup:
                page.locator('#detail-risk .whatsapp-contact').click()
            chat=popup.value
            expect(chat.locator('#simulation-student')).to_contain_text(legacy_name)
            expect(chat.locator('#simulation-stage')).to_have_attribute('data-stage','consentimento')
            chat.close()
            page.get_by_role('button',name='Fechar atendimento',exact=True).click()
            for width in [390,320]:
                page.set_viewport_size({'width':width,'height':844})
                for status in ['geral','em_andamento']:
                    page.locator(f'[data-ticket-status="{status}"]').click()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,status)
                    expect(page.locator('[data-column-status]:visible')).to_have_count(4 if status=='geral' else 1)
                    page.evaluate('window.scrollTo(0,0)')
                    page.screenshot(path=str(OUT/f'{status}-mobile-{width}.png'),full_page=True,animations='disabled')
            assert not errors,errors
            assert not external,external
            browser.close()
            print('OK quadro geral e quatro status, risco alto/médio/baixo/sem avaliação, detalhes, paginação, filtros e contadores exatos.')
            print('OK desktop e mobile 390/320 px, sem overflow, erros JS ou requisições externas.')
    finally:
        server.shutdown();server.server_close();thread.join()
