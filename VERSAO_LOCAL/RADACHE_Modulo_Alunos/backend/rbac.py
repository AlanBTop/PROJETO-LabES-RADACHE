"""Perfis e escopos explícitos: analista nunca herda privilégios operacionais."""
import unicodedata

CAMPI={'caceres':'Câmpus de Cáceres','varzea-grande':'Câmpus de Várzea Grande','cuiaba':'Câmpus de Cuiabá'}
ADMIN={'admin_tecnico','admin_geral'}
OPERATIONAL=ADMIN|{'diretor_campus','gestor_curso','coordenador_curso','funcionario_curso'}
ANALYST='analista_institucional'
ATTENDANT='atendente_academico'
MANAGERS=ADMIN|{'gestor_curso','coordenador_curso'}
PROFILES={'admin_tecnico':'Administrador Técnico',ANALYST:'Analista Institucional',
          'diretor_campus':'Diretor do Câmpus','gestor_curso':'Gestor de Curso',ATTENDANT:'Atendente Acadêmico'}


def campus_id(value):
    text=''.join(c for c in unicodedata.normalize('NFD',str(value or '')) if not unicodedata.combining(c)).casefold()
    text=text.replace('campus de ','').replace('campus ','').strip().replace(' ','-')
    return text if text in CAMPI else None


def allowed(user,course,campus=None):
    if user['perfil'] in ADMIN:return True
    if user['perfil'] not in OPERATIONAL|{ATTENDANT}:return False
    if campus is not None and campus_id(campus)!=user.get('campusId','caceres'):return False
    return user['perfil']=='diretor_campus' or course in user.get('cursoIds',[user.get('cursoId')])


def analytics_scope(user):
    if user['perfil'] in ADMIN:return None
    return dict(campusId=user.get('campusId','caceres'),cursoIds=None if user['perfil']=='diretor_campus' else user.get('cursoIds',[user.get('cursoId')]))


def student_allowed(user,student):
    from course_catalog import course_id
    return allowed(user,course_id(student['curso']),student.get('campus'))


def audit(user,path,query,result):
    from contextlib import closing
    from datetime import datetime,timezone
    import json,database
    with closing(database.get_connection()) as c,c:
        c.execute('''CREATE TABLE IF NOT EXISTS institucional_auditoria (
          id INTEGER PRIMARY KEY, data TEXT NOT NULL, usuario_id TEXT NOT NULL,
          perfil TEXT NOT NULL, recurso TEXT NOT NULL, filtros TEXT NOT NULL, resultado INTEGER NOT NULL)''')
        safe={k:str(v)[:100] for k,v in query.items() if k in {'campus','curso','periodo','inicio','fim','risco'}}
        c.execute('INSERT INTO institucional_auditoria(data,usuario_id,perfil,recurso,filtros,resultado) VALUES (?,?,?,?,?,?)',
                  (datetime.now(timezone.utc).isoformat(),user.get('id') or user.get('username','sessao'),user.get('perfil',user.get('role','')),path.split('?')[0][:160],json.dumps(safe),result))
