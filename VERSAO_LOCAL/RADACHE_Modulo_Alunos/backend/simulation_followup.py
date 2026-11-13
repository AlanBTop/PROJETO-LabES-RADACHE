"""Converte check-ins concluídos em atendimentos no quadro existente, sem copiar cadastro."""
from contextlib import closing
from datetime import datetime, timezone
import json
from uuid import uuid4
import simulation_store as store


def sync():
    """Avaliações são uma fila durável: reinício e novas consultas recuperam pendências."""
    if not store.OPERATIONAL.exists():
        return
    from gestao_local import curso_id
    academic={a['id']:a for a in store.students()}
    with closing(store.connect(store.OPERATIONAL)) as c,c:
        # O inicializador garante o esquema; compatibilidade com ferramentas antigas.
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='gestao_simulacoes'").fetchone():
            return
        if not c.execute('''SELECT 1 FROM avaliacoes_sim a LEFT JOIN gestao_simulacoes g
          ON g.sessao_id=a.sessao_id WHERE g.sessao_id IS NULL LIMIT 1''').fetchone():
            return
        c.execute('BEGIN IMMEDIATE')
        pending=c.execute('''SELECT a.sessao_id,a.aluno_id FROM avaliacoes_sim a
          LEFT JOIN gestao_simulacoes g ON g.sessao_id=a.sessao_id
          WHERE g.sessao_id IS NULL ORDER BY a.rowid''').fetchall()
        for row in pending:
            aid,sid=row['aluno_id'],row['sessao_id']
            student=academic.get(aid)
            if not student and aid < 0:
                try:
                    student=store.conversation_student(aid)
                except LookupError:
                    continue
            if not student:
                continue
            current=[json.loads(r[0]) for r in c.execute('SELECT dados FROM gestao_chamados WHERE aluno_id=? ORDER BY rowid DESC',(aid,))]
            ticket=next((t for t in current if t['status'] not in {'resolvido','encerrado'}),None)
            received=datetime.now(timezone.utc).isoformat()
            new=ticket is None
            if new:
                ident='sim-'+sid
                ticket=dict(id=ident,alunoId=str(-aid),cursoId=curso_id(student['curso']),
                    protocolo='SIM-'+str(c.execute('SELECT COUNT(*) FROM gestao_chamados').fetchone()[0]+1).zfill(6),titulo='Acompanhamento acadêmico',
                    descricao='Questionário concluído no WhatsApp simulado. Consulte as respostas e registre as ações de acompanhamento acadêmico.',
                    origem='whatsapp_simulado',status='aberto',categoria='academico',responsavel=None,
                    abertoEm=received,ultimaAtividadeEm=received,tempoResolucaoMin=None,resolvidoEm=None,encerradoPor=None)
                c.execute('INSERT INTO gestao_chamados VALUES (?,?,?)',(ident,aid,json.dumps(ticket)))
            else:
                ident=ticket['id']
                ticket.update(ultimaAtividadeEm=received,cursoId=curso_id(student['curso']))
                if ticket['status']=='aguardando_aluno':
                    ticket['status']='em_andamento'
                c.execute('UPDATE gestao_chamados SET dados=? WHERE id=?',(json.dumps(ticket),ident))
            event=dict(id=uuid4().hex,tipo='abertura' if new else 'questionario',
                texto='Questionário recebido pelo WhatsApp simulado. Respostas disponíveis neste atendimento.',
                criadoEm=received,autor={'nome':'RADACHE · Simulação local'},visivelAoAluno=False,sessaoId=sid)
            c.execute('INSERT INTO gestao_eventos VALUES (?,?,?)',(event['id'],ident,json.dumps(event)))
            c.execute('INSERT INTO gestao_simulacoes VALUES (?,?)',(sid,ident))


def enrich(ticket):
    """Monta a ficha com respostas atuais; revogação não deixa cópias sensíveis em eventos."""
    if ticket.get('origem')!='whatsapp_simulado':
        return ticket
    from gestao_local import curso_id
    aid=-int(ticket['alunoId'])
    try:
        student=store.conversation_student(aid)
    except LookupError:
        return ticket
    with closing(store.connect(store.OPERATIONAL,True)) as c:
        rows=c.execute('''SELECT a.sessao_id,a.dados FROM gestao_simulacoes g
          JOIN avaliacoes_sim a ON a.sessao_id=g.sessao_id
          WHERE g.chamado_id=? ORDER BY a.rowid DESC''',(ticket['id'],)).fetchall()
        checkins=[dict(sessaoId=r['sessao_id'],**json.loads(r['dados'])) for r in rows]
    return {**ticket,'alunoNome':student['nome'],'matricula':student['matricula'],
        'cursoId':curso_id(student['curso']),'situacaoAcademica':student['status'],
        'questionarios':checkins,'consentimentoRevogado':not bool(checkins)}


def tickets():
    if not store.OPERATIONAL.exists():
        return []
    with closing(store.connect(store.OPERATIONAL,True)) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='gestao_chamados'").fetchone():
            return []
        rows=[json.loads(r[0]) for r in c.execute('SELECT dados FROM gestao_chamados ORDER BY rowid DESC').fetchall()]
    # Libera a leitura antes de abrir outras conexões para enriquecer as fichas.
    # Evita bloqueio circular com uma sincronização concorrente aguardando commit.
    return [enrich(ticket) for ticket in rows]
