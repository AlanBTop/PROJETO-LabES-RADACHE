"""Mock HTTP do protótipo. Valida e ecoa mensagens, sem banco ou provedor externo."""
from datetime import datetime, timedelta
import json
from uuid import UUID, uuid4

ENDPOINT = "/mock-api/mensagens"
LIMITE_CORPO = 32768
CAMPOS = {"id_cliente", "conteudo_texto", "id_remetente", "id_destinatario", "timestamp"}


def aceitar_mensagem(payload):
    """Valida o contrato relacional e retorna confirmação explicitamente não persistida.

    Este mock não consulta alunos nem mantém histórico. O endpoint de produção deve
    autenticar o remetente, validar FKs e fazer INSERT parametrizado em transação,
    com UNIQUE(id_cliente) para evitar duplicação quando o cliente tentar novamente.
    """
    if not isinstance(payload, dict) or set(payload) != CAMPOS:
        raise ValueError("Envie exatamente: " + ", ".join(sorted(CAMPOS)) + ".")
    texto = payload["conteudo_texto"]
    if not isinstance(texto, str) or not texto.strip() or len(texto) > 4000:
        raise ValueError("conteudo_texto deve conter de 1 a 4000 caracteres.")
    for campo in ("id_remetente", "id_destinatario"):
        if type(payload[campo]) is not int or not 0 < payload[campo] <= 9007199254740991:
            raise ValueError(campo + " deve ser um inteiro positivo seguro.")
    try:
        if not isinstance(payload["id_cliente"], str):
            raise ValueError()
        UUID(payload["id_cliente"])
    except (ValueError, AttributeError):
        raise ValueError("id_cliente deve ser um UUID válido.") from None
    try:
        instante = payload["timestamp"]
        if not isinstance(instante, str) or len(instante) > 64:
            raise ValueError()
        data = datetime.fromisoformat(instante.replace("Z", "+00:00"))
        if data.utcoffset() != timedelta(0):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("timestamp deve ser ISO 8601 em UTC (ex.: 2026-10-26T14:30:00.000Z).") from None
    return {
        "sucesso": True,
        "modo": "mock",
        "persistido": False,
        "dados": {**payload, "id_mensagem": str(uuid4())},
    }


def responder(handler):
    """Adaptador compartilhado entre o servidor RADACHE e o inicializador isolado."""
    def json_response(status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.end_headers()
        handler.wfile.write(body)

    # Fechar a conexão evita reutilizar bytes de um corpo recusado ou malformado.
    handler.close_connection = True
    try:
        if handler.headers.get("Transfer-Encoding"):
            return json_response(400, {"sucesso": False, "erro": "Envie JSON com Content-Length."})
        length = int(handler.headers.get("Content-Length", "0"))
        if length > LIMITE_CORPO:
            # Evita TCP reset no Windows antes de o cliente receber o HTTP 413.
            if length <= 1_000_000:
                handler.connection.settimeout(2)
                try:
                    handler.rfile.read(length)
                except OSError:
                    pass
            return json_response(413, {"sucesso": False, "erro": "Corpo maior que 32 KiB."})
        if length <= 0:
            raise ValueError("Envie um corpo JSON não vazio.")
        if handler.headers.get_content_type() != "application/json":
            # Consome apenas o corpo já limitado a 32 KiB, com prazo finito.
            # Fechar com bytes pendentes pode abortar a resposta 415 no Windows.
            handler.connection.settimeout(2)
            try:
                handler.rfile.read(length)
            except OSError:
                pass
            return json_response(415, {"sucesso": False, "erro": "Use Content-Type: application/json."})
        payload = json.loads(handler.rfile.read(length).decode("utf-8"))
        resposta = aceitar_mensagem(payload)
    except (ValueError, UnicodeDecodeError) as erro:
        return json_response(400, {"sucesso": False, "erro": str(erro) or "JSON inválido."})
    return json_response(201, resposta)
