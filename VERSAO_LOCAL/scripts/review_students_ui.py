"""Inspeção da página publicada localmente, sem alterar seus cadastros."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validacao/alunos_aprimorados';OUT.mkdir(parents=True,exist_ok=True)
BASE='http://localhost:8080'
errors=[];external=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1050})
    def route(r):
        if r.request.url.startswith(BASE+'/'):r.continue_()
        else:external.append(r.request.url);r.abort()
    context.route('**/*',route)
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(BASE+'/alunos/')
    page.screenshot(path=str(OUT/'login-desktop.png'),full_page=True)
    page.locator('#password').fill('admin123');page.locator('#login-form button').click()
    expect(page.locator('#workspace')).to_be_visible()
    expect(page.locator('#stat-total')).to_have_text('17')
    expect(page.locator('#students tr')).to_have_count(8)
    page.screenshot(path=str(OUT/'catalogo-desktop.png'),full_page=True)
    page.locator('#next-page').click();expect(page.locator('#page-label')).to_have_text('2 de 3')
    page.locator('#filter').fill('DEMO-2026-001');expect(page.locator('#students tr')).to_have_count(1)
    expect(page.locator('#students')).to_contain_text('Ana Clara Monteiro')
    page.locator('#clear-filters').click()
    page.locator('#course-filter').select_option(label='Enfermagem');expect(page.locator('#students tr')).to_have_count(2)
    page.locator('#clear-filters').click()
    page.locator('#status-filter').select_option('trancado');expect(page.locator('#students tr')).to_have_count(1)
    expect(page.locator('#students .chat-link')).not_to_have_attribute('href')
    page.locator('#clear-filters').click()
    page.locator('#filter').fill('nao existe neste catalogo');expect(page.locator('#empty-state')).to_be_visible()
    page.locator('#clear-filters').click()
    page.locator('#new-student').click();expect(page.locator('#student-dialog')).to_be_visible()
    page.screenshot(path=str(OUT/'formulario-desktop.png'),full_page=True)
    page.keyboard.press('Escape');expect(page.locator('#student-dialog')).not_to_be_visible()
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),str(width)
        page.screenshot(path=str(OUT/f'catalogo-mobile-{width}.png'),full_page=True)
        page.locator('#new-student').click()
        assert page.evaluate('document.querySelector("#student-dialog").scrollWidth <= document.querySelector("#student-dialog").clientWidth'),str(width)
        page.screenshot(path=str(OUT/f'formulario-mobile-{width}.png'),full_page=True)
        page.keyboard.press('Escape')
    assert not errors,errors
    assert not external,external
    print('OK: 17 alunos persistidos; paginação, busca, filtros, estado vazio, formulário e telas de 1440/390/320 px; sem erros JS ou recursos externos.')
    browser.close()
