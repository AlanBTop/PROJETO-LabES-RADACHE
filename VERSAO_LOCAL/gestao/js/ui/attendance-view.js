import { STATUS, CATEGORIAS } from '../config.js';
import { $, el, button, data, options } from './dom.js';

export function setupAttendance(actions) {
  for (const status of ['encerrado','reaberto']) {
    const tab=button('');tab.dataset.ticketStatus=status;
    const count=el('strong','','—');count.dataset.statusCount=status;
    tab.append(el('span','',STATUS[status]),count);$('.ticket-views').append(tab);
  }
  $('[data-ticket-status="aberto"] span:last-of-type').textContent=STATUS.aberto;
  const filters=el('div','filters');
  const search=el('input');search.id='ticket-search';search.type='search';search.placeholder='Ticket, aluno ou matrícula';search.setAttribute('aria-label','Pesquisar atendimentos');
  const order=el('select');order.id='ticket-order';order.setAttribute('aria-label','Ordenar atendimentos');
  options(order,[{id:'risco',nome:'Risco acadêmico'},{id:'prioridade',nome:'Prioridade operacional'},{id:'data',nome:'Data de abertura'}],null);
  const unassigned=el('label','check-field');const check=el('input');check.type='checkbox';check.id='ticket-unassigned';unassigned.append(check,el('span','','Somente sem responsável'));
  for(const [control,title] of [[search,'Pesquisar atendimentos'],[order,'Ordenar por']]){const label=el('label','field inline-field');label.append(el('span','',title),control);filters.append(label);}
  filters.append(unassigned);$('.ticket-views').before(filters);
  let timer;search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(actions.filtrar,300);});
  order.addEventListener('change',actions.filtrar);check.addEventListener('change',actions.filtrar);
  $('#clear-ticket-filters').addEventListener('click',()=>{search.value='';order.value='risco';check.checked=false;actions.filtrar();});
  const metrics=el('div','metrics');metrics.id='attendance-metrics';$('#metrics').after(metrics);
  const team=el('section','table-card');team.id='attendance-team';team.hidden=true;$('#attendance-metrics').after(team);
  const wrapper=el('div','table-card');wrapper.id='attendance-table';
  const scroll=el('div','table-scroll'),table=el('table'),head=el('thead'),row=el('tr');
  for(const title of ['Ticket','Aluno','Curso','Categoria','Prioridade','Status','Abertura','Atualização','Ação'])row.append(el('th','',title));
  head.append(row);const body=el('tbody');body.id='attendance-rows';table.append(head,body);scroll.append(table);wrapper.append(scroll);
  wrapper.addEventListener('click',event=>{const target=event.target.closest('[data-open-case]');if(target)actions.abrir(target.dataset.openCase);});
  $('#ticket-board').after(wrapper);
}

export function attendanceFilters() {
  return {busca:$('#ticket-search').value.trim(),ordem:$('#ticket-order').value,semResponsavel:$('#ticket-unassigned').checked?'1':''};
}

export function attendanceMetrics(value) {
  const target=$('#attendance-metrics');target.replaceChildren();
  if(!value){$('#attendance-team').replaceChildren();return;}
  for(const [key,label] of Object.entries({totalAtribuidos:'Atribuídos',emAndamento:'Em andamento',aguardandoResposta:'Aguardando resposta',totalResolvidos:'Resolvidos',totalPendentes:'Pendentes',semResponsavel:'Sem responsável',totalReabertos:'Reaberturas',totalAtendentesAtivos:'Atendentes ativos'})){
    const card=el('article','metric-card'),content=el('div');card.dataset.attendanceMetric=key;content.append(el('p','',label),el('strong','',String(value[key]??0)));card.append(content);target.append(card);
  }
  const team=$('#attendance-team');team.replaceChildren(el('h3','','Distribuição da equipe'));
  team.hidden=!value.equipe?.length;
  for(const member of value.equipe||[])team.append(el('p','',`${member.nome} · ${member.ativo?'Ativo':'Inativo'} · ${member.ativos} casos ativos · ${member.resolvidos} resolvidos${member.ativo&&!member.ativos?' · Disponível':''}`));
  team.append(el('p','muted','Os volumes descrevem a distribuição de casos; não classificam o desempenho individual.'));
}

export function attendanceTable(columns,courses,selected) {
  const rows=Object.entries(columns).filter(([key])=>selected==='geral'||key===selected).flatMap(([,v])=>v.itens);
  const order=$('#ticket-order').value;
  if(order==='data')rows.sort((a,b)=>b.abertoEm.localeCompare(a.abertoEm));
  if(order==='prioridade')rows.sort((a,b)=>({alta:0,normal:1,baixa:2}[a.prioridade||'normal']-({alta:0,normal:1,baixa:2}[b.prioridade||'normal'])||a.abertoEm.localeCompare(b.abertoEm)));
  $('#attendance-rows').replaceChildren(...rows.map(item=>{
    const row=el('tr');
    for(const text of [item.protocolo,item.alunoNome||'Cadastro indisponível',courses.get(item.cursoId)||item.cursoId,CATEGORIAS[item.categoria]||item.categoria,{alta:'Alta',normal:'Normal',baixa:'Baixa'}[item.prioridade||'normal'],STATUS[item.status],data(item.abertoEm),data(item.ultimaAtividadeEm)])row.append(el('td','',text));
    const cell=el('td'),open=button('Visualizar');open.dataset.openCase=item.id;cell.append(open);row.append(cell);return row;
  }));
  if(!rows.length){const row=el('tr'),cell=el('td','','Nenhum atendimento carregado para este filtro.');cell.colSpan=9;row.append(cell);$('#attendance-rows').append(row);}
}
