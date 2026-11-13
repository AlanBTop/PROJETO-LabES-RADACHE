"""Cria um exemplo identificado para consulta na página de alunos, sem substituir registros."""
from contextlib import closing
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'RADACHE_Modulo_Alunos/backend'))
import database
import gestao_local as gestao
import simulation_store as store
import simulation_followup
import staff


def main():
    store.init();database.init_db();gestao.iniciar()
    matricula='DEMO-ALUNOS-2026-001'
    student=next((s for s in store.students() if s['matricula']==matricula),None)
    if student:
        aid=student['id']
    else:
        aid=store.save(dict(nome='EXEMPLO FICTICIO - Mariana Silva',matricula=matricula,
            curso='Ciência da Computação',campus='Câmpus de Cáceres',periodo=3,status='ativo',
            email='mariana.exemplo@radache.test',telefone='',nota_media=6.5,frequencia=72))
        sid=store.session(aid)['sessao_id']
        for text in ('1','3','2'):
            store.session(aid,dict(acao='responder',texto=text,sessao_id=sid,id_cliente=uuid4().hex))
        simulation_followup.sync()
    login='exemplo.alunos'
    with closing(database.get_connection()) as conn:
        existing=conn.execute('SELECT dados FROM gestao_usuarios WHERE email=?',(login,)).fetchone()
        admin=json.loads(conn.execute("SELECT dados FROM gestao_usuarios WHERE id='admin'").fetchone()[0])
    if not existing:
        staff.handle('POST','usuarios',{},dict(nome='Gestor de exemplo - Alunos',login=login,
            senhaInicial='Exemplo@2026',perfil='gestor_curso',campusId='caceres',cursoIds=['ciencia-da-computacao']),admin)
    session=gestao.tratar('POST','login',{},dict(login=login,senha='Exemplo@2026'),'')
    record=gestao.tratar('GET','alunos/'+str(-aid),{},{},session['token'])
    assert record['matricula']==matricula
    gestao.tratar('POST','logout',{},{},session['token'])
    print('Exemplo pronto:',record['nome'])
    print('Login: exemplo.alunos | Senha: Exemplo@2026')
    print('Lista: http://localhost:8080/gestao/#alunos')
    print('Ficha: http://localhost:8080/gestao/#alunos/'+str(-aid))
    if record.get('avaliacaoAtual'):print('Risco registrado:',record['avaliacaoAtual'].get('indice_risco'))


if __name__=='__main__':main()
