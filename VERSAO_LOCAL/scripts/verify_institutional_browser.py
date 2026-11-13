"""QA do analista: redirecionamento, três câmpus, filtros, proteção e gestão técnica."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend/tests'))
from test_institutional import InstitutionalTests
import rbac

OUT=ROOT/'validacao/analista_institucional';OUT.mkdir(parents=True,exist_ok=True)
fixture=InstitutionalTests();fixture.setUp()
try:
    for campus in rbac.CAMPI:fixture.seed(campus)
    for ids in fixture.ids.values():
        for aid in ids[:5]:
            import simulation_store as store
            from uuid import uuid4
            store.save({'nota_media':10,'frequencia':100},aid)
            store.session(aid,dict(acao='mes',id_cliente=str(uuid4())))
            fixture.complete(aid,'1','5')
    base=fixture.base;errors=[];external=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
        context=browser.new_context(viewport={'width':1512,'height':1050})
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') else (external.append(r.request.url),r.abort()))
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/gestao/')
        page.locator('#login-email').fill('analista@radache.local');page.locator('#login-password').fill('admin123');page.locator('#login-submit').click()
        expect(page).to_have_url(base+'/institucional/')
        expect(page.locator('#workspace')).to_be_visible()
        expect(page.locator('#kpis strong').nth(2)).to_have_text('≈ 120')
        expect(page.locator('#campus-chart .campus-row')).to_have_count(3)
        expect(page.locator('#technical-link')).not_to_be_visible()
        expect(page.locator('body')).not_to_contain_text('PRIVADO')
        page.screenshot(path=str(OUT/'institucional-desktop.png'),full_page=True,animations='disabled')
        page.locator('#campus').select_option('varzea-grande')
        expect(page.locator('#kpis strong').nth(2)).to_have_text('≈ 40')
        page.locator('#risk').select_option('alto')
        expect(page.locator('#kpis strong').nth(2)).to_have_text('≈ 15')
        page.locator('#clear').click();expect(page.locator('#kpis strong').nth(2)).to_have_text('≈ 120')
        for width in [390,320]:
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            page.screenshot(path=str(OUT/f'institucional-mobile-{width}.png'),full_page=True,animations='disabled')
        fixture.seed('caceres',high=1,low=0,course='Pedagogia')
        page.locator('#refresh').click()
        expect(page.locator('#kpis strong').nth(2)).to_have_text('Protegido')
        page.locator('#campus').select_option('caceres');page.locator('#course').select_option('pedagogia')
        expect(page.locator('#refresh')).to_be_enabled()
        expect(page.locator('#kpis strong').nth(2)).to_have_text('Protegido')
        page.set_viewport_size({'width':1512,'height':1050})
        page.screenshot(path=str(OUT/'grupos-protegidos.png'),full_page=True,animations='disabled')
        for endpoint in ['/api/alunos','/api/analytics/students/1','/simulation-api/alunos','/api/local/usuarios']:
            assert context.request.get(base+endpoint).status==403,endpoint
        assert context.request.post(base+'/api/institucional/resumo',data={}).status==405
        data=context.request.get(base+'/api/institucional/resumo').json()
        assert 'PRIVADO' not in str(data)
        page.goto(base+'/gestao/')
        expect(page).to_have_url(base+'/institucional/')
        expect(page.locator('#workspace')).to_be_visible()
        page.locator('#logout').click();expect(page.locator('#login-panel')).to_be_visible()
        # O mesmo painel é permitido ao técnico; o analista não recebe este link.
        page.locator('#email').fill('admin@radache.local');page.locator('#password').fill('admin123');page.locator('#login-submit').click()
        expect(page.locator('#workspace')).to_be_visible();expect(page.locator('#technical-link')).to_be_visible()
        page.goto(base+'/gestao/#usuarios')
        page.locator('#login-email').fill('admin@radache.local');page.locator('#login-password').fill('admin123');page.locator('#login-submit').click()
        expect(page.locator('#users-body tr')).to_have_count(20)
        page.locator('#create-user-button').click()
        page.locator('#user-form input[name="nome"]').fill('TESTE Analista Adicional')
        page.locator('#user-form input[name="email"]').fill('analista-teste@radache.local')
        page.locator('#user-initial-password').fill('Inicial#2026')
        page.locator('#user-profile').select_option('analista_institucional')
        expect(page.locator('#user-campus-field')).not_to_be_visible()
        expect(page.locator('#user-course-field')).not_to_be_visible()
        page.locator('#user-save').click();expect(page.locator('#user-dialog')).not_to_be_visible()
        page.locator('#user-role-filter').select_option('analista_institucional')
        expect(page.locator('#users-body tr')).to_have_count(2)
        assert not errors,errors
        assert not external,external
        browser.close()
    print('OK analista redirecionado, estatísticas dos três câmpus, filtros, supressão de grupos e acesso operacional negado.')
    print('OK 20 acessos iniciais e gestão técnica de perfis, desktop/mobile 390/320 px, sem erros JS ou acesso externo.')
finally:fixture.tearDown()
