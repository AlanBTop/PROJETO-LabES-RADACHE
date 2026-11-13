"""Persistência da demonstração: cadastro isolado, conversas e roteiro no servidor."""
from contextlib import closing
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import calendar
import json
import os
from pathlib import Path
import re
import sqlite3
import course_catalog
import risk_history
import rbac
from uuid import uuid4
from risk import calcular_indice_risco, classificar_risco

ROOT = Path(__file__).resolve().parent.parent
ACADEMIC = Path(os.environ.get('RADACHE_MOCK_DB', ROOT / 'database/mock_sigaa.db'))
OPERATIONAL = Path(os.environ.get('RADACHE_SIM_DB', ROOT / 'database/radache.db'))
# Reutiliza literalmente o roteiro existente; não há serviço externo.
TEXTS = dict(re.findall(r'(\w+):\s*`([^`]+)`', (ROOT / 'frontend/mensagens/js/data/checkin-textos.js').read_text(encoding='utf-8')))
FIN = ['não sinto dificuldade', 'dificuldade leve', 'dificuldade significativa', 'considerando trancar por motivo financeiro']


def connect(path, readonly=False):
    if readonly:
        conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init():
    with closing(connect(ACADEMIC)) as c, c:
        c.execute('''CREATE TABLE IF NOT EXISTS alunos (
          id INTEGER PRIMARY KEY AUTOINCREMENT, matricula TEXT NOT NULL UNIQUE COLLATE NOCASE,
          nome TEXT NOT NULL, curso TEXT NOT NULL, periodo INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL DEFAULT 'ativo', campus TEXT NOT NULL DEFAULT 'Câmpus de Cáceres',
          email TEXT NOT NULL DEFAULT '', telefone TEXT NOT NULL DEFAULT '',
          nota_media REAL, frequencia REAL, data_cadastro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    if ACADEMIC.resolve() == (ROOT/'database/mock_sigaa.db').resolve():
        import_legacy(ROOT/'database/alunos_mock_isolado.db')
    with closing(connect(OPERATIONAL)) as c, c:
        c.executescript('''CREATE TABLE IF NOT EXISTS sessoes (
          id TEXT PRIMARY KEY, aluno_id INTEGER NOT NULL, estado TEXT NOT NULL,
          criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
          CREATE INDEX IF NOT EXISTS sessoes_aluno ON sessoes(aluno_id);
          CREATE TABLE IF NOT EXISTS mensagens (
          id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL REFERENCES sessoes(id),
          aluno_id INTEGER NOT NULL, remetente TEXT NOT NULL, conteudo TEXT NOT NULL,
          timestamp TEXT NOT NULL, pergunta TEXT, sensivel INTEGER NOT NULL DEFAULT 0);
          CREATE INDEX IF NOT EXISTS mensagens_aluno ON mensagens(aluno_id);
          CREATE TABLE IF NOT EXISTS avaliacoes_sim (
          sessao_id TEXT PRIMARY KEY REFERENCES sessoes(id), aluno_id INTEGER NOT NULL,
          dados TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS comandos (
          id TEXT PRIMARY KEY, aluno_id INTEGER NOT NULL, assinatura TEXT NOT NULL, resultado TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS gestao_chamados (
          id TEXT PRIMARY KEY, aluno_id INTEGER NOT NULL, dados TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS gestao_chamados_aluno ON gestao_chamados(aluno_id);
          CREATE TABLE IF NOT EXISTS gestao_eventos (
          id TEXT PRIMARY KEY, chamado_id TEXT REFERENCES gestao_chamados(id), dados TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS gestao_acoes (
          id TEXT PRIMARY KEY, chamado_id TEXT NOT NULL, assinatura TEXT NOT NULL, resultado TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS gestao_simulacoes (
          sessao_id TEXT PRIMARY KEY, chamado_id TEXT NOT NULL REFERENCES gestao_chamados(id));''')


def import_legacy(source):
    """Importação única do sandbox SQLite anterior; o arquivo de origem é somente leitura."""
    if not source.exists():
        return
    with closing(connect(ACADEMIC)) as target, target:
        target.execute('CREATE TABLE IF NOT EXISTS migracoes (nome TEXT PRIMARY KEY)')
        if target.execute("SELECT 1 FROM migracoes WHERE nome='sandbox-anterior'").fetchone():
            return
        with closing(connect(source,True)) as old:
            rows=old.execute('SELECT id,nome,matricula,curso,criado_em FROM alunos_mock').fetchall()
        for row in rows:
            target.execute('INSERT OR IGNORE INTO alunos(id,nome,matricula,curso,data_cadastro) VALUES (?,?,?,?,?)',tuple(row))
        target.execute("INSERT INTO migracoes VALUES ('sandbox-anterior')")


def students():
    if not ACADEMIC.exists():
        return []
    with closing(connect(ACADEMIC, True)) as c:
        return [{**dict(r), 'curso': course_catalog.canonical(r['curso'])}
                for r in c.execute('SELECT * FROM alunos ORDER BY id DESC')]


def student(ident, active=False):
    with closing(connect(ACADEMIC, True)) as c:
        row = c.execute('SELECT * FROM alunos WHERE id=?', (ident,)).fetchone()
    if not row:
        raise LookupError('Aluno fictício não encontrado.')
    if active and row['status'] != 'ativo':
        raise ValueError('Aluno desativado ou sem vínculo ativo. Reative no gerenciamento para simular.')
    return {**dict(row), 'curso': course_catalog.canonical(row['curso'])}


def conversation_student(ident, active=False):
    """IDs negativos consultam o cadastro original, sem copiar ou alterar alunos."""
    if ident > 0:
        return student(ident, active)
    import database
    row = database.get_aluno_by_id(-ident)
    if not row or row.get('status_exclusao'):
        raise LookupError('Aluno não encontrado.')
    if active and row['status'] != 'ativo':
        raise ValueError('Aluno sem vínculo ativo para esta simulação.')
    assessment = row.get('avaliacao_atual') or {}
    return {**{k:row.get(k) for k in ('nome','matricula','curso','periodo','status','campus')},
            'id':ident, 'curso':course_catalog.canonical(row['curso']),
            'nota_media':assessment.get('nota_media'), 'frequencia':assessment.get('frequencia')}


def save(data, ident=None):
    allowed = {'nome','matricula','curso','periodo','status','campus','email','telefone','nota_media','frequencia'}
    if set(data) - allowed:
        raise ValueError('Campos de cadastro não reconhecidos.')
    merged = {**(student(ident) if ident else {}), **data}
    from aluno_service import AlunoService
    AlunoService._validar({k:v for k,v in merged.items() if v is not None or k not in ('nota_media','frequencia')}, ('nome','matricula','curso'))
    merged['curso'] = course_catalog.canonical(merged['curso'])
    if 'campus' in data:
        campus=rbac.campus_id(data['campus'])
        if campus:merged['campus']=rbac.CAMPI[campus]
        elif not ident or data['campus']!=student(ident).get('campus'):
            raise ValueError('Selecione Cáceres, Várzea Grande ou Cuiabá.')
    if merged.get('email') and not merged['email'].lower().endswith(('.test', '.invalid', '.example')):
        raise ValueError('Use e-mail fictício com domínio .test, .invalid ou .example.')
    if merged.get('telefone') and not re.fullmatch(r'0{10,13}', merged['telefone']):
        raise ValueError('Deixe telefone vazio ou use somente zeros para a simulação.')
    fields = [k for k in allowed if k in merged]
    values = [merged[k] for k in fields]
    try:
        with closing(connect(ACADEMIC)) as c, c:
            if ident:
                c.execute('UPDATE alunos SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', values+[ident])
                return ident
            return c.execute('INSERT INTO alunos ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',values).lastrowid
    except sqlite3.IntegrityError:
        raise ValueError('Matrícula fictícia já existente.') from None


def deactivate(ident):
    student(ident)
    with closing(connect(ACADEMIC)) as c, c:
        c.execute("UPDATE alunos SET status='inativo' WHERE id=?", (ident,))
    return True


def now():
    return datetime.now(timezone.utc).isoformat()


def months(value, amount, day=None):
    d = datetime.fromisoformat(value)
    year, month = divmod(d.year*12+d.month-1+amount,12)
    return d.replace(year=year, month=month+1, day=min(day or d.day,calendar.monthrange(year,month+1)[1])).isoformat()


def valid(s):
    return bool(s['consentimento'] and s['dataConsentimento'] and s['timestamp'] < months(s['dataConsentimento'],12))


def open_cycle(s):
    ok = valid(s)
    s.update(etapa='aguardando_inicio' if ok else 'consentimento', consentimento=ok,
             financeira=None, emocional=None, concluidoMes=None, ultimaInteracao=s['timestamp'], lembreteEnviado=False)
    return ['mensal' if ok else 'boasVindas']


def snapshot(s):
    expiry = months(s['dataConsentimento'],12) if s['dataConsentimento'] else None
    return {**s, 'consentimento':valid(s), 'validadeConsentimento':expiry,
            'consentimentoExpirado':bool(expiry and s['timestamp'] >= expiry),
            'F':None if s['financeira'] is None else [0,33,66,100][s['financeira']-1],
            'P':None if s['emocional'] is None else (5-s['emocional'])/4*100}


def message(c, sid, aid, sender, content, timestamp, question=None, sensitive=False, ident=None):
    c.execute('INSERT INTO mensagens VALUES (?,?,?,?,?,?,?,?)',
              (ident or str(uuid4()),sid,aid,sender,content,timestamp,question,int(sensitive)))


def result(c, aid):
    row = c.execute('SELECT * FROM sessoes WHERE aluno_id=? ORDER BY rowid DESC LIMIT 1',(aid,)).fetchone()
    history = [dict(r) for r in c.execute('SELECT * FROM mensagens WHERE aluno_id=? ORDER BY rowid',(aid,))]
    return {'sessao_id':row['id'], 'estado':snapshot(json.loads(row['estado'])), 'mensagens':history}


def session(aid, body=None):
    """BEGIN IMMEDIATE serializa transições e retries; cadastro abre somente em leitura."""
    academic = conversation_student(aid, active=True)
    baseline=[]
    if aid<0:
        import database
        baseline=list(reversed(database.get_aluno_by_id(-aid).get('historico_avaliacoes',[])))
    body = body or {}
    action = body.get('acao','carregar')
    if action not in ('carregar','responder','reiniciar','mes','ano','dias'):
        raise ValueError('Ação de simulação inválida.')
    ident = body.get('id_cliente')
    if action != 'carregar' and (not isinstance(ident,str) or not 1 <= len(ident) <= 100):
        raise ValueError('Identificador da operação obrigatório.')
    signature = json.dumps(body,sort_keys=True,ensure_ascii=False)
    with closing(connect(OPERATIONAL)) as c, c:
        c.execute('BEGIN IMMEDIATE')
        if ident:
            old = c.execute('SELECT * FROM comandos WHERE id=?',(ident,)).fetchone()
            if old:
                if old['aluno_id'] != aid or old['assinatura'] != signature:
                    raise ValueError('Identificador de operação reutilizado com outro conteúdo.')
                return json.loads(old['resultado'])
        row = c.execute('SELECT * FROM sessoes WHERE aluno_id=? ORDER BY rowid DESC LIMIT 1',(aid,)).fetchone()
        s = json.loads(row['estado']) if row else None
        sid = row['id'] if row else None
        output = []
        new_session = not row or action in ('reiniciar','mes','ano')
        if action == 'responder' and (not row or body.get('sessao_id') != sid):
            raise ValueError('Sessão inválida ou desatualizada. Recarregue a conversa.')
        if new_session:
            if s and action in ('mes','ano'):
                s['timestamp'] = months(s['timestamp'],1 if action=='mes' else 12,s['diaCalendario'])
            else:
                s = dict(timestamp=now(),consentimento=False,dataConsentimento=None)
                s['diaCalendario'] = datetime.fromisoformat(s['timestamp']).day
            output = open_cycle(s)
            sid = str(uuid4())
            c.execute('INSERT INTO sessoes(id,aluno_id,estado) VALUES (?,?,?)',(sid,aid,json.dumps(s)))
        elif action == 'dias':
            was = valid(s)
            s['timestamp'] = (datetime.fromisoformat(s['timestamp'])+timedelta(days=3)).isoformat()
            s['diaCalendario'] = datetime.fromisoformat(s['timestamp']).day
            if was and not valid(s):
                output = open_cycle(s)
            elif s['etapa'] in ('consentimento','aguardando_inicio','financeira','emocional') and not s['lembreteEnviado']:
                s['lembreteEnviado'] = True
                output = ['lembrete']
        elif action == 'responder':
            content = body.get('texto')
            if not isinstance(content,str) or not content.strip() or len(content)>4000:
                raise ValueError('A resposta deve ter entre 1 e 4000 caracteres.')
            command = content.strip().upper()
            stage = s['etapa']
            sensitive = False
            s['ultimaInteracao'] = s['timestamp']
            if body.get('tipo','texto') != 'texto':
                output = ['naoTexto']
            elif command == 'REVOGAR':
                # O roteiro promete apagar respostas: remove também estado, avaliações e cache de retries.
                c.execute("UPDATE mensagens SET conteudo='Resposta removida após revogação.',sensivel=0 WHERE aluno_id=? AND sensivel=1",(aid,))
                c.execute('DELETE FROM avaliacoes_sim WHERE aluno_id=?',(aid,))
                c.execute('DELETE FROM comandos WHERE aluno_id=?',(aid,))
                for previous in c.execute('SELECT id,estado FROM sessoes WHERE aluno_id=?',(aid,)).fetchall():
                    cleaned = json.loads(previous['estado'])
                    cleaned.update(financeira=None,emocional=None,consentimento=False,dataConsentimento=None,etapa='revogado',concluidoMes=None)
                    c.execute('UPDATE sessoes SET estado=? WHERE id=?',(json.dumps(cleaned),previous['id']))
                s.update(etapa='revogado',consentimento=False,dataConsentimento=None,financeira=None,emocional=None,concluidoMes=None)
                output = ['revogacao']
            elif not valid(s) and stage in ('aguardando_inicio','financeira','emocional','concluido'):
                output = open_cycle(s)
            elif s.get('concluidoMes') == s['timestamp'][:7]:
                output = ['respondido']
            elif stage == 'concluido' or command == 'INICIAR' and stage not in ('financeira','emocional'):
                output = open_cycle(s)
            elif command == 'INICIAR':
                output = [stage]
            elif stage in ('recusado','revogado'):
                output = ['recusa' if stage=='recusado' else 'revogacao']
            elif stage == 'consentimento' and command in ('1','2'):
                ok = command=='1'
                s.update(etapa='financeira' if ok else 'recusado',consentimento=ok,dataConsentimento=s['timestamp'] if ok else None)
                output = ['financeira' if ok else 'recusa']
            elif stage == 'aguardando_inicio' and command=='1':
                s['etapa']='financeira'
                output=['financeira']
            elif stage == 'financeira' and command in ('1','2','3','4'):
                s.update(financeira=int(command),etapa='emocional')
                sensitive=True
                output=['emocional']
            elif stage == 'emocional' and command in ('1','2','3','4','5'):
                s.update(emocional=int(command),etapa='concluido',concluidoMes=s['timestamp'][:7])
                sensitive=True
                output=['encerramento']
                evaluation = dict(data_avaliacao=s['timestamp'],nota_media=academic['nota_media'],frequencia=academic['frequencia'],
                    resposta_financeira=FIN[s['financeira']-1],resposta_psicologica=s['emocional'])
                f,p = [0,33,66,100][s['financeira']-1],(5-s['emocional'])/4*100
                situation = lambda v: 'estavel' if v<=33 else 'moderada' if v<67 else 'critica'
                evaluation.update(situacao_financeira=situation(f),situacao_psicologica=situation(p),indice_risco=None,classificacao_risco=None)
                if academic['nota_media'] is not None and academic['frequencia'] is not None:
                    index=calcular_indice_risco(academic['nota_media'],academic['frequencia'],evaluation['resposta_financeira'],s['emocional'])
                    evaluation.update(indice_risco=index,classificacao_risco=classificar_risco(index))
                else:
                    evaluation['limitacao']='Informe média e frequência fictícias no gerenciamento para calcular o risco no próximo check-in.'
                previous=risk_history.latest(baseline+[json.loads(r[0]) for r in c.execute('SELECT dados FROM avaliacoes_sim WHERE aluno_id=? ORDER BY rowid',(aid,))])
                evaluation['metadados_risco']=risk_history.snapshot(evaluation,previous,'whatsapp_simulado',sid)
                c.execute('INSERT INTO avaliacoes_sim VALUES (?,?,?)',(sid,aid,json.dumps(evaluation)))
            else:
                output=['invalida',{'consentimento':'boasVindas','aguardando_inicio':'mensal'}.get(stage,stage)]
            message(c,sid,aid,'aluno',content,s['timestamp'],stage,sensitive)
        for key in output:
            message(c,sid,aid,'sistema',TEXTS[key],s['timestamp'],s['etapa'])
        c.execute('UPDATE sessoes SET estado=? WHERE id=?',(json.dumps(s),sid))
        data=result(c,aid)
        if ident:
            # Salva somente a assinatura para deduplicação; o histórico é relido em retries.
            c.execute('INSERT INTO comandos VALUES (?,?,?,?)',(ident,aid,signature,json.dumps(data)))
        return data


def projected():
    if not ACADEMIC.exists():
        return []
    catalog = students()
    if not catalog:
        return []
    student_ids = {student['id'] for student in catalog}
    with closing(connect(OPERATIONAL)) as c:
        # Uma leitura por tabela evita três consultas extras por aluno.
        # As listas mantêm a mesma ordem rowid do contrato anterior.
        evaluations_by_student = defaultdict(list)
        sessions_by_student = defaultdict(list)
        messages_by_student = defaultdict(list)
        for row in c.execute('SELECT aluno_id,dados FROM avaliacoes_sim WHERE aluno_id>0 ORDER BY rowid DESC'):
            if row['aluno_id'] in student_ids:
                evaluations_by_student[row['aluno_id']].append(json.loads(row['dados']))
        for row in c.execute('SELECT id,aluno_id,estado FROM sessoes WHERE aluno_id>0 ORDER BY rowid DESC'):
            if row['aluno_id'] in student_ids:
                sessions_by_student[row['aluno_id']].append(dict(id=row['id'], **snapshot(json.loads(row['estado']))))
        for row in c.execute('SELECT * FROM mensagens WHERE aluno_id>0 ORDER BY rowid'):
            if row['aluno_id'] in student_ids:
                messages_by_student[row['aluno_id']].append(dict(row))
        output=[]
        for a in catalog:
            aid=a['id']
            evaluations=evaluations_by_student[aid]
            sessions=sessions_by_student[aid]
            latest=risk_history.latest(list(reversed(evaluations))) or (evaluations[0] if evaluations else None)
            history=messages_by_student[aid]
            output.append({**a, 'id':-aid,'ficticio':True,'status_exclusao':0,
                'situacao_financeira':latest.get('situacao_financeira') if latest else None,
                'situacao_psicologica':latest.get('situacao_psicologica') if latest else None,
                'indice_risco':latest.get('indice_risco') if latest else None,
                'classificacao_risco':latest.get('classificacao_risco') if latest else None,
                'avaliacao_atual':latest,'historico_avaliacoes':evaluations,'historico_checkins':sessions,
                'mensagens_simuladas':history,'ultima_interacao':history[-1]['timestamp'] if history else None})
        return output
