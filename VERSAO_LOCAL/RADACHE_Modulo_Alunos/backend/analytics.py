"""Modelo de leitura analítico local. Não altera cadastro, risco, mensagens ou atendimentos."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import math
import unicodedata
import database
import course_catalog
import risk_history
import rbac
import simulation_store as store
from risk import classificar_risco, calcular_nota, calcular_frequencia, calcular_financeiro, calcular_psicologico

LEVELS=('alto','medio','baixo','sem_avaliacao')
LABELS={'alto':'Risco alto','medio':'Risco médio','baixo':'Risco baixo','sem_avaliacao':'Sem avaliação'}
CLASS={'critico':'alto','moderado':'medio','estavel':'baixo'}
STATUSES={'aberto','em_andamento','aguardando_aluno','resolvido','sem_atendimento','sem_resposta','respondido','sem_avaliacao'}


def date(value):
    if not value:return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (TypeError,ValueError):return None


def valid_index(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<=value<=100


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFD',str(value)) if not unicodedata.combining(c)).casefold()


def pct(n,d):return round(n/d*100,1) if d else None


def source():
    """Leitura em lote nos três arquivos. IDs negativos distinguem o catálogo fictício."""
    students=[];tickets=[];events=defaultdict(list)
    if database.DB_PATH.exists():
        with closing(store.connect(database.DB_PATH,True)) as c:
            academic=[dict(r) for r in c.execute('SELECT * FROM alunos WHERE status_exclusao=0').fetchall()]
            evaluations=defaultdict(list);checkins=defaultdict(list)
            for r in c.execute('SELECT * FROM avaliacoes').fetchall():evaluations[r['aluno_id']].append(dict(r))
            for r in c.execute('SELECT * FROM checkins').fetchall():checkins[r['aluno_id']].append(dict(r))
            for a in academic:students.append({**a,'avaliacoes':evaluations[a['id']],'checkins':checkins[a['id']]})
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if 'gestao_chamados' in tables:
                tickets.extend(json.loads(r[0]) for r in c.execute('SELECT dados FROM gestao_chamados').fetchall())
                for r in c.execute('SELECT chamado_id,dados FROM gestao_eventos').fetchall():events[r[0]].append(json.loads(r[1]))
    academic=store.students()
    evaluations=defaultdict(list);checkins=defaultdict(list)
    if store.OPERATIONAL.exists():
        with closing(store.connect(store.OPERATIONAL,True)) as c:
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if 'avaliacoes_sim' in tables:
                for r in c.execute('SELECT aluno_id,sessao_id,dados FROM avaliacoes_sim ORDER BY rowid').fetchall():
                    evaluations[r['aluno_id']].append(dict(id=r['sessao_id'],**json.loads(r['dados'])))
                for r in c.execute('SELECT id,aluno_id,estado FROM sessoes ORDER BY rowid').fetchall():
                    checkins[r['aluno_id']].append(dict(id=r['id'],**json.loads(r['estado'])))
            if 'gestao_chamados' in tables:
                tickets.extend(json.loads(r[0]) for r in c.execute('SELECT dados FROM gestao_chamados').fetchall())
                for r in c.execute('SELECT chamado_id,dados FROM gestao_eventos').fetchall():events[r[0]].append(json.loads(r[1]))
    for a in students:
        a['avaliacoes'].extend(evaluations[-a['id']])
        a['checkins'].extend(dict(q,_simulacao=True) for q in checkins[-a['id']])
    for a in academic:students.append({**a,'id':-a['id'],'avaliacoes':evaluations[a['id']],'checkins':checkins[a['id']]})
    by_student=defaultdict(list)
    for ticket in tickets:
        try:aid=int(ticket['alunoId'])
        except (KeyError,ValueError,TypeError):continue
        ticket={**ticket,'eventos':sorted(events[ticket['id']],key=lambda e:date(e.get('criadoEm')) or datetime.min.replace(tzinfo=timezone.utc))}
        by_student[aid].append(ticket)
    for a in students:
        a['curso']=course_catalog.canonical(a['curso'])
        a['campus']=a.get('campus') or 'Câmpus não informado'
        a['avaliacoes']=sorted([e for e in a['avaliacoes'] if date(e.get('data_avaliacao'))],key=lambda e:date(e['data_avaliacao']))
        completed=[]
        for q in a['checkins']:
            if a['id']<0 or q.get('_simulacao'):
                ok=q.get('etapa')=='concluido' and q.get('financeira') is not None and q.get('emocional') is not None
                when=q.get('timestamp')
                normalized=dict(id=q['id'],data=when,financeira=store.FIN[q['financeira']-1] if ok else None,emocional=q.get('emocional'))
            else:
                ok=q.get('consentimento_lgpd')==1 and q.get('estado_conversa')=='concluido' and bool(q.get('resposta_financeira')) and bool(q.get('resposta_psicologica'))
                when=q.get('data_checkin')
                normalized=dict(id=q['id'],data=when,financeira=q.get('resposta_financeira'),emocional=q.get('resposta_psicologica'))
            if ok and date(when):completed.append(normalized)
        a['respondidos']=sorted(completed,key=lambda q:date(q['data']))
        a['atendimentos']=sorted(by_student[a['id']],key=lambda t:date(t.get('ultimaAtividadeEm')) or datetime.min.replace(tzinfo=timezone.utc),reverse=True)
    return students


def filters(query):
    f={k:str(query.get(k,'')) for k in ('campus','curso','periodo','inicio','fim','risco','acompanhamento','alerta')}
    f['curso']=course_catalog.canonical(f['curso'])
    if any(len(v)>150 for v in f.values()):raise ValueError('Filtro muito longo.')
    if f['periodo']:
        try:p=int(f['periodo'])
        except ValueError:raise ValueError('Período inválido.') from None
        if not 1<=p<=16:raise ValueError('Período deve estar entre 1 e 16.')
    if f['risco'] and f['risco'] not in LEVELS:raise ValueError('Nível de risco inválido.')
    if f['acompanhamento'] and f['acompanhamento'] not in STATUSES:raise ValueError('Situação de acompanhamento inválida.')
    if f['alerta'] and f['alerta'] not in ('alto','subiu_para_alto','sem_resposta_recente','sem_primeiro_atendimento'):raise ValueError('Alerta inválido.')
    for key in ('inicio','fim'):
        if f[key]:
            try:datetime.strptime(f[key],'%Y-%m-%d')
            except ValueError:raise ValueError('Informe datas no formato AAAA-MM-DD.') from None
    if f['inicio'] and f['fim'] and f['inicio']>f['fim']:raise ValueError('A data inicial deve ser anterior à final.')
    return f


def within(value,f):
    d=date(value)
    if not d:return False
    day=d.date().isoformat()
    return (not f['inicio'] or day>=f['inicio']) and (not f['fim'] or day<=f['fim'])


def prepare(student,f):
    a={**student}
    a['historico_valido']=[e for e in a['avaliacoes'] if valid_index(e.get('indice_risco'))]
    a['avaliacoes_recorte']=[e for e in a['historico_valido'] if within(e['data_avaliacao'],f)]
    a['avaliacao']=a['avaliacoes_recorte'][-1] if a['avaliacoes_recorte'] else None
    a['risco']=CLASS[classificar_risco(a['avaliacao']['indice_risco'])] if a['avaliacao'] else 'sem_avaliacao'
    a['questionarios_recorte']=[q for q in a['respondidos'] if within(q['data'],f)]
    a['ultimo_questionario']=a['questionarios_recorte'][-1]['data'] if a['questionarios_recorte'] else None
    a['atendimentos_recorte']=[t for t in a['atendimentos'] if within(t.get('abertoEm'),f) or within(t.get('ultimaAtividadeEm'),f)]
    a['atendimento']=next((t for t in a['atendimentos_recorte'] if t['status']!='resolvido'),a['atendimentos_recorte'][0] if a['atendimentos_recorte'] else None)
    a['situacao_acompanhamento']=a['atendimento']['status'] if a['atendimento'] else 'sem_atendimento'
    a['recebeu_atendimento']=any(t.get('responsavel') or any(e.get('autor',{}).get('uid') for e in t['eventos']) for t in a['atendimentos_recorte'])
    last_two=a['avaliacoes_recorte'][-2:]
    a['subiu_para_alto']=len(last_two)==2 and CLASS[classificar_risco(last_two[0]['indice_risco'])]=='medio' and a['risco']=='alto'
    a['alto']=a['risco']=='alto'
    a['sem_resposta_recente']=not a['respondidos'] or date(a['respondidos'][-1]['data'])<datetime.now(timezone.utc)-timedelta(days=30)
    a['sem_primeiro_atendimento']=bool(a['questionarios_recorte']) and not a['recebeu_atendimento']
    return a


def matches(a,f):
    if f['campus'] and a['campus']!=f['campus']:return False
    if f['curso'] and a['curso']!=f['curso']:return False
    if f['periodo'] and str(a['periodo'])!=f['periodo']:return False
    if f['risco'] and a['risco']!=f['risco']:return False
    if f['alerta'] and (a['status']!='ativo' or not a[f['alerta']]):return False
    status=f['acompanhamento']
    if status=='sem_resposta' and a['questionarios_recorte']:return False
    if status=='respondido' and not a['questionarios_recorte']:return False
    if status=='sem_avaliacao' and a['risco']!='sem_avaliacao':return False
    if status in {'aberto','em_andamento','aguardando_aluno','resolvido','sem_atendimento'} and a['situacao_acompanhamento']!=status:return False
    return True


def metrics(students):
    eligible=[a for a in students if a['status']=='ativo']
    counts=Counter(a['risco'] for a in eligible)
    assessed=len(eligible)-counts['sem_avaliacao']
    responded=sum(bool(a['questionarios_recorte']) for a in eligible)
    return dict(cadastrados=len(students),elegiveis=len(eligible),cursos=len({(a['campus'],a['curso']) for a in students}),
        **{k:counts[k] for k in LEVELS},avaliados=assessed,
        cobertura_avaliacao=pct(assessed,len(eligible)),cobertura_questionario=pct(responded,len(eligible)),
        alto_pct_total=pct(counts['alto'],len(eligible)),alto_pct_avaliados=pct(counts['alto'],assessed),
        sem_avaliacao_pct=pct(counts['sem_avaliacao'],len(eligible)),sem_resposta=len(eligible)-responded,
        checkins=sum(len(a['questionarios_recorte']) for a in students),atendimentos=sum(len(a['atendimentos_recorte']) for a in students))


def factors(students,role):
    samples=defaultdict(list)
    for a in students:
        if a['status']!='ativo':continue
        assessment=a['avaliacao'] or {}
        q=a['questionarios_recorte'][-1] if a['questionarios_recorte'] else {}
        values=[('notas',assessment.get('nota_media'),calcular_nota),('frequencia',assessment.get('frequencia'),calcular_frequencia),
            ('financeiro',assessment.get('resposta_financeira') or q.get('financeira') or assessment.get('situacao_financeira'),calcular_financeiro),
            ('emocional',assessment.get('resposta_psicologica') or q.get('emocional'),calcular_psicologico)]
        for key,value,func in values:
            if value is None:continue
            try:samples[key].append(func(value))
            except (TypeError,ValueError):pass
    names={'notas':'Desempenho acadêmico','frequencia':'Frequência','financeiro':'Situação financeira','emocional':'Bem-estar emocional'}
    return [dict(chave=k,nome=label,amostra=len(samples[k]),media=round(sum(samples[k])/len(samples[k]),1) if samples[k] else None)
            for k,label in names.items() if role=='coordenacao' or k=='emocional']


def evolution(students,f):
    observed={date(e['data_avaliacao']).strftime('%Y-%m') for a in students for e in a['avaliacoes_recorte']}
    months=sorted(observed|{date(q['data']).strftime('%Y-%m') for a in students for q in a['questionarios_recorte']})[-24:]
    points=[]
    for month in months:
        counts=Counter();checkins=0
        for a in students:
            checkins+=sum(date(q['data']).strftime('%Y-%m')==month for q in a['questionarios_recorte'])
            if a['status']!='ativo':continue
            history=[e for e in a['historico_valido'] if date(e['data_avaliacao']).strftime('%Y-%m')<=month]
            created=date(a.get('data_cadastro'))
            if not history and created and created.strftime('%Y-%m')>month:continue
            counts[CLASS[classificar_risco(history[-1]['indice_risco'])] if history else 'sem_avaliacao']+=1
        points.append(dict(mes=month,checkins=checkins,**{k:counts[k] for k in LEVELS}))
    return dict(pontos=points,suficiente=len(observed)>=2,
        nota='Coorte atual dos filtros; última avaliação válida conhecida ao final de cada mês com registros. Até 24 meses observados. Não representa evasão efetiva.')


def student_row(a):
    assessment=a['avaliacao']
    ticket=a['atendimento']
    evolution=risk_history.describe(a['avaliacoes_recorte'])
    return dict(id=a['id'],nome=a['nome'],matricula=a['matricula'],curso=a['curso'],campus=a['campus'],periodo=a['periodo'],status=a['status'],
        risco=a['risco'],indice=assessment['indice_risco'] if assessment else None,
        ultima_avaliacao=assessment['data_avaliacao'] if assessment else None,ultimo_acompanhamento=a['ultimo_questionario'],
        situacao=a['situacao_acompanhamento'],atendimento_id=ticket['id'] if ticket else None,
        questionarios=len(a['questionarios_recorte']),subiu_para_alto=a['subiu_para_alto'],recebeu_atendimento=a['recebeu_atendimento'],
        evolucao_risco={k:evolution[k] for k in ('direcao','variacao')})


def overview(query,role='coordenacao',scope=None):
    f=filters(query);all_students=source()
    if scope:
        scoped_user=dict(perfil='diretor_campus' if scope['cursoIds'] is None else 'gestor_curso',**scope)
        all_students=[a for a in all_students if rbac.student_allowed(scoped_user,a)]
    prepared=[prepare(a,f) for a in all_students]
    selected=[a for a in prepared if matches(a,f)]
    groups=defaultdict(list)
    for a in selected:groups[(a['campus'],a['curso'])].append(a)
    # Mantém cursos sem alunos neste recorte visíveis, com ausência de dados explícita.
    catalog_pairs={(course_catalog.DEFAULT_CAMPUS,n) for n in course_catalog.COURSES}
    if scope:
        catalog_pairs={(rbac.CAMPI[scope['campusId']],n) for n in course_catalog.COURSES if scope['cursoIds'] is None or course_catalog.course_id(n) in scope['cursoIds']}
    catalog_pairs.update((a['campus'],a['curso']) for a in all_students)
    pairs={(campus,course) for campus,course in catalog_pairs
           if (not f['campus'] or campus==f['campus']) and (not f['curso'] or course==f['curso'])}
    if f['curso'] and not pairs:pairs.add((f['campus'] or 'Câmpus de Cáceres',f['curso']))
    courses=[]
    for campus,course in pairs:
        rows=groups[(campus,course)]
        dates=[a['ultimo_questionario'] for a in rows if a['ultimo_questionario']]
        courses.append(dict(campus=campus,nome=course,**metrics(rows),ultimo_acompanhamento=max(dates,key=date) if dates else None))
    sort=query.get('ordenacao','alto_pct')
    sorts={'alto_pct':lambda c:(-(c['alto_pct_total'] or 0),-c['sem_avaliacao'],norm(c['nome'])),
        'risco_total':lambda c:(-(c['alto']+c['medio']),norm(c['nome'])),
        'sem_avaliacao':lambda c:(-c['sem_avaliacao'],norm(c['nome'])),'nome':lambda c:norm(c['nome'])}
    if sort not in sorts:raise ValueError('Ordenação de cursos inválida.')
    courses.sort(key=sorts[sort])
    totals=metrics(selected)
    totals['cursos']=len(pairs)
    eligible=[a for a in selected if a['status']=='ativo']
    directions=Counter(risk_history.describe(a['avaliacoes_recorte'])['direcao'] for a in eligible)
    cutoff=datetime.now(timezone.utc)-timedelta(days=30)
    alerts=dict(alto=sum(a['risco']=='alto' for a in eligible),subiu_para_alto=sum(a['subiu_para_alto'] for a in eligible),
        sem_resposta_recente=sum(not a['respondidos'] or date(a['respondidos'][-1]['data'])<cutoff for a in eligible),
        sem_primeiro_atendimento=sum(bool(a['questionarios_recorte']) and not a['recebeu_atendimento'] for a in eligible))
    periods=[dict(periodo=p,**metrics([a for a in selected if a['periodo']==p])) for p in sorted({a['periodo'] for a in selected})]
    students=[]
    if f['curso']:
        students=[student_row(a) for a in selected]
        search=norm(query.get('busca',''))
        students=[a for a in students if search in norm(a['nome']+' '+a['matricula'])]
        order=query.get('ordenar_alunos','risco')
        orders={'risco':lambda a:(LEVELS.index(a['risco']),-(a['indice'] or 0),norm(a['nome'])),
            'nome':lambda a:norm(a['nome']),'periodo':lambda a:(a['periodo'],norm(a['nome'])),
            'recente':lambda a:-(date(a['ultimo_acompanhamento']).timestamp() if a['ultimo_acompanhamento'] else 0)}
        if order not in orders:raise ValueError('Ordenação de estudantes inválida.')
        students.sort(key=orders[order])
    try:page=int(query.get('pagina',1));limit=int(query.get('limite',8))
    except (TypeError,ValueError):raise ValueError('Paginação inválida.') from None
    if page<1 or not 1<=limit<=50:raise ValueError('Paginação inválida.')
    pages=max(1,math.ceil(len(students)/limit));page=min(page,pages)
    return dict(atualizado_em=datetime.now(timezone.utc).isoformat(),perfil=role,filtros=f,kpis=totals,cursos=courses,periodos=periods,
        mudancas_risco={key:directions[key] for key in ('diminuiu','aumentou','estavel','inicial','sem_avaliacao')},
        distribuicao=[dict(chave=k,nome=LABELS[k],quantidade=totals[k],percentual=pct(totals[k],totals['elegiveis'])) for k in LEVELS],
        fatores=factors(selected,role),evolucao=evolution(selected,f),alertas=alerts,
        estudantes=dict(itens=students[(page-1)*limit:page*limit],total=len(students),pagina=page,paginas=pages),
        opcoes=dict(campus=sorted({c for c,n in catalog_pairs}),
            cursos=[dict(campus=c,nome=n) for c,n in sorted(catalog_pairs)],
            periodos=sorted({a['periodo'] for a in all_students})),
        definicoes=dict(elegiveis='Alunos com situação acadêmica ativa. Risco e cobertura usam este denominador.',
            avaliacao='Última avaliação numérica válida registrada dentro do intervalo de datas selecionado.',
            percentuais='Alto risco no total = alto / ativos. Alto risco entre avaliados = alto / ativos com avaliação válida.',
            resposta='Questionário consentido e concluído; uma sessão é contada uma única vez. Sem resposta considera o intervalo selecionado.',
            fatores='Média dos componentes normalizados pela regra risk.py; cada fator informa seu número de observações. Não é prevalência de problemas pessoais.'))


def detail(ident,role='coordenacao',scope=None):
    student=next((a for a in source() if a['id']==ident),None)
    if not student:return None
    if scope and not rbac.student_allowed(dict(perfil='diretor_campus' if scope['cursoIds'] is None else 'gestor_curso',**scope),student):return None
    a=prepare(student,filters({}));result=student_row(a)
    history=a['historico_valido']
    result['historico_avaliacoes']=[{k:v for k,v in e.items() if role=='coordenacao' or k in {'data_avaliacao','indice_risco','classificacao_risco','situacao_psicologica'}} for e in history]
    result['questionarios']=[q if role=='coordenacao' else {k:v for k,v in q.items() if k!='financeira'} for q in a['respondidos']]
    result['atendimentos']=[{k:v for k,v in t.items() if k in {'id','protocolo','status','abertoEm','ultimaAtividadeEm','responsavel'} or role=='coordenacao'} for t in a['atendimentos']]
    result['variacao']=round(history[-1]['indice_risco']-history[-2]['indice_risco'],2) if len(history)>=2 else None
    result['evolucao_risco']=risk_history.describe(a['avaliacoes'],role)
    result['atual']=a['avaliacao'] if role=='coordenacao' else ({k:v for k,v in (a['avaliacao'] or {}).items() if k in {'data_avaliacao','indice_risco','classificacao_risco','situacao_psicologica'}} or None)
    return result
