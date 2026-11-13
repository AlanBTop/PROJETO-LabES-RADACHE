"""Gestão por curso independente: biblioteca padrão, sessões em memória e SQLite local."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import secrets
import re
import threading
import time
import unicodedata
import sqlite3
from urllib.parse import urlparse, parse_qs, unquote
from uuid import uuid4

import database
import rbac
import institution_accounts
import course_catalog
import simulation_store
import simulation_followup
import attendance
import staff
from aluno_service import AlunoService
from auth import gerar_hash_senha, ITERACOES_PBKDF2

LOCK = threading.RLock()
SESSOES = {}
TRANSICOES = attendance.TRANSITIONS
CATEGORIAS = {'academico', 'financeiro', 'ti', 'outro'}
EQUIPE = rbac.OPERATIONAL | {rbac.ATTENDANT}
SERVICO = AlunoService()


def agora():
    return datetime.now(timezone.utc).isoformat()


def curso_id(nome):
    return course_catalog.course_id(nome)


def cursos():
    return course_catalog.available()


def iniciar():
    with LOCK, closing(database.get_connection()) as conn, conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS gestao_usuarios (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, dados TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS gestao_chamados (id TEXT PRIMARY KEY, aluno_id INTEGER REFERENCES alunos(id) ON DELETE CASCADE, dados TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS gestao_eventos (id TEXT PRIMARY KEY, chamado_id TEXT REFERENCES gestao_chamados(id) ON DELETE CASCADE, dados TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS gestao_acoes (id TEXT PRIMARY KEY, chamado_id TEXT NOT NULL, assinatura TEXT NOT NULL, resultado TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS gestao_meta (chave TEXT PRIMARY KEY);
        ''')
        attendance.initialize(conn)
        if conn.execute("SELECT 1 FROM gestao_meta WHERE chave='inicializado'").fetchone():
            institution_accounts.initialize(conn)
            staff.initialize(conn)
            return
        cred = gerar_hash_senha('admin123')
        for uid, nome, perfil in [('admin', 'Administração local', 'admin_geral'),
                                  ('coord', 'Coordenação local', 'coordenador_curso'),
                                  ('equipe', 'Equipe local', 'funcionario_curso'),
                                  ('caest', 'CAEst local', 'caest'), ('prae', 'PRAE local', 'prae')]:
            dados = {'id': uid, 'nome': nome, 'email': uid + '@radache.local', 'perfil': perfil,
                     'cursoId': 'ciencia-da-computacao' if perfil in {'coordenador_curso', 'funcionario_curso'} else '',
                     'ativo': True, 'versaoAcesso': 1, 'criadoEm': agora()}
            conn.execute('INSERT INTO gestao_usuarios VALUES (?,?,?,?,?)',
                         (uid, dados['email'], json.dumps(dados), cred['salt'], cred['password_hash']))
        estudantes = conn.execute('SELECT id, curso FROM alunos WHERE status_exclusao=0 ORDER BY id LIMIT 4').fetchall()
        for i, aluno in enumerate(estudantes):
            uid = 'exemplo-' + str(i + 1)
            data = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            item = {'id': uid, 'alunoId': str(aluno['id']), 'cursoId': curso_id(aluno['curso']),
                    'protocolo': 'LOCAL-' + str(i + 1).zfill(4),
                    'titulo': ['Exemplo local: acompanhamento acadêmico', 'Exemplo local: apoio financeiro',
                               'Exemplo local: acesso ao portal', 'Exemplo local: atendimento concluído'][i],
                    'descricao': 'Atendimento fictício para explorar a gestão local. Os registros ficam apenas neste SQLite.',
                    'status': ['aberto','em_andamento','aguardando_aluno','resolvido'][i], 'categoria': list(('academico', 'financeiro', 'ti', 'outro'))[i],
                    'responsavel': None, 'abertoEm': data, 'ultimaAtividadeEm': data,
                    'tempoResolucaoMin': 60 if i == 3 else None,
                    'resolvidoEm': data if i == 3 else None, 'encerradoPor': 'equipe' if i == 3 else None}
            conn.execute('INSERT INTO gestao_chamados VALUES (?,?,?)', (uid, aluno['id'], json.dumps(item)))
            evento(conn, uid, {'tipo': 'abertura', 'texto': 'Exemplo criado para navegação local.',
                              'criadoEm': data, 'autor': {'nome': 'RADACHE local'}, 'visivelAoAluno': True})
        conn.execute("INSERT INTO gestao_meta VALUES ('inicializado')")
        institution_accounts.initialize(conn)
        staff.initialize(conn)


def evento(conn, chamado, dados):
    dados = {'id': uuid4().hex, **dados}
    conn.execute('INSERT INTO gestao_eventos VALUES (?,?,?)', (dados['id'], chamado, json.dumps(dados)))


class ErroLocal(Exception):
    def __init__(self, status, mensagem):
        self.status, self.mensagem = status, mensagem


def exigir(condicao, mensagem='Acesso fora do escopo deste perfil.', status=403):
    if not condicao:
        raise ErroLocal(status, mensagem)


def usuario_publico(row):
    return json.loads(row['dados'])


def legacy_user(legacy):
    email=legacy['username'] if '@' in legacy['username'] else legacy['username']+'@radache.local'
    try:
        with closing(database.get_connection()) as c:
            row=c.execute('SELECT dados FROM gestao_usuarios WHERE lower(email)=?',(email.lower(),)).fetchone()
            if not row and legacy['role']=='coordenacao':row=c.execute("SELECT dados FROM gestao_usuarios WHERE id='admin'").fetchone()
        return json.loads(row[0]) if row else None
    except sqlite3.OperationalError:return None


def sessao(token):
    with LOCK:
        dados = SESSOES.get(token)
        if dados and dados['expira'] <= time.time():
            SESSOES.pop(token, None)
            raise ErroLocal(401, 'Entre novamente para continuar.')
        if not dados:
            import app
            legacy=app.auth.obter_sessao(token)
            if legacy:
                user=legacy_user(legacy)
                if user and user['ativo']:return {**user,'uid':user['id']}
        exigir(dados and dados['expira'] > time.time(), 'Entre novamente para continuar.', 401)
        with closing(database.get_connection()) as conn:
            row = conn.execute('SELECT * FROM gestao_usuarios WHERE id=?', (dados['uid'],)).fetchone()
        exigir(row, 'Sessão encerrada.', 401)
        usuario = usuario_publico(row)
        exigir(usuario['ativo'] and usuario['versaoAcesso'] == dados['versao'], 'Seu acesso mudou. Entre novamente.', 401)
        return {**usuario, 'uid': usuario['id']}


def escopo(usuario, curso, campus=None):
    return rbac.allowed(usuario,curso,campus)


def campos_acesso(body):
    profile={'coordenador_curso':'gestor_curso','funcionario_curso':'gestor_curso'}.get(body.get('perfil'),body.get('perfil'))
    exigir(profile in rbac.PROFILES,'Perfil inválido.',400)
    campus=body.get('campusId','caceres')
    courses=body.get('cursoIds') or ([body['cursoId']] if body.get('cursoId') else [])
    exigir(isinstance(courses,list) and all(isinstance(c,str) for c in courses),'Cursos inválidos.',400)
    if profile in rbac.ADMIN or profile==rbac.ANALYST:campus='';courses=[]
    else:exigir(campus in rbac.CAMPI,'Selecione um câmpus válido.',400)
    if profile=='diretor_campus':courses=[]
    if profile in {'gestor_curso',rbac.ATTENDANT}:exigir(courses and set(courses)<={c['id'] for c in cursos()},'Selecione os cursos atribuídos.',400)
    return dict(perfil=profile,campusId=campus,cursoIds=list(dict.fromkeys(courses)),cursoId=courses[0] if courses else '')


def pagina(itens, query):
    try:
        inicio = int(query.get('depois', '0'))
        limite = int(query.get('limite', '30'))
        exigir(inicio >= 0 and 1 <= limite <= 100, 'Paginação inválida.', 400)
    except ValueError:
        raise ErroLocal(400, 'Paginação inválida.') from None
    fim = inicio + limite
    return {'itens': itens[inicio:fim], 'proximaPagina': str(fim) if fim < len(itens) else None}


def risco_atendimentos(itens, historico=False):
    """Risco atual lido da fonte; nunca salvo em chamados ou no cache de ações."""
    if not itens:
        return []
    import analytics
    import risk_history
    students = {str(a['id']): a for a in analytics.source()}
    result = []
    histories = {}
    for item in itens:
        student = students.get(str(item.get('alunoId')))
        risk = {'nivel': 'sem_avaliacao', 'indice': None, 'dataAvaliacao': None}
        if student:
            current = analytics.prepare(student, analytics.filters({}))
            assessment = current['avaliacao'] or {}
            risk = dict(nivel=current['risco'], indice=assessment.get('indice_risco'),
                        dataAvaliacao=assessment.get('data_avaliacao'))
        if student and student['id'] not in histories:
            histories[student['id']]=risk_history.describe(student['avaliacoes'])
        evolution=histories.get(student['id']) if student else risk_history.describe([])
        if not historico:evolution={k:v for k,v in evolution.items() if k not in {'avaliacoes','pontos'}}
        result.append({**item, **({'alunoNome': student['nome'], 'matricula': student['matricula']} if student else {}),
                       'evolucaoRisco': evolution,
                       'riscoAcademico': risk,
                       'whatsappSimuladoUrl': '/mensagens/?aluno='+str(-student['id']) if student and student['status']=='ativo' else None})
    return result


def aluno_publico(aluno):
    return {**{k: aluno[k] for k in ('nome', 'matricula', 'campus', 'periodo', 'email', 'telefone', 'status')},
            'id': str(aluno['id']), 'cursoId': curso_id(aluno['curso']), 'criadoEm': aluno['data_cadastro'],
            'avaliacaoAtual': aluno.get('avaliacao_atual')}


def tratar(method, caminho, query, body, token):
    if caminho == 'login' and method == 'POST':
        with closing(database.get_connection()) as conn:
            row = conn.execute('SELECT * FROM gestao_usuarios WHERE lower(email)=? OR lower(json_extract(dados,\'$.login\'))=?', (str(body.get('login',body.get('email', ''))).strip().casefold(),)*2).fetchone()
        exigir(row, 'E-mail ou senha inválidos.', 401)
        derivado = hashlib.pbkdf2_hmac('sha256', str(body.get('senha', '')).encode(), bytes.fromhex(row['salt']), ITERACOES_PBKDF2).hex()
        usuario = usuario_publico(row)
        exigir(hmac.compare_digest(derivado, row['password_hash']) and usuario['ativo'], 'E-mail ou senha inválidos.', 401)
        token = secrets.token_urlsafe(32)
        with LOCK:
            now = time.time()
            for expired in [key for key, value in SESSOES.items() if value['expira'] <= now]:
                SESSOES.pop(expired, None)
            SESSOES[token] = {'uid': usuario['id'], 'versao': usuario['versaoAcesso'], 'expira': time.time() + 28800}
        return {'token': token, 'usuario': {**usuario, 'uid': usuario['id']}}
    usuario = sessao(token)
    if caminho == 'logout' and method == 'POST':
        with LOCK:
            SESSOES.pop(token, None)
        return {}
    if caminho == 'sessao' and method == 'GET':
        return usuario
    if caminho == 'sessao/acesso' and method == 'POST':
        with LOCK, closing(database.get_connection()) as conn, conn:
            usuario = sessao(token)
            usuario['ultimoAcessoEm'] = agora()
            conn.execute('UPDATE gestao_usuarios SET dados=? WHERE id=?', (json.dumps(usuario), usuario['id']))
        return usuario
    exigir(usuario['perfil'] in EQUIPE)
    if caminho.split('/')[0] in {'usuarios','responsaveis','funcionarios','transferencias'}:
        return staff.handle(method,caminho,query,body,usuario)
    if caminho=='cursos' and method=='GET' and query.get('campusId'):
        campus=query['campusId']
        exigir(usuario['perfil'] in rbac.ADMIN|{'diretor_campus'} or campus==usuario.get('campusId'))
        with LOCK,closing(database.get_connection()) as conn,conn:
            items=staff.catalog(conn,campus)
        if usuario['perfil'] not in rbac.ADMIN|{'diretor_campus'}:items=[c for c in items if c['id'] in staff.user_courses(usuario)]
        return pagina(items,query)
    exigir(usuario['perfil']!='diretor_campus' or method=='GET','Direção do câmpus: acesso de consulta.',403)
    gestor = usuario['perfil'] in rbac.MANAGERS
    admin = usuario['perfil'] in rbac.ADMIN
    segmentos = caminho.split('/')
    exigir(bool(re.fullmatch(r'(?:cursos|responsaveis|indicadores|usuarios(?:/[^/]+(?:/convite)?)?|alunos(?:/[^/]+)?|atendimentos(?:/[^/]+(?:/(?:historico|comentarios|status|classificacao|responsavel))?)?)', caminho)), 'Endpoint não encontrado.', 404)
    recurso, ident = segmentos[0], segmentos[1] if len(segmentos) > 1 else None
    curso_filtro = query.get('cursoId', '')
    campus_filtro=query.get('campusId','')
    if campus_filtro:exigir(campus_filtro in rbac.CAMPI and (admin or campus_filtro==usuario.get('campusId')))
    if curso_filtro:
        exigir(escopo(usuario, curso_filtro))
    if recurso == 'cursos' and method == 'GET':
        return pagina([c for c in cursos() if escopo(usuario, c['id'])], query)
    if recurso == 'alunos':
        exigir(method == 'GET', 'Dados acadêmicos são somente leitura. Use o sandbox isolado para dados fictícios.', 405)
        if not ident and method == 'GET':
            itens = [aluno_publico(a) for a in SERVICO.listar() if attendance.student_access(usuario,a) and (not campus_filtro or rbac.campus_id(a.get('campus'))==campus_filtro) and (not curso_filtro or curso_id(a['curso']) == curso_filtro)]
            return pagina(itens, query)
        if ident:
            exigir(bool(re.fullmatch(r'-?[1-9][0-9]*', ident)), 'Aluno não encontrado.', 404)
            aluno = SERVICO.obter(int(ident))
            exigir(aluno and not aluno.get('status_exclusao'), 'Aluno não encontrado.', 404)
            exigir(attendance.student_access(usuario,aluno))
            if method == 'GET':
                return aluno_publico(aluno)
        if method in {'POST', 'PATCH'}:
            exigir(gestor)
            curso = curso_id(aluno['curso']) if ident else body.get('cursoId')
            nome_curso = next((c['nome'] for c in cursos() if c['id'] == curso), None)
            exigir(nome_curso, 'Selecione um curso válido.', 400)
            exigir(escopo(usuario, curso))
            dados = {**body, 'curso': nome_curso}
            if ident:
                SERVICO.atualizar(int(ident), dados)
            else:
                ident = str(SERVICO.cadastrar(dados))
            return aluno_publico(SERVICO.obter(int(ident)))
    if recurso in {'atendimentos', 'indicadores'}:
        simulation_followup.sync()
        simulated = bool(ident and ident.startswith('sim-'))
        connection = simulation_store.connect(simulation_store.OPERATIONAL) if simulated else database.get_connection()
        with LOCK, closing(connection) as conn, conn:
            if method != 'GET':conn.execute('BEGIN IMMEDIATE')
            if simulated:
                itens = simulation_followup.tickets()
            else:
                itens = [json.loads(row[0]) for row in conn.execute('SELECT dados FROM gestao_chamados ORDER BY id')]
                itens.extend(simulation_followup.tickets())
            itens.sort(key=lambda i: i['ultimaAtividadeEm'], reverse=True)
            allowed={str(a['id']):a for a in SERVICO.listar() if rbac.student_allowed(usuario,a)}
            itens = [i for i in itens if attendance.visible(usuario,i,allowed) and (not campus_filtro or rbac.campus_id(allowed[i['alunoId']].get('campus'))==campus_filtro) and (not curso_filtro or i['cursoId'] == curso_filtro)]
            if recurso == 'indicadores' and method == 'GET':
                with closing(database.get_connection()) as users_conn:
                    members=[usuario_publico(r) for r in users_conn.execute('SELECT * FROM gestao_usuarios')]
                members=[u for u in members if attendance.manages_user(usuario,u) and (not curso_filtro or curso_filtro in u.get('cursoIds',[])) and (not campus_filtro or campus_filtro==u.get('campusId'))]
                return attendance.metrics(itens,members)
            if not ident and method == 'GET':
                for chave in ('status', 'categoria'):
                    if query.get(chave): itens = [i for i in itens if i[chave] == query[chave]]
                if query.get('responsavelUid'): itens = [i for i in itens if (i['responsavel'] or {}).get('uid') == query['responsavelUid']]
                # Ordena o conjunto inteiro antes de paginar: um risco alto antigo
                # não pode ficar escondido atrás de uma página de riscos baixos.
                itens = risco_atendimentos(itens)
                if query.get('busca'):
                    search=query['busca'].casefold()
                    itens=[i for i in itens if search in ' '.join(str(i.get(k,'')) for k in ('protocolo','titulo','alunoNome','matricula')).casefold()]
                if query.get('semResponsavel')=='1':itens=[i for i in itens if not i.get('responsavel')]
                prioridade = {'alto': 0, 'medio': 1, 'baixo': 2, 'sem_avaliacao': 3}
                itens.sort(key=lambda i: prioridade[i['riscoAcademico']['nivel']])
                if query.get('ordem')=='data':itens.sort(key=lambda i:i['abertoEm'],reverse=True)
                if query.get('ordem')=='prioridade':itens.sort(key=lambda i:({'alta':0,'normal':1,'baixa':2}.get(i.get('prioridade','normal'),1),i['abertoEm']))
                result = pagina(itens, query)
                result['total'] = len(itens)
                return result
            item = next((i for i in itens if i['id'] == ident), None)
            exigir(item, 'Atendimento não encontrado.', 404)
            if method == 'GET':
                if len(segmentos) == 2: return risco_atendimentos([item],historico=True)[0]
                if segmentos[2] == 'historico':
                    return pagina([json.loads(r[0]) for r in conn.execute('SELECT dados FROM gestao_eventos WHERE chamado_id=? ORDER BY rowid', (ident,))], query)
            if method == 'POST' and len(segmentos) == 3:
                acao = segmentos[2]
                exigir(acao in {'comentarios', 'status', 'classificacao', 'responsavel'}, 'Ação desconhecida.', 404)
                id_acao = body.get('idAcao')
                exigir(isinstance(id_acao, str) and 1 <= len(id_acao) <= 100, 'Identificador de ação inválido.', 400)
                assinatura = json.dumps([usuario['uid'], caminho, body], sort_keys=True)
                anterior = conn.execute('SELECT * FROM gestao_acoes WHERE id=?', (id_acao,)).fetchone()
                if anterior:
                    exigir(anterior['assinatura'] == assinatura, 'Identificador já utilizado em outra ação.', 409)
                    return risco_atendimentos([simulation_followup.enrich(json.loads(anterior['resultado']))],historico=True)[0]
                exigir(usuario['perfil']!=rbac.ATTENDANT or acao in {'comentarios','status'})
                exigir(acao!='status' or body.get('status') not in {'reaberto','encerrado'} or gestor)
                exigir(item['status'] not in attendance.TERMINAL or (gestor and acao in {'status','comentarios'}), 'Este chamado já foi resolvido.', 409)
                # Respostas são lidas da fonte; nunca copiadas para chamados ou cache de ações.
                item = {k:v for k,v in item.items() if k not in {'alunoNome','matricula','situacaoAcademica','questionarios','consentimentoRevogado'}}
                texto = str(body.get('texto', '')).strip()
                exigir(acao == 'responsavel' or 1 <= len(texto) <= 9500, 'Informe o texto da ação.', 400)
                tipo = 'acao'
                if acao == 'status':
                    exigir(body.get('status') in TRANSICOES[item['status']], 'Transição de status inválida.', 409)
                    exigir(body.get('status') not in {'reaberto','encerrado'} or gestor)
                    exigir(body.get('status')!='em_andamento' or item.get('responsavel'), 'Atribua um atendente antes de iniciar.',409)
                    item['status'] = body['status']
                    if item['status']=='reaberto':
                        item.update(reaberturas=item.get('reaberturas',0)+1,resolvidoEm=None,tempoResolucaoMin=None,encerradoPor=None)
                        tipo='reabertura'
                    if item['status'] == 'aguardando_aluno': item['aguardandoAlunoEm'] = agora()
                    if item['status'] == 'resolvido':
                        item.update(resolvidoEm=agora(), encerradoPor='equipe', tempoResolucaoMin=round((datetime.now(timezone.utc) - datetime.fromisoformat(item['abertoEm'])).total_seconds() / 60))
                        tipo = 'encerramento'
                elif acao == 'classificacao':
                    exigir(gestor)
                    exigir(body.get('categoria') in CATEGORIAS, 'Categoria inválida.', 400)
                    item['categoria'] = body['categoria']; tipo = 'classificacao'
                    if 'prioridade' in body:
                        exigir(body['prioridade'] in {'alta','normal','baixa'},'Prioridade inválida.',400)
                        item['prioridade']=body['prioridade']
                elif acao == 'responsavel':
                    exigir(gestor)
                    anterior_responsavel=item.get('responsavel')
                    motivo=str(body.get('texto','')).strip()
                    exigir(1<=len(motivo)<=9500,'Informe o motivo da atribuição ou transferência.',400)
                    if body.get('uid'):
                        with closing(database.get_connection()) as users_conn:
                            row = users_conn.execute('SELECT * FROM gestao_usuarios WHERE id=?', (body.get('uid'),)).fetchone()
                        exigir(row, 'Responsável não encontrado.', 404)
                        pessoa = usuario_publico(row)
                        exigir(pessoa['ativo'] and pessoa['perfil'] == rbac.ATTENDANT and rbac.student_allowed(pessoa,allowed[item['alunoId']]))
                        item['responsavel'] = {'uid': pessoa['id'], 'nome': pessoa['nome']}
                        if item['status']=='aberto':item['status']='em_andamento'
                    else:
                        item['responsavel']=None
                        item['status']='aberto'
                    tipo='atribuicao'
                    texto='Responsável: '+(anterior_responsavel or {}).get('nome','Não atribuído')+' → '+(item['responsavel'] or {}).get('nome','Não atribuído')+'. Motivo: '+motivo
                item['ultimaAtividadeEm'] = agora()
                evento(conn, ident, {'tipo': tipo, 'texto': texto, 'criadoEm': agora(), 'autor': {'uid': usuario['uid'], 'nome': usuario['nome']}, 'visivelAoAluno': bool(body.get('visivelAoAluno', False)), **({'responsavelAnterior':anterior_responsavel,'novoResponsavel':item['responsavel'],'motivo':motivo} if acao=='responsavel' else {})})
                conn.execute('UPDATE gestao_chamados SET dados=? WHERE id=?', (json.dumps(item), ident))
                conn.execute('INSERT INTO gestao_acoes VALUES (?,?,?,?)', (id_acao, ident, assinatura, json.dumps(item)))
                return risco_atendimentos([simulation_followup.enrich(item)],historico=True)[0]
    raise ErroLocal(404, 'Endpoint não encontrado.')


def responder(handler):
    parsed = urlparse(handler.path)
    prefixo = '/api/local/' if parsed.path.startswith('/api/local/') else '/api/v1/'
    caminho = unquote(parsed.path[len(prefixo):]).strip('/')
    try:
        body = handler._body() if handler.command in {'POST', 'PATCH'} else {}
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        resultado = tratar(handler.command, caminho, query, body, handler._token())
        if caminho=='login':handler._set_session_cookie(resultado['token'])
        if caminho=='logout':handler._set_session_cookie()
        handler._json(200, {'sucesso': True, 'dados': resultado})
    except ErroLocal as erro:
        handler._json(erro.status, {'sucesso': False, 'erro': {'mensagem': erro.mensagem}})
    except (ValueError, TypeError, KeyError) as erro:
        handler._json(400, {'sucesso': False, 'erro': {'mensagem': str(erro)}})
    except Exception:
        handler._json(500, {'sucesso': False, 'erro': {'mensagem': 'Não foi possível concluir a operação local.'}})
