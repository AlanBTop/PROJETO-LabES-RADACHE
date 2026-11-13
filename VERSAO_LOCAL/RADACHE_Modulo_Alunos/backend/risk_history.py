"""Evidências e comparação de avaliações; o atendimento nunca participa do cálculo."""
from datetime import datetime, timezone
import json
import math
from risk import calcular_nota, calcular_frequencia, calcular_financeiro, calcular_psicologico, carregar_pesos

FACTORS = {
    'notas': ('Desempenho acadêmico', 'nota_media', calcular_nota),
    'frequencia': ('Frequência', 'frequencia', calcular_frequencia),
    'financeiro': ('Situação financeira', 'resposta_financeira', calcular_financeiro),
    'psicologico': ('Bem-estar emocional', 'resposta_psicologica', calcular_psicologico),
}


def valid(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<=value<=100


def instant(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError,TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def metadata(e):
    value=e.get('metadados_risco') or {}
    if isinstance(value,str):
        try:return json.loads(value)
        except (ValueError,TypeError):return {}
    return value


def components(e):
    values={}
    for key,(name,field,func) in FACTORS.items():
        raw=e.get(field)
        if raw is None:continue
        try:values[key]=dict(nome=name,valor=raw,risco=round(func(raw),2))
        except (ValueError,TypeError):continue
    return values


def comparison(current, previous=None):
    index=current.get('indice_risco');old=previous.get('indice_risco') if previous else None
    delta=round(index-old,2) if valid(index) and valid(old) else None
    direction='sem_avaliacao' if not valid(index) else 'inicial' if delta is None else 'aumentou' if delta>0 else 'diminuiu' if delta<0 else 'estavel'
    before=components(previous or {});after=components(current)
    weights=metadata(current).get('pesos');old_weights=metadata(previous or {}).get('pesos')
    factors=[]
    if delta is not None:
        for key,value in after.items():
            if key not in before:continue
            old_value=before[key]
            difference=round(value['risco']-old_value['risco'],2)
            contribution=round(value['risco']*weights[key]-old_value['risco']*old_weights[key],2) if weights and old_weights and key in weights and key in old_weights else None
            if difference or contribution:
                factors.append(dict(chave=key,nome=value['nome'],anterior=old_value['valor'],atual=value['valor'],
                    componente_anterior=old_value['risco'],componente_atual=value['risco'],variacao_componente=difference,
                    variacao_contribuicao=contribution))
    return dict(indice_anterior=old if valid(old) else None,variacao_pontos=delta,direcao=direction,fatores=factors,
                comparacao_completa=bool(weights and old_weights and len(before)==4 and len(after)==4),
                pesos_alterados=bool(weights and old_weights and weights!=old_weights))


def snapshot(e, previous, origin, reference):
    """Metadados imutáveis gravados com as respostas e os pesos usados nesta avaliação."""
    result=dict(origem=origin,referencia=str(reference),versao_formula='risk.py:quatro-componentes-v1',
                pesos=carregar_pesos(),componentes=components(e))
    result.update(comparison({**e,'metadados_risco':result},previous))
    return result


def latest(history):
    rows=[e for e in history if valid(e.get('indice_risco'))]
    return max(enumerate(rows),key=lambda pair:(instant(pair[1].get('data_avaliacao')),pair[0]))[1] if rows else None


def describe(history, role='coordenacao'):
    rows=sorted(history,key=lambda e:instant(e.get('data_avaliacao')))
    previous=None;output=[];points=[]
    for e in rows:
        c=comparison(e,previous)
        if role!='coordenacao':c['fatores']=[f for f in c['fatores'] if f['chave']=='psicologico']
        origin=metadata(e).get('origem') or e.get('origem_dados') or 'registro_academico'
        entry=dict(data=e.get('data_avaliacao'),indice=e.get('indice_risco') if valid(e.get('indice_risco')) else None,
                   origem=origin,referencia=metadata(e).get('referencia'),**c)
        output.append(entry)
        if valid(e.get('indice_risco')):
            points.append(dict(data=e['data_avaliacao'],indice=e['indice_risco'],direcao=c['direcao']))
            previous=e
    current=points[-1]['indice'] if points else None;initial=points[0]['indice'] if points else None
    last=next((e for e in reversed(output) if e['indice'] is not None),None)
    return dict(inicial=initial,atual=current,variacao=last['variacao_pontos'] if last else None,
                variacao_total=round(current-initial,2) if len(points)>=2 else None,
                direcao=last['direcao'] if last else 'sem_avaliacao',pontos=points,avaliacoes=output,
                nota='Comparação de evidências registradas. O status e a quantidade de atendimentos não alteram o índice. Não demonstra causalidade da intervenção nem probabilidade de evasão.')
