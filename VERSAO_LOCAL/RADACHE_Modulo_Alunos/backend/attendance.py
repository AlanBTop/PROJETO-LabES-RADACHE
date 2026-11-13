"""Regras de atendimento sobre os tickets existentes, sem duplicar cadastros."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
import rbac
import database

TERMINAL = {'resolvido', 'encerrado'}
TRANSITIONS = {
    'aberto': ['em_andamento'],
    'em_andamento': ['aguardando_aluno', 'resolvido'],
    'aguardando_aluno': ['em_andamento', 'resolvido'],
    'resolvido': ['reaberto', 'encerrado'],
    'encerrado': ['reaberto'],
    'reaberto': ['em_andamento', 'aguardando_aluno', 'resolvido'],
}


def initialize(conn):
    conn.execute('CREATE INDEX IF NOT EXISTS gestao_eventos_chamado ON gestao_eventos(chamado_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS gestao_chamados_aluno ON gestao_chamados(aluno_id)')
    conn.execute('''CREATE TABLE IF NOT EXISTS gestao_equipe_auditoria (
        id INTEGER PRIMARY KEY, usuario_id TEXT NOT NULL, autor_id TEXT NOT NULL,
        data TEXT NOT NULL, antes TEXT, depois TEXT NOT NULL)''')


def owner(ticket):
    return (ticket.get('responsavel') or {}).get('uid')


def visible(user, ticket, students):
    student = students.get(str(ticket['alunoId']))
    if not student or not rbac.student_allowed(user, student):
        return False
    return user['perfil'] != rbac.ATTENDANT or owner(ticket) == user['id']


def all_tickets():
    import simulation_followup
    with closing(database.get_connection()) as conn:
        tickets = [json.loads(r[0]) for r in conn.execute('SELECT dados FROM gestao_chamados')]
    return tickets + simulation_followup.tickets()


def student_access(user, student):
    if not rbac.student_allowed(user, student):
        return False
    if user['perfil'] != rbac.ATTENDANT:
        return True
    return any(str(t['alunoId']) == str(student['id']) and owner(t) == user['id']
               and t['status'] not in TERMINAL for t in all_tickets())


def manages_user(manager, member):
    if manager['perfil'] in rbac.ADMIN:
        return True
    if manager['perfil']=='diretor_campus':
        return member['perfil']==rbac.ATTENDANT and member.get('campusId')==manager.get('campusId')
    courses = member.get('cursoIds') or [member.get('cursoId')]
    return (manager['perfil'] in rbac.MANAGERS and member['perfil'] == rbac.ATTENDANT
            and member.get('campusId') == manager.get('campusId') and bool(courses)
            and bool(set(courses) & set(manager.get('cursoIds') or [manager.get('cursoId')])))


def metrics(tickets, members):
    now = datetime.now(timezone.utc)
    resolved = [t for t in tickets if t['status'] in TERMINAL]
    active = [t for t in tickets if t['status'] not in TERMINAL]
    durations = [t['tempoResolucaoMin'] for t in resolved if t.get('tempoResolucaoMin') is not None]
    team = [dict(uid=u['id'], nome=u['nome'], ativo=u['ativo'],
                 ativos=sum(owner(t) == u['id'] for t in active),
                 resolvidos=sum(owner(t) == u['id'] for t in resolved))
            for u in members if u['perfil'] == rbac.ATTENDANT]
    return dict(totalAtribuidos=sum(bool(owner(t)) for t in tickets), totalAtendimentos=len(tickets),
                emAndamento=sum(t['status'] in {'em_andamento', 'reaberto'} for t in tickets),
                aguardandoResposta=sum(t['status'] == 'aguardando_aluno' for t in tickets),
                totalPendentes=len(active), semResponsavel=sum(not owner(t) for t in active),
                totalResolvidos=len(resolved), totalReabertos=sum(t.get('reaberturas', 0) for t in tickets),
                tempoMedioResolucaoMin=sum(durations)/len(durations) if durations else None,
                paradosMais48h=sum(datetime.fromisoformat(t['ultimaAtividadeEm']) < now-timedelta(hours=48) for t in active),
                totalAtendentesAtivos=sum(u['ativo'] for u in team), equipe=team)
