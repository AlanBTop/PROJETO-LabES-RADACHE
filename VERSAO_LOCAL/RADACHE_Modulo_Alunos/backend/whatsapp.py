"""
========================================================================================
RADACHE — Módulo de Gerenciamento de Alunos
Arquivo: whatsapp.py
Camada: Integração Externa (WhatsApp Business Cloud API - Meta) & Máquina de Estados
========================================================================================

ARQUITETURA DA INTEGRAÇÃO E CONFORMIDADE LGPD:
1. CANAL OFICIAL DA META (Graph API):
   - Não utiliza emuladores não oficiais (como Baileys ou Selenium) que causam banimentos.
   - Comunicação via HTTPS oficial com a API Cloud do WhatsApp Business da Meta.
   - Uso de Modelos Aprovados (HSM Templates) para disparo proativo fora da janela de 24h.

2. MÁQUINA DE ESTADOS CONVERSACIONAL (State Machine):
   - 'aguardando_consentimento': Dispara o convite LGPD com explicação do propósito.
   - 'pergunta_financeira'     : Pergunta sobre custos de moradia, transporte e permanência (1 a 4).
   - 'pergunta_psicologica'    : Pergunta sobre bem-estar e estresse acadêmico (1 a 5).
   - 'concluido'               : Salva os dados e dispara recálculo em tempo real do RE.
   - 'recusado'                : Discente respondeu NÃO; nenhum dado é coletado.
   - 'revogado'                : Discente enviou comando de cancelamento; respostas são expurgadas.

3. PRIVACY BY DESIGN & DIREITO DO TITULAR (LGPD Arts. 7º, 8º e 18):
   - Consentimento livre, informado e inequívoco antes de fazer qualquer pergunta sensível.
   - A recusa em participar NÃO gera punição acadêmica ou cancelamento de matrícula.
   - Comando de revogação a qualquer momento ('REVOGAR', 'CANCELAR', 'SAIR'):
     remove imediatamente as respostas financeiras e psicológicas já registradas.

4. SEGURANÇA CRIPTOGRÁFICA DE WEBHOOKS:
   - Validação da assinatura digital HMAC-SHA256 (cabeçalho 'X-Hub-Signature-256')
     para garantir que toda mensagem recebida partiu autenticamente dos servidores da Meta.
"""
from contextlib import closing
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import database

# Mapeamento semântico das opções de resposta financeira
FINANCEIRO = {
    "1": "Não sinto dificuldade",
    "2": "Dificuldade leve",
    "3": "Dificuldade significativa",
    "4": "Considerando trancar por motivo financeiro",
}

# Textos institucionais do diálogo com discentes
PERGUNTA_CONSENTIMENTO = (
    "Olá! A UNEMAT convida você para o check-in mensal do RADACHE. Serão solicitadas "
    "respostas sobre situação financeira e bem-estar psicológico, vinculadas aos seus "
    "dados acadêmicos para calcular um indicador de risco de evasão e apoiar o acompanhamento "
    "pelas equipes autorizadas da Universidade. Participar é voluntário; recusar não afeta "
    "seu vínculo acadêmico ou acesso a serviços. Sem seu aceite, nenhuma resposta será coletada. "
    "Você pode revogar a qualquer momento respondendo REVOGAR, CANCELAR ou SAIR. Para exercer "
    "outros direitos LGPD, procure o canal institucional do Encarregado de Dados da UNEMAT. "
    "Responda SIM para consentir ou NÃO para recusar."
)
PERGUNTA_FINANCEIRA = (
    "Como está sua situação financeira para permanecer no curso? Responda apenas com um número:\n"
    "1 — Não sinto dificuldade\n2 — Dificuldade leve\n3 — Dificuldade significativa\n"
    "4 — Considerando trancar por motivo financeiro"
)
PERGUNTA_PSICOLOGICA = (
    "Em uma escala de 1 a 5, como você avalia seu bem-estar psicológico neste mês?\n"
    "1 — Muito ruim; 2 — Ruim; 3 — Regular; 4 — Bom; 5 — Muito bom"
)
MENSAGEM_RECUSA = "Tudo bem. Seu consentimento não foi registrado e nenhuma pergunta será feita."
MENSAGEM_REVOGACAO = "Seu consentimento foi revogado. Este check-in foi encerrado e suas respostas foram removidas."
MENSAGEM_INVALIDA = "Não reconheci essa resposta. Por favor, siga as opções numéricas da pergunta."

# Vocabulário semântico aceito para revogação imediata de consentimento
COMANDOS_REVOGACAO = {
    "revogar", "revogar consentimento", "revogar meu consentimento",
    "cancelar", "parar", "sair", "stop", "quero cancelar", "não quero mais", "nao quero mais",
}


def _configuracao():
    """Lê as credenciais do ambiente e exige o mínimo necessário para enviar."""
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    if not token or not phone_id:
        raise RuntimeError("Configure WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID para enviar mensagens.")
    versao = os.environ.get("WHATSAPP_API_VERSION", "").strip()
    if not versao:
        raise RuntimeError("Configure WHATSAPP_API_VERSION com a versão ativa da Graph API.")
    return token, phone_id, versao


def enviar_texto(telefone, texto):

    """Envia uma mensagem de texto usando somente urllib da biblioteca padrão."""
    token, phone_id, versao = _configuracao()
    url = "https://graph.facebook.com/{}/{}/messages".format(versao, phone_id)
    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual",
        "to": telefone, "type": "text", "text": {"preview_url": False, "body": texto},
    }
    request = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("Falha ao enviar mensagem pela Meta: HTTP {} {}".format(exc.code, detalhe)) from exc


def enviar_template(telefone, nome_modelo, parametros=()):
    """Envia modelo previamente aprovado, necessário para iniciar/reabrir conversas."""
    token, phone_id, versao = _configuracao()
    idioma = os.environ.get("WHATSAPP_TEMPLATE_IDIOMA", "pt_BR").strip()
    if not nome_modelo:
        raise RuntimeError("Configure o nome do modelo de mensagem aprovado pela Meta.")
    template = {"name": nome_modelo, "language": {"code": idioma}}
    if parametros:
        template["components"] = [{"type": "body", "parameters": [
            {"type": "text", "text": str(valor)} for valor in parametros
        ]}]
    payload = {"messaging_product": "whatsapp", "to": telefone, "type": "template", "template": template}
    url = "https://graph.facebook.com/{}/{}/messages".format(versao, phone_id)
    request = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("Falha ao enviar modelo Meta: HTTP {} {}".format(exc.code, detalhe)) from exc


def validar_assinatura(corpo, assinatura, segredo):
    """Verifica X-Hub-Signature-256 para autenticar o webhook da Meta."""
    if not segredo or not assinatura or not assinatura.startswith("sha256="):
        return False
    esperada = "sha256=" + hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, assinatura)


def _digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def _telefone_internacional(valor):
    numero = _digitos(valor)
    return "55" + numero if len(numero) in (10, 11) else numero


def _encontrar_aluno_por_telefone(origem):
    """Associa apenas um telefone cadastrado; números ambíguos não são processados."""
    telefone = _digitos(origem)
    if len(telefone) < 10:
        return None
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT id, telefone FROM alunos WHERE status='ativo' AND status_exclusao=0"
    ).fetchall()
    conn.close()
    correspondencias = []
    for row in rows:
        cadastrado = _digitos(row["telefone"])
        if telefone == cadastrado or _telefone_internacional(telefone) == _telefone_internacional(cadastrado):
            correspondencias.append(row["id"])
    return correspondencias[0] if len(correspondencias) == 1 else None


def iniciar_checkin(aluno_id):
    with _fluxo_lock:
        return _iniciar_checkin(aluno_id)


def _iniciar_checkin(aluno_id):
    """Cria pendência sem consentimento e envia somente o convite LGPD."""
    conn = database.get_connection()
    aluno = conn.execute(
        "SELECT telefone FROM alunos WHERE id=? AND status='ativo' AND status_exclusao=0", (aluno_id,)
    ).fetchone()
    if not aluno:
        conn.close()
        raise ValueError("Aluno ativo não encontrado.")
    telefone = _telefone_internacional(aluno["telefone"])
    if len(telefone) not in (12, 13) or not telefone.startswith("55"):
        conn.close()
        raise ValueError("O aluno não possui telefone válido.")
    aberta = conn.execute(
        "SELECT id FROM checkins WHERE aluno_id=? AND estado_conversa IN ('aguardando_consentimento','pergunta_financeira','pergunta_psicologica') ORDER BY id DESC LIMIT 1",
        (aluno_id,),
    ).fetchone()
    if aberta:
        conn.close()
        raise ValueError("Já existe um check-in aguardando resposta para este aluno.")
    cursor = conn.execute(
        "INSERT INTO checkins (aluno_id,consentimento_lgpd,estado_conversa,ultima_interacao,lembrete_enviado) VALUES (?,0,'aguardando_consentimento',CURRENT_TIMESTAMP,0)",
        (aluno_id,),
    )
    checkin_id = cursor.lastrowid
    conn.commit()
    conn.close()
    try:
        modelo = os.environ.get("WHATSAPP_TEMPLATE_CONSENTIMENTO", "").strip()
        enviar_template(telefone, modelo, (PERGUNTA_CONSENTIMENTO,))
    except Exception:
        conn = database.get_connection()
        conn.execute("DELETE FROM checkins WHERE id=? AND consentimento_lgpd=0", (checkin_id,))
        conn.commit()
        conn.close()
        raise
    return checkin_id


def _pendencia_atual(aluno_id):
    conn = database.get_connection()
    row = conn.execute(
        "SELECT id, consentimento_lgpd, estado_conversa FROM checkins WHERE aluno_id=? AND estado_conversa IN ('aguardando_consentimento','pergunta_financeira','pergunta_psicologica') ORDER BY id DESC LIMIT 1",
        (aluno_id,),
    ).fetchone()
    conn.close()
    return row



# O servidor usa threads: serializa transições e entregas para não duplicar eventos.
_fluxo_lock = threading.RLock()


def _preparar_resposta(conn, aluno_id, texto):
    resposta = re.sub(r"[^\w\s]", "", str(texto or ""), flags=re.UNICODE).strip().casefold()
    pendencia = conn.execute(
        """SELECT id,consentimento_lgpd,estado_conversa FROM checkins WHERE aluno_id=?
           AND estado_conversa IN ('aguardando_consentimento','pergunta_financeira','pergunta_psicologica')
           ORDER BY id DESC LIMIT 1""", (aluno_id,)
    ).fetchone()
    if resposta in COMANDOS_REVOGACAO:
        if pendencia and pendencia["estado_conversa"] == "aguardando_consentimento":
            conn.execute("UPDATE checkins SET estado_conversa='recusado',ultima_interacao=CURRENT_TIMESTAMP WHERE id=?", (pendencia["id"],))
            return MENSAGEM_RECUSA
        ultimo = conn.execute("SELECT id,estado_conversa FROM checkins WHERE aluno_id=? ORDER BY id DESC LIMIT 1", (aluno_id,)).fetchone()
        checkin = conn.execute("SELECT id FROM checkins WHERE aluno_id=? AND consentimento_lgpd=1 ORDER BY id DESC LIMIT 1", (aluno_id,)).fetchone()
        if checkin and (not ultimo or ultimo["estado_conversa"] != "revogado"):
            conn.execute("""UPDATE checkins SET consentimento_lgpd=0,resposta_financeira=NULL,
                resposta_psicologica=NULL,resposta_academica=NULL,estado_conversa='revogado',
                ultima_interacao=CURRENT_TIMESTAMP,lembrete_enviado=0 WHERE id=?""", (checkin["id"],))
            return MENSAGEM_REVOGACAO
        return None
    if not pendencia:
        return None
    checkin_id, estado = pendencia["id"], pendencia["estado_conversa"]
    if estado == "aguardando_consentimento":
        if resposta in ("sim", "s", "aceito", "concordo"):
            conn.execute("""UPDATE checkins SET consentimento_lgpd=1,estado_conversa='pergunta_financeira',
                ultima_interacao=CURRENT_TIMESTAMP,lembrete_enviado=0 WHERE id=?""", (checkin_id,))
            return PERGUNTA_FINANCEIRA
        if resposta in ("não", "nao", "n", "recuso", "recusar", "não quero", "nao quero"):
            conn.execute("UPDATE checkins SET consentimento_lgpd=0,estado_conversa='recusado',ultima_interacao=CURRENT_TIMESTAMP WHERE id=?", (checkin_id,))
            return MENSAGEM_RECUSA
        return "Responda SIM para consentir com o check-in ou NÃO para recusar."
    if pendencia["consentimento_lgpd"] != 1:
        conn.execute("UPDATE checkins SET estado_conversa='recusado' WHERE id=?", (checkin_id,))
        return None
    if estado == "pergunta_financeira":
        valor = FINANCEIRO.get(resposta)
        if not valor:
            return MENSAGEM_INVALIDA + "\n" + PERGUNTA_FINANCEIRA
        conn.execute("""UPDATE checkins SET resposta_financeira=?,estado_conversa='pergunta_psicologica',
            ultima_interacao=CURRENT_TIMESTAMP,lembrete_enviado=0 WHERE id=?""", (valor, checkin_id))
        return PERGUNTA_PSICOLOGICA
    if resposta not in ("1", "2", "3", "4", "5"):
        return MENSAGEM_INVALIDA + "\n" + PERGUNTA_PSICOLOGICA
    conn.execute("""UPDATE checkins SET resposta_psicologica=?,estado_conversa='concluido',
        ultima_interacao=CURRENT_TIMESTAMP,lembrete_enviado=0 WHERE id=?""", (resposta, checkin_id))
    # Atualização e recálculo pertencem à mesma transação.
    database.recalcular_avaliacao_por_checkin(checkin_id, conn)
    return "Obrigado por responder. Seu check-in foi registrado."


def processar_mensagem(origem, texto, mensagem_id=None):
    """Reentregas repetem apenas a entrega pendente, nunca a transição da pesquisa."""
    with _fluxo_lock:
        with closing(database.get_connection()) as conn, conn:
            evento = conn.execute("SELECT resposta,enviado FROM whatsapp_eventos WHERE mensagem_id=?", (mensagem_id,)).fetchone() if mensagem_id else None
            if evento:
                if evento["enviado"]:
                    return False
                mensagem = evento["resposta"]
            else:
                aluno_id = _encontrar_aluno_por_telefone(origem)
                if aluno_id is None:
                    return False
                mensagem = _preparar_resposta(conn, aluno_id, texto)
                if mensagem_id:
                    conn.execute("INSERT INTO whatsapp_eventos (mensagem_id,origem,resposta,enviado) VALUES (?,?,?,?)",
                                 (mensagem_id, _digitos(origem), mensagem, int(mensagem is None)))
        if mensagem is None:
            return False
        enviar_texto(_digitos(origem), mensagem)
        if mensagem_id:
            with closing(database.get_connection()) as conn, conn:
                conn.execute("UPDATE whatsapp_eventos SET enviado=1 WHERE mensagem_id=?", (mensagem_id,))
        return True


def enviar_lembretes_pendentes():
    with _fluxo_lock:
        return _enviar_lembretes_pendentes()


def _enviar_lembretes_pendentes():
    """Envia uma única lembrança após três dias sem interação com resposta pendente."""
    conn = database.get_connection()
    rows = conn.execute(
        """SELECT c.id,c.estado_conversa,c.consentimento_lgpd,a.telefone FROM checkins c JOIN alunos a ON a.id=c.aluno_id
           WHERE ((c.consentimento_lgpd=0 AND c.estado_conversa='aguardando_consentimento')
               OR (c.consentimento_lgpd=1 AND c.estado_conversa IN ('pergunta_financeira','pergunta_psicologica')))
             AND c.lembrete_enviado=0 AND c.ultima_interacao IS NOT NULL
             AND datetime(c.ultima_interacao) <= datetime('now','-3 days')
             AND a.status='ativo' AND a.status_exclusao=0"""
    ).fetchall()
    conn.close()
    enviados = 0
    for row in rows:
        if row["estado_conversa"] == "aguardando_consentimento":
            modelo = os.environ.get("WHATSAPP_TEMPLATE_CONSENTIMENTO", "").strip()
            parametros = (PERGUNTA_CONSENTIMENTO,)
        else:
            modelo = os.environ.get("WHATSAPP_TEMPLATE_LEMBRETE", "").strip()
            pergunta = PERGUNTA_FINANCEIRA if row["estado_conversa"] == "pergunta_financeira" else PERGUNTA_PSICOLOGICA
            parametros = (pergunta,)
        try:
            enviar_template(_telefone_internacional(row["telefone"]), modelo, parametros)
        except Exception:
            continue
        conn = database.get_connection()
        conn.execute("UPDATE checkins SET lembrete_enviado=1 WHERE id=? AND lembrete_enviado=0", (row["id"],))
        conn.commit()
        conn.close()
        enviados += 1
    return enviados


def iniciar_agendador_lembretes():
    """Executa o verificador em segundo plano enquanto o servidor estiver ativo."""
    def ciclo():
        while True:
            try:
                enviar_lembretes_pendentes()
            except Exception as exc:
                print("[RADACHE] Falha ao verificar lembretes WhatsApp: {}".format(exc))
            time.sleep(3600)
    threading.Thread(target=ciclo, name="radache-lembretes-whatsapp", daemon=True).start()



def extrair_mensagens(payload, incluir_ids=False):
    """Valida a estrutura antes de tratar o lote; notificações de status são ignoradas."""
    if not isinstance(payload, dict) or not isinstance(payload.get("entry", []), list):
        raise ValueError("Webhook deve conter um objeto com lista entry.")
    mensagens = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for mensagem in value.get("messages", []):
                    tipo = mensagem.get("type")
                    if tipo == "text":
                        texto = mensagem.get("text", {}).get("body", "")
                    elif tipo == "button":
                        texto = mensagem.get("button", {}).get("text", "")
                    elif tipo == "interactive":
                        interactive = mensagem.get("interactive", {})
                        texto = (interactive.get("button_reply") or interactive.get("list_reply") or {}).get("title", "")
                    else:
                        continue
                    origem = mensagem.get("from", "")
                    if not isinstance(origem, str) or not isinstance(texto, str):
                        raise ValueError("Origem e texto devem ser strings.")
                    dados = (origem, texto, mensagem.get("id")) if incluir_ids else (origem, texto)
                    mensagens.append(dados)
    except (AttributeError, TypeError) as exc:
        raise ValueError("Estrutura de webhook inválida.") from exc
    return mensagens
