"""Povoa os três câmpus com dados fictícios identificados, sem substituir registros."""
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid5,NAMESPACE_URL

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RADACHE_Modulo_Alunos/backend'))
import simulation_store as store,database,course_catalog,rbac,risk_history
from risk import calcular_indice_risco,calcular_financeiro,calcular_psicologico,classificar_risco
from aluno_service import AlunoService

GROUPS={
 'A':[(2,50,4,1),(1,30,4,1),(0,0,4,1)],
 'M':[(2,50,4,1),(4,65,3,2),(5.5,70,3,3)],
 'B':[(7.5,80,2,4),(8.5,90,1,4),(9,96,1,5)],
 'N':[]}
FIRST=['Ana','Lucas','Beatriz','Rafael','Mariana','Pedro','Camila','Gabriel','Isabela','Matheus']
LAST=['Ribeiro Costa','Almeida Rocha','Lima Souza','Mendes Castro','Pereira Silva','Oliveira Duarte']
dump=lambda value:json.dumps(value,ensure_ascii=False)
ident=lambda value:str(uuid5(NAMESPACE_URL,'radache:povoamento-universidades:v1:'+value))


def populate():
    store.init()
    now=datetime.now(timezone.utc).replace(day=5,hour=14,minute=0,second=0,microsecond=0)
    start=store.months(now.isoformat(),-2)
    if now>datetime.now(timezone.utc):start=store.months(start,-1)
    stamps=[store.months(start,i) for i in range(3)]
    with closing(store.connect(store.OPERATIONAL)) as c,c:
        c.execute('CREATE TABLE IF NOT EXISTS povoamento_universidades (matricula TEXT PRIMARY KEY,aluno_id INTEGER NOT NULL,versao INTEGER NOT NULL)')
        done={r[0] for r in c.execute('SELECT matricula FROM povoamento_universidades')}
    with closing(store.connect(store.ACADEMIC,True)) as c:
        old=[dict(r) for r in c.execute('SELECT * FROM alunos ORDER BY id')]
    with closing(store.connect(store.OPERATIONAL,True)) as c:
        old_evaluations=[tuple(r) for r in c.execute('SELECT sessao_id,dados FROM avaliacoes_sim ORDER BY rowid')]
    existing={a['matricula'].upper():a for a in old};plans=[];created=0
    for ci,(campus,campus_name) in enumerate(rbac.CAMPI.items()):
        code=['CA','VG','CB'][ci]
        for course_n,course in enumerate(course_catalog.COURSES,1):
            # Lote leve: quatro grupos de cinco, totalizando 20 por câmpus.
            if course!='Ciência da Computação':continue
            for group,path in GROUPS.items():
                for n in range(1,6):
                    registration=f'UNIV26-{code}{course_n:02d}{group}{n:02d}'
                    if registration in done:continue
                    email=registration.lower()+'@universidades.radache.test'
                    prior=existing.get(registration)
                    if prior and prior.get('email')!=email:continue
                    grade,attendance=(path[-1][0],path[-1][1]) if path else (None,None)
                    name=f'DEMO {FIRST[(course_n+n+ci)%len(FIRST)]} {LAST[(course_n+n)%len(LAST)]} {code}-{course_n:02d}{group}{n:02d}'
                    student=dict(nome=name,matricula=registration,curso=course,campus=campus_name,periodo=1,status='ativo',
                                 email=email,telefone='',nota_media=grade,frequencia=attendance,data_cadastro=start)
                    AlunoService._validar({k:v for k,v in student.items() if v is not None},('nome','matricula','curso'))
                    plans.append((student,prior,group,path,course_n,ci))
    backup=None
    if plans:
        backup=ROOT.parent/'ARQUIVO/backups/versao_local'/('backup_povoamento_'+datetime.now().strftime('%Y%m%d_%H%M%S'));backup.mkdir(parents=True)
        for path in (store.ACADEMIC,store.OPERATIONAL,database.DB_PATH):
            with closing(store.connect(path)) as source,closing(sqlite3.connect(backup/path.name)) as target:source.backup(target)
    with closing(store.connect(store.ACADEMIC)) as c,c:
        for student,prior,*_ in plans:
            if prior:student['id']=prior['id'];continue
            fields=list(student)
            student['id']=c.execute('INSERT INTO alunos ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',[student[k] for k in fields]).lastrowid
            created+=1
    states=('aberto','em_andamento','aguardando_aluno','resolvido')
    with closing(store.connect(store.OPERATIONAL)) as c,c:
        for student,prior,group,path,course_n,ci in plans:
            aid=student['id'];registration=student['matricula'];previous=None;session_ids=[]
            for cycle,(grade,attendance,finance,emotion) in enumerate(path):
                stamp=stamps[cycle];sid=ident(registration+':sessao:'+str(cycle));session_ids.append(sid)
                state=dict(timestamp=stamp,consentimento=True,dataConsentimento=start,diaCalendario=5,etapa='concluido',
                    financeira=finance,emocional=emotion,concluidoMes=stamp[:7],ultimaInteracao=stamp,lembreteEnviado=False,demonstracao=True)
                c.execute('INSERT OR IGNORE INTO sessoes(id,aluno_id,estado,criado_em) VALUES (?,?,?,?)',(sid,aid,dump(state),stamp))
                evaluation=dict(data_avaliacao=stamp,nota_media=grade,frequencia=attendance,resposta_financeira=store.FIN[finance-1],resposta_psicologica=emotion)
                score=calcular_indice_risco(grade,attendance,evaluation['resposta_financeira'],emotion)
                situation=lambda v:'estavel' if v<=33 else 'moderada' if v<67 else 'critica'
                evaluation.update(indice_risco=score,classificacao_risco=classificar_risco(score),
                    situacao_financeira=situation(calcular_financeiro(evaluation['resposta_financeira'])),situacao_psicologica=situation(calcular_psicologico(emotion)),demonstracao=True)
                evaluation['metadados_risco']=risk_history.snapshot(evaluation,previous,'povoamento_demonstrativo',sid)
                c.execute('INSERT OR IGNORE INTO avaliacoes_sim VALUES (?,?,?)',(sid,aid,dump(evaluation)));previous=evaluation
                messages=[('sistema','Demonstração: aluno e respostas inteiramente fictícios.',None,False),('aluno','1','consentimento',False),
                    ('sistema',store.TEXTS['financeira'],'financeira',False),('aluno',str(finance),'financeira',True),
                    ('sistema',store.TEXTS['emocional'],'emocional',False),('aluno',str(emotion),'emocional',True),('sistema',store.TEXTS['encerramento'],None,False)]
                for mi,(sender,text,question,sensitive) in enumerate(messages):
                    mid=ident(sid+':mensagem:'+str(mi))
                    c.execute('INSERT OR IGNORE INTO mensagens VALUES (?,?,?,?,?,?,?,?)',(mid,sid,aid,sender,text,stamp,question,int(sensitive)))
            if path:
                tid='sim-'+ident(registration+':atendimento');status=states[(course_n+ci+list(GROUPS).index(group))%4]
                resolved=status=='resolvido';end=stamps[-1]
                ticket=dict(id=tid,alunoId=str(-aid),cursoId=course_catalog.course_id(student['curso']),protocolo=registration.replace('UNIV26','UNI'),
                    titulo='DEMO · Acompanhamento acadêmico',descricao='Dados fictícios criados para demonstração dos três câmpus. Não houve contato com uma pessoa real.',
                    origem='whatsapp_simulado',status=status,categoria='academico',responsavel=None if status=='aberto' else {'uid':'admin','nome':'Administrador Técnico · Demonstração'},
                    abertoEm=start,ultimaAtividadeEm=end,tempoResolucaoMin=round((datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()/60) if resolved else None,
                    resolvidoEm=end if resolved else None,encerradoPor='equipe' if resolved else None,demonstracao=True)
                if status=='aguardando_aluno':ticket['aguardandoAlunoEm']=end
                c.execute('INSERT OR IGNORE INTO gestao_chamados VALUES (?,?,?)',(tid,aid,dump(ticket)))
                for cycle,sid in enumerate(session_ids):
                    c.execute('INSERT OR IGNORE INTO gestao_simulacoes VALUES (?,?)',(sid,tid))
                    event=dict(id=ident(tid+':evento:'+str(cycle)),tipo='abertura' if not cycle else 'questionario',texto='DEMO · Questionário fictício registrado para demonstrar evolução dos indicadores.',
                               criadoEm=stamps[cycle],autor={'nome':'RADACHE · Dados fictícios'},visivelAoAluno=False,sessaoId=sid)
                    c.execute('INSERT OR IGNORE INTO gestao_eventos VALUES (?,?,?)',(event['id'],tid,dump(event)))
                if status!='aberto':
                    event=dict(id=ident(tid+':acao'),tipo='encerramento' if resolved else 'acao',texto='DEMO · '+{'em_andamento':'Acompanhamento em andamento.','aguardando_aluno':'Aguardando retorno do aluno.','resolvido':'Atendimento concluído; o risco permanece independente do status.'}[status],
                               criadoEm=end,autor={'uid':'admin','nome':'Administrador Técnico · Demonstração'},visivelAoAluno=False)
                    c.execute('INSERT OR IGNORE INTO gestao_eventos VALUES (?,?,?)',(event['id'],tid,dump(event)))
            c.execute('INSERT OR IGNORE INTO povoamento_universidades VALUES (?,?,1)',(registration,aid))
    # Conferência curta dos dados gravados, sem executar bateria de testes.
    with closing(store.connect(store.ACADEMIC,True)) as c:
        for a in old:
            if dict(c.execute('SELECT * FROM alunos WHERE id=?',(a['id'],)).fetchone())!=a:raise RuntimeError('Cadastro anterior alterado.')
        rows=c.execute("SELECT campus,COUNT(*) n,COUNT(DISTINCT curso) courses FROM alunos WHERE matricula LIKE 'UNIV26-%' GROUP BY campus").fetchall()
    with closing(store.connect(store.OPERATIONAL,True)) as c:
        for sid,data in old_evaluations:
            if c.execute('SELECT dados FROM avaliacoes_sim WHERE sessao_id=?',(sid,)).fetchone()[0]!=data:raise RuntimeError('Avaliação anterior alterada.')
    result=dict(novos_alunos=created,campus=[dict(r) for r in rows],avaliacoes_criadas=sum(len(p[3]) for p in plans),
                atendimentos_criados=sum(bool(p[3]) for p in plans),registros_anteriores_preservados=True,backup=str(backup) if backup else None)
    out=ROOT/'validacao/povoamento_universidades';out.mkdir(parents=True,exist_ok=True)
    (out/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)


if __name__=='__main__':populate()
