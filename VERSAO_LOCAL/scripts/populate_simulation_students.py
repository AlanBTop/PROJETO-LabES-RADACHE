"""Acrescenta perfis fictícios variados, sem sobrescrever os cadastros existentes."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import simulation_store as store

PROFILES=[
 ('Ana Clara Monteiro','Ciência da Computação',4,8.7,94,'ativo'),
 ('Lucas Henrique Vidal','Ciência da Computação',6,6.2,73,'ativo'),
 ('Beatriz Costa Andrade','Pedagogia',3,9.1,98,'ativo'),
 ('Rafael Almeida Torres','Direito',7,7.8,88,'ativo'),
 ('Mariana Ribeiro Campos','Enfermagem',5,8.4,92,'ativo'),
 ('Pedro Augusto Lemos','Agronomia',2,7.3,85,'ativo'),
 ('Camila Duarte Freitas','Administração',4,8.0,90,'ativo'),
 ('Gabriel Rocha Nunes','Ciência da Computação',2,5.8,68,'ativo'),
 ('Isabela Martins Pires','Pedagogia',6,8.9,96,'ativo'),
 ('Matheus Silva Peixoto','Direito',3,7.1,81,'ativo'),
 ('Larissa Mendes Farias','Enfermagem',8,9.3,97,'ativo'),
 ('Felipe Cardoso Brito','Agronomia',5,6.5,76,'ativo'),
 ('Sofia Azevedo Moura','Administração',1,None,None,'ativo'),
 ('Thiago Fernandes Reis','Ciência da Computação',5,6.0,71,'trancado'),
 ('Júlia Nogueira Tavares','Pedagogia',4,7.4,83,'inativo'),
 ('Bruno Teixeira Macedo','Direito',10,8.6,95,'formado'),
]


def populate():
    store.init()
    existing={a['matricula'] for a in store.students()}
    created=0
    for i,(name,course,period,average,attendance,status) in enumerate(PROFILES,1):
        registration=f'DEMO-2026-{i:03d}'
        if registration in existing:
            continue
        store.save(dict(nome=name,matricula=registration,curso=course,periodo=period,
            nota_media=average,frequencia=attendance,status=status,email=f'aluno.demo{i:02d}@radache.test',telefone=''))
        created+=1
    return created


if __name__=='__main__':
    created=populate()
    print(f'{created} alunos fictícios adicionados; {len(store.students())} cadastros no total. Nenhum cadastro existente foi alterado.')
