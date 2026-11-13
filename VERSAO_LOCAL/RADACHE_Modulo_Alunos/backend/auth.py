"""
========================================================================================
RADACHE — Módulo de Gerenciamento de Alunos
Arquivo: auth.py
Camada: Segurança, Autenticação e Controle de Acesso (RBAC & LGPD)
========================================================================================

PILARE DE SEGURANÇA E CONFORMIDADE:
1. ARMAZENAMENTO SEGURO DE SENHAS (PBKDF2-HMAC-SHA256):
   - O sistema NUNCA armazena senhas em texto puro.
   - Utiliza PBKDF2 com 310.000 iterações (recomendação OWASP) e 'salts' aleatórios
     de 16 bytes (32 caracteres hexadecimais) gerados com secrets.token_hex(16).
   - Inviabiliza ataques por Rainbow Tables (tabelas de pré-computação) e força bruta.

2. PREVENÇÃO DE ATAQUES DE TEMPORIZAÇÃO (Timing Attacks):
   - A validação de hashes utiliza hmac.compare_digest(), garantindo comparação em
     tempo constante (O(1)), evitando que um atacante deduza caracteres pelo tempo de resposta.

3. CONTROLE DE ACESSO BASEADO EM PAPÉIS (RBAC) & MENOR PRIVILÉGIO (LGPD Art. 6º, III):
   - Cada perfil de usuário institucional tem uma visão estritamente filtrada dos dados:
     * coordenacao : Acesso irrestrito (CRUD de alunos, envio de check-ins, métricas completas).
     * nae         : Foco no suporte psicossocial. Vê dados cadastrais + risco + estado psicológico.
     * caest       : Foco na permanência acadêmica. Vê dados cadastrais + média + frequência.
     * prae        : Foco no suporte socioeconômico. Vê dados cadastrais + situação financeira.
   - A função projetar_aluno() higieniza a resposta JSON antes de trafegar na rede!

4. GERENCIAMENTO DE SESSÕES (Bearer Tokens):
   - Tokens aleatórios de 32 bytes criptograficamente seguros (secrets.token_urlsafe(32)).
   - Sessões voláteis com TTL de 8 horas guardadas na memória do servidor.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

# Parâmetros de Criptografia conforme recomendações de segurança da OWASP
ITERACOES_PBKDF2 = 310_000

# Perfis válidos no domínio da UNEMAT
PERFIS = {"coordenacao", "nae", "caest", "prae",'admin_tecnico','analista_institucional','diretor_campus','gestor_curso'}

# Campos cadastrais mínimos permitidos a todos os perfis autenticados
CAMPOS_COMUNS = {"id", "nome", "matricula", "curso", "campus", "periodo", "status"}

# Matriz RBAC: Campos sensíveis permitidos por perfil (Minimização de Dados - LGPD)
CAMPOS_POR_PERFIL = {
    "nae": CAMPOS_COMUNS | {"indice_risco", "classificacao_risco", "situacao_psicologica"},
    "caest": CAMPOS_COMUNS | {"nota_media", "frequencia"},
    "prae": CAMPOS_COMUNS | {"situacao_financeira"},
}


def projetar_aluno(aluno, perfil):
    """
    Higieniza o dicionário do aluno, removendo atributos confidenciais fora do escopo do perfil.
    
    Exemplo de Proteção LGPD:
    - Um técnico do PRAE não tem acesso aos dados psicológicos coletados pelo WhatsApp.
    - Um assistente do CAEst não vê os dados de vulnerabilidade financeira.
    """
    if perfil == "coordenacao":
        return aluno
    permitidos = CAMPOS_POR_PERFIL.get(perfil)
    if not permitidos:
        raise ValueError("Perfil sem política de acesso configurada.")
    
    # Filtra as chaves de primeiro nível
    resultado = {campo: valor for campo, valor in aluno.items() if campo in permitidos}
    
    # Se houver nó de avaliação aninhado, projeta apenas os campos autorizados
    if "avaliacao_atual" in aluno:
        campos_avaliacao = permitidos - CAMPOS_COMUNS - {"situacao"}
        avaliacao = aluno["avaliacao_atual"]
        resultado["avaliacao_atual"] = (
            {campo: valor for campo, valor in avaliacao.items() if campo in campos_avaliacao}
            if avaliacao else None
        )
    return resultado


def gerar_hash_senha(senha, salt=None):
    """
    Gera um par salt (aleatório) e hash PBKDF2-SHA256 para configuração de usuários em RADACHE_USERS.
    Exige tamanho mínimo de 8 caracteres.
    """
    if not isinstance(senha, str) or len(senha) < 8:
        raise ValueError("A senha deve ter ao menos 8 caracteres.")
    salt = salt or secrets.token_hex(16)
    try:
        salt_bytes = bytes.fromhex(salt)
    except ValueError as erro:
        raise ValueError("O salt deve ser hexadecimal.") from erro
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt_bytes, ITERACOES_PBKDF2)
    return {"salt": salt, "password_hash": derivado.hex()}


def carregar_usuarios(configuracao=None):
    """
    Carrega o mapa de credenciais seguras a partir do JSON da variável de ambiente RADACHE_USERS.
    Rejeita terminantemente senhas em texto puro por diretriz de segurança.
    """
    configuracao = configuracao if configuracao is not None else os.getenv("RADACHE_USERS", "{}")
    try:
        usuarios = json.loads(configuracao) if isinstance(configuracao, str) else dict(configuracao)
    except (ValueError, TypeError) as erro:
        raise ValueError("RADACHE_USERS deve conter um objeto JSON válido.") from erro
    if not isinstance(usuarios, dict):
        raise ValueError("RADACHE_USERS deve mapear nomes de usuário para credenciais.")
    for nome, usuario in usuarios.items():
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError("O nome de usuário deve ser texto não vazio.")
        if not isinstance(usuario, dict) or not usuario.get("salt") or not usuario.get("password_hash"):
            raise ValueError("Cada usuário precisa ter salt e password_hash PBKDF2.")
        if "password" in usuario:
            raise ValueError("Senhas em texto puro não são aceitas em RADACHE_USERS.")
        if usuario.get("role") not in PERFIS:
            raise ValueError("Perfil inválido para o usuário {}.".format(nome))
        try:
            if len(bytes.fromhex(usuario["salt"])) < 16 or len(bytes.fromhex(usuario["password_hash"])) != 32:
                raise ValueError()
        except (ValueError, TypeError) as erro:
            raise ValueError("Salt e password_hash devem estar em hexadecimal.") from erro
    return usuarios


class SessionManager:
    """
    Gerenciador thread-safe de sessões de usuário na memória do processo.
    Controla emissão de tokens Bearer, verificação de expiração e logout.
    """

    def __init__(self, usuarios=None, ttl_seconds=8 * 60 * 60):
        # Usuários com credenciais hash carregadas
        self.usuarios = carregar_usuarios(usuarios or {})
        # Tempo de vida padrão: 8 horas (duração do expediente)
        self.ttl_seconds = int(ttl_seconds)
        self._sessoes = {}
        # Lock reentrante para acesso concorrente seguro
        self._lock = threading.RLock()

    def autenticar(self, nome, senha):
        """
        Valida as credenciais submetidas no login.
        Se válidas, cria um token Bearer único com expiração e perfil associado.
        """
        if not isinstance(nome, str) or not isinstance(senha, str):
            return None
        usuario = self.usuarios.get(nome)
        if not usuario:
            return None
        
        # Deriva o hash da senha fornecida com o salt armazenado
        derivado = hashlib.pbkdf2_hmac(
            "sha256", senha.encode("utf-8"), bytes.fromhex(usuario["salt"]), ITERACOES_PBKDF2
        ).hex()
        
        # Comparação em tempo constante para mitigar timing attacks
        if not hmac.compare_digest(derivado, usuario["password_hash"]):
            return None
        
        # Emite um novo token opaco de alta entropia
        token = secrets.token_urlsafe(32)
        expiracao = int(time.time()) + self.ttl_seconds
        sessao = {"username": nome, "role": usuario["role"], "expires_at": expiracao}
        for key in ('campusId','cursoId','cursoIds'):
            if key in usuario:sessao[key]=usuario[key]
        
        with self._lock:
            now = int(time.time())
            for expired in [key for key, value in self._sessoes.items() if value['expires_at'] <= now]:
                self._sessoes.pop(expired, None)
            self._sessoes[token] = sessao
            
        return {"token": token, **sessao}

    def obter_sessao(self, token):
        """
        Recupera os dados da sessão vinculada ao token, verificando se ainda está dentro do TTL.
        """
        if not token:
            return None
        with self._lock:
            sessao = self._sessoes.get(token)
            if not sessao:
                return None
            if sessao["expires_at"] <= int(time.time()):
                # Remove sessão expirada da memória
                self._sessoes.pop(token, None)
                return None
            return dict(sessao)

    def encerrar(self, token):
        """Invalida o token imediatamente (logout explícito)."""
        with self._lock:
            return self._sessoes.pop(token, None) is not None

