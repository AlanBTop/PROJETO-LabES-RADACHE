"""Reduz exclusivamente o lote identificado UNIV26 para 20 alunos por câmpus."""
from contextlib import closing
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import simulation_store as store,database,rbac


def main():
    with closing(store.connect(store.OPERATIONAL,True)) as c:
        owned={r['aluno_id']:r['matricula'] for r in c.execute('SELECT aluno_id,matricula FROM povoamento_universidades')}
    with closing(store.connect(store.ACADEMIC,True)) as c:
        students=[dict(r) for r in c.execute('SELECT * FROM alunos')]
    generated=[a for a in students if a['id'] in owned]
    if any(owned[a['id']]!=a['matricula'] or not a['matricula'].startswith('UNIV26-') for a in generated):
        raise RuntimeError('Lote não corresponde aos registros gerados; nenhuma remoção foi feita.')
    keep=[a for a in generated if a['curso']=='Ciência da Computação']
    counts=Counter(a['campus'] for a in keep)
    if counts!={campus:20 for campus in rbac.CAMPI.values()}:raise RuntimeError('Os 20 registros por câmpus não estão disponíveis.')
    keep_ids={a['id'] for a in keep};remove=[a['id'] for a in generated if a['id'] not in keep_ids]
    untouched={a['id']:a for a in students if a['id'] not in set(remove)}
    backup=ROOT.parent/'ARQUIVO/backups/versao_local'/('backup_reducao_campi_'+datetime.now().strftime('%Y%m%d_%H%M%S'));backup.mkdir(parents=True)
    for path in (store.ACADEMIC,store.OPERATIONAL,database.DB_PATH):
        with closing(store.connect(path)) as source,closing(sqlite3.connect(backup/path.name)) as target:source.backup(target)
    with closing(store.connect(store.OPERATIONAL)) as c,c:
        c.execute('CREATE TEMP TABLE remover(id INTEGER PRIMARY KEY)')
        c.executemany('INSERT INTO remover VALUES (?)',[(i,) for i in remove])
        c.execute('CREATE TEMP TABLE chamados_remover AS SELECT id FROM gestao_chamados WHERE aluno_id IN (SELECT id FROM remover)')
        for table in ('gestao_simulacoes','gestao_eventos','gestao_acoes'):
            c.execute('DELETE FROM '+table+' WHERE chamado_id IN (SELECT id FROM chamados_remover)')
        c.execute('DELETE FROM gestao_chamados WHERE id IN (SELECT id FROM chamados_remover)')
        for table in ('avaliacoes_sim','mensagens','comandos','sessoes','povoamento_universidades'):
            c.execute('DELETE FROM '+table+' WHERE aluno_id IN (SELECT id FROM remover)')
    with closing(store.connect(store.ACADEMIC)) as c,c:
        c.execute('CREATE TEMP TABLE remover(id INTEGER PRIMARY KEY)')
        c.executemany('INSERT INTO remover VALUES (?)',[(i,) for i in remove])
        c.execute('DELETE FROM alunos WHERE id IN (SELECT id FROM remover)')
    with closing(store.connect(store.ACADEMIC,True)) as c:
        after={r['id']:dict(r) for r in c.execute('SELECT * FROM alunos')}
    if after!=untouched:raise RuntimeError('Divergência na preservação dos outros cadastros.')
    result=dict(alunos_gerados_restantes=len(keep),removidos_do_lote=len(remove),
                por_campus=dict(counts),registros_anteriores_preservados=True,total_cadastro_ficticio=len(after),backup=str(backup))
    output=ROOT/'validacao/povoamento_universidades/reducao.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
