"""
========================================================================================
RADACHE — Módulo de Gerenciamento de Alunos
Arquivo: app.py
Camada: Servidor de Aplicação HTTP / Controlador REST (API Gateway do Módulo)
========================================================================================

DECISÕES DE DESIGN E ENGENHARIA DE SOFTWARE:
1. ZERO DEPENDÊNCIAS EXTERNAS (Zero pip install):
   - Construído integralmente com a biblioteca padrão do Python 3 (http.server, urllib, json, hmac).
   - Justificativa: Elimina problemas de ambiente, facilidade máxima de implantação em laboratório
     acadêmico ou servidores institucionais restritos da UNEMAT.
2. SERVIDOR MULTI-THREADING (ThreadingHTTPServer):
   - Cada requisição HTTP é processada concorrentemente em uma thread separada, permitindo
     múltiplos acessos simultâneos sem gargalo de I/O.
3. CONTRATO DE API RESTful & CORS:
   - Endpoints semânticos (/api/alunos, /api/dashboard, /api/session, /api/login, etc.).
   - Suporte completo a CORS para permitir integração com ferramentas externas ou protótipos.
4. SEGURANÇA E HIGIENIZAÇÃO DE ENTRADA:
   - Limite estrito de 1MB para payloads JSON contra ataques de negação de serviço (DoS/Buffer Overflow).
   - Validação de rotas estáticas contra ataques de Path Traversal (resolve().relative_to(root)).
   - Middleware de autorização RBAC e verificação de Bearer token.
"""
import json
import mimetypes
import hmac
import os
import re
import sys
import urllib.parse
from email.utils import formatdate
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Garante que o diretório atual esteja no PYTHONPATH para importação dos módulos irmãos
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))
import database
import rbac
import whatsapp
import mock_mensagens
import gestao_local
import mock_alunos
import simulation_store
import simulation_api
import analytics
import course_catalog
from aluno_service import AlunoService
from auth import SessionManager, carregar_usuarios, projetar_aluno

# Diretórios dos frontends
FRONTEND_DIR = CURRENT_DIR.parent / "frontend"
DEMO_DIR = CURRENT_DIR.parent.parent / "painel-demo" / "public"
ASSETS_DIR = CURRENT_DIR.parent.parent / "assets"
GESTAO_DIR = CURRENT_DIR.parent.parent / "gestao"
PORTAL_DIR = CURRENT_DIR.parent.parent / "portal"
PORT = 8080

# Injeção de dependências: Fachada de alunos e Gerenciador de Sessões
alunos = AlunoService()
auth = SessionManager(carregar_usuarios())


class RadacheRequestHandler(BaseHTTPRequestHandler):
    """
    Controlador HTTP principal: Trata roteamento REST, segurança, CORS e arquivos estáticos.
    """

    def setup(self):
        super().setup()
        # Evita manter uma thread bloqueada indefinidamente por um corpo incompleto.
        self.connection.settimeout(15)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        super().end_headers()

    def _internal_error(self, error):
        # Logs e respostas não incluem payloads, caminhos, tokens ou segredos da exceção.
        self.log_error('Falha interna: %s', type(error).__name__)
        return self._json(500, {'sucesso': False, 'erro': 'Não foi possível concluir a operação. Tente novamente.'})

    def _json(self, status, payload):
        """Helper para envio padronizado de respostas JSON com headers de CORS e UTF-8."""
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if getattr(self,'_cookie',None) is not None:
            self.send_header('Set-Cookie',self._cookie);self._cookie=None
        try:
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Consultas antigas podem ser canceladas ao trocar os filtros.
            self.close_connection = True

    def _body(self):
        """
        Lê e decodifica o corpo JSON da requisição com proteção de buffer limit (máx 1MB).
        Lança ValueError explicativo caso o payload não seja um objeto JSON válido.
        """
        length = int(self.headers.get("Content-Length", "0"))
        if self.headers.get("Transfer-Encoding") or not 0 < length <= 1_000_000:
            self.close_connection = True
            # Descarta apenas os bytes já disponíveis, com limite e prazo curtos.
            # No Windows, fechar com corpo pendente pode abortar o HTTP 400.
            previous_timeout = self.connection.gettimeout()
            try:
                self.connection.settimeout(0.1)
                if length or self.headers.get('Transfer-Encoding'):
                    self.rfile.read1(4096)
            except OSError:
                pass
            finally:
                self.connection.settimeout(previous_timeout)
            raise ValueError("O corpo JSON deve ter entre 1 byte e 1 MB.")
        def constante_invalida(valor):
            raise ValueError("Constante JSON inválida: " + valor)
        data = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=constante_invalida)
        if not isinstance(data, dict):
            raise ValueError("O corpo deve ser um objeto JSON.")
        return data

    def _id(self):
        """Extrai o ID numérico final do caminho REST (ex: /api/alunos/4 -> 4)."""
        try:
            path = urllib.parse.urlparse(self.path).path
            match = re.fullmatch(r"/api/alunos/(-?[1-9][0-9]*)/?", path)
            return int(match.group(1)) if match else None
        except ValueError:
            return None

    def _token(self):
        """Extrai a credencial Bearer do cabeçalho HTTP Authorization."""
        esquema, _, credencial = self.headers.get("Authorization", "").partition(" ")
        header=credencial.strip() if esquema.lower()=='bearer' else ''
        cookies=SimpleCookie()
        try:cookies.load(self.headers.get('Cookie',''))
        except Exception:pass
        cookie=cookies.get('radache_session');cookie=cookie.value if cookie else ''
        # Uma sessão de analista ativa não pode ser contornada por um token antigo na aba.
        for value in (cookie,header):
            session=self._session(value)
            if session and session.get('perfil')==rbac.ANALYST:return value
        if header and self._session(header):return header
        if cookie and self._session(cookie):return cookie
        return header or cookie

    def _session(self,token):
        if not token:return None
        old=auth.obter_sessao(token)
        if old:
            stored=gestao_local.legacy_user(old)
            if stored:
                if not stored['ativo']:return None
                return {**stored,'username':stored['email'],'role':'coordenacao' if stored['perfil'] in rbac.OPERATIONAL else stored['perfil'],
                        'scope':rbac.analytics_scope(stored) if stored['perfil'] in rbac.OPERATIONAL else None}
            profile={'coordenacao':'admin_tecnico'}.get(old['role'],old['role'])
            user={**old,'perfil':profile,'id':old['username']}
            if profile in rbac.OPERATIONAL:user.update(role='coordenacao',scope=rbac.analytics_scope(user))
            return user
        try:
            user=gestao_local.sessao(token)
            return {**user,'username':user['email'],'role':'coordenacao' if user['perfil'] in rbac.OPERATIONAL else user['perfil'],
                    'scope':rbac.analytics_scope(user) if user['perfil'] in rbac.OPERATIONAL else None}
        except gestao_local.ErroLocal:return None

    def _set_session_cookie(self,token=''):
        cookies=SimpleCookie()
        try:cookies.load(self.headers.get('Cookie',''))
        except Exception:pass
        previous=cookies.get('radache_session')
        if previous and previous.value!=token:
            auth.encerrar(previous.value);gestao_local.SESSOES.pop(previous.value,None)
        self._cookie='radache_session='+token+'; Path=/; HttpOnly; SameSite=Strict; Max-Age='+('28800' if token else '0')

    def _guard_data(self):
        path=urllib.parse.urlsplit(self.path).path
        if path in ('/api/login','/api/local/login','/api/v1/login'):return True
        if path.startswith(('/api/','/simulation-api/')):
            if not self._proteger_api():return False
            if path.startswith('/api/institucional/') and self.command!='GET':
                rbac.audit(self.sessao,path,{},405);self._descartar_corpo();self._json(405,{'sucesso':False,'erro':'Indicadores institucionais são somente leitura.'});return False
            return True
        current=self._session(self._token())
        if path.startswith('/mock-api/') and current and current['perfil'] in {rbac.ANALYST,rbac.ATTENDANT}:
            rbac.audit(current,path,{},403);self._descartar_corpo();self._json(403,{'sucesso':False,'erro':'Perfil institucional: somente leitura agregada.'});return False
        return True

    def _descartar_corpo(self):
        """Descarta payloads de operações negadas para manter a conexão HTTP íntegra."""
        if self.command not in ("POST", "PUT", "PATCH"):
            return
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            if 0 <= tamanho <= 1_000_000:

                self.rfile.read(tamanho)
            else:
                self.close_connection = True
        except ValueError:
            self.close_connection = True

    def _proteger_api(self):
        """Valida o token de sessão antes de acessar qualquer endpoint privado."""
        sessao = self._session(self._token())
        if sessao:
            self.sessao = sessao
            path=urllib.parse.urlsplit(self.path).path
            if sessao['perfil']==rbac.ATTENDANT and not (path.startswith(('/api/local/','/api/v1/')) or path in ('/api/session','/api/logout')):
                rbac.audit(sessao,path,{},403);self._descartar_corpo()
                self._json(403,{'sucesso':False,'erro':'Atendente: utilize somente seus atendimentos atribuídos.'});return False
            if sessao['perfil']==rbac.ANALYST and not (path.startswith('/api/institucional/') or path in ('/api/session','/api/logout','/api/local/sessao','/api/local/logout','/api/v1/sessao','/api/v1/logout')):
                rbac.audit(sessao,path,{},403);self._descartar_corpo()
                self._json(403,{'sucesso':False,'erro':'Analista Institucional: somente indicadores agregados.'});return False
            return True
        # Descarta o corpo não autorizado para preservar a resposta HTTP keep-alive.
        if self.command in ("POST", "PUT", "PATCH"):
            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                if 0 <= tamanho <= 1_000_000:
                    self.rfile.read(tamanho)
                else:
                    self.close_connection = True
            except ValueError:
                self.close_connection = True
        self._json(401, {"sucesso": False, "erro": "Acesso negado. Entre no sistema para continuar."})
        return False

    def _exigir_coordenacao(self):
        if self.sessao.get('perfil') in rbac.ADMIN:
            return True
        self._descartar_corpo()
        self._json(403, {"sucesso": False, "erro": "Este perfil tem acesso somente para consulta."})
        return False

    def do_OPTIONS(self):
        self._json(200, {})

    def do_HEAD(self):
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith(('/api/', '/simulation-api/', '/mock-api/', '/webhooks/')) or path == '/healthz':
            return self._json(405, {'sucesso': False, 'erro': 'Use GET para consultar este endpoint.'})
        return self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if not self._guard_data():return
            current=self._session(self._token())
            if current and current['perfil']==rbac.ANALYST and path.rstrip('/') in ('/gestao','/alunos','/mensagens','/painel-demo','/gestao/index.html','/alunos/index.html'):
                self.send_response(302);self.send_header('Location','/institucional/');self.end_headers();return
            if path.startswith('/api/institucional/'):
                import institutional
                return institutional.respond(self)
            if path.startswith("/simulation-api/"):
                return simulation_api.respond(self)
            if path.startswith("/api/mock-alunos"):
                return mock_alunos.responder(self)
            if path == "/healthz":
                return self._json(200, {"servico": "radache-local", "versao": 3, "moduloAlunos": "sqlite-simulacao", "pasta": str(CURRENT_DIR.parent.parent)})
            if path.startswith(("/api/v1/", "/api/local/")):
                return gestao_local.responder(self)
            if path in ("/", "/index.html"):
                return self._static(PORTAL_DIR / "index.html", PORTAL_DIR)
            for prefixo, pasta in (("/gestao", GESTAO_DIR), ("/alunos", FRONTEND_DIR), ("/portal", PORTAL_DIR),('/institucional',GESTAO_DIR.parent/'institucional')):
                if path == prefixo:
                    self.send_response(302)
                    self.send_header("Location", prefixo + "/")
                    self.end_headers()
                    return
                if path.startswith(prefixo + "/"):
                    relative = urllib.parse.unquote(path[len(prefixo) + 1:]) or "index.html"
                    return self._static(pasta / relative, pasta)
            # Verificação pública do webhook configurado no painel da Meta.
            if path == "/webhooks/whatsapp":
                modo = query.get("hub.mode", [""])[0]
                token = query.get("hub.verify_token", [""])[0]
                desafio = query.get("hub.challenge", [""])[0]
                esperado = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
                if modo == "subscribe" and esperado and hmac.compare_digest(token, esperado):
                    body = desafio.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    return self.wfile.write(body)
                return self._json(403, {"sucesso": False, "erro": "Verificação do webhook recusada."})
            if path.startswith("/api/") and not self._proteger_api():
                return
            if path == "/api/session":
                return self._json(200, {"sucesso": True, "usuario": self.sessao})
            if path == '/api/cursos':
                return self._json(200, {'sucesso': True, 'dados': course_catalog.available()})
            if path == '/api/analytics' or path.startswith('/api/analytics/students/'):
                if self.sessao['role'] not in ('coordenacao','nae'):
                    return self._json(403, {'sucesso':False,'erro':'Este painel analítico exige perfil de coordenação ou NAE.'})
                if path == '/api/analytics':
                    data = analytics.overview({k:v[0] for k,v in query.items()},self.sessao['role'],self.sessao.get('scope'))
                else:
                    match = re.fullmatch(r'/api/analytics/students/(-?[1-9][0-9]*)',path)
                    data = analytics.detail(int(match[1]),self.sessao['role'],self.sessao.get('scope')) if match else None
                    if data is None:
                        return self._json(404, {'sucesso':False,'erro':'Aluno não encontrado.'})
                return self._json(200, {'sucesso':True,'dados':data})
            if path == "/api/dashboard":
                k=analytics.overview({},self.sessao['role'],self.sessao.get('scope'))['kpis']
                metricas=dict(total_alunos=k['cadastrados'],alunos_ativos=k['elegiveis'],alunos_criticos=k['alto'],alunos_moderados=k['medio'],alunos_estaveis=k['baixo'])
                if self.sessao["role"] in ("caest", "prae"):
                    metricas = {"total_alunos": metricas["total_alunos"], "alunos_ativos": metricas["alunos_ativos"]}
                return self._json(200, {"sucesso": True, "dados": metricas})
            if path == "/api/alunos":
                filtros = {key: values[0] for key, values in query.items()}
                if "risco" in filtros and self.sessao["role"] not in ("coordenacao", "nae"):
                    return self._json(403, {"sucesso": False, "erro": "Filtro de risco fora do escopo deste perfil."})
                dados = alunos.listar(filtros)
                if self.sessao.get('scope'):dados=[a for a in dados if rbac.student_allowed(self.sessao,a)]
                if self.sessao["role"] not in ("coordenacao", "nae"):
                    dados.sort(key=lambda aluno: aluno["nome"].casefold())
                dados = [projetar_aluno(aluno, self.sessao["role"]) for aluno in dados]
                return self._json(200, {"sucesso": True, "total": len(dados), "dados": dados})
            if path.startswith("/api/alunos/"):
                aluno_id = self._id()
                if aluno_id is None:
                    return self._json(400, {"sucesso": False, "erro": "ID inválido."})
                dado = alunos.obter(aluno_id)
                if dado and self.sessao.get('scope') and not rbac.student_allowed(self.sessao,dado):dado=None
                if dado is None:
                    return self._json(404, {"sucesso": False, "erro": "Aluno não encontrado."})
                return self._json(200, {"sucesso": True, "dados": projetar_aluno(dado, self.sessao["role"])})
            if path.startswith("/api/"):
                return self._json(404, {"sucesso": False, "erro": "Endpoint não encontrado."})
            if path in ("/mensagens", "/mensagens/"):
                if path == "/mensagens":
                    self.send_response(302)
                    self.send_header("Location", "/mensagens/")
                    self.end_headers()
                    return
                return self._static(FRONTEND_DIR / "mensagens" / "index.html", FRONTEND_DIR)
            if path == "/painel-demo":
                self.send_response(302)
                self.send_header("Location", "/painel-demo/")
                self.end_headers()
                return
            if path.startswith("/assets/"):
                relative = urllib.parse.unquote(path[len("/assets/"):])
                return self._static(ASSETS_DIR / relative, ASSETS_DIR)
            if path == "/painel-demo" or path.startswith("/painel-demo/"):
                relative = path[len("/painel-demo/"):] if path.startswith("/painel-demo/") else ""
                return self._static(DEMO_DIR / (relative or "index.html"), DEMO_DIR)
            relative = path.lstrip("/") or "index.html"
            return self._static(FRONTEND_DIR / relative, FRONTEND_DIR)
        except ValueError as exc:
            return self._json(400, {"sucesso": False, "erro": str(exc)})
        except Exception as exc:
            return self._internal_error(exc)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._guard_data():return
        if path.startswith('/api/institucional/'):
            import institutional
            return institutional.respond(self)
        if path.startswith("/simulation-api/"):
            return simulation_api.respond(self)
        if path.startswith("/api/mock-alunos"):
            return mock_alunos.responder(self)
        if path == "/api/alunos":
            return self._bloquear_escrita_academica()
        if path.startswith(("/api/v1/", "/api/local/")):
            return gestao_local.responder(self)
        # Mock público e sem persistência, isolado dos endpoints privados /api/.
        if path == mock_mensagens.ENDPOINT:
            return mock_mensagens.responder(self)
        if path == "/webhooks/whatsapp":
            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                if tamanho <= 0 or tamanho > 1_000_000:
                    return self._json(400, {"sucesso": False, "erro": "Tamanho de webhook inválido."})
                corpo = self.rfile.read(tamanho)
                assinatura = self.headers.get("X-Hub-Signature-256", "")
                segredo = os.environ.get("WHATSAPP_APP_SECRET", "")
                if not whatsapp.validar_assinatura(corpo, assinatura, segredo):
                    return self._json(401, {"sucesso": False, "erro": "Assinatura do webhook inválida."})
                payload = json.loads(corpo.decode("utf-8"))
                for origem, texto, mensagem_id in whatsapp.extrair_mensagens(payload, incluir_ids=True):
                    if mensagem_id:
                        whatsapp.processar_mensagem(origem, texto, mensagem_id)
                    else:
                        whatsapp.processar_mensagem(origem, texto)
                return self._json(200, {"sucesso": True})
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                return self._json(400, {"sucesso": False, "erro": str(exc) or "Webhook inválido."})
            except Exception as exc:
                return self._internal_error(exc)
        if path == "/api/login":
            try:
                dados = self._body()
                sessao = auth.autenticar(dados.get("usuario"), dados.get("senha"))
                if sessao:
                    context=self._session(sessao['token'])
                    if context:sessao.update(role=context['perfil'])
                    else:sessao=None
                if not sessao:
                    name=str(dados.get('usuario',''))
                    try:
                        result=gestao_local.tratar('POST','login',{},dict(email=name if '@' in name else name+'@radache.local',senha=dados.get('senha')),'')
                        s=self._session(result['token']);sessao=dict(token=result['token'],username=s['username'],role=s['perfil'],expires_at=int(__import__('time').time())+28800)
                    except Exception:pass
                if not sessao:
                    return self._json(401 if auth.usuarios else 503, {"sucesso": False, "erro": "Usuário ou senha inválidos."})
                self._set_session_cookie(sessao['token'])
                return self._json(200, {"sucesso": True, "token": sessao["token"], "usuario": {
                    "username": sessao["username"], "role": sessao["role"], "expires_at": sessao["expires_at"]
                }})
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                return self._json(400, {"sucesso": False, "erro": str(exc) or "JSON inválido."})
        if path == "/api/logout":
            if not self._proteger_api():
                return
            auth.encerrar(self._token())
            gestao_local.SESSOES.pop(self._token(),None);self._set_session_cookie()
            return self._json(200, {"sucesso": True, "mensagem": "Sessão encerrada."})
        if path.startswith("/api/") and not self._proteger_api():
            return
        if path == "/api/checkins/enviar":
            if not self._exigir_coordenacao():
                return
            try:
                whatsapp._configuracao()
                if not os.environ.get("WHATSAPP_TEMPLATE_CONSENTIMENTO", "").strip():
                    raise RuntimeError("Configure WHATSAPP_TEMPLATE_CONSENTIMENTO com o modelo aprovado.")
            except RuntimeError as exc:
                return self._json(503, {"sucesso": False, "erro": str(exc)})
            conn = database.get_connection()
            ids = [row["id"] for row in conn.execute(
                """SELECT id FROM alunos WHERE status='ativo' AND status_exclusao=0
                   AND NOT EXISTS (SELECT 1 FROM checkins c WHERE c.aluno_id=alunos.id
                     AND (date(c.data_checkin,'start of month')=date('now','start of month')
                       OR c.estado_conversa IN ('aguardando_consentimento','pergunta_financeira','pergunta_psicologica')))"""
            ).fetchall()]
            conn.close()
            enviados, falhas = 0, []
            for aluno_id in ids:
                try:
                    whatsapp.iniciar_checkin(aluno_id)
                    enviados += 1
                except Exception as exc:
                    falhas.append({"aluno_id": aluno_id, "erro": str(exc)})
            return self._json(200 if not falhas else 502, {"sucesso": not falhas, "enviados": enviados, "falhas": falhas})
        if path == "/api/alunos" and not self._exigir_coordenacao():
            return
        if path != "/api/alunos":
            return self._json(404, {"sucesso": False, "erro": "Endpoint não encontrado."})
        try:
            aluno_id = alunos.cadastrar(self._body())
            return self._json(201, {"sucesso": True, "mensagem": "Aluno cadastrado com sucesso.", "aluno_id": aluno_id})
        except ValueError as exc:
            return self._json(409 if "matrícula" in str(exc).lower() else 400, {"sucesso": False, "erro": str(exc)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, {"sucesso": False, "erro": "JSON inválido."})
        except Exception as exc:
            return self._json(400, {"sucesso": False, "erro": str(exc)})

    def _bloquear_escrita_academica(self):
        if not self._proteger_api(): return
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/api/alunos/') and self._id() is None:
            self._descartar_corpo()
            return self._json(404, {'sucesso': False, 'erro': 'Endpoint não encontrado.'})
        if not self._exigir_coordenacao(): return
        self._descartar_corpo()
        return self._json(405, {"sucesso": False, "erro": "Dados acadêmicos são somente leitura. Use o sandbox isolado para incluir ou excluir dados fictícios."})

    def do_PATCH(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._guard_data():return
        if path.startswith("/simulation-api/"):
            return simulation_api.respond(self)
        if path.startswith("/api/mock-alunos"):
            return mock_alunos.responder(self)
        if path == "/api/alunos" or path.startswith("/api/alunos/"):
            return self._bloquear_escrita_academica()
        if path.startswith(("/api/v1/", "/api/local/")):
            return gestao_local.responder(self)
        return self._json(404, {"sucesso": False, "erro": "Endpoint não encontrado."})

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._guard_data():return
        if path.startswith("/simulation-api/"):
            return simulation_api.respond(self)
        if path.startswith("/api/mock-alunos"):
            return mock_alunos.responder(self)
        return self._bloquear_escrita_academica()

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if not self._guard_data():return
        if path.startswith("/simulation-api/"):
            return simulation_api.respond(self)
        if path.startswith("/api/mock-alunos"):
            return mock_alunos.responder(self)
        if path == "/api/alunos" or path.startswith("/api/alunos/"):
            return self._bloquear_escrita_academica()
        if not self._proteger_api():
            return
        if not self._exigir_coordenacao():
            return
        parsed = urllib.parse.urlparse(self.path)
        aluno_id = self._id()
        if not parsed.path.startswith("/api/alunos/") or aluno_id is None:
            return self._json(404, {"sucesso": False, "erro": "Endpoint ou ID inválido."})
        modo = urllib.parse.parse_qs(parsed.query).get("modo", ["logica"])[0]
        try:
            if not alunos.excluir(aluno_id, modo):
                return self._json(404, {"sucesso": False, "erro": "Aluno não encontrado."})
            mensagem = "Aluno inativado." if modo == "logica" else "Aluno removido definitivamente."
            return self._json(200, {"sucesso": True, "mensagem": mensagem, "modo": modo})
        except ValueError as exc:
            return self._json(400, {"sucesso": False, "erro": str(exc)})

    def _static(self, target, root):
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError:
            return self._json(403, {"sucesso": False, "erro": "Caminho inválido."})
        if not target.is_file():
            return self._json(404, {"sucesso": False, "erro": "Arquivo não encontrado."})
        stat = target.stat()
        etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        validators = self.headers.get('If-None-Match', '')
        unchanged = any(value.strip() == '*' or value.strip().removeprefix('W/') == etag.removeprefix('W/') for value in validators.split(','))
        self.send_response(304 if unchanged else 200)
        # Revalida a cada uso: alterações locais aparecem imediatamente sem versionar URLs.
        self.send_header('Cache-Control', 'private, no-cache')
        self.send_header('ETag', etag)
        self.send_header('Last-Modified', formatdate(stat.st_mtime, usegmt=True))
        if unchanged:
            self.end_headers()
            return
        self.send_header("Content-Type", (mimetypes.guess_type(str(target))[0] or "application/octet-stream") + ("; charset=utf-8" if target.suffix in (".html", ".js", ".css") else ""))
        self.send_header("Content-Length", str(stat.st_size))
        self.end_headers()
        if self.command != 'HEAD':
            try:
                with target.open('rb') as source:
                    import shutil
                    shutil.copyfileobj(source, self.wfile)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True

    def log_message(self, fmt, *args):
        if any(code in str(args) for code in (" 400 ", " 409 ", " 500 ")):
            super().log_message(fmt, *args)


def run_server(port=PORT, open_browser=False, start_page="/", start_pages=None):
    simulation_store.init()
    database.init_db()
    gestao_local.iniciar()
    # A versão local usa somente o simulador; não agenda envios reais.
    server = ThreadingHTTPServer((os.environ.get("RADACHE_HOST", "127.0.0.1"), port), RadacheRequestHandler)
    print("RADACHE disponível em http://localhost:{}".format(port))
    if open_browser:
        import webbrowser
        for page in start_pages or (start_page,):
            webbrowser.open("http://localhost:{}{}".format(port, page), new=2)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else PORT)
