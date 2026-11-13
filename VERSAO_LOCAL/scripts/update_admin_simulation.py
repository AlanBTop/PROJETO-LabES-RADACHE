from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'RADACHE_Modulo_Alunos/frontend/index.html'
s=p.read_text(encoding='utf-8')
s=s.replace('src="app.js"','src="admin-simulation.js"').replace('RADACHE / SANDBOX ISOLADO','RADACHE / SIMULAÇÃO LOCAL').replace('<h1>Controle de alunos fictícios</h1>','<h1>Gerenciamento de Alunos — Ambiente de Simulação</h1>')
start=s.index('<p class="notice">');end=s.index('</p>',start)+4
s=s[:start]+'<p class="notice"><strong>Somente dados fictícios.</strong> Cadastre, consulte, edite e desative alunos para demonstração. O cadastro acadêmico é separado das conversas. A desativação preserva o histórico e impede novas respostas.</p>'+s[end:]
s=s.replace('<a href="http://127.0.0.1:8091/" target="_blank" rel="noopener">Abrir integração C</a>','<a href="/mensagens/">WhatsApp simulado</a>')
start=s.index('<p class="small">Use apenas');end=s.index('</p>',start)+4
s=s[:start]+'<p class="small">Use apenas informações inventadas. Média e frequência são opcionais e permitem aplicar a fórmula de risco existente ao concluir um questionário.</p>'+s[end:]
s=s.replace(' pattern="TESTE-[A-Z0-9-]{1,40}" maxlength="46"',' maxlength="20"')
s=s.replace('<select id="course" required><option>Ciência da Computação</option><option>Pedagogia</option></select>','<input id="course" required maxlength="100" list="courses"><datalist id="courses"><option value="Ciência da Computação"><option value="Pedagogia"></datalist>')
s=s.replace('<button>Incluir aluno fictício</button>','''<label>Período<input id="period" type="number" min="1" max="16" value="1" required></label>
<label>Situação acadêmica<select id="academic-status"><option value="ativo">Ativo</option><option value="inativo">Inativo</option><option value="trancado">Trancado</option><option value="formado">Formado</option></select></label>
<label>Média fictícia (opcional)<input id="average" type="number" min="0" max="10" step="0.01"></label>
<label>Frequência fictícia % (opcional)<input id="attendance" type="number" min="0" max="100" step="0.01"></label>
<label>E-mail fictício (opcional, domínio .test)<input id="email" type="email" placeholder="aluno@example.test"></label>
<label>Telefone fictício (opcional, somente zeros)<input id="phone" maxlength="13"></label>
<button id="save-student">Cadastrar aluno fictício</button><button id="cancel-edit" type="button">Novo cadastro / cancelar edição</button>''')
p.write_text(s,encoding='utf-8')
