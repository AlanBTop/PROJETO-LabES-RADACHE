"""Verificação real em Edge/Chromium, com banco temporário e rede externa bloqueada."""
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "RADACHE_Modulo_Alunos/backend"))
import app
import database
from auth import SessionManager, gerar_hash_senha
from playwright.sync_api import sync_playwright, expect

OUT = ROOT / "validacao"
OUT.mkdir(exist_ok=True)
checks = []
def passed(name):
    checks.append(name)
    print("OK:", name, flush=True)

def login(page, username="coord"):
    expect(page.locator("#login-screen")).to_be_visible()
    page.locator("#login-usuario").fill(username)
    page.locator("#login-senha").fill("senha-de-teste")
    page.locator("#login-form button").click()
    expect(page.locator("#app-shell")).to_be_visible()
    expect(page.locator("#alunos-tbody tr")).not_to_have_count(0)

def overflow(page):
    return page.evaluate("({width:innerWidth, scroll:document.documentElement.scrollWidth})")

with tempfile.TemporaryDirectory() as temp:
    database.DB_PATH = Path(temp) / "browser.db"
    database.init_db()
    cred = gerar_hash_senha("senha-de-teste")
    app.auth = SessionManager({name: {**cred, "role": role} for name, role in
        [("coord", "coordenacao"), ("nae", "nae"), ("caest", "caest"), ("prae", "prae")]})
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.RadacheRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = "http://127.0.0.1:" + str(server.server_port)
    errors, external, failed_resources = [], [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
            def deny_external(route):
                external.append(route.request.url)
                route.abort()
            context.route("https://**", deny_external)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failed_resources.append(response.url) if response.status >= 400 and "/api/" not in response.url else None)
            page.goto(url + "/alunos/", wait_until="networkidle")
            login(page)
            expect(page.locator("#kpi-total")).to_have_text("8")
            expect(page.locator("#kpi-ativos")).to_have_text("7")
            passed("Login e métricas SQLite")
            # Combina pesquisa, curso e risco.
            page.locator("#search-input").fill("Lucas")
            page.locator("#filter-curso").select_option("Ciência da Computação")
            page.locator("#filter-risco").select_option("critico")
            expect(page.locator("#alunos-tbody tr")).to_have_count(1)
            expect(page.locator("#alunos-tbody")).to_contain_text("Lucas Silva")
            page.locator("#search-input").fill("")
            page.locator("#filter-curso").select_option("")
            page.locator("#filter-risco").select_option("")
            expect(page.locator("#alunos-tbody tr")).to_have_count(8)
            passed("Pesquisa e filtros combinados")
            # Formulário completo e persistência após recarregar.
            page.locator("#btn-add-aluno").click()
            for field, value in {"nome": "Teste Navegador", "matricula": "BROWSER1", "email": "teste@example.com", "telefone": "(65) 99999-0000"}.items():
                page.locator("#aluno-" + field).fill(value)
            page.locator("#aluno-curso").select_option("Direito")
            page.locator("#aluno-risco-inicial").fill("0")
            page.locator("#form-aluno button[type=submit]").click()
            expect(page.locator("#modal-aluno")).not_to_be_visible()
            expect(page.locator("#kpi-total")).to_have_text("9")
            page.reload(wait_until="networkidle")
            expect(page.locator("#kpi-total")).to_have_text("9")
            row = page.locator("#alunos-tbody tr").filter(has_text="Teste Navegador")
            expect(row).to_contain_text("Estável · 0%")
            row.locator("button[title='Editar Aluno']").click()
            expect(page.locator("#lbl-risco-val")).to_have_text("0%")
            page.locator("#aluno-nome").fill("Teste Editado")
            page.locator("#form-aluno button[type=submit]").click()
            expect(page.locator("#modal-aluno")).not_to_be_visible()
            expect(page.locator("#alunos-tbody")).to_contain_text("Teste Editado")
            with closing(database.get_connection()) as conn:
                aluno = conn.execute("SELECT id FROM alunos WHERE matricula='BROWSER1'").fetchone()
                count = conn.execute("SELECT COUNT(*) FROM avaliacoes WHERE aluno_id=?", (aluno["id"],)).fetchone()[0]
                assert count == 1
            passed("Cadastro, persistência, edição e risco zero")
            row = page.locator("#alunos-tbody tr").filter(has_text="Teste Editado")
            row.locator("button[title='Excluir Aluno']").click()
            page.locator("#modal-excluir button").filter(has_text="Inativar Aluno").click()
            expect(page.locator("#modal-excluir")).not_to_be_visible()
            expect(page.locator("#kpi-total")).to_have_text("8")
            passed("Exclusão lógica pela interface")
            # Confere corpo do modal rolável e botões dentro da tela.
            for width, height in [(320,568), (375,667), (390,844), (768,1024), (1440,900)]:
                page.set_viewport_size({"width": width, "height": height})
                assert overflow(page)["scroll"] <= width + 1, overflow(page)
                page.locator("#btn-add-aluno").click()
                modal = page.locator("#modal-aluno .modal-content").bounding_box()
                assert modal["y"] >= 0 and modal["y"] + modal["height"] <= height + 1, modal
                body = page.locator("#modal-aluno .modal-body")
                assert body.evaluate("(el) => el.scrollHeight >= el.clientHeight")
                button = page.locator("#form-aluno button[type=submit]").bounding_box()
                assert button["y"] + button["height"] <= height, button
                page.screenshot(path=str(OUT / ("gestao-modal-" + str(width) + ".png")))
                page.keyboard.press("Escape")
                expect(page.locator("#modal-aluno")).not_to_be_visible()
            passed("Layout e modal em 320, 375, 390, 768 e 1440 px")
            page.set_viewport_size({"width":1440, "height":900})
            page.screenshot(path=str(OUT / "gestao-desktop.png"), full_page=True)
            # Falha de API não pode mudar o modo nem habilitar gravação fictícia.
            page.route("**/api/**", lambda route: route.abort())
            page.evaluate("() => carregarDados()")
            assert page.evaluate("useApi") is True
            expect(page.locator("#mode-indicator")).to_contain_text("Falha de conexão")
            page.unroute("**/api/**")
            page.evaluate("() => carregarDados()")
            passed("Erro de rede preserva o modo conectado")
            # Dados hostis e mesmo curso em outro câmpus.
            from aluno_service import AlunoService
            service = AlunoService()
            service.cadastrar({"nome": '<img src=x onerror="window.xss=1">', "matricula":"XSS1", "curso":"Direito", "campus":"Outro Câmpus",
                "periodo":16, "email":"x@example.com", "telefone":"65999990000", "indice_risco":33.5})
            page.goto(url + "/painel-demo", wait_until="networkidle")
            assert page.url.endswith("/painel-demo/")
            expect(page.locator("#panel-mode")).to_contain_text("Coordenação")
            expect(page.locator("#campus-grid > button")).to_have_count(2)
            page.locator("#campus-grid > button").filter(has_text="Outro Câmpus").click()
            page.locator("#courses-grid > button").filter(has_text="Direito").click()
            expect(page.locator("#card-total")).to_have_text("1")
            expect(page.locator("#student-table-body")).to_contain_text("Moderado · 33,5%")
            assert page.locator("#student-table-body img").count() == 0
            assert page.evaluate("window.xss") is None
            page.locator("#student-table-body tr").click()
            expect(page.locator("#student-modal")).to_be_visible()
            expect(page.locator("#student-modal-content")).to_contain_text("Histórico registrado")
            assert "Jun" not in page.locator("#student-modal-content").inner_text()
            page.keyboard.press("Escape")
            passed("Painel: câmpus separados, limite 33.5%, XSS e histórico real")
            for width, height in [(320,568), (390,844), (768,1024), (1440,900)]:
                page.set_viewport_size({"width": width, "height": height})
                assert overflow(page)["scroll"] <= width + 1, overflow(page)
                page.screenshot(path=str(OUT / ("painel-" + str(width) + ".png")), full_page=True)
            passed("Layout responsivo do painel")
            page.set_viewport_size({"width":1440, "height":900})
            # Todos os perfis setoriais: visibilidade e permissão efetiva.
            for role, visible, hidden in [("nae","Risco Psicológico","Risco Econômico"), ("caest","Indicadores acadêmicos","Risco Psicológico"), ("prae","Risco Econômico","Indicadores acadêmicos")]:
                page.goto(url + "/alunos/", wait_until="networkidle")
                page.locator("#btn-logout").click()
                login(page, role)
                expect(page.locator("#btn-add-aluno")).not_to_be_visible()
                assert page.locator("button[title='Editar Aluno']").count() == 0
                page.goto(url + "/painel-demo/", wait_until="networkidle")
                page.locator("#campus-grid > button").filter(has_text="Câmpus de Cáceres").click()
                page.locator("#courses-grid > button").filter(has_text="Direito").click()
                expect(page.locator("th").filter(has_text=visible)).to_be_visible()
                expect(page.locator("th").filter(has_text=hidden)).not_to_be_visible()
                page.locator("#student-table-body tr").first.click()
                expect(page.locator("#student-modal")).to_be_visible()
                page.keyboard.press("Escape")
            passed("RBAC nos dois front-ends: NAE, CAEst e PRAE")
            token = page.evaluate("sessionStorage.getItem('radache_token')")
            page.request.post(url + "/api/logout", headers={"Authorization":"Bearer " + token})
            page.evaluate("() => loadSharedStudents()")
            expect(page.locator("#screen-home")).to_be_visible()
            expect(page.locator("#student-table-body")).to_be_empty()
            passed("Sessão revogada limpa os dados privados do painel")
            # Standalone e links relativos sem serviços externos.
            page.goto((ROOT / "RADACHE_Modulo_Alunos/frontend/index.html").as_uri(), wait_until="networkidle")
            expect(page.locator("#alunos-tbody tr")).to_have_count(8)
            assert page.evaluate("useApi") is False
            page.locator('a[href="../../painel-demo/public/index.html"]').click()
            expect(page.locator("#panel-mode")).to_contain_text("fictícios")
            expect(page.locator("#campus-grid > button")).to_have_count(3)
            passed("Modo standalone e navegação entre módulos por arquivo")
            assert not errors, errors
            assert not external, external
            assert not failed_resources, failed_resources
            passed("Sem erros JavaScript, recursos ausentes ou requisições externas")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
(OUT / "resultado_navegador.json").write_text(json.dumps({"checks": checks, "errors": errors, "external_requests": external, "missing_resources":failed_resources}, ensure_ascii=False, indent=2), encoding="utf-8")
print("Verificações concluídas:", len(checks))


