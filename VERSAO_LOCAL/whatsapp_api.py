#!/usr/bin/env python3
"""
RADACHE — API do WhatsApp (US-B7 / US-B8)

Usa a WhatsApp Business Cloud API (Meta). Só biblioteca padrão do Python.

Faz:
  - Webhook (GET verificação / POST mensagens recebidas) com checagem de assinatura
  - Envio de mensagens (texto e template aprovado)
  - Fluxo do check-in: consentimento LGPD -> pergunta financeira -> pergunta
    psicológica -> fim. Revogação a qualquer momento (REVOGAR).
  - Lembrete após 3 dias sem resposta
  - Grava tudo no SQLite

Variáveis de ambiente:
  WHATSAPP_TOKEN            token de acesso (Meta)
  WHATSAPP_PHONE_ID         ID do número de telefone (Meta)
  WHATSAPP_VERIFY_TOKEN     texto que você escolhe e informa no painel da Meta
  WHATSAPP_APP_SECRET       segredo do app (valida a assinatura do webhook)
  WHATSAPP_ADMIN_KEY        chave para chamar as rotas /admin/*
  WHATSAPP_TEMPLATE_CHECKIN template aprovado com o texto de consentimento
  WHATSAPP_TEMPLATE_LEMBRETE template aprovado do lembrete
  WHATSAPP_API_VERSION      padrão v21.0
  WHATSAPP_MODO_TESTE=1     não envia nada à Meta, só imprime as mensagens
  RADACHE_DB                caminho do SQLite (padrão radache.db)
  PORT                      porta do servidor (padrão 8081)
"""
import hashlib
import hmac
import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------- configuração
def cfg(nome, padrao=""):
    return os.environ.get(nome, padrao)

MODO_TESTE = cfg("WHATSAPP_MODO_TESTE") == "1"
DB_PATH = cfg("RADACHE_DB", "radache.db")
DIAS_LEMBRETE = 3

# Pontuação usada pelo cálculo do RE (US-B9)
OPCOES_FINANCEIRAS = {
    "1": ("Não sinto dificuldade", 0),
    "2": ("Dificuldade leve", 33),
    "3": ("Dificuldade significativa", 66),
    "4": ("Considerando trancar por motivo financeiro", 100),
}

TEXTO_CONSENTIMENTO = (
    "Olá! Aqui é o RADACHE, da UNEMAT. Vamos fazer 2 perguntas rápidas sobre "
    "sua situação financeira e seu bem-estar, para o NAE poder apoiar você.\n\n"
    "Suas respostas são confidenciais (LGPD), usadas só pelo CAEst/PRAE/NAE, e "
    "você pode revogar quando quiser enviando REVOGAR.\n\n"
    "Você aceita participar?\n1 - Sim\n2 - Não"
)
TEXTO_FINANCEIRA = (
    "Pergunta 1 de 2: como está sua situação financeira para continuar no curso?\n"
    "1 - Não sinto dificuldade\n2 - Dificuldade leve\n3 - Dificuldade significativa\n"
    "4 - Considerando trancar por motivo financeiro"
)
TEXTO_PSICOLOGICA = (
    "Pergunta 2 de 2: como você avalia seu bem-estar emocional hoje?\n"
    "1 - Muito ruim\n2 - Ruim\n3 - Regular\n4 - Bom\n5 - Muito bom"
)
TEXTO_FIM = "Obrigado! Suas respostas foram registradas. Para revogar seu consentimento, envie REVOGAR."
TEXTO_RECUSA = "Tudo bem, nada foi registrado. Se mudar de ideia, envie INICIAR."
TEXTO_REVOGADO = "Consentimento revogado e suas respostas foram apagadas. Para voltar a participar, envie INICIAR."
TEXTO_INVALIDO = "Não entendi. Responda apenas com o número de uma das opções."

# ---------------------------------------------------------------- banco de dados
def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def criar_tabelas():
    with conectar() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS whatsapp_sessoes (
            telefone TEXT PRIMARY KEY,
            etapa TEXT NOT NULL,              -- consentimento|financeira|psicologica|concluido|recusou|revogado
            consentimento INTEGER NOT NULL DEFAULT 0,
            data_consentimento TEXT,
            resposta_financeira INTEGER,      -- 1 a 4
            pontos_financeiro INTEGER,        -- 0, 33, 66 ou 100
            resposta_psicologica INTEGER,     -- 1 a 5
            lembrete_enviado INTEGER NOT NULL DEFAULT 0,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            concluido_em TEXT
        );
        CREATE TABLE IF NOT EXISTS whatsapp_msgs_processadas (
            msg_id TEXT PRIMARY KEY,
            recebido_em TEXT NOT NULL
        );
        """)

def agora():
    return datetime.now().isoformat(timespec="seconds")

def so_digitos(telefone):
    return "".join(c for c in str(telefone) if c.isdigit())

def mascarar(telefone):
    return telefone[:4] + "*" * max(len(telefone) - 6, 0) + telefone[-2:]

# ---------------------------------------------------------------- envio (Meta)
def _post_meta(payload):
    """Envia um payload para a Cloud API. Retorna (ok, resposta)."""
    if MODO_TESTE:
        print(f"[TESTE] -> {mascarar(payload['to'])}: {json.dumps(payload, ensure_ascii=False)[:300]}")
        return True, {"teste": True}
    token, phone_id = cfg("WHATSAPP_TOKEN"), cfg("WHATSAPP_PHONE_ID")
    if not token or not phone_id:
        return False, {"erro": "WHATSAPP_TOKEN ou WHATSAPP_PHONE_ID não configurados"}
    url = f"https://graph.facebook.com/{cfg('WHATSAPP_API_VERSION', 'v21.0')}/{phone_id}/messages"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return False, {"erro": f"HTTP {e.code}", "detalhe": e.read().decode("utf-8", "ignore")[:300]}
    except Exception as e:
        return False, {"erro": str(e)}

def enviar_texto(para, texto):
    """Texto livre: só funciona dentro da janela de 24 h após o aluno escrever."""
    return _post_meta({
        "messaging_product": "whatsapp", "to": para, "type": "text",
        "text": {"body": texto, "preview_url": False},
    })

def enviar_template(para, nome_template, idioma="pt_BR"):
    """Mensagem iniciada por nós: a Meta exige template aprovado."""
    return _post_meta({
        "messaging_product": "whatsapp", "to": para, "type": "template",
        "template": {"name": nome_template, "language": {"code": idioma}},
    })

# ---------------------------------------------------------------- fluxo do check-in
def _obter(con, telefone):
    return con.execute("SELECT * FROM whatsapp_sessoes WHERE telefone = ?", (telefone,)).fetchone()

def _nova_sessao(con, telefone):
    t = agora()
    con.execute("""INSERT INTO whatsapp_sessoes (telefone, etapa, criado_em, atualizado_em)
                   VALUES (?, 'consentimento', ?, ?)
                   ON CONFLICT(telefone) DO UPDATE SET
                     etapa='consentimento', consentimento=0, data_consentimento=NULL,
                     resposta_financeira=NULL, pontos_financeiro=NULL, resposta_psicologica=NULL,
                     lembrete_enviado=0, concluido_em=NULL, atualizado_em=excluded.atualizado_em""",
                (telefone, t, t))

def ao_concluir_checkin(telefone, dados):
    """
    Gancho chamado quando o aluno termina as 2 perguntas.
    Aqui entra o recálculo do RE (US-B9) e a gravação em avaliacoes/checkins.
    `dados` = {resposta_financeira, pontos_financeiro, resposta_psicologica}
    """
    print(f"[CHECK-IN CONCLUÍDO] {mascarar(telefone)} {dados}")

def processar_mensagem(telefone, texto):
    """Recebe o que o aluno escreveu e devolve o texto da resposta."""
    comando = texto.strip().lower()
    with conectar() as con:
        sessao = _obter(con, telefone)

        # Revogar vale em qualquer etapa (LGPD): apaga as respostas
        if comando in ("revogar", "parar", "sair"):
            _nova_sessao(con, telefone)
            con.execute("UPDATE whatsapp_sessoes SET etapa='revogado' WHERE telefone = ?", (telefone,))
            return TEXTO_REVOGADO

        if comando == "iniciar" or sessao is None:
            _nova_sessao(con, telefone)
            return TEXTO_CONSENTIMENTO

        etapa = sessao["etapa"]
        t = agora()

        if etapa == "consentimento":
            if comando in ("1", "sim", "s"):
                con.execute("""UPDATE whatsapp_sessoes SET etapa='financeira', consentimento=1,
                               data_consentimento=?, atualizado_em=? WHERE telefone=?""", (t, t, telefone))
                return TEXTO_FINANCEIRA
            if comando in ("2", "nao", "não", "n"):
                con.execute("UPDATE whatsapp_sessoes SET etapa='recusou', atualizado_em=? WHERE telefone=?", (t, telefone))
                return TEXTO_RECUSA
            return TEXTO_INVALIDO + "\n\n" + TEXTO_CONSENTIMENTO

        if etapa == "financeira":
            if comando in OPCOES_FINANCEIRAS:
                pontos = OPCOES_FINANCEIRAS[comando][1]
                con.execute("""UPDATE whatsapp_sessoes SET etapa='psicologica', resposta_financeira=?,
                               pontos_financeiro=?, atualizado_em=? WHERE telefone=?""",
                            (int(comando), pontos, t, telefone))
                return TEXTO_PSICOLOGICA
            return TEXTO_INVALIDO + "\n\n" + TEXTO_FINANCEIRA

        if etapa == "psicologica":
            if comando in ("1", "2", "3", "4", "5"):
                con.execute("""UPDATE whatsapp_sessoes SET etapa='concluido', resposta_psicologica=?,
                               concluido_em=?, atualizado_em=? WHERE telefone=?""",
                            (int(comando), t, t, telefone))
                final = _obter(con, telefone)
                ao_concluir_checkin(telefone, {
                    "resposta_financeira": final["resposta_financeira"],
                    "pontos_financeiro": final["pontos_financeiro"],
                    "resposta_psicologica": final["resposta_psicologica"],
                })
                return TEXTO_FIM
            return TEXTO_INVALIDO + "\n\n" + TEXTO_PSICOLOGICA

        if etapa == "concluido":
            return "Suas respostas deste mês já foram registradas. Para revogar o consentimento, envie REVOGAR."
        return TEXTO_RECUSA if etapa == "recusou" else TEXTO_REVOGADO

# ---------------------------------------------------------------- ações iniciadas pelo sistema
def iniciar_checkin(telefone):
    """Abre o check-in de um aluno enviando o template de consentimento."""
    telefone = so_digitos(telefone)
    with conectar() as con:
        _nova_sessao(con, telefone)
    return enviar_template(telefone, cfg("WHATSAPP_TEMPLATE_CHECKIN", "radache_checkin"))

def enviar_lembretes():
    """Chame uma vez por dia (cron). Lembra quem não respondeu em 3 dias, uma única vez."""
    limite = (datetime.now() - timedelta(days=DIAS_LEMBRETE)).isoformat(timespec="seconds")
    enviados = 0
    with conectar() as con:
        pendentes = con.execute("""SELECT telefone FROM whatsapp_sessoes
            WHERE etapa IN ('consentimento','financeira','psicologica')
              AND lembrete_enviado = 0 AND atualizado_em <= ?""", (limite,)).fetchall()
        for linha in pendentes:
            ok, _ = enviar_template(linha["telefone"], cfg("WHATSAPP_TEMPLATE_LEMBRETE", "radache_lembrete"))
            if ok:
                con.execute("UPDATE whatsapp_sessoes SET lembrete_enviado=1 WHERE telefone=?", (linha["telefone"],))
                enviados += 1
    return enviados

# ---------------------------------------------------------------- webhook
def assinatura_valida(corpo, cabecalho):
    segredo = cfg("WHATSAPP_APP_SECRET")
    if not segredo:
        return MODO_TESTE  # sem segredo, só aceitamos em modo teste
    esperado = "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho or "")

def _extrair_mensagens(payload):
    """Gera (id, telefone, texto) de cada mensagem de texto/botão do payload da Meta."""
    for entrada in payload.get("entry", []):
        for mudanca in entrada.get("changes", []):
            for m in mudanca.get("value", {}).get("messages", []):
                tipo = m.get("type")
                if tipo == "text":
                    texto = m["text"].get("body", "")
                elif tipo == "button":
                    texto = m["button"].get("text", "")
                elif tipo == "interactive":
                    i = m["interactive"]
                    texto = (i.get("button_reply") or i.get("list_reply") or {}).get("id", "")
                else:
                    texto = ""  # áudio, imagem etc.
                yield m.get("id", ""), m.get("from", ""), texto

def tratar_webhook(payload):
    for msg_id, telefone, texto in _extrair_mensagens(payload):
        with conectar() as con:  # a Meta reenvia eventos: ignora o que já foi tratado
            if msg_id:
                try:
                    con.execute("INSERT INTO whatsapp_msgs_processadas VALUES (?, ?)", (msg_id, agora()))
                except sqlite3.IntegrityError:
                    continue
        if not texto:
            enviar_texto(telefone, "Por enquanto só consigo ler mensagens de texto. Responda com o número da opção.")
            continue
        enviar_texto(telefone, processar_mensagem(telefone, texto))

class Handler(BaseHTTPRequestHandler):
    def _json(self, codigo, corpo):
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _admin_ok(self):
        chave = cfg("WHATSAPP_ADMIN_KEY")
        return bool(chave) and hmac.compare_digest(self.headers.get("X-Admin-Key", ""), chave)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/webhook":  # verificação feita pela Meta ao cadastrar o webhook
            q = parse_qs(url.query)
            if q.get("hub.mode") == ["subscribe"] and q.get("hub.verify_token", [""])[0] == cfg("WHATSAPP_VERIFY_TOKEN") != "":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(q["hub.challenge"][0].encode())
                return
            return self._json(403, {"erro": "verificação recusada"})
        self._json(404, {"erro": "rota não encontrada"})

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        corpo = self.rfile.read(tamanho)
        if self.path == "/webhook":
            if not assinatura_valida(corpo, self.headers.get("X-Hub-Signature-256")):
                return self._json(403, {"erro": "assinatura inválida"})
            try:
                tratar_webhook(json.loads(corpo or b"{}"))
            except Exception as e:  # sempre responde 200 para a Meta não reenviar em loop
                print("[ERRO webhook]", e)
            return self._json(200, {"ok": True})
        if self.path in ("/admin/iniciar", "/admin/lembretes"):
            if not self._admin_ok():
                return self._json(401, {"erro": "acesso negado"})
            if self.path == "/admin/lembretes":
                return self._json(200, {"lembretes_enviados": enviar_lembretes()})
            try:
                telefone = json.loads(corpo)["telefone"]
            except Exception:
                return self._json(400, {"erro": "envie {\"telefone\": \"5565999999999\"}"})
            ok, resp = iniciar_checkin(telefone)
            return self._json(200 if ok else 502, {"ok": ok, "resposta": resp})
        self._json(404, {"erro": "rota não encontrada"})

    def log_message(self, formato, *args):
        pass  # evita registrar telefones em log

if __name__ == "__main__":
    criar_tabelas()
    porta = int(cfg("PORT", "8081"))
    print(f"API do WhatsApp na porta {porta} (modo teste: {MODO_TESTE})")
    ThreadingHTTPServer(("0.0.0.0", porta), Handler).serve_forever()
