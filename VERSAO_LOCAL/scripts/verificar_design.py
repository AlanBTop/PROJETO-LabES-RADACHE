"""Confere a identidade compartilhada nas telas locais, sem alterar seus dados."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validacao/design'
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:8080'
errors, checks = [], []

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    context.route('https://**', lambda route: route.abort())
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))

    def capture(name, title=None):
        page.evaluate('window.scrollTo(0, 0)')
        page.evaluate('document.fonts.ready')
        palette = page.evaluate('''() => {
          const style = getComputedStyle(document.documentElement);
          return {blue: style.getPropertyValue('--radache-blue').trim(),
            yellow: style.getPropertyValue('--radache-yellow').trim(),
            font: getComputedStyle(document.body).fontFamily,
            background: getComputedStyle(document.body).backgroundColor};
        }''')
        assert palette['blue'] == '#051d53', (name, palette)
        assert palette['yellow'] == '#f2b719', (name, palette)
        assert 'Inter' in palette['font'], (name, palette)
        assert palette['background'] == 'rgb(248, 250, 252)', (name, palette)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name
        if title:
            assert page.locator(title).evaluate('(el) => getComputedStyle(el).fontSize') == '24px', name
        page.screenshot(path=str(OUT / (name + '.png')), full_page=True)
        checks.append(name)

    page.goto(BASE, wait_until='networkidle')
    capture('portal-desktop', 'h1')
    page.goto(BASE + '/gestao/', wait_until='networkidle')
    expect(page.locator('#login-submit')).to_be_enabled()
    capture('login-gestao', '#login-title')
    page.locator('#login-email').fill('admin@radache.local')
    page.locator('#login-password').fill('admin123')
    page.locator('#login-submit').click()
    expect(page.locator('#app-shell')).to_be_visible()
    expect(page.locator('#refresh-button')).to_be_enabled()
    capture('chamados-desktop', '#page-title')
    page.locator('[data-page=usuarios]').click()
    expect(page.locator('#users-page')).to_be_visible()
    capture('equipe-desktop', '#page-title')
    page.locator('[data-page=alunos]').click()
    expect(page.locator('#students-page')).to_be_visible()
    capture('alunos-curso-desktop', '#page-title')
    for width in [320, 390, 768]:
        page.set_viewport_size({'width': width, 'height': 900})
        capture('gestao-' + str(width), '#page-title')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.goto(BASE + '/alunos/', wait_until='networkidle')
    expect(page.locator('#login-screen')).to_be_visible()
    capture('login-alunos', '#login-screen h1')
    page.locator('#login-usuario').fill('coord')
    page.locator('#login-senha').fill('admin123')
    page.locator('#login-form button').click()
    expect(page.locator('#app-shell')).to_be_visible()
    capture('alunos-desktop', '.page-title')
    page.locator('#btn-add-aluno').click()
    expect(page.locator('#modal-aluno')).to_be_visible()
    capture('formulario-aluno')
    page.locator('#modal-aluno .modal-close').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    capture('alunos-mobile', '.page-title')
    page.goto(BASE + '/painel-demo/', wait_until='networkidle')
    expect(page.locator('#btn-go-student, #screen-whatsapp')).to_have_count(0)
    expect(page.locator('#panel-mode')).to_contain_text('Coordenação')
    capture('painel-mobile')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    capture('painel-desktop')
    capture('campus-desktop', '#screen-campus h1')
    page.locator('#campus-grid > button').first.click()
    capture('cursos-desktop', '#courses-title')
    page.locator('#courses-grid > button').first.click()
    capture('indicadores-desktop', '#dash-title')
    page.goto(BASE + '/mensagens/', wait_until='networkidle')
    expect(page.locator('#workspace')).to_be_visible()
    capture('mensagens-desktop', 'h1')
    for width in [320, 390, 768]:
        page.set_viewport_size({'width': width, 'height': 900})
        capture('mensagens-' + str(width), 'h1')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.goto(BASE + '/mensagens/?modo=api', wait_until='networkidle')
    capture('mensagens-api')
    assert not errors, errors
    browser.close()

(OUT / 'resultado.json').write_text(json.dumps({'telas': checks, 'erros': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print('OK:', len(checks), 'telas; identidade, tipografia e largura validadas; sem erros JavaScript.')
