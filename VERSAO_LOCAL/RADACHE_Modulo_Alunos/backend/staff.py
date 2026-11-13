"""Lotação única, vínculos multicurso e transferências locais auditadas."""
from contextlib import closing
import json
import re
from uuid import uuid4
import database
import simulation_store as store
import course_catalog
import rbac
import attendance


def initialize(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS campus_cursos (
        campus_id TEXT NOT NULL REFERENCES campus(id), curso_id TEXT NOT NULL,
        nome TEXT NOT NULL, PRIMARY KEY(campus_id,curso_id));
      CREATE TABLE IF NOT EXISTS atendentes_vinculos (
        id INTEGER PRIMARY KEY, usuario_id TEXT NOT NULL REFERENCES gestao_usuarios(id),
        campus_id TEXT NOT NULL, curso_id TEXT NOT NULL, inicio TEXT NOT NULL, fim TEXT,
        autor_id TEXT NOT NULL, FOREIGN KEY(campus_id,curso_id) REFERENCES campus_cursos(campus_id,curso_id));
      CREATE UNIQUE INDEX IF NOT EXISTS vinculo_atual ON atendentes_vinculos(usuario_id,curso_id) WHERE fim IS NULL;
      CREATE TRIGGER IF NOT EXISTS vinculo_mesmo_campus_update BEFORE UPDATE OF campus_id,usuario_id,fim ON atendentes_vinculos
      WHEN NEW.fim IS NULL BEGIN
        SELECT CASE WHEN EXISTS(SELECT 1 FROM atendentes_vinculos WHERE usuario_id=NEW.usuario_id AND id!=OLD.id AND fim IS NULL AND campus_id!=NEW.campus_id)
          OR NEW.campus_id!=json_extract((SELECT dados FROM gestao_usuarios WHERE id=NEW.usuario_id),'$.campusId')
          THEN RAISE(ABORT,'Vinculo de outro campus') END;
      END;
      CREATE TABLE IF NOT EXISTS funcionarios_transferencias (
        id TEXT PRIMARY KEY, usuario_id TEXT NOT NULL REFERENCES gestao_usuarios(id),
        origem TEXT NOT NULL REFERENCES campus(id), destino TEXT NOT NULL REFERENCES campus(id), dados TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS transferencia_usuario ON funcionarios_transferencias(usuario_id);
      CREATE TRIGGER IF NOT EXISTS vinculo_mesmo_campus BEFORE INSERT ON atendentes_vinculos
      WHEN NEW.fim IS NULL BEGIN
        SELECT CASE WHEN EXISTS(SELECT 1 FROM atendentes_vinculos WHERE usuario_id=NEW.usuario_id AND fim IS NULL AND campus_id!=NEW.campus_id)
          OR NEW.campus_id!=json_extract((SELECT dados FROM gestao_usuarios WHERE id=NEW.usuario_id),'$.campusId')
          THEN RAISE(ABORT,'Vinculo de outro campus') END;
      END;
      CREATE TRIGGER IF NOT EXISTS usuario_campus_valido BEFORE UPDATE OF dados ON gestao_usuarios
      WHEN json_extract(NEW.dados,'$.perfil')='atendente_academico' BEGIN
        SELECT CASE WHEN COALESCE(json_extract(NEW.dados,'$.campusId'),'') NOT IN ('caceres','cuiaba','varzea-grande')
          OR EXISTS(SELECT 1 FROM json_each(NEW.dados,'$.cursoIds') c WHERE NOT EXISTS(
            SELECT 1 FROM campus_cursos cc WHERE cc.campus_id=json_extract(NEW.dados,'$.campusId') AND cc.curso_id=c.value))
          OR EXISTS(SELECT 1 FROM atendentes_vinculos WHERE usuario_id=NEW.id AND fim IS NULL AND campus_id!=json_extract(NEW.dados,'$.campusId'))
          THEN RAISE(ABORT,'Lotacao ou cursos invalidos') END;
      END;
      CREATE TRIGGER IF NOT EXISTS usuario_campus_insercao BEFORE INSERT ON gestao_usuarios
      WHEN json_extract(NEW.dados,'$.perfil')='atendente_academico' BEGIN
        SELECT CASE WHEN COALESCE(json_extract(NEW.dados,'$.campusId'),'') NOT IN ('caceres','cuiaba','varzea-grande')
          OR EXISTS(SELECT 1 FROM json_each(NEW.dados,'$.cursoIds') c WHERE NOT EXISTS(
            SELECT 1 FROM campus_cursos cc WHERE cc.campus_id=json_extract(NEW.dados,'$.campusId') AND cc.curso_id=c.value))
          THEN RAISE(ABORT,'Lotacao ou cursos invalidos') END;
      END;
    ''')
    refresh_catalog(conn)
    from gestao_local import agora
    for row in conn.execute('SELECT dados FROM gestao_usuarios').fetchall():
        user=json.loads(row[0])
        if user['perfil']==rbac.ATTENDANT:
            for course in user.get('cursoIds',[]):
                conn.execute('INSERT OR IGNORE INTO atendentes_vinculos(usuario_id,campus_id,curso_id,inicio,autor_id) VALUES (?,?,?,?,?)',
                             (user['id'],user['campusId'],course,agora(),'migracao'))


def refresh_catalog(conn):
    """Materializa apenas vínculos observados nos cadastros locais existentes."""
    names={c['id']:c['nome'] for c in course_catalog.catalog()}
    pairs=[]
    for row in conn.execute('SELECT DISTINCT curso,campus FROM alunos'):
        campus=rbac.campus_id(row['campus'])
        if campus:pairs.append((campus,course_catalog.course_id(row['curso']),course_catalog.canonical(row['curso'])))
    if store.ACADEMIC.exists():
        for student in store.students():
            campus=rbac.campus_id(student.get('campus'))
            if campus:pairs.append((campus,course_catalog.course_id(student['curso']),course_catalog.canonical(student['curso'])))
    for row in conn.execute('SELECT dados FROM gestao_usuarios'):
        user=json.loads(row[0]);campus=user.get('campusId')
        if campus in rbac.CAMPI:
            for course in user.get('cursoIds') or [user.get('cursoId')]:
                if course:pairs.append((campus,course,names.get(course,course)))
    conn.executemany('INSERT OR IGNORE INTO campus_cursos VALUES (?,?,?)',pairs)


def user_courses(user):
    return set(user.get('cursoIds') or ([user['cursoId']] if user.get('cursoId') else []))


def same_campus(actor, user):
    return actor['perfil'] in rbac.ADMIN or (actor['perfil'] in rbac.MANAGERS|{'diretor_campus'}
            and user['perfil']==rbac.ATTENDANT and actor.get('campusId')==user.get('campusId'))


def visible(actor,user,lookup=False):
    return same_campus(actor,user) and (actor['perfil'] in rbac.ADMIN|{'diretor_campus'} or lookup
                                       or bool(user_courses(actor)&user_courses(user)))


def catalog(conn,campus):
    refresh_catalog(conn)
    return [dict(id=r['curso_id'],nome=r['nome'],ativo=True,campusId=r['campus_id'])
            for r in conn.execute('SELECT * FROM campus_cursos WHERE campus_id=? ORDER BY nome',(campus,))]


def validate_courses(conn,campus,courses,required=True):
    from gestao_local import exigir
    exigir(campus in rbac.CAMPI,'Câmpus inválido.',400)
    exigir(isinstance(courses,list) and all(isinstance(c,str) for c in courses),'Cursos inválidos.',400)
    exigir(not required or bool(courses),'Selecione pelo menos um curso.',400)
    allowed={c['id'] for c in catalog(conn,campus)}
    exigir(set(courses)<=allowed,'Os cursos devem pertencer ao câmpus selecionado no banco local.',400)
    return list(dict.fromkeys(courses))


def audit(conn,actor,before,after):
    from gestao_local import agora
    conn.execute('INSERT INTO gestao_equipe_auditoria(usuario_id,autor_id,data,antes,depois) VALUES (?,?,?,?,?)',
                 (after['id'],actor['id'],agora(),json.dumps(before) if before else None,json.dumps(after)))


def sync_links(conn,actor,user):
    from gestao_local import agora
    active=conn.execute('SELECT * FROM atendentes_vinculos WHERE usuario_id=? AND fim IS NULL',(user['id'],)).fetchall()
    courses=user_courses(user) if user['perfil']==rbac.ATTENDANT else set()
    for row in active:
        if row['curso_id'] not in courses or row['campus_id']!=user.get('campusId'):
            conn.execute('UPDATE atendentes_vinculos SET fim=? WHERE id=?',(agora(),row['id']))
    for course in courses:
        conn.execute('INSERT OR IGNORE INTO atendentes_vinculos(usuario_id,campus_id,curso_id,inicio,autor_id) VALUES (?,?,?,?,?)',
                     (user['id'],user['campusId'],course,agora(),actor['id']))


def attach(conn):
    if store.OPERATIONAL.exists():
        conn.execute('ATTACH DATABASE ? AS operacao',(str(store.OPERATIONAL.resolve()),))


def assigned(conn,uid):
    result=[]
    schemas=['main']+(['operacao'] if any(r[1]=='operacao' for r in conn.execute('PRAGMA database_list')) else [])
    for schema in schemas:
        for row in conn.execute(f'SELECT dados FROM {schema}.gestao_chamados'):
            ticket=json.loads(row[0])
            if attendance.owner(ticket)==uid and ticket['status'] not in attendance.TERMINAL:
                result.append((schema,ticket))
    return result


def redistribute(conn,actor,user,cases,mapping,apply=True):
    from gestao_local import exigir,agora,SERVICO
    exigir(isinstance(mapping,dict),'Informe a redistribuição dos atendimentos.',400)
    students={str(s['id']):s for s in SERVICO.listar()}
    for schema,ticket in cases:
        target=mapping.get(ticket['id'])
        exigir(target and target!=user['id'],'Redistribua todos os atendimentos ativos antes de concluir.',409)
        row=conn.execute('SELECT dados FROM gestao_usuarios WHERE id=?',(target,)).fetchone()
        member=json.loads(row[0]) if row else None;student=students.get(str(ticket['alunoId']))
        exigir(member and member['ativo'] and member['perfil']==rbac.ATTENDANT and student
               and member.get('campusId')==user['campusId'] and rbac.student_allowed(member,student),
               'Novo responsável precisa estar habilitado no curso e câmpus de origem.',403)
        if not apply:continue
        before=ticket['responsavel'];ticket.update(responsavel=dict(uid=member['id'],nome=member['nome']),ultimaAtividadeEm=agora())
        event=dict(id=uuid4().hex,tipo='atribuicao',texto='Redistribuição administrativa: '+before['nome']+' → '+member['nome'],
                   criadoEm=agora(),autor=dict(uid=actor['id'],nome=actor['nome']),responsavelAnterior=before,novoResponsavel=ticket['responsavel'],
                   motivo='Alteração de vínculos ou transferência de câmpus',visivelAoAluno=False)
        conn.execute(f'UPDATE {schema}.gestao_chamados SET dados=? WHERE id=?',(json.dumps(ticket),ticket['id']))
        conn.execute(f'INSERT INTO {schema}.gestao_eventos VALUES (?,?,?)',(event['id'],ticket['id'],json.dumps(event)))


def summary(actor,users):
    from gestao_local import SERVICO
    students={str(s['id']):s for s in SERVICO.listar()}
    tickets=[t for t in attendance.all_tickets() if str(t['alunoId']) in students and rbac.student_allowed(actor,students[str(t['alunoId'])])]
    return [{**u,'login':u.get('login',u['email']),
             'atendimentosAtivos':sum(attendance.owner(t)==u['id'] and t['status'] not in attendance.TERMINAL for t in tickets),
             'atendimentosResolvidos':sum(attendance.owner(t)==u['id'] and t['status'] in attendance.TERMINAL for t in tickets)} for u in users]


def handle(method,path,query,body,actor):
    from gestao_local import exigir,LOCK,agora,pagina,campos_acesso
    from auth import gerar_hash_senha
    parts=path.split('/');resource=parts[0];uid=parts[1] if len(parts)>1 else None
    admin=actor['perfil'] in rbac.ADMIN;manager=actor['perfil'] in rbac.MANAGERS;director=actor['perfil']=='diretor_campus'
    exigir(admin or manager or director or (resource=='responsaveis' and actor['perfil']==rbac.ATTENDANT))
    with LOCK,closing(database.get_connection()) as conn:
        attach(conn)
        with conn:
            conn.execute('BEGIN IMMEDIATE' if method!='GET' else 'BEGIN')
            users=[json.loads(r[0]) for r in conn.execute('SELECT dados FROM gestao_usuarios ORDER BY email')]
            current_actor=next((u for u in users if u['id']==actor['id']),None)
            exigir(current_actor and current_actor['ativo'] and current_actor['versaoAcesso']==actor['versaoAcesso'],'Seu acesso mudou. Entre novamente.',401)
            if resource=='transferencias':
                return transfers(conn,method,parts,body,actor,users)
            if resource=='funcionarios':
                exigir(method=='GET' and not uid,'Endpoint não encontrado.',404)
                items=[u for u in users if u['perfil']==rbac.ATTENDANT and same_campus(actor,u)]
            else:
                exigir(resource in {'usuarios','responsaveis'},'Endpoint não encontrado.',404)
                items=[u for u in users if visible(actor,u)]
                if resource=='usuarios':items=[u for u in items if u['perfil'] in rbac.PROFILES]
            if resource=='responsaveis':
                exigir(method=='GET' and not uid,'Endpoint não encontrado.',404)
                if actor['perfil']==rbac.ATTENDANT:items=[u for u in users if u['id']==actor['id']]
                items=[{**u,'uid':u['id']} for u in items if u['perfil']==rbac.ATTENDANT and u['ativo']]
            campus=query.get('campusId');course=query.get('cursoId');search=query.get('busca','').casefold().strip()
            if campus:
                exigir(campus in rbac.CAMPI and (admin or campus==actor.get('campusId')))
                items=[u for u in items if u.get('campusId')==campus]
            if course:items=[u for u in items if course in user_courses(u)]
            if search:items=[u for u in items if search in (u['nome']+' '+u.get('login',u['email'])).casefold()]
            if query.get('perfil'):items=[u for u in items if u['perfil']==query['perfil']]
            if method=='GET' and not uid:return pagina(summary(actor,items),query)
            user=next((u for u in users if u['id']==uid),None)
            if uid:
                exigir(user and same_campus(actor,user),'Funcionário não encontrado.',404)
                exigir(user['perfil'] in rbac.PROFILES,'Perfil legado preservado fora da gestão de acessos.',403)
                if len(parts)==3 and parts[2]=='historico' and method=='GET':
                    return dict(vinculos=[dict(r) for r in conn.execute('SELECT * FROM atendentes_vinculos WHERE usuario_id=? ORDER BY id',(uid,))],
                        transferencias=[{'id':r['id'],**json.loads(r['dados'])} for r in conn.execute('SELECT * FROM funcionarios_transferencias WHERE usuario_id=?',(uid,))],
                        alteracoes=[dict(data=r['data'],autorId=r['autor_id'],antes=json.loads(r['antes']) if r['antes'] else None,depois=json.loads(r['depois'])) for r in conn.execute('SELECT * FROM gestao_equipe_auditoria WHERE usuario_id=? ORDER BY id',(uid,))])
                if len(parts)==2 and method=='GET':return summary(actor,[user])[0]
                if len(parts)==3 and parts[2]=='ativos' and method=='GET':
                    from gestao_local import SERVICO
                    students={str(s['id']):s for s in SERVICO.listar()}
                    return dict(itens=[dict(id=t['id'],protocolo=t['protocolo'],cursoId=t['cursoId']) for _,t in assigned(conn,uid)
                               if str(t['alunoId']) in students and rbac.student_allowed(actor,students[str(t['alunoId'])])])
            exigir(manager,'Este perfil pode consultar funcionários e solicitar transferências.',403)
            if not uid and method=='POST':
                access=campos_acesso(body);login=str(body.get('login',body.get('email',''))).strip().casefold()
                exigir(1<=len(login)<=254 and re.fullmatch(r'[\w.@+\-]+',login),'Informe um login válido.',400)
                exigir(not any(u.get('login',u['email']).casefold()==login or u['email'].casefold()==login for u in users),'Login já existente. Localize o funcionário para vinculá-lo.',409)
                if not admin:exigir(access['perfil']==rbac.ATTENDANT and access['campusId']==actor.get('campusId') and set(access['cursoIds'])<=user_courses(actor))
                if access['perfil'] in {'gestor_curso',rbac.ATTENDANT}:access['cursoIds']=validate_courses(conn,access['campusId'],access['cursoIds'])
                name=str(body.get('nome','')).strip();password=body.get('senhaInicial')
                exigir(1<=len(name)<=150 and isinstance(password,str) and 8<=len(password)<=128,'Informe nome e senha inicial de 8 a 128 caracteres.',400)
                user=dict(id=uuid4().hex,nome=name,email=login,login=login,**access,ativo=True,versaoAcesso=1,criadoEm=agora())
                credential=gerar_hash_senha(password)
                conn.execute('INSERT INTO gestao_usuarios VALUES (?,?,?,?,?)',(user['id'],login,json.dumps(user),credential['salt'],credential['password_hash']))
                sync_links(conn,actor,user);audit(conn,actor,None,user)
                return user
            exigir(user,'Usuário não encontrado.',404)
            if len(parts)==3 and parts[2]=='convite' and method=='POST':return {'convite':'local','mensagem':'Use a senha inicial definida no cadastro.'}
            exigir(method=='PATCH' and len(parts)==2,'Endpoint não encontrado.',404)
            exigir(user['id']!=actor['id'])
            before=dict(user)
            exigir(not set(body)-{'nome','perfil','campusId','cursoIds','cursoId','ativo','redistribuicoes'},'Campos inválidos.',400)
            if user['perfil']==rbac.ATTENDANT:
                exigir(body.get('campusId',user.get('campusId'))==user.get('campusId'),'Use Transferência de Funcionários entre Câmpus para mudar a lotação.',409)
            if not admin:
                exigir(user['perfil']==rbac.ATTENDANT and body.get('perfil',rbac.ATTENDANT)==rbac.ATTENDANT)
                if 'ativo' in body or 'nome' in body:
                    exigir(user_courses(user)<=user_courses(actor),'Para alterar nome ou situação de um funcionário compartilhado, solicite ao Administrador Técnico.')
            if 'nome' in body:
                exigir(isinstance(body['nome'],str) and 1<=len(body['nome'].strip())<=150,'Nome inválido.',400)
                user['nome']=body['nome'].strip()
            if 'ativo' in body:
                exigir(type(body['ativo']) is bool,'Situação inválida.',400);user['ativo']=body['ativo']
            if 'cursoIds' in body and (user['perfil']==rbac.ATTENDANT or body.get('perfil',user['perfil']) in {'gestor_curso',rbac.ATTENDANT}):
                selected=validate_courses(conn,user['campusId'],body['cursoIds'],False)
                if not admin:
                    exigir(set(selected)<=user_courses(actor),'Selecione somente os cursos sob sua responsabilidade.')
                    selected=sorted((user_courses(user)-user_courses(actor))|set(selected))
                user.update(cursoIds=selected,cursoId=selected[0] if selected else '')
            if admin and user['perfil']!=rbac.ATTENDANT and any(k in body for k in ('perfil','campusId','cursoIds','cursoId')):
                user.update(campos_acesso({**user,**body}))
            elif 'perfil' in body and body['perfil']!=user['perfil']:
                exigir(admin);user.update(campos_acesso({**user,**body}))
            removed=user_courses(before)-user_courses(user)
            affected=[(s,t) for s,t in assigned(conn,user['id']) if t['cursoId'] in removed or not user['ativo'] or user['perfil']!=rbac.ATTENDANT]
            redistribute(conn,actor,before,affected,body.get('redistribuicoes',{}))
            user['versaoAcesso']+=1
            conn.execute('UPDATE gestao_usuarios SET dados=? WHERE id=?',(json.dumps(user),user['id']))
            sync_links(conn,actor,user);audit(conn,actor,before,user)
            return user


def transfers(conn,method,parts,body,actor,users):
    from gestao_local import exigir,agora
    admin=actor['perfil'] in rbac.ADMIN;director=actor['perfil']=='diretor_campus'
    exigir(admin or director)
    rows=[{'id':r['id'],'usuarioId':r['usuario_id'],**json.loads(r['dados'])} for r in conn.execute('SELECT * FROM funcionarios_transferencias ORDER BY rowid DESC')]
    if method=='GET' and len(parts)==1:
        return dict(itens=[r for r in rows if admin or actor['campusId'] in {r['origem'],r['destino']}])
    if method=='POST' and len(parts)==1:
        user=next((u for u in users if u['id']==body.get('usuarioId')),None)
        exigir(user and user['perfil']==rbac.ATTENDANT and same_campus(actor,user))
        destination=body.get('destino');exigir(destination!=user['campusId'],'Selecione outro câmpus.',400)
        courses=validate_courses(conn,destination,body.get('cursoIds',[]),False)
        reason=str(body.get('motivo','')).strip();exigir(1<=len(reason)<=3000,'Informe a justificativa.',400)
        record=dict(id=uuid4().hex,usuarioId=user['id'],nome=user['nome'],origem=user['campusId'],destino=destination,cursoIds=courses,
                    motivo=reason,criadoEm=agora(),solicitadoPor=actor['id'],status='pendente',
                    autorizacoes={user['campusId']:dict(uid=actor['id'],data=agora())},redistribuicoes=body.get('redistribuicoes',{}),versaoOrigem=user['versaoAcesso'])
        # A solicitação valida o plano; a confirmação revalida antes de alterar os casos.
        if not admin:redistribute(conn,actor,user,assigned(conn,user['id']),record['redistribuicoes'],apply=False)
        if admin:execute_transfer(conn,record,user,actor)
        conn.execute('INSERT INTO funcionarios_transferencias VALUES (?,?,?,?,?)',(record['id'],user['id'],record['origem'],destination,json.dumps(record)))
        return record
    record=next((r for r in rows if len(parts)>1 and r['id']==parts[1]),None)
    exigir(record,'Transferência não encontrada.',404)
    exigir(record['status']=='pendente','Transferência já concluída.',409)
    exigir(method=='POST' and len(parts)==3 and parts[2]=='confirmar','Endpoint não encontrado.',404)
    exigir(admin or actor['campusId']==record['destino'],'A direção do câmpus de destino deve confirmar.')
    user=next(u for u in users if u['id']==record['usuarioId'])
    exigir(user['campusId']==record['origem'] and user['versaoAcesso']==record['versaoOrigem'],'Os vínculos mudaram desde a solicitação. Solicite uma nova transferência.',409)
    record['autorizacoes'][record['destino']]=dict(uid=actor['id'],data=agora())
    execute_transfer(conn,record,user,actor)
    conn.execute('UPDATE funcionarios_transferencias SET dados=? WHERE id=?',(json.dumps(record),record['id']))
    return record


def execute_transfer(conn,record,user,actor):
    from gestao_local import agora,exigir
    before=dict(user)
    # O autor da origem autorizou as redistribuições; o destino confirma a lotação.
    origin_author=record['autorizacoes'][record['origem']]['uid']
    author_row=conn.execute('SELECT dados FROM gestao_usuarios WHERE id=?',(origin_author,)).fetchone()
    origin_actor=json.loads(author_row[0]) if author_row else None
    exigir(origin_actor and origin_actor['ativo'] and (origin_actor['perfil'] in rbac.ADMIN or (origin_actor['perfil']=='diretor_campus' and origin_actor['campusId']==record['origem'])), 'A autorização de origem deixou de ser válida.')
    redistribute(conn,origin_actor,user,assigned(conn,user['id']),record['redistribuicoes'])
    # Fecha vínculos antes de trocar lotação: o trigger impede câmpus simultâneos.
    conn.execute('UPDATE atendentes_vinculos SET fim=? WHERE usuario_id=? AND fim IS NULL',(agora(),user['id']))
    courses=validate_courses(conn,record['destino'],record['cursoIds'],False)
    user.update(campusId=record['destino'],cursoIds=courses,cursoId=courses[0] if courses else '',versaoAcesso=user['versaoAcesso']+1)
    conn.execute('UPDATE gestao_usuarios SET dados=? WHERE id=?',(json.dumps(user),user['id']))
    sync_links(conn,actor,user);audit(conn,actor,before,user)
    record.update(status='concluida',concluidaEm=agora(),confirmadoPor=actor['id'])
    if actor['perfil'] in rbac.ADMIN:record['autorizacoes'][record['destino']]=dict(uid=actor['id'],data=agora())
