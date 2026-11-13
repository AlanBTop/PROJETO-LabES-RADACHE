"""Validação do chat em Edge real, com mock HTTP local e sem tocar no banco."""
import json
from pathlib import Path
import sys
import threading

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from iniciar_mensagens import MensagensHandler, ThreadingHTTPServer

OUT = ROOT / "validacao" / "mensagens"
OUT.mkdir(parents=True, exist_ok=True)
checks = []


def passed(texto):
    checks.append(texto)
    print("OK:", texto, flush=True)


def sem_overflow(page):
    medidas = page.evaluate("({viewport: innerWidth, conteudo: document.documentElement.scrollWidth})")
    assert medidas["conteudo"] <= medidas["viewport"], medidas


server = ThreadingHTTPServer(("127.0.0.1", 0), MensagensHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = f"http://127.0.0.1:{server.server_port}"
errors, externos, falhas_recursos = [], [], []
try:
    with sync_playwright() as playwright:
        edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        browser = playwright.chromium.launch(executable_path=str(edge) if edge.exists() else None, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("response", lambda response: falhas_recursos.append(response.url) if response.status >= 400 and "/mock-api/" not in response.url else None)

        def bloquear_externo(route):
            externos.append(route.request.url)
            route.abort()

        context.route("https://**", bloquear_externo)
        for resource in ("/assets/radache-theme.css", "/assets/fonts/inter.css"):
            response = page.request.get(url + resource)
            assert response.status == 200, (resource, response.status)
        assert page.request.get(url + "/assets/%2e%2e/portal/index.html").status == 404
        passed("Servidor isolado carrega a identidade compartilhada e limita os arquivos à pasta de assets")
        page.goto(url + "/mensagens/?modo=api", wait_until="networkidle")
        expect(page.locator(".contact")).to_have_count(6)
        expect(page.locator(".message")).to_have_count(6)
        expect(page.locator("#send-button")).to_be_disabled()
        sem_overflow(page)
        page.screenshot(path=str(OUT / "desktop.png"), full_page=True)
        passed("Renderização desktop, seis contatos e nenhum recurso externo")

        controle = {"modo": "hold", "pendentes": []}
        requests = []

        def interceptar(route):
            requests.append(route.request.post_data_json)
            if controle["modo"] == "hold":
                controle["pendentes"].append(route)
            elif controle["modo"] == "fail":
                route.fulfill(status=503, content_type="application/json", body=json.dumps({"sucesso": False, "erro": "Falha simulada de teste."}))
            elif controle["modo"] == "network":
                route.abort("failed")
            else:
                route.continue_()

        page.route("**/mock-api/mensagens", interceptar)
        mensagem = "Olá, equipe! Validação com acentos e emoji 💚"
        with page.expect_request("**/mock-api/mensagens") as request_info:
            page.locator("#message-input").fill(mensagem)
            page.locator("#message-input").press("Enter")
        payload = request_info.value.post_data_json
        bubble = page.locator(f'[data-message-id="{payload["id_cliente"]}"]')
        expect(bubble).to_have_attribute("data-status", "enviando")
        expect(bubble).to_contain_text(mensagem)
        expect(page.locator("#message-input")).to_have_value("")
        assert payload["id_destinatario"] == 101 and payload["id_remetente"] == 1
        assert set(payload) == {"id_cliente", "conteudo_texto", "id_remetente", "id_destinatario", "timestamp"}
        assert request_info.value.method == "POST"
        assert request_info.value.headers["content-type"] == "application/json"
        assert controle["pendentes"], "A resposta deve permanecer suspensa"
        passed("Mensagem aparece no DOM enquanto o POST ainda está sem resposta")

        # Uma segunda conversa pode enviar enquanto a primeira requisição está pendente.
        page.locator('[data-contact-id="102"]').click()
        page.locator("#message-input").fill("Mensagem para Lucas em paralelo")
        with page.expect_request("**/mock-api/mensagens"):
            page.locator("#send-button").click()
        expect(page.locator('.message[data-status="enviando"]')).to_have_count(1)
        assert len(controle["pendentes"]) == 2
        controle["pendentes"][1].continue_()
        expect(page.locator('.message[data-status="confirmado"]')).to_have_count(1)
        controle["pendentes"][0].continue_()
        page.locator('[data-contact-id="101"]').click()
        expect(bubble).to_have_attribute("data-status", "confirmado")
        expect(page.locator("#response-preview")).to_contain_text("Mensagem para Lucas em paralelo")
        passed("Envios simultâneos preservam destinatários e a inspeção mais recente")

        # Inspeciona JSON da última requisição; confirmação deve declarar mock sem banco.
        page.locator('.chat-header [data-open-inspector]').click()
        expect(page.locator("#api-dialog")).to_be_visible()
        resposta = json.loads(page.locator("#response-preview").inner_text())
        assert resposta["sucesso"] and not resposta["persistido"] and resposta["modo"] == "mock"
        assert json.loads(page.locator("#payload-preview").inner_text())["id_destinatario"] == 102
        page.screenshot(path=str(OUT / "inspecao-json.png"), full_page=True)
        page.keyboard.press("Escape")
        expect(page.locator("#api-dialog")).not_to_be_visible()
        passed("Inspeção apresenta payload e confirmação HTTP real sem persistência")

        # Erro HTTP e nova tentativa explícita, com o mesmo UUID e uma única bolha.
        controle["modo"] = "fail"
        page.locator("#message-input").fill("Mensagem para testar recuperação")
        with page.expect_request("**/mock-api/mensagens") as falha_info:
            page.locator("#send-button").click()
        falha_payload = falha_info.value.post_data_json
        failed = page.locator(f'[data-message-id="{falha_payload["id_cliente"]}"]')
        expect(failed).to_have_attribute("data-status", "falhou")
        expect(page.locator("#api-status")).to_have_text("HTTP 503 · falha")
        page.screenshot(path=str(OUT / "falha-e-reenvio.png"), full_page=True)
        controle["modo"] = "pass"
        with page.expect_request("**/mock-api/mensagens") as retry_info:
            failed.locator("button").click()
        assert retry_info.value.post_data_json == falha_payload
        expect(failed).to_have_attribute("data-status", "confirmado")
        expect(failed).to_have_count(1)
        passed("HTTP 503 preserva a mensagem e o retry mantém payload/UUID sem duplicação")

        controle["modo"] = "network"
        page.locator("#message-input").fill("Mensagem durante falha de rede")
        page.locator("#send-button").click()
        expect(page.locator('.message[data-status="falhou"]')).to_have_count(1)
        expect(page.locator("#api-status")).to_have_text("Falha de conexão")
        controle["modo"] = "pass"
        page.locator('.message[data-status="falhou"] button').click()
        expect(page.locator('.message[data-status="falhou"]')).to_have_count(0)
        passed("Falha de rede também permite recuperação manual")

        # Não enviar texto vazio nem interpretar HTML recebido do usuário.
        antes = len(requests)
        page.locator("#message-input").fill("   ")
        expect(page.locator("#send-button")).to_be_disabled()
        page.locator("#message-input").press("Enter")
        assert len(requests) == antes
        xss = '<img src=x onerror="window.execucaoIndevida=true">'
        page.locator("#message-input").fill(xss)
        page.locator("#send-button").click()
        expect(page.locator(".message-content").last).to_have_text(xss)
        expect(page.locator(".message img")).to_have_count(0)
        assert page.evaluate("window.execucaoIndevida") is None
        passed("Texto vazio não gera POST e conteúdo HTML é exibido como texto seguro")

        page.locator("#message-input").fill("Primeira linha")
        page.locator("#message-input").press("Shift+Enter")
        page.locator("#message-input").type("Segunda linha")
        expect(page.locator("#message-input")).to_have_value("Primeira linha\nSegunda linha")
        page.locator('[data-contact-id="104"]').click()
        expect(page.locator("#message-input")).to_have_value("")
        page.locator("#message-input").fill("Rascunho de Rafael")
        page.locator('[data-contact-id="101"]').click()
        expect(page.locator("#message-input")).to_have_value("Primeira linha\nSegunda linha")
        passed("Shift+Enter e rascunhos independentes por destinatário")

        page.locator("#emoji-toggle").click()
        page.locator('[data-emoji="💚"]').click()
        expect(page.locator("#message-input")).to_have_value("Primeira linha\nSegunda linha💚")
        expect(page.locator("#emoji-picker")).not_to_be_visible()
        page.locator("#chat-search-toggle").click()
        page.locator("#message-search").fill("ATENCAO")
        expect(page.locator("#search-results")).to_have_text("1 resultado")
        expect(page.locator(".message.match")).to_have_count(1)
        page.locator("#close-chat-search").click()
        page.locator("#contact-search").fill("beatriz")
        expect(page.locator(".contact")).to_have_count(1)
        page.locator("#contact-search").fill("inexistente")
        expect(page.locator(".contact")).to_have_count(0)
        expect(page.locator(".empty-state")).to_be_visible()
        page.locator("#contact-search").fill("")
        page.locator('[data-filter="unread"]').click()
        expect(page.locator(".contact")).to_have_count(1)  # Lucas já foi lido.
        page.locator('[data-filter="all"]').click()
        passed("Emojis, pesquisa sem acentos, lista vazia e filtro de não lidas")

        # Contratos de erro e timeout do serviço, com dependência HTTP injetada.
        resultado_servico = page.evaluate("""async () => {
            const {ApiService, ApiError} = await import('./js/services/api-service.js');
            const payload = {id_cliente: crypto.randomUUID(), conteudo_texto: 'Teste', id_remetente: 1, id_destinatario: 101, timestamp: new Date().toISOString()};
            const config = {endpoint: '/teste', timeoutMs: 10};
            const casos = [
              new Response('<html>erro</html>', {status: 200}),
              new Response(JSON.stringify({sucesso: false, erro: 'Negado'}), {status: 200}),
              new Response('{}', {status: 200}),
              new Response('', {status: 201})
            ];
            for (const response of casos) {
              try { await new ApiService(config, async () => response).enviarMensagem(payload); return 'Erro aceito como sucesso'; }
              catch (error) { if (!(error instanceof ApiError)) return 'Tipo de erro incorreto'; }
            }
            const vazio = await new ApiService(config, async () => new Response(null, {status: 204})).enviarMensagem(payload);
            if (vazio.status !== 204 || vazio.dados !== null) return '204 inválido';
            try {
              await new ApiService(config, (_, options) => new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('abort', 'AbortError'))))).enviarMensagem(payload);
              return 'Timeout não detectado';
            } catch (error) { if (!(error instanceof ApiError) || !error.message.includes('tempo')) return 'Timeout incorreto'; }
            return 'ok';
        }""")
        assert resultado_servico == "ok", resultado_servico
        passed("Serviço rejeita resposta inválida, trata 204 e cancela no timeout")

        # Verificação responsiva em três larguras, incluindo 320 px.
        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        mobile.goto(url + "/mensagens/?modo=api", wait_until="networkidle")
        expect(mobile.locator(".sidebar")).to_be_visible()
        expect(mobile.locator(".chat")).not_to_be_visible()
        sem_overflow(mobile)
        mobile.screenshot(path=str(OUT / "mobile-contatos.png"), full_page=True)
        mobile.locator('[data-contact-id="101"]').click()
        expect(mobile.locator(".chat")).to_be_visible()
        expect(mobile.locator(".sidebar")).not_to_be_visible()
        sem_overflow(mobile)
        mobile.locator("#message-input").fill("Envio pelo celular 💚")
        mobile.locator("#send-button").click()
        expect(mobile.locator('.message[data-status="confirmado"]')).to_have_count(1)
        mobile.screenshot(path=str(OUT / "mobile-chat.png"), full_page=True)
        for largura in (320, 768):
            mobile.set_viewport_size({"width": largura, "height": 844})
            sem_overflow(mobile)
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.locator("#back-button").click()
        expect(mobile.locator(".sidebar")).to_be_visible()
        mobile.reload(wait_until="networkidle")
        mobile.locator('[data-contact-id="101"]').click()
        expect(mobile.locator(".message")).to_have_count(6)
        passed("Layout em 320/390/768/1440 px, navegação móvel e histórico sem persistência")

        # Experiência padrão: o usuário responde como aluno ao bot RADACHE.
        sim = context.new_page()
        sim.on("pageerror", lambda error: errors.append(str(error)))
        sim.goto(url + "/mensagens/", wait_until="networkidle")
        textos = sim.evaluate("async () => (await import('./js/data/checkin-textos.js')).CHECKIN_TEXTOS")
        expect(sim.locator("#chat-name")).to_have_text("RADACHE")
        expect(sim.locator("#simulation-stage")).to_have_attribute("data-stage", "consentimento")
        expect(sim.locator(".message-content")).to_have_text(textos["boasVindas"])
        expect(sim.locator(".message")).to_have_attribute("data-template", "radache_boas_vindas")
        expect(sim.locator("#simulation-controls")).to_be_visible()
        expect(sim.locator('[data-answer="1"]')).to_be_visible()
        sem_overflow(sim)
        sim.screenshot(path=str(OUT / "simulacao-convite.png"), full_page=True)
        passed("Simulação padrão apresenta convite exato e identifica o papel do aluno")

        def responder(valor):
            sim.locator("#message-input").fill(valor)
            sim.locator("#send-button").click()
            expect(sim.locator("#simulation-typing")).not_to_be_visible()

        def etapa(valor):
            expect(sim.locator("#simulation-stage")).to_have_attribute("data-stage", valor)

        responder("oi")
        etapa("consentimento")
        expect(sim.locator(".message-content").nth(-2)).to_have_text(textos["invalida"])
        expect(sim.locator(".message-content").last).to_have_text(textos["boasVindas"])
        sim.locator('[data-answer="1"]').click()
        etapa("financeira")
        expect(sim.locator(".message-content").last).to_have_text(textos["financeira"])
        sim.locator("#simulate-audio").click()
        expect(sim.locator("#simulation-typing")).not_to_be_visible()
        expect(sim.locator(".message-content").last).to_have_text(textos["naoTexto"])
        etapa("financeira")
        responder("9")
        etapa("financeira")
        expect(sim.locator(".message-content").nth(-2)).to_have_text(textos["invalida"])
        expect(sim.locator(".message-content").last).to_have_text(textos["financeira"])
        passed("Consentimento e respostas inválidas/áudio respeitam a etapa atual")

        sim.locator('[data-answer="3"]').click()
        etapa("emocional")
        expect(sim.locator(".message-content").last).to_have_text(textos["emocional"])
        expect(sim.locator("#simulation-data")).to_contain_text("F: 66")
        sim.screenshot(path=str(OUT / "simulacao-pergunta-emocional.png"), full_page=True)
        sim.locator('[data-answer="2"]').click()
        etapa("concluido")
        expect(sim.locator(".message-content").last).to_have_text(textos["encerramento"])
        expect(sim.locator("#simulation-data")).to_contain_text("F: 66 · P: 75")
        sim.locator(".simulation-details summary").click()
        sim.screenshot(path=str(OUT / "simulacao-concluida.png"), full_page=True)
        responder("1")
        expect(sim.locator(".message-content").last).to_have_text(textos["respondido"])
        responder("INICIAR")
        expect(sim.locator(".message-content").last).to_have_text(textos["respondido"])
        passed("Duas perguntas calculam F/P e impedem repetição dentro do mesmo mês")

        responder("REVOGAR")
        etapa("revogado")
        expect(sim.locator(".message-content").last).to_have_text(textos["revogacao"])
        expect(sim.locator("#simulation-data")).to_contain_text("Consentimento: não · F: — · P: —")
        expect(sim.get_by_text("Resposta removida após revogação.", exact=True)).to_have_count(2)
        responder("INICIAR")
        etapa("consentimento")
        sim.locator('[data-answer="2"]').click()
        etapa("recusado")
        expect(sim.locator(".message-content").last).to_have_text(textos["recusa"])
        expect(sim.locator("#simulation-data")).to_contain_text("Consentimento: não · F: — · P: —")
        sim.locator('[data-answer="INICIAR"]').click()
        etapa("consentimento")
        passed("Revogação limpa respostas e recusa permite reinício com novo consentimento")

        sim.locator('[data-simulation-action="dias"]').click()
        expect(sim.locator(".message-content").last).to_have_text(textos["lembrete"])
        quantidade = sim.locator(".message").count()
        sim.locator('[data-simulation-action="dias"]').click()
        expect(sim.locator(".message")).to_have_count(quantidade)
        sim.locator('[data-answer="1"]').click()
        etapa("financeira")
        data_anterior = sim.locator("#simulation-date").inner_text()
        sim.locator('[data-simulation-action="mes"]').click()
        etapa("aguardando_inicio")
        assert sim.locator("#simulation-date").inner_text() != data_anterior
        expect(sim.locator(".message-content").last).to_have_text(textos["mensal"])
        passed("Relógio virtual gera um lembrete após três dias e abre o próximo mês")

        sim.locator("#message-input").fill("Rascunho de Ana")
        sim.locator('[data-contact-id="102"]').click()
        etapa("consentimento")
        expect(sim.locator(".message")).to_have_count(1)
        expect(sim.locator("#message-input")).to_have_value("")
        sim.locator('[data-answer="1"]').click()
        etapa("financeira")
        sim.locator('[data-contact-id="101"]').click()
        etapa("aguardando_inicio")
        expect(sim.locator("#message-input")).to_have_value("Rascunho de Ana")
        passed("Alunos têm estados e rascunhos independentes na simulação")

        sim_controle = {"falhar": True}
        sim_requests = []

        def falha_simulada(route):
            sim_requests.append(route.request.post_data_json)
            if sim_controle["falhar"]:
                route.fulfill(status=503, content_type="application/json", body='{"sucesso":false,"erro":"Falha simulada"}')
            else:
                route.continue_()

        sim.route("**/mock-api/mensagens", falha_simulada)
        responder("1")
        etapa("aguardando_inicio")
        expect(sim.locator('.message[data-status="falhou"]')).to_have_count(1)
        assert sim_requests[-1]["id_remetente"] == 101 and sim_requests[-1]["id_destinatario"] == 1
        sim_controle["falhar"] = False
        sim.locator('.message[data-status="falhou"] button').click()
        etapa("financeira")
        assert sim_requests[-1] == sim_requests[-2]
        sim_controle["falhar"] = True
        responder("3")
        sim.locator('[data-simulation-action="mes"]').click()
        etapa("aguardando_inicio")
        expect(sim.locator('.message[data-status="falhou"]')).to_have_count(0)
        expect(sim.locator('.message[data-status="obsoleto"]')).to_have_count(1)
        passed("Falha HTTP mantém o roteiro e retries antigos são cancelados ao mudar o ciclo")

        sim.unroute("**/mock-api/mensagens", falha_simulada)
        consentimento_anterior = sim.locator("#simulation-consent").inner_text()
        sim.locator('[data-simulation-action="ano"]').click()
        etapa("consentimento")
        expect(sim.locator(".message").last).to_have_attribute("data-template", "radache_boas_vindas")
        expect(sim.locator(".message-content").last).to_have_text(textos["boasVindas"])
        expect(sim.locator("#simulation-consent")).to_contain_text("Vencido em:")
        expect(sim.locator("#simulation-data")).to_contain_text("Consentimento: não")
        sim.locator('[data-answer="1"]').click()
        etapa("financeira")
        consentimento_renovado = sim.locator("#simulation-consent").inner_text()
        assert consentimento_renovado != consentimento_anterior
        assert "Válido até:" in consentimento_renovado
        passed("Vencimento anual reenvia boas-vindas e exige aceite para renovar a data")

        sim.locator('[data-simulation-action="mes"]').click()
        etapa("aguardando_inicio")
        expect(sim.locator(".message").last).to_have_attribute("data-template", "radache_mensal")
        expect(sim.locator(".message-content").last).to_have_text(textos["mensal"])
        expect(sim.locator('[data-answer="1"]')).to_have_text("1 · Começar as perguntas")
        expect(sim.locator('[data-answer="2"]')).to_have_count(0)
        expect(sim.locator("#simulation-consent")).to_have_text(consentimento_renovado)
        sim.screenshot(path=str(OUT / "simulacao-convite-mensal.png"), full_page=True)
        responder("2")
        etapa("aguardando_inicio")
        expect(sim.locator(".message-content").nth(-2)).to_have_text(textos["invalida"])
        expect(sim.locator(".message-content").last).to_have_text(textos["mensal"])
        responder("1")
        etapa("financeira")
        expect(sim.locator("#simulation-consent")).to_have_text(consentimento_renovado)
        passed("Mensal aguarda 1 e inicia perguntas sem renovar ou revogar o consentimento")

        # Exercita todos os valores financeiros/emocionais sem acoplar o teste ao DOM.
        maquina = sim.evaluate("""async () => {
            const {CheckinSimulator} = await import('./js/services/checkin-simulator.js');
            const inicio = Date.parse('2026-10-26T12:00:00Z');
            for (let f=1; f<=4; f++) for (let p=1; p<=5; p++) {
                const s = new CheckinSimulator(() => inicio);
                s.reiniciar(101); s.responder(101, '1'); s.responder(101, String(f)); s.responder(101, String(p));
                const estado = s.estado(101);
                if (estado.F !== [0,33,66,100][f-1] || estado.P !== ((5-p)/4)*100 || estado.etapa !== 'concluido') return 'F/P incorretos';
                if (s.avancarTresDias(101).length !== 0) return 'Lembrete após conclusão';
                s.responder(101, 'REVOGAR');
                if (s.estado(101).F !== null || s.estado(101).P !== null || s.estado(101).consentimento) return 'Revogação incompleta';
            }
            const s = new CheckinSimulator(() => inicio);
            s.reiniciar(101); s.responder(101, '2');
            if (s.avancarTresDias(101).length !== 0) return 'Lembrete após recusa';
            s.responder(101, 'INICIAR'); s.responder(101, '1');
            for (const resposta of ['0', '5', '1.5', '01', 'banana']) {
                if (s.responder(101, resposta).mensagens.length !== 2 || s.estado(101).etapa !== 'financeira' || s.estado(101).F !== null) return 'Opção inválida alterou o estado';
            }
            const virada = new CheckinSimulator(() => new Date(2026, 0, 31, 23, 50).getTime());
            virada.reiniciar(101); virada.responder(101, '1'); virada.responder(101, '4'); virada.responder(101, '1');
            virada.avancarTresDias(101); virada.responder(101, 'oi');
            if (virada.estado(101).etapa !== 'aguardando_inicio' || virada.estado(101).F !== null) return 'Virada de mês incorreta';
            virada.proximoMes(101);
            const novaData = new Date(virada.estado(101).timestamp);
            if (novaData.getDate() !== 3 || novaData.getMonth() !== 2 || novaData.getHours() !== 23) return 'Relógio local inconsistente';
            return 'ok';
        }""")
        assert maquina == "ok", maquina
        passed("Máquina de estados valida 20 combinações F/P, revogação e opções inválidas")

        anual = sim.evaluate("""async () => {
            const {CheckinSimulator} = await import('./js/services/checkin-simulator.js');
            const inicial = new Date(2026, 0, 31, 10, 15, 30).getTime();
            const s = new CheckinSimulator(() => inicial);
            if (s.reiniciar(1)[0].template !== 'radache_boas_vindas' || s.estado(1).dataConsentimento !== null) return 'Primeiro contato incorreto';
            s.responder(1, '1');
            const consentimento = s.estado(1).dataConsentimento;
            const validade = s.estado(1).validadeConsentimento;
            for (let mes=1; mes<12; mes++) {
                if (s.proximoMes(1)[0].template !== 'radache_mensal' || s.estado(1).etapa !== 'aguardando_inicio') return 'Mensal incorreto em ' + mes;
                const lembrete = s.estado(1).timestamp;
                s.responder(1, '2');
                if (!s.estado(1).consentimento || s.estado(1).etapa !== 'aguardando_inicio') return '2 mensal revogou autorização';
                s.responder(1, '1');
                if (s.estado(1).dataConsentimento !== consentimento || s.estado(1).validadeConsentimento !== validade) return 'Mensal renovou a autorização';
            }
            const renovacao = s.proximoMes(1);
            if (renovacao[0].template !== 'radache_boas_vindas' || !s.estado(1).consentimentoExpirado || s.estado(1).consentimento || s.estado(1).etapa !== 'consentimento') return 'Falha no limite exato de 12 meses';
            if (s.estado(1).timestamp !== validade) return 'Avanço mensal perdeu o dia de referência';
            s.responder(1, '1');
            if (s.estado(1).dataConsentimento !== validade || !s.estado(1).consentimento) return 'Renovação não atualizou a data';
            s.responder(1, 'REVOGAR');
            if (s.estado(1).dataConsentimento !== null || s.estado(1).validadeConsentimento !== null) return 'Revogação manteve autorização';
            if (s.proximoMes(1)[0].template !== 'radache_boas_vindas') return 'Revogado recebeu mensal';
            s.responder(1, '2');
            if (s.proximoMes(1)[0].template !== 'radache_boas_vindas') return 'Recusado recebeu mensal';

            const bissexto = new CheckinSimulator(() => new Date(2024, 1, 29, 15, 0).getTime());
            bissexto.reiniciar(1); bissexto.responder(1, '1');
            const vence = new Date(bissexto.estado(1).validadeConsentimento);
            if (vence.getFullYear() !== 2025 || vence.getMonth() !== 1 || vence.getDate() !== 28 || vence.getHours() !== 15) return 'Ano bissexto incorreto';
            if (bissexto.avancarDozeMeses(1)[0].template !== 'radache_boas_vindas') return 'Renovação de ano bissexto incorreta';

            const pendente = new CheckinSimulator(() => new Date(2026, 0, 1, 12).getTime());
            pendente.reiniciar(1); pendente.responder(1, '1'); pendente.avancarMeses(1, 11);
            const dataOriginal = pendente.estado(1).dataConsentimento;
            if (pendente.avancarTresDias(1)[0].template !== 'radache_lembrete' || pendente.estado(1).etapa !== 'aguardando_inicio') return 'Sem lembrete em aguardando_inicio';
            if (pendente.estado(1).dataConsentimento !== dataOriginal) return 'Lembrete renovou a autorização';
            if (pendente.avancarTresDias(1).length !== 0) return 'Lembrete duplicado';
            pendente.responder(1, '1');
            let ultima;
            for (let i=0; i<9; i++) ultima = pendente.avancarTresDias(1);
            if (ultima[0]?.template !== 'radache_boas_vindas' || pendente.estado(1).etapa !== 'consentimento') return 'Etapa pendente não pediu renovação no vencimento';
            return 'ok';
        }""")
        assert anual == "ok", anual
        passed("Consentimento anual: 11 mensais, vencimento exato, renovação, bissexto e lembrete")

        sim.locator('[data-simulation-action="reiniciar"]').click()
        expect(sim.locator(".message")).to_have_count(1)
        for largura in (390, 320, 768):
            sim.set_viewport_size({"width": largura, "height": 844})
            sem_overflow(sim)
        sim.set_viewport_size({"width": 390, "height": 844})
        sim.locator('[data-answer="1"]').click()
        etapa("financeira")
        sim.screenshot(path=str(OUT / "simulacao-mobile.png"), full_page=True)
        sim.locator("#back-button").click()
        expect(sim.locator(".sidebar")).to_be_visible()
        sim.reload(wait_until="networkidle")
        sim.locator('[data-contact-id="101"]').click()
        etapa("consentimento")
        expect(sim.locator(".message")).to_have_count(1)
        passed("Simulação responsiva em 320/390/768 px e reinício sem persistência")

        assert not errors, errors
        assert not externos, externos
        assert not falhas_recursos, falhas_recursos
        (OUT / "resultado.json").write_text(json.dumps({"resultado": "aprovado", "verificacoes": checks, "erros_javascript": errors, "recursos_externos": externos, "recursos_com_falha": falhas_recursos}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)

print(f"Concluído: {len(checks)} verificações. Evidências em {OUT}", flush=True)
