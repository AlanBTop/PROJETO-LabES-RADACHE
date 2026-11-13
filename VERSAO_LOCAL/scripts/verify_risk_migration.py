"""Registra e compara avaliações da instalação antes/depois da migração, sem escrita nos bancos."""
from contextlib import closing
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import database,simulation_store as store


def state():
    with closing(store.connect(database.DB_PATH,True)) as c:
        columns='id,aluno_id,nota_media,frequencia,situacao_financeira,situacao_psicologica,indice_risco,classificacao_risco,data_avaliacao'
        legacy=[dict(r) for r in c.execute('SELECT '+columns+' FROM avaliacoes ORDER BY id')]
    with closing(store.connect(store.OPERATIONAL,True)) as c:
        operational=[dict(r) for r in c.execute('SELECT * FROM avaliacoes_sim ORDER BY rowid')]
    with closing(store.connect(store.ACADEMIC,True)) as c:
        students=[dict(r) for r in c.execute('SELECT * FROM alunos ORDER BY id')]
    def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return dict(avaliacoes_originais=len(legacy),avaliacoes_simuladas=len(operational),alunos_ficticios=len(students),
                hash_avaliacoes_originais=digest(legacy),hash_avaliacoes_simuladas=digest(operational),hash_cadastro_ficticio=digest(students))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path);parser.add_argument('--verify',type=Path)
    args=parser.parse_args();current=state()
    if args.verify:
        previous=json.loads(args.verify.read_text(encoding='utf-8'))
        if previous!=current:raise SystemExit('Dados anteriores divergiram; confira a migração antes de continuar.')
        print('OK avaliações e cadastro preservados integralmente.')
    if args.snapshot:
        args.snapshot.parent.mkdir(parents=True,exist_ok=True)
        args.snapshot.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(current,ensure_ascii=True))
