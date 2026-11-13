"""Leitura institucional agregada em SQL, com coortes fixas e supressão complementar."""
from collections import defaultdict
from contextlib import closing
from datetime import date
import calendar
import json
import re
import sqlite3
from urllib.parse import parse_qs,urlsplit
import database
import simulation_store as store
import course_catalog
import rbac

K=5
MIN_COHORT=10
RISKS=('alto','medio','baixo','sem_avaliacao')
COURSES={c['id']:c['nome'] for c in course_catalog.catalog()}
COURSES['outros']='Outros cursos de cadastros anteriores'


def course_key(value):
    ident=course_catalog.course_id(value)
    return ident if ident in COURSES else 'outros'


def filters(query):
    if set(query)-{'campus','curso','periodo','inicio','fim','risco'}:raise ValueError('Filtro não permitido na análise institucional.')
    f={k:str(query.get(k,'')) for k in ('campus','curso','periodo','inicio','fim','risco')}
    if f['campus'] and f['campus'] not in rbac.CAMPI:raise ValueError('Câmpus inválido.')
    if f['curso'] and f['curso'] not in COURSES:raise ValueError('Curso inválido.')
    if f['risco'] and f['risco'] not in RISKS:raise ValueError('Risco inválido.')
    if f['periodo']:
        if not re.fullmatch(r'\d{4}-[12]',f['periodo']):raise ValueError('Período deve ser ano e semestre civil: AAAA-1 ou AAAA-2.')
        if f['inicio'] or f['fim']:raise ValueError('Use o semestre civil ou o intervalo mensal, sem combiná-los.')
        year,semester=map(int,f['periodo'].split('-'))
        f['inicio']=f'{year:04d}-{1 if semester==1 else 7:02d}'
        f['fim']=f'{year:04d}-{6 if semester==1 else 12:02d}'
    for key in ('inicio','fim'):
        if f[key]:
            if not re.fullmatch(r'\d{4}-\d{2}',f[key]):raise ValueError('Intervalos institucionais usam meses completos, no formato AAAA-MM.')
            year,month=map(int,f[key].split('-'));date(year,month,1)
    if f['inicio'] and f['fim'] and f['inicio']>f['fim']:raise ValueError('Intervalo inválido.')
    return f


def connect():
    c=sqlite3.connect(':memory:',uri=True);c.row_factory=sqlite3.Row
    for name,path in [('academic',store.ACADEMIC),('legacy',database.DB_PATH),('operations',store.OPERATIONAL)]:
        c.execute('ATTACH DATABASE ? AS '+name,(path.resolve().as_uri()+'?mode=ro',))
    c.create_function('campus_key',1,lambda s:rbac.campus_id(s) or 'fora_catalogo',deterministic=True)
    c.create_function('course_key',1,course_key,deterministic=True)
    return c


CTE='''WITH
 students AS (
  SELECT id sid,campus_key(campus) campus,course_key(curso) curso,periodo,status,data_cadastro FROM legacy.alunos WHERE status_exclusao=0
  UNION ALL SELECT -id,campus_key(campus),course_key(curso),periodo,status,data_cadastro FROM academic.alunos),
 evaluations AS (
  SELECT aluno_id sid,data_avaliacao stamp,indice_risco score,0 source,id seq FROM legacy.avaliacoes
  UNION ALL SELECT -aluno_id,json_extract(dados,'$.data_avaliacao'),json_extract(dados,'$.indice_risco'),1,rowid FROM operations.avaliacoes_sim),
 questions AS (
  SELECT aluno_id sid,data_checkin stamp FROM legacy.checkins WHERE consentimento_lgpd=1 AND estado_conversa='concluido' AND resposta_financeira IS NOT NULL AND resposta_psicologica IS NOT NULL
  UNION ALL SELECT -aluno_id,json_extract(estado,'$.timestamp') FROM operations.sessoes WHERE json_extract(estado,'$.etapa')='concluido' AND json_extract(estado,'$.financeira') IS NOT NULL AND json_extract(estado,'$.emocional') IS NOT NULL),
 tickets AS (
  SELECT CAST(json_extract(dados,'$.alunoId') AS INTEGER) sid,json_extract(dados,'$.abertoEm') opened,json_extract(dados,'$.resolvidoEm') resolved FROM legacy.gestao_chamados
  UNION ALL SELECT CAST(json_extract(dados,'$.alunoId') AS INTEGER),json_extract(dados,'$.abertoEm'),json_extract(dados,'$.resolvidoEm') FROM operations.gestao_chamados)
'''


def months(c,f):
    rows=c.execute(CTE+'''SELECT DISTINCT substr(stamp,1,7) month FROM
       (SELECT stamp FROM evaluations UNION ALL SELECT stamp FROM questions UNION ALL SELECT opened FROM tickets)
       WHERE julianday(stamp) IS NOT NULL ORDER BY month''').fetchall()
    observed=[r[0] for r in rows if r[0] and (not f['inicio'] or r[0]>=f['inicio']) and (not f['fim'] or r[0]<=f['fim'])]
    return observed[-24:] or [f['fim'] or f['inicio'] or date.today().strftime('%Y-%m')]


def atoms(c,month):
    year,m=map(int,month.split('-'));start=month+'-01';end=month+f'-{calendar.monthrange(year,m)[1]:02d}'
    sql=CTE+''', ranked AS (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY sid ORDER BY julianday(stamp) DESC,source DESC,seq DESC) rn
      FROM evaluations WHERE typeof(score) IN ('integer','real') AND score BETWEEN 0 AND 100 AND julianday(stamp) IS NOT NULL AND date(stamp)<=:end),
    qs AS (SELECT sid,COUNT(*) covered,SUM(CASE WHEN date(stamp)>=:start THEN 1 ELSE 0 END) amount FROM questions WHERE date(stamp)<=:end GROUP BY sid),
    ts AS (SELECT sid,SUM(CASE WHEN date(opened) BETWEEN :start AND :end THEN 1 ELSE 0 END) amount,
      SUM(CASE WHEN date(resolved) BETWEEN :start AND :end THEN 1 ELSE 0 END) resolved FROM tickets GROUP BY sid),
    facts AS (
      SELECT s.campus,s.curso,s.periodo,s.status,
       CASE WHEN s.status!='ativo' THEN 'inativo' WHEN e.score IS NULL THEN 'sem_avaliacao' WHEN e.score>=67 THEN 'alto' WHEN e.score>33 THEN 'medio' ELSE 'baixo' END risk,
       CASE WHEN e.score IS NULL OR p.score IS NULL THEN 'sem_comparacao' WHEN e.score<p.score THEN 'diminuiu' WHEN e.score>p.score THEN 'aumentou' ELSE 'estavel' END direction,
       CASE WHEN q.covered>0 THEN 1 ELSE 0 END responded,
       CASE WHEN COALESCE(t.amount,0)+COALESCE(t.resolved,0)>0 THEN 1 ELSE 0 END attended,
       COALESCE(q.amount,0) questions,COALESCE(t.amount,0) tickets,COALESCE(t.resolved,0) resolutions
      FROM students s LEFT JOIN ranked e ON e.sid=s.sid AND e.rn=1 LEFT JOIN ranked p ON p.sid=s.sid AND p.rn=2
       LEFT JOIN qs q ON q.sid=s.sid LEFT JOIN ts t ON t.sid=s.sid
      WHERE date(s.data_cadastro)<=:end)
    SELECT campus,curso,periodo,risk,direction,responded,attended,COUNT(*) n,
      SUM(questions) questions,SUM(tickets) tickets,SUM(resolutions) resolutions
    FROM facts GROUP BY campus,curso,periodo,risk,direction,responded,attended'''
    rows=[dict(r) for r in c.execute(sql,dict(start=start,end=end))]
    cohorts=defaultdict(list)
    for r in rows:cohorts[(r['campus'],r['curso'],r['periodo'])].append(r)
    safe=[];blocked=set()
    for key,group in cohorts.items():
        if key[0] not in rbac.CAMPI or sum(r['n'] for r in group)<MIN_COHORT or any(r['n']<K for r in group):blocked.add(key)
        else:
            for row in group:
                # Todas as consultas somam as mesmas células publicáveis arredondadas.
                safe.append({**row,**{field:5*((row[field]+2)//5) for field in ('n','questions','tickets','resolutions')}})
    return safe,blocked


def rollup(public,blocked,f,campus=None,course=None):
    def selected(c,u):return (not (campus or f['campus']) or c==(campus or f['campus'])) and (not (course or f['curso']) or u==(course or f['curso']))
    if any(selected(c,u) for c,u,p in blocked):return dict(protegido=True,motivo='Coorte pequena ou combinação sensível. Totais complementares também são ocultados.',valores=None)
    rows=[r for r in public if selected(r['campus'],r['curso']) and (not f['risco'] or r['risk']==f['risco'])]
    values=dict(cadastrados=sum(r['n'] for r in rows),ativos=sum(r['n'] for r in rows if r['risk']!='inativo'),
                respondentes=sum(r['n'] for r in rows if r['responded'] and r['risk']!='inativo'),
                questionarios=sum(r['questions'] for r in rows),atendimentos=sum(r['tickets'] for r in rows),resolucoes=sum(r['resolutions'] for r in rows))
    values.update({k:sum(r['n'] for r in rows if r['risk']==k) for k in RISKS})
    values['avaliados']=sum(values[k] for k in RISKS if k!='sem_avaliacao')
    for direction in ('diminuiu','aumentou','estavel'):
        values[direction]=sum(r['n'] for r in rows if r['direction']==direction and r['risk']!='inativo')
    values['comparaveis']=sum(values[d] for d in ('diminuiu','aumentou','estavel'))
    pct=lambda n,d:round(100*n/d,1) if d else None
    values.update({k+'_pct':pct(values[k],values['ativos']) for k in RISKS})
    values.update(cobertura=pct(values['respondentes'],values['ativos']),cobertura_avaliacao=pct(values['avaliados'],values['ativos']),
                  melhora_pct=pct(values['diminuiu'],values['comparaveis']))
    return dict(protegido=False,valores=values)


def overview(query):
    f=filters(query)
    with closing(connect()) as c:
        observed=months(c,f);cubes=[(month,*atoms(c,month)) for month in observed]
    month,public,blocked=cubes[-1]
    result=dict(filtros=f,referencia=month,politica=dict(minimo_coorte=MIN_COHORT,minimo_celula=K,arredondamento=5,
      texto='Coortes fixas por câmpus, curso e semestre do aluno; células pequenas e totais complementares são suprimidos. Contagens aproximadas em múltiplos de 5; percentuais derivam dessas mesmas células. Não há filtros por aluno nem dias avulsos.'),
      opcoes=dict(campus=[dict(id=k,nome=v) for k,v in rbac.CAMPI.items()],cursos=[dict(id=k,nome=v) for k,v in COURSES.items()]),
      resumo=rollup(public,blocked,f),
      campus=[dict(id=k,nome=v,**rollup(public,blocked,f,campus=k)) for k,v in rbac.CAMPI.items() if not f['campus'] or f['campus']==k],
      cursos=[dict(id=k,nome=v,**rollup(public,blocked,f,course=k)) for k,v in COURSES.items() if not f['curso'] or f['curso']==k],
      evolucao=[dict(mes=m,**rollup(p,b,f),campus=[dict(id=k,nome=v,**rollup(p,b,f,campus=k)) for k,v in rbac.CAMPI.items() if not f['campus'] or f['campus']==k]) for m,p,b in cubes])
    result['catalogo']=dict(campus=3,cursos=len(course_catalog.COURSES))
    result['cursos'].sort(key=lambda row:(row['protegido'],-((row.get('valores') or {}).get('alto_pct') or 0),row['nome']))
    # Eventos são somas dos mesmos meses/células, nunca uma consulta alternativa de totais exatos.
    result['eventos_periodo']=None if any(p['protegido'] for p in result['evolucao']) else {
        k:sum(p['valores'][k] for p in result['evolucao']) for k in ('questionarios','atendimentos','resolucoes')}
    return result


def respond(handler):
    user=handler.sessao;parsed=urlsplit(handler.path);query={k:v[0] for k,v in parse_qs(parsed.query,keep_blank_values=True).items()}
    allowed={'/api/institucional/resumo','/api/institucional/campus','/api/institucional/cursos/riscos','/api/institucional/evolucao'}
    status=200
    try:
        if user['perfil'] not in rbac.ADMIN|{rbac.ANALYST}:status=403;raise PermissionError('Este perfil não possui acesso institucional.')
        if handler.command!='GET':status=405;raise PermissionError('Os indicadores institucionais são somente leitura.')
        if parsed.path not in allowed:status=404;raise PermissionError('Endpoint institucional não encontrado.')
        if any(len(v)>1 for v in parse_qs(parsed.query,keep_blank_values=True).values()):raise ValueError('Filtros duplicados não são permitidos.')
        data=overview(query)
        if parsed.path.endswith('/campus'):data={k:data[k] for k in ('campus','politica','filtros','referencia')}
        elif parsed.path.endswith('/cursos/riscos'):data={k:data[k] for k in ('cursos','politica','filtros','referencia')}
        elif parsed.path.endswith('/evolucao'):data={k:data[k] for k in ('evolucao','politica','filtros','referencia')}
        rbac.audit(user,parsed.path,query,200)
        return handler._json(200,{'sucesso':True,'dados':data})
    except ValueError as e:status=400;error=str(e)
    except PermissionError as e:error=str(e)
    except sqlite3.Error:status=503;error='Leitura institucional indisponível. Tente atualizar.'
    rbac.audit(user,parsed.path,query,status)
    return handler._json(status,{'sucesso':False,'erro':error})
