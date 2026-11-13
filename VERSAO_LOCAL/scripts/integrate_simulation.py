"""Aplicação pontual da integração às interfaces existentes."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'RADACHE_Modulo_Alunos/backend'
F=ROOT/'RADACHE_Modulo_Alunos/frontend'

def edit(path, changes):
    text=path.read_text(encoding='utf-8')
    for before,after in changes:
        if before not in text: raise RuntimeError(f'Trecho não encontrado: {path}: {before[:70]}')
        text=text.replace(before,after)
    backup=ROOT.parent/'ARQUIVO/backups/versao_local/backup_simulacao_20261107'/path.relative_to(ROOT)
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists(): shutil.copy2(path,backup)
    path.write_text(text,encoding='utf-8')

edit(B/'run_local.py',[("    if os.environ.get('RADACHE_ENV','development')=='development':", "    if False:  # A simulação SQLite local independe da versão PostgreSQL.")])
edit(B/'mock_alunos.py',[("USE_LOCAL_TEST_STORE=False","USE_LOCAL_TEST_STORE=False")])
# Substitui apenas o adaptador do catálogo; a versão anterior fica no backup.
(B/'mock_alunos.py').write_text('''"""Catálogo acadêmico fictício local; escrita exclusiva no módulo administrativo."""
import simulation_store as store
from simulation_api import respond as responder, store_enabled as habilitado

def listar(): return store.students()
def incluir(dados): return store.save(dados)
def excluir(ident): return store.deactivate(ident)
def projetados(): return store.projected() if habilitado() else []
''',encoding='utf-8')
edit(B/'app.py',[
 ('import mock_alunos','import mock_alunos\nimport simulation_store\nimport simulation_api'),
 ('        try:\n            if path.startswith("/api/mock-alunos"):', '        try:\n            if path.startswith("/simulation-api/"):\n                return simulation_api.respond(self)\n            if path.startswith("/api/mock-alunos"):') ,
 ('        if path.startswith("/api/mock-alunos"):\n            return mock_alunos.responder(self)', '        if path.startswith("/simulation-api/"):\n            return simulation_api.respond(self)\n        if path.startswith("/api/mock-alunos"):\n            return mock_alunos.responder(self)'),
 ('"moduloAlunos": "catalogo-compartilhado"','"moduloAlunos": "sqlite-simulacao"'),
 ("                metricas['alunos_ativos'] += len(demos)","                metricas['alunos_ativos'] += sum(a['status']=='ativo' for a in demos)\n                for classe in ('criticos','moderados','estaveis'):\n                    singular={'criticos':'critico','moderados':'moderado','estaveis':'estavel'}[classe]\n                    metricas['alunos_'+classe] += sum(a['status']=='ativo' and a['classificacao_risco']==singular for a in demos)"),
 ('    database.init_db()','    simulation_store.init()\n    database.init_db()'),
 ('    whatsapp.iniciar_agendador_lembretes()','    # A versão local usa somente o simulador; não agenda envios reais.')])
edit(B/'gestao_local.py',[("    nomes = {'Ciência da Computação', 'Direito', 'Agronomia', 'Pedagogia', 'Enfermagem'}", "    nomes = {'Ciência da Computação', 'Direito', 'Agronomia', 'Pedagogia', 'Enfermagem'}\n    import simulation_store\n    nomes.update(a['curso'] for a in simulation_store.students())")])
edit(F/'mensagens/js/app.js',[("endpoint: '/mock-api/mensagens', timeoutMs: 10000, modo: 'mock', simulacao: true", "endpoint: '/simulation-api', timeoutMs: 10000, modo: 'local', simulacao: true"),(')).iniciar();\n}', ')).iniciar();\n}')])
edit(F/'mensagens/js/ui/chat-view.js',[
 ('Demonstração local: sem WhatsApp real, aprovação de templates ou gravação no banco.','Demonstração local com alunos e conversas persistidos em SQLite.'),
 ('Tudo acontece com dados fictícios na memória da aba. As respostas passam pelo mock HTTP local; nenhuma informação é gravada no banco. Recarregar reinicia a demonstração.','Os dados fictícios e as conversas ficam nos bancos locais. Recarregar recupera o histórico; reiniciar cria uma nova sessão e preserva as anteriores.'),
 ('Persistência: nenhuma','Persistência: SQLite local'),
 ("confirmado: this.config.modo === 'mock' ?", "confirmado: this.config.simulacao ? 'Salva no banco local' : this.config.modo === 'mock' ?")])
edit(ROOT/'painel-demo/public/js/app.js',[
 ('  let history = null;', '  let history = null;\n  let simulationMessages = [];\n  let simulationSessions = [];'),
 ('      history = payload.dados.historico_avaliacoes;', '      history = payload.dados.historico_avaliacoes;\n      simulationMessages = payload.dados.mensagens_simuladas || [];\n      simulationSessions = payload.dados.historico_checkins || [];'),
 ('  openModal("student-modal");', '''  if (simulationSessions.length) {
    const heading=document.createElement('h2'); heading.textContent='Questionários e respostas do WhatsApp'; content.appendChild(heading);
    for (const session of simulationSessions) {
      const title=document.createElement('p'); title.textContent='Sessão '+session.id+' · '+session.timestamp+' · '+session.etapa; content.appendChild(title);
      for (const message of simulationMessages.filter(m => m.sessao_id===session.id)) {
        const line=document.createElement('p'); line.className='small muted';
        line.textContent=message.timestamp+' · '+(message.remetente==='aluno'?'Aluno':'RADACHE')+' · '+message.conteudo;
        content.appendChild(line);
      }
    }
  }
  openModal("student-modal");''')])
