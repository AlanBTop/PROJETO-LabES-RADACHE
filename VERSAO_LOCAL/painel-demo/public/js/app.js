/* Painel analítico: o backend consolida indicadores; aqui são desenhadas as visualizações. */
import { renderRiskHistory, changeLabel } from '/assets/risk-history.js';
const $=id=>document.getElementById(id);
const levels=['alto','medio','baixo','sem_avaliacao'];
const riskNames={alto:'Risco alto',medio:'Risco médio',baixo:'Risco baixo',sem_avaliacao:'Sem avaliação'};
const colors={alto:'#de6377',medio:'#e8b54f',baixo:'#62ac91',sem_avaliacao:'#cbd4e1'};
const statusNames={aberto:'Aberto',em_andamento:'Em andamento',aguardando_aluno:'Aguardando aluno',resolvido:'Resolvido',sem_atendimento:'Sem chamado no recorte'};
const alertNames={alto:'Estudantes em risco alto',subiu_para_alto:'Passaram de médio para alto',sem_resposta_recente:'Sem resposta há 30 dias',sem_primeiro_atendimento:'Aguardando primeiro atendimento'};
let token=sessionStorage.getItem('radache_token')||'',data=null,request=null,requestId=0,profileRequest=null,page=1;
let state={campus:'',curso:'',periodo:'',inicio:'',fim:'',risco:'',acompanhamento:'',alerta:''};
const fmt=n=>n==null?'—':Number(n).toLocaleString('pt-BR',{maximumFractionDigits:1});
const percent=n=>n==null?'—':fmt(n)+'%';
const dt=(s,time=false)=>{if(!s)return 'Sem registro';const d=new Date(String(s).replace(' ','T'));return Number.isNaN(d.getTime())?'Sem data válida':d.toLocaleString('pt-BR',time?{dateStyle:'short',timeStyle:'short'}:{dateStyle:'short'});};
function el(tag,cls='',text){const n=document.createElement(tag);n.className=cls;if(text!==undefined&&text!==null)n.textContent=text;return n;}
function icon(name){const n=el('i',name);n.setAttribute('aria-hidden','true');return n;}
function badge(level,index){return el('span','badge '+level,riskNames[level]+(index==null?'':' · '+fmt(index)+' / 100'));}
function empty(target,title,note){const n=el('div','empty-state');n.append(el('strong','',title),el('p','',note));target.replaceChildren(n);}
async function api(path,signal){const response=await fetch(path,{headers:{Authorization:'Bearer '+token},cache:'no-store',signal});const result=await response.json();if(!response.ok){const error=new Error(result.erro||'Não foi possível consultar os dados locais.');error.status=response.status;throw error;}return result.dados;}
function writeHash(replace=false){const hash=state.curso?'#'+new URLSearchParams({curso:state.curso,campus:state.campus}):'#geral';history[replace?'replaceState':'pushState'](null,'',hash);}
function readHash(){const params=new URLSearchParams(location.hash.slice(1));state.curso=params.get('curso')||'';state.campus=params.get('campus')||'';}
function clearAccess(message=''){
  requestId++;request?.abort();profileRequest?.abort();token='';data=null;sessionStorage.removeItem('radache_token');
  $('workspace').hidden=true;$('access-panel').hidden=false;$('logout').hidden=true;$('profile-badge').hidden=true;
  $('login-error').textContent=message;$('login-error').hidden=!message;
  for(const id of ['kpis','ranking-body','comparison-chart','student-table-body','student-modal-content','risk-donut','distribution-legend','checkin-chart','evolution-chart','factors-chart','alerts-list','definitions-content','course-banner'])$(id).replaceChildren();
  $('student-modal').close();$('definitions-dialog').close();$('student-modal-title').textContent='Perfil de acompanhamento';
  $('observed-evolution')?.replaceChildren();
}
async function load({quiet=false}={}){
  if(!token)return;
  request?.abort();const controller=new AbortController();request=controller;const id=++requestId;
  const timeout=setTimeout(()=>controller.abort('timeout'),25000);
  const params=new URLSearchParams({...state,ordenacao:$('rank-sort').value,busca:$('student-search').value,ordenar_alunos:$('student-order').value,pagina:String(page)});
  $('btn-refresh').disabled=true;$('workspace').setAttribute('aria-busy','true');$('panel-error').hidden=true;
  $('loading-state').hidden=quiet||!!data;
  try{
    const result=await api('/api/analytics?'+params,controller.signal);
    if(id!==requestId)return;
    data=result;page=result.estudantes.pagina;
    $('access-panel').hidden=true;$('workspace').hidden=false;$('analysis-content').hidden=false;$('logout').hidden=false;$('profile-badge').hidden=false;
    render();
  }catch(error){
    if(id!==requestId)return;
    if(error.status===401){clearAccess('Sua sessão expirou. Entre novamente.');return;}
    if(error.name==='AbortError'&&controller.signal.reason!=='timeout')return;
    const message=controller.signal.reason==='timeout'?'A consulta demorou mais que o esperado. Tente atualizar.':error.message;
    if(!data){$('login-error').textContent=message;$('login-error').hidden=false;}
    else{$('panel-error').textContent=message;$('panel-error').hidden=false;$('analysis-content').hidden=true;}
  }finally{clearTimeout(timeout);if(id===requestId){$('btn-refresh').disabled=false;$('loading-state').hidden=true;$('workspace').setAttribute('aria-busy','false');}}
}
function optionList(node,items,label,value){node.replaceChildren(new Option(label,''),...items.map(v=>new Option(typeof v==='string'?v:v.label,typeof v==='string'?v:v.value)));if(value&&!Array.from(node.options).some(o=>o.value===String(value)))node.add(new Option(value+' (sem alunos no recorte)',value));node.value=value;}
function renderOptions(){
  optionList($('overview-campus'),data.opcoes.campus,'Todos os câmpus',state.campus);
  optionList($('overview-course'),[...new Set(data.opcoes.cursos.filter(c=>!state.campus||c.campus===state.campus).map(c=>c.nome))],'Todos os cursos',state.curso);
  optionList($('filter-period'),data.opcoes.periodos.map(p=>({label:p+'º semestre',value:String(p)})),'Todos os semestres',state.periodo);
  $('filter-risk').value=state.risco;$('filter-followup').value=state.acompanhamento;$('filter-start').value=state.inicio;$('filter-end').value=state.fim;
}
function render(){
  renderOptions();
  const course=!!state.curso,k=data.kpis;
  $('page-kicker').textContent=course?'VISÃO DETALHADA DO CURSO':'VISÃO UNIVERSIDADE / CÂMPUS';
  $('page-title').replaceChildren(course?state.curso:'Panorama acadêmico',el('span','','.'));
  $('page-description').textContent=course?'Uma visão próxima dos estudantes e de cada acompanhamento.':'Conheça o cenário. Identifique prioridades. Aproxime o apoio.';
  $('nav-location').textContent=course?'Visão por curso':'Visão institucional';
  $('back-general').hidden=!course;$('general-nav').classList.toggle('active',!course);$('course-nav').classList.toggle('active',course);
  $('profile-badge').textContent=data.perfil==='nae'?'NAE':'CO';
  $('ranking-panel').hidden=course;$('students-panel').hidden=!course;
  $('scope-summary').textContent=[state.campus||'Todos os câmpus',state.curso||fmt(k.cursos)+' cursos',state.periodo?state.periodo+'º semestre':'Todos os semestres',state.inicio||state.fim?`${state.inicio?dt(state.inicio+'T12:00:00'):'Início do histórico'} a ${state.fim?dt(state.fim+'T12:00:00'):'último registro'} (UTC)`:'Todo o histórico'].join(' · ');
  $('last-sync').textContent='Atualizado às '+new Date(data.atualizado_em).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  $('denominator-note').textContent=`Risco e cobertura consideram ${fmt(k.elegiveis)} alunos ativos. ${fmt(k.cadastrados-k.elegiveis)} outros vínculos no recorte.`;
  renderKpis(course);renderComparison(course);renderDistribution();renderRanking();renderStudents();renderHistory();renderFactors();renderAlerts();renderDefinitions();
  let changes=$('observed-evolution');
  if(!changes){changes=el('section','observed-evolution');changes.id='observed-evolution';changes.setAttribute('aria-label','Mudanças observadas no risco');$('kpis').after(changes);}
  const observed=data.mudancas_risco||{};
  changes.replaceChildren(el('strong','','Evolução observada'),el('span','improved',fmt(observed.diminuiu||0)+' com redução'),el('span','worsened',fmt(observed.aumentou||0)+' com aumento'),el('span','',fmt(observed.estavel||0)+' estáveis'),el('small','',`Comparação das duas últimas avaliações válidas no recorte, entre alunos ativos. ${fmt((observed.inicial||0)+(observed.sem_avaliacao||0))} sem duas avaliações para comparar. Atendimento realizado não significa melhora do risco.`));
  $('course-banner').hidden=!course;
  if(course){const left=el('div');left.append(el('strong','',state.campus||data.cursos[0]?.campus||'Câmpus não informado'),el('span','',fmt(k.cadastrados)+' cadastros · '+fmt(k.elegiveis)+' alunos ativos elegíveis'));
    const last=data.cursos.map(c=>c.ultimo_acompanhamento).filter(Boolean).sort().at(-1),right=el('div','course-banner-right');right.append(el('strong','',percent(k.cobertura_avaliacao)+' com avaliação válida'),el('span','','Último check-in: '+dt(last,true)));$('course-banner').replaceChildren(left,right);}
}
function renderKpis(course){
  const k=data.kpis;
  const general=[['cadastrados','Alunos cadastrados','Todos os vínculos do recorte','fa-solid fa-users',''],['cursos','Cursos monitorados','Ofertas por câmpus','fa-solid fa-graduation-cap',''],['alto','Estudantes em risco alto','Índice igual ou superior a 67 / 100','fa-solid fa-circle-exclamation','high'],['medio','Estudantes em risco médio','Acima de 33 e abaixo de 67 / 100','fa-solid fa-triangle-exclamation','medium'],['baixo','Estudantes em risco baixo','Índice igual ou inferior a 33 / 100','fa-solid fa-shield-heart','low'],['alto_pct_total','Alto risco / alunos ativos','Percentual no total elegível','fa-solid fa-chart-pie','high'],['sem_resposta','Sem resposta no recorte','Questionário ainda não concluído','fa-regular fa-comment-dots',''],['checkins','Acompanhamentos realizados','Questionários consentidos e concluídos','fa-regular fa-calendar-check','']];
  const detailed=[['cadastrados','Estudantes do curso','Todos os vínculos do recorte','fa-solid fa-users',''],['cobertura_avaliacao','Cobertura de avaliação','Avaliação válida / alunos ativos','fa-solid fa-chart-pie',''],['alto','Estudantes em risco alto','Índice igual ou superior a 67 / 100','fa-solid fa-circle-exclamation','high'],['medio','Estudantes em risco médio','Acima de 33 e abaixo de 67 / 100','fa-solid fa-triangle-exclamation','medium'],['baixo','Estudantes em risco baixo','Índice igual ou inferior a 33 / 100','fa-solid fa-shield-heart','low'],['sem_avaliacao','Sem avaliação válida','Sem classificação de risco','fa-regular fa-circle-question',''],['cobertura_questionario','Cobertura dos questionários','Respondentes / alunos ativos','fa-regular fa-comment-dots',''],['checkins','Acompanhamentos realizados','Questionários consentidos e concluídos','fa-regular fa-calendar-check','']];
  $('kpis').replaceChildren(...(course?detailed:general).map(([key,label,note,i,tone])=>{const card=el('article','kpi '+tone);card.dataset.metric=key;const image=el('span','kpi-icon');image.append(icon(i));card.append(image,el('span','kpi-label',label),el('strong','',key.endsWith('_total')||key.startsWith('cobertura')?percent(k[key]):fmt(k[key])),el('small','',note));return card;}));
}
function stack(counts){const bar=el('div','stacked-bar');const total=levels.reduce((s,k)=>s+(counts[k]||0),0);bar.setAttribute('role','img');bar.setAttribute('aria-label',levels.map(k=>riskNames[k]+': '+(counts[k]||0)).join('; '));for(const key of levels){const segment=el('span','segment '+key);segment.style.width=(total?(counts[key]||0)/total*100:0)+'%';segment.title=riskNames[key]+': '+fmt(counts[key]||0);bar.append(segment);}return bar;}
function openCourse(name,campus){state.curso=name;state.campus=campus;page=1;$('student-search').value='';writeHash();void load();window.scrollTo({top:0,behavior:'smooth'});}
function renderComparison(course){
  $('comparison-title').textContent=course?'Risco por semestre':'Risco por curso';
  $('comparison-note').textContent=course?'Distribuição entre alunos ativos de cada semestre. Sem avaliação permanece visível.':'Veja o tamanho de cada grupo, inclusive quem ainda não tem avaliação.';
  const rows=course?data.periodos:data.cursos;
  $('comparison-count').textContent=rows.length+(course?' semestres':' cursos');
  if(!rows.length){empty($('comparison-chart'),'Nenhum registro neste recorte','Ajuste os filtros para consultar outros estudantes.');return;}
  $('comparison-chart').replaceChildren(...rows.map(c=>{const row=el(course?'div':'button','comparison-row');if(!course){row.type='button';row.dataset.course=c.nome;row.onclick=()=>openCourse(c.nome,c.campus);}
    const label=el('span','comparison-name');label.append(el('strong','',course?c.periodo+'º semestre':c.nome),el('small','',c.elegiveis?percent(c.cobertura_avaliacao)+' avaliados':c.cadastrados?'Sem alunos ativos':'Sem alunos no recorte'));
    const total=el('span','comparison-total',fmt(c.elegiveis));total.append(el('small','','ativos'));row.append(label,stack(c),total);return row;}));
}
function renderDistribution(){
  const k=data.kpis;let cursor=0;
  const stops=data.distribuicao.map(d=>{const start=cursor;cursor+=d.percentual||0;return `${colors[d.chave]} ${start}% ${cursor}%`;});
  const donut=el('div','donut');donut.style.background=k.elegiveis?'conic-gradient('+stops.join(',')+')':'#edf1f7';
  donut.setAttribute('role','img');donut.setAttribute('aria-label',data.distribuicao.map(d=>d.nome+': '+d.quantidade).join('; '));
  const center=el('div','donut-center');center.append(el('strong','',fmt(k.elegiveis)),el('small','','alunos ativos'));donut.append(center);$('risk-donut').replaceChildren(donut);
  $('distribution-legend').replaceChildren(...data.distribuicao.map(d=>{const row=el('div','distribution-item');row.append(el('i','dot '+({alto:'high',medio:'medium',baixo:'low',sem_avaliacao:'missing'}[d.chave])),el('span','',d.nome),el('strong','legend-count',fmt(d.quantidade)),el('small','',percent(d.percentual)));return row;}));
  const coverage=$('coverage-note');coverage.replaceChildren();
  for(const [title,value] of [['Cobertura de avaliação',k.cobertura_avaliacao],['Alto risco entre avaliados',k.alto_pct_avaliados],['Alto risco no total elegível',k.alto_pct_total]]){const line=el('p');line.append(title+': ',el('strong','',percent(value)));coverage.append(line);}
  if(!k.elegiveis)coverage.append(el('p','','Sem alunos ativos para calcular percentuais.'));
}
function renderRanking(){
  $('ranking-empty').hidden=!!data.cursos.length;
  $('ranking-body').replaceChildren(...data.cursos.map((c,i)=>{const row=el('tr');const first=el('td'),name=el('div','rank-title'),title=el('div'),link=el('button','course-name-button',c.nome);link.type='button';link.onclick=()=>openCourse(c.nome,c.campus);title.append(link,el('span','cell-subtitle',c.campus));name.append(el('span','rank-index',i+1),title);first.append(name);row.append(first,el('td','',fmt(c.elegiveis)),el('td','risk-number high',fmt(c.alto)),el('td','risk-number medium',fmt(c.medio)),el('td','risk-number low',fmt(c.baixo)));
    const missing=el('td','neutral',fmt(c.sem_avaliacao));missing.append(el('span','cell-subtitle',percent(c.sem_avaliacao_pct)+' dos ativos'));row.append(missing,el('td','risk-number high',percent(c.alto_pct_total)),el('td','',dt(c.ultimo_acompanhamento)));
    const cell=el('td'),open=el('button','icon-button');open.type='button';open.setAttribute('aria-label','Abrir curso '+c.nome);open.append(icon('fa-solid fa-arrow-right'));open.onclick=()=>openCourse(c.nome,c.campus);cell.append(open);row.append(cell);return row;}));
}
function renderStudents(){
  const list=data.estudantes;
  $('student-count').textContent=fmt(list.total)+' estudantes';$('students-empty').hidden=!!list.total;
  $('student-table-body').replaceChildren(...list.itens.map(s=>{const row=el('tr');row.dataset.studentId=s.id;
    const person=el('td');const name=el('span','student-name',s.nome);person.append(name,el('span','cell-subtitle',s.matricula));if(s.status!=='ativo')name.append(el('span','student-status','('+s.status+')'));
    const risk=el('td');risk.append(badge(s.risco,s.indice));if(s.subiu_para_alto)risk.append(el('span','cell-subtitle','Passou de médio para alto'));
    if(s.evolucao_risco?.variacao!=null)risk.append(el('span','risk-change '+s.evolucao_risco.direcao,changeLabel(s.evolucao_risco)));
    const status=el('td');status.append(el('span','badge',statusNames[s.situacao]||s.situacao));if(!s.recebeu_atendimento&&s.questionarios)status.append(el('span','cell-subtitle','Sem ação da equipe registrada'));
    const action=el('td'),button=el('button','row-detail','Ver perfil');button.type='button';button.setAttribute('aria-label','Ver perfil de '+s.nome);button.onclick=()=>openStudent(s.id);action.append(button);
    row.append(person,el('td','',s.periodo+'º'),risk,el('td','',dt(s.ultimo_acompanhamento)),status,action);return row;}));
  $('student-page').textContent=list.pagina+' de '+list.paginas;$('student-previous').disabled=list.pagina<=1;$('student-next').disabled=list.pagina>=list.paginas;
  $('student-page-note').textContent=list.total?`Página ${list.pagina} · ${list.itens.length} de ${list.total} estudantes`:'Nenhum estudante neste recorte';
}
function renderHistory(){
  const points=data.evolucao.pontos;
  if(!points.length){empty($('checkin-chart'),'Sem acompanhamentos no período','Os questionários concluídos aparecerão aqui.');}
  else{
    const chart=el('div','month-bars');const maximum=Math.max(1,...points.map(p=>p.checkins));
    for(const p of points){const column=el('div','month-column');column.append(el('span','column-value',fmt(p.checkins)));const bar=el('div','column-bar');bar.style.height=(p.checkins/maximum*105)+'px';bar.title=p.mes+': '+p.checkins+' questionários';column.append(bar,el('span','month-label',monthLabel(p.mes)));chart.append(column);}$('checkin-chart').replaceChildren(chart);
  }
  if(!data.evolucao.suficiente){empty($('evolution-chart'),'Histórico insuficiente para comparar','São necessários registros válidos em pelo menos dois meses distintos. Nenhuma tendência foi estimada.');}
  else{
    const chart=el('div','month-bars');const maximum=Math.max(1,...points.map(p=>levels.reduce((s,k)=>s+p[k],0)));
    for(const p of points){const column=el('div','month-column'),bar=el('div','month-stack'),total=levels.reduce((s,k)=>s+p[k],0);bar.style.height=(total/maximum*112)+'px';bar.setAttribute('role','img');bar.setAttribute('aria-label',p.mes+'; '+levels.map(k=>riskNames[k]+': '+p[k]).join('; '));for(const key of levels){const seg=el('span','segment '+key);seg.style.height=(total?p[key]/total*100:0)+'%';seg.title=riskNames[key]+': '+p[key];bar.append(seg);}column.append(el('span','column-value',fmt(total)),bar,el('span','month-label',monthLabel(p.mes)));chart.append(column);}$('evolution-chart').replaceChildren(chart);
  }
  $('evolution-note').textContent=data.evolucao.nota;
}
function monthLabel(month){return new Date(month+'-15T12:00:00').toLocaleDateString('pt-BR',{month:'short',year:'2-digit'});}
function renderFactors(){
  $('factors-chart').replaceChildren(...data.fatores.map(f=>{const item=el('div'),heading=el('div','factor-head'),label=el('span','',f.nome);label.append(el('small','',`n = ${f.amostra}`));heading.append(label,el('strong','',f.media==null?'Sem dados':fmt(f.media)+' / 100'));const track=el('div','factor-track'),fill=el('span','factor-fill '+f.chave);fill.style.width=(f.media||0)+'%';track.append(fill);item.append(heading,track);return item;}));
}
function renderAlerts(){
  const notes={alto:'Última avaliação válida com índice ≥ 67%.',subiu_para_alto:'Duas últimas avaliações válidas: médio → alto.',sem_resposta_recente:'Nenhum questionário completo nos últimos 30 dias.',sem_primeiro_atendimento:'Questionário concluído, sem responsável ou ação da equipe.'};
  $('alerts-list').replaceChildren(...Object.entries(data.alertas).map(([key,count])=>{const row=el('button','alert-item '+(key==='alto'?'high':''));row.type='button';row.setAttribute('aria-pressed',String(state.alerta===key));const copy=el('span','alert-copy',alertNames[key]);copy.append(el('small','',notes[key]));row.append(copy,el('strong','',fmt(count)),icon('fa-solid fa-chevron-right'));row.onclick=()=>{state.alerta=state.alerta===key?'':key;page=1;void load();};return row;}));
  $('alert-scope').hidden=!state.alerta;$('alert-scope').textContent=state.alerta?'Filtro ativo: '+alertNames[state.alerta]+'. Clique novamente no alerta ou use Limpar para remover.':'';
}
function renderDefinitions(){
  const names={elegiveis:'Quem entra nas contagens',avaliacao:'Situação atual de risco',percentuais:'Dois percentuais diferentes',resposta:'Cobertura e acompanhamentos',fatores:'Fatores observados'};
  $('definitions-content').replaceChildren(...Object.entries(data.definicoes).map(([key,value])=>{const node=el('section','definition');node.append(el('h3','',names[key]||key),el('p','',value));return node;}));
  $('definitions-content').append(el('p','definitions-footer','Faixas da regra existente: baixo ≤ 33%; médio > 33% e < 67%; alto ≥ 67%. O semestre corresponde ao período atual do cadastro; não há calendário letivo estruturado. Use as datas para o recorte temporal. Cobertura do questionário e cobertura da avaliação são indicadores distintos.'));
}
async function openStudent(id){
  profileRequest?.abort();const controller=new AbortController();profileRequest=controller;
  $('student-modal-title').textContent='Perfil de acompanhamento';$('student-modal-content').replaceChildren(el('p','empty-state','Carregando histórico do estudante…'));if(!$('student-modal').open)$('student-modal').showModal();
  try{const student=await api('/api/analytics/students/'+id,controller.signal);if(controller!==profileRequest)return;renderProfile(student);}catch(error){if(error.name==='AbortError')return;if(error.status===401){clearAccess('Sua sessão expirou. Entre novamente.');return;}$('student-modal-content').replaceChildren(el('p','empty-state',error.message));}
}
function renderProfile(s){
  $('student-modal-title').textContent=s.nome;
  const root=el('div','profile-content'),summary=el('dl','profile-summary');
  for(const [label,value] of [['Matrícula',s.matricula],['Curso',s.curso],['Câmpus',s.campus],['Semestre',s.periodo+'º'],['Situação acadêmica',s.status],['Último check-in',dt(s.ultimo_acompanhamento,true)]]){const group=el('div');group.append(el('dt','',label),el('dd','',value));summary.append(group);}root.append(summary,badge(s.risco,s.indice));
  if(!s.atual)root.append(el('p','profile-note','Sem avaliação numérica válida. As respostas podem estar registradas sem índice, quando faltam média ou frequência para aplicar a fórmula.'));
  root.append(renderRiskHistory(s.evolucao_risco));
  root.append(el('h3','','Questionários e respostas do WhatsApp'));
  const questions=el('ul','profile-list'),emotions={1:'Muito ruim',2:'Ruim',3:'Regular',4:'Bom',5:'Muito bom'};
  for(const q of [...s.questionarios].reverse()){const row=el('li','profile-record');row.append(el('strong','',dt(q.data,true)));if(q.financeira!==undefined)row.append(el('p','','Situação financeira: '+q.financeira));row.append(el('p','','Bem-estar emocional: '+(emotions[q.emocional]||q.emocional)));questions.append(row);}root.append(questions);
  if(!s.questionarios.length)root.append(el('p','empty-inline','Nenhum questionário consentido e concluído disponível.'));
  root.append(el('h3','','Atendimentos e andamentos'));
  if(!s.atendimentos.length)root.append(el('p','empty-inline','Este aluno ainda não possui atendimento registrado.'));
  for(const t of s.atendimentos){const record=el('section','profile-record');record.append(el('strong','',t.protocolo+' · '+(statusNames[t.status]||t.status)),el('p','','Última atividade: '+dt(t.ultimaAtividadeEm,true)),el('p','','Responsável: '+(t.responsavel?.nome||'Não atribuído')));for(const event of t.eventos||[]){record.append(el('h4','',dt(event.criadoEm,true)+' · '+(event.autor?.nome||'RADACHE')),el('p','',event.texto));}const link=el('a','inline-link','Abrir atendimento →');link.href='/gestao/#chamados/'+encodeURIComponent(t.id);record.append(link);root.append(record);}
  $('student-modal-content').replaceChildren(root);
}
function resetFilters(){state={campus:'',curso:'',periodo:'',inicio:'',fim:'',risco:'',acompanhamento:'',alerta:''};page=1;$('date-preset').value='all';$('student-search').value='';writeHash();void load();}
function changed(){page=1;void load();}
// Os limites do backend usam dias UTC, assim como as datas persistidas.
const dateInput=d=>d.toISOString().slice(0,10);
$('panel-login').onsubmit=async event=>{event.preventDefault();$('login-submit').disabled=true;$('login-error').hidden=true;try{const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario:$('login-user').value,senha:$('login-password').value})});const result=await response.json();if(!response.ok)throw new Error(result.erro||'Não foi possível entrar.');if(result.usuario?.role==="analista_institucional"){location.replace("/institucional/");return;}token=result.token;sessionStorage.setItem('radache_token',token);$('login-password').value='';await load();}catch(error){$('login-error').textContent=error.message;$('login-error').hidden=false;}finally{$('login-submit').disabled=false;}};
$('logout').onclick=async()=>{const old=token;clearAccess();try{await fetch('/api/logout',{method:'POST',headers:{Authorization:'Bearer '+old}});}catch{}};
$('btn-refresh').onclick=()=>load();
$('overview-campus').onchange=()=>{state.campus=$('overview-campus').value;state.curso='';writeHash();changed();};
$('overview-course').onchange=()=>{state.curso=$('overview-course').value;writeHash();changed();};
for(const [id,key] of [['filter-period','periodo'],['filter-risk','risco'],['filter-followup','acompanhamento'],['filter-start','inicio'],['filter-end','fim']])$(id).onchange=()=>{state[key]=$(id).value;if(key==='inicio'||key==='fim')$('date-preset').value='custom';changed();};
$('date-preset').onchange=()=>{const mode=$('date-preset').value;if(mode==='custom'){$('advanced-filters').hidden=false;$('advanced-toggle').setAttribute('aria-expanded','true');return;}const today=new Date(),start=new Date(today);if(mode==='all'){state.inicio='';state.fim='';}else{if(mode==='year')start.setUTCMonth(0,1);else start.setUTCDate(today.getUTCDate()-Number(mode)+1);state.inicio=dateInput(start);state.fim=dateInput(today);}changed();};
$('advanced-toggle').onclick=()=>{const open=$('advanced-filters').hidden;$('advanced-filters').hidden=!open;$('advanced-toggle').setAttribute('aria-expanded',String(open));};
$('clear-filters').onclick=resetFilters;$('general-nav').onclick=$('back-general').onclick=()=>{state.curso='';state.alerta='';$('student-search').value='';page=1;writeHash();void load();};
$('course-nav').onclick=()=>{if(state.curso)$('students-panel').scrollIntoView({behavior:'smooth'});else $('ranking-panel').scrollIntoView({behavior:'smooth'});};
$('rank-sort').onchange=changed;$('student-order').onchange=changed;
let searchTimer;$('student-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(changed,240);};
$('student-previous').onclick=()=>{page--;void load();};$('student-next').onclick=()=>{page++;void load();};
$('definitions-button').onclick=()=>$('definitions-dialog').showModal();$('close-definitions').onclick=()=>$('definitions-dialog').close();
$('close-profile').onclick=()=>{$('student-modal').close();profileRequest?.abort();};
for(const id of ['student-modal','definitions-dialog'])$(id).addEventListener('click',event=>{const dialog=$(id),r=dialog.getBoundingClientRect();if(event.target===dialog&&(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom))dialog.close();});
$('student-modal').addEventListener('close',()=>profileRequest?.abort());
function refreshQuiet(){if(token&&!document.hidden&&!document.querySelector('dialog[open]')&&$('workspace').getAttribute('aria-busy')!=='true')void load({quiet:true});}
window.addEventListener('focus',refreshQuiet);document.addEventListener('visibilitychange',refreshQuiet);setInterval(refreshQuiet,15000);
window.addEventListener('popstate',()=>{readHash();page=1;void load();});
readHash();if(token)void load();
