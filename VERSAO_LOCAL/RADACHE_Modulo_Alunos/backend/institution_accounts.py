"""Migração idempotente das equipes locais e conta institucional independente."""
from functools import lru_cache
import json
import hashlib
import hmac
from datetime import datetime,timezone
import rbac
from auth import gerar_hash_senha,ITERACOES_PBKDF2


@lru_cache(maxsize=64)
def credential(email):return gerar_hash_senha('admin123')


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS campus (id TEXT PRIMARY KEY,nome TEXT NOT NULL UNIQUE)')
    conn.executemany('INSERT OR IGNORE INTO campus VALUES (?,?)',rbac.CAMPI.items())
    if conn.execute("SELECT 1 FROM gestao_meta WHERE chave='rbac-institucional-v1'").fetchone():return
    now=datetime.now(timezone.utc).isoformat()
    demos=[('admin','Administrador Técnico','admin_tecnico','',''),
           ('analista','Analista Institucional','analista_institucional','','')]
    courses=['ciencia-da-computacao','ciencia-da-computacao','pedagogia','direito','administracao']
    for campus,name in rbac.CAMPI.items():
        demos.append(('diretor-'+campus,'Direção · '+name,'diretor_campus',campus,''))
        for i,course in enumerate(courses,1):
            uid=('coord' if i==1 else 'equipe') if campus=='caceres' and i<=2 else f'gestor{i}-{campus}'
            demos.append((uid,f'Gestor {i} · {name}','gestor_curso',campus,course))
    for uid,name,profile,campus,course in demos:
        email=uid+'@radache.local'
        old=conn.execute('SELECT dados,salt,password_hash FROM gestao_usuarios WHERE id=?',(uid,)).fetchone()
        if old:
            data=json.loads(old[0]);data.update(perfil=profile,campusId=campus,cursoId=course,cursoIds=[course] if course else [])
            data['versaoAcesso']=data.get('versaoAcesso',1)+1
            conn.execute('UPDATE gestao_usuarios SET dados=? WHERE id=?',(json.dumps(data),uid))
            demo=hashlib.pbkdf2_hmac('sha256',b'admin123',bytes.fromhex(old['salt']),ITERACOES_PBKDF2).hex()
            if hmac.compare_digest(demo,old['password_hash']):
                cred=credential(email)
                conn.execute('UPDATE gestao_usuarios SET salt=?,password_hash=? WHERE id=?',(cred['salt'],cred['password_hash'],uid))
        else:
            data=dict(id=uid,nome=name,email=email,perfil=profile,campusId=campus,cursoId=course,cursoIds=[course] if course else [],
                      ativo=True,versaoAcesso=1,criadoEm=now)
            cred=credential(email)
            conn.execute('INSERT INTO gestao_usuarios VALUES (?,?,?,?,?)',(uid,email,json.dumps(data),cred['salt'],cred['password_hash']))
    # Contas antigas são conservadas, sem elevá-las a um novo cargo operacional.
    for uid in ('caest','prae'):
        row=conn.execute('SELECT dados FROM gestao_usuarios WHERE id=?',(uid,)).fetchone()
        if row:
            data=json.loads(row[0]);data.update(ativo=False);data['versaoAcesso']=data.get('versaoAcesso',1)+1
            conn.execute('UPDATE gestao_usuarios SET dados=? WHERE id=?',(json.dumps(data),uid))
    conn.execute("INSERT INTO gestao_meta VALUES ('rbac-institucional-v1')")
