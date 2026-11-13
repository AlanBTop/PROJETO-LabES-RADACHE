"""Atualiza contratos antigos: cadastro editável somente na administração fictícia."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
T=ROOT/'RADACHE_Modulo_Alunos/backend/tests'
def update(name,changes):
    p=T/name;s=p.read_text(encoding='utf-8')
    b=ROOT.parent/'ARQUIVO/backups/versao_local/backup_simulacao_20261107'/p.relative_to(ROOT);b.parent.mkdir(parents=True,exist_ok=True)
    if not b.exists():shutil.copy2(p,b)
    for old,new in changes:
        if old not in s:raise ValueError(name+': '+old[:60])
        s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')

update('test_maintenance.py',[
 ('def test_matricula_duplicada_retorna_409(self):','def test_cadastro_operacional_bloqueia_escrita_mesmo_com_matricula_duplicada(self):'),
 ('self.assertEqual(status, 409)','self.assertEqual(status, 405)'),
 ('self.request("POST", "/api/alunos", raw=','self.request("POST", "/api/mock-alunos", raw=')])
update('test_gestao_local.py',[
 ('''        novo = self.api('POST', 'alunos', {'nome': 'Aluno local', 'matricula': 'LOCAL999', 'cursoId': 'direito', 'campus': 'Cáceres', 'periodo': 2, 'email': 'local@example.com', 'telefone': '65999990000', 'status': 'ativo'})
        self.assertEqual(database.get_aluno_by_id(int(novo['id']))['curso'], 'Direito')
        self.api('PATCH', 'alunos/' + novo['id'], {'nome': 'Nome alterado'})
        self.assertEqual(database.get_aluno_by_id(int(novo['id']))['nome'], 'Nome alterado')''',
 '''        for method,path in [('POST','alunos'),('PATCH','alunos/1')]:
            with self.assertRaises(gestao.ErroLocal) as error:
                self.api(method,path,{'nome':'Aluno local'})
            self.assertEqual(error.exception.status,405)
        self.assertEqual(original,database.list_alunos())''')])
p=T/'test_mock_isolado.py'
s=p.read_text(encoding='utf-8')
b=ROOT.parent/'ARQUIVO/backups/versao_local/backup_simulacao_20261107'/p.relative_to(ROOT);b.parent.mkdir(parents=True,exist_ok=True)
if not b.exists():shutil.copy2(p,b)
s=s.replace('import app,auth,database,gestao_local,mock_alunos','import app,auth,database,gestao_local,mock_alunos\nimport simulation_store as store')
s=s.replace('cls.old_mock=mock_alunos.DB_PATH','cls.old_mock=(store.ACADEMIC,store.OPERATIONAL); cls.old_auth=app.auth')
s=s.replace('        mock_alunos.USE_LOCAL_TEST_STORE=True\n','')
s=s.replace("mock_alunos.DB_PATH=Path(cls.temp.name)/'mock.db'","store.ACADEMIC=Path(cls.temp.name)/'mock.db'; store.OPERATIONAL=Path(cls.temp.name)/'operacional.db'; store.init()")
s=s.replace('mock_alunos.DB_PATH=cls.old_mock','store.ACADEMIC,store.OPERATIONAL=cls.old_mock; app.auth=cls.old_auth')
s=s.replace('        mock_alunos.USE_LOCAL_TEST_STORE=False\n','')
s=s.replace('test_01_create_delete_isolated_and_update_denied','test_01_create_deactivate_isolated_and_admin_update_allowed')
s=s.replace("self.call('/api/mock-alunos/'+str(ident),method,body)[0],405","self.call('/api/mock-alunos/'+str(ident),method,body)[0],200")
s=s.replace('with mock_alunos.conectar() as conn:', 'with store.connect(store.ACADEMIC,True) as conn:')
s=s.replace('sqlite3.IntegrityError', 'sqlite3.OperationalError').replace("UPDATE alunos_mock SET nome='TESTE OUTRO'","UPDATE alunos SET nome='TESTE OUTRO'")
s=s.replace("{'nome':'Nome real','matricula':'123','curso':'Curso'}", "{'nome':'TESTE','matricula':'123','curso':'Curso','email':'real@example.com'}")
start=s.index('    def test_04_browser(self):');end=s.index('\n\nif __name__',start)
s=s[:start]+'''    def test_04_simulation_rejects_deactivated_student_and_preserves_session(self):
        status,result=self.call('/api/mock-alunos','POST',{'nome':'TESTE Sessão','matricula':'TESTE-SESSAO','curso':'Teste'})
        self.assertEqual(status,201)
        ident=result['id']
        self.assertEqual(self.call(f'/simulation-api/alunos/{ident}/conversa')[0],200)
        self.assertEqual(self.call('/api/mock-alunos/'+str(ident),'DELETE')[0],200)
        self.assertEqual(self.call(f'/simulation-api/alunos/{ident}/conversa')[0],400)
        self.assertEqual(len(next(a for a in store.projected() if a['id']==-ident)['historico_checkins']),1)
'''+s[end:]
p.write_text(s,encoding='utf-8')
