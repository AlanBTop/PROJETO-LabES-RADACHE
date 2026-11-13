import { CATEGORIAS, STATUS, TRANSICOES } from '../config.js';
import { $, el, icon, button, options, vazio, metadata, iniciais, data, duracao, relativo } from './dom.js';
import { renderRiskHistory, changeLabel } from '/assets/risk-history.js';
import { setupAttendance, attendanceFilters, attendanceMetrics, attendanceTable } from './attendance-view.js';

const TIPOS = { abertura: ['Abertura', 'tickets'], questionario: ['Questionário recebido', 'comment'], classificacao: ['Classificação', 'edit'], acao: ['Ação da equipe', 'comment'], validacao: ['Validação', 'check'], encerramento: ['Encerramento', 'check'] };
const RISCOS = { alto: 'Risco alto', medio: 'Risco médio', baixo: 'Risco baixo', sem_avaliacao: 'Sem avaliação' };
const formatIndex = n => Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 2 });

function risco(item, detalhado = false) {
  const r = item.riscoAcademico || { nivel: 'sem_avaliacao', indice: null };
  const nivel = RISCOS[r.nivel] ? r.nivel : 'sem_avaliacao';
  const node = el('span', `academic-risk risk-${nivel}${detalhado ? ' risk-detail' : ''}`);
  const label = el('span', 'risk-label'); label.append(icon(nivel === 'alto' ? 'warning' : nivel === 'sem_avaliacao' ? 'clock' : 'shield'), el('strong', '', RISCOS[nivel]));
  node.append(label, el('span', 'risk-value', r.indice == null ? 'Sem índice válido' : `Índice ${formatIndex(r.indice)} / 100`));
  if (detalhado) node.append(el('small', '', r.dataAvaliacao ? `Última avaliação válida: ${data(r.dataAvaliacao)}` : 'Não há avaliação válida disponível para este aluno.'));
  return node;
}

export class TicketsView {
  constructor() { this.status = 'geral'; this.colunas = {}; }

  filtros() { return attendanceFilters(); }

  conectar(acoes) {
    setupAttendance(acoes);
    options($('#category-filter'), Object.entries(CATEGORIAS).map(([id, nome]) => ({ id, nome })), 'Todas as categorias');
    for (const id of ['#category-filter', '#responsible-filter']) $(id).addEventListener('change', acoes.filtrar);
    $('#clear-ticket-filters').addEventListener('click', () => { $('#category-filter').value = ''; $('#responsible-filter').value = ''; acoes.filtrar(); });
    $('#ticket-board').addEventListener('click', event => {
      const card = event.target.closest('[data-ticket-id]');
      if (card) return acoes.abrir(card.dataset.ticketId);
      const more = event.target.closest('[data-more-status]');
      if (more) return acoes.mais(more.dataset.moreStatus);
      const retry = event.target.closest('[data-retry-status]');
      if (retry) acoes.recarregar(retry.dataset.retryStatus);
    });
    document.querySelectorAll('[data-ticket-status]').forEach(button => button.addEventListener('click', () => {
      this.status = button.dataset.ticketStatus; this.atualizarAbas();
    }));
    const detailRisk = el('div'); detailRisk.id = 'detail-risk'; $('#detail-badges').after(detailRisk);
    const evolution = el('div'); evolution.id = 'detail-risk-evolution'; $('#detail-metadata').after(evolution);
    $('#ticket-action-type').addEventListener('change', () => this.camposAcao());
    $('#action-status').addEventListener('change', () => this.camposAcao());
    $('#ticket-action-form').addEventListener('submit', event => { event.preventDefault(); acoes.registrar(); });
    $('#assume-ticket').addEventListener('click', acoes.assumir);
    $('#more-history').addEventListener('click', acoes.maisHistorico);
    $('#copy-protocol').addEventListener('click', acoes.copiarProtocolo);
  }

  responsaveis(itens, selecionado = '') {
    const lista = itens.map(u => ({ id: u.uid, nome: u.nome }));
    if (selecionado && !lista.some(u => u.id === selecionado)) lista.push({ id: selecionado, nome: 'Responsável selecionado (indisponível)' });
    options($('#responsible-filter'), lista, 'Todos os responsáveis', selecionado);
  }

  indicadores(dados) {
    attendanceMetrics(dados);
    $('#metric-average').textContent = dados ? duracao(dados.tempoMedioResolucaoMin) : '—';
    $('#metric-stalled').textContent = dados ? String(dados.paradosMais48h ?? 0) : '—';
    $('#metric-resolved').textContent = dados ? String(dados.totalResolvidos ?? 0) : '—';
  }

  quadro(colunas, cursos) {
    this.cursos=cursos;
    this.colunas = colunas;
    const nodes = Object.keys(STATUS).map(status => {
      const estado = colunas[status];
      const section = el('section', `ticket-column status-${status}`);
      section.dataset.columnStatus = status; section.setAttribute('aria-label', STATUS[status]);
      const heading = el('div', 'column-heading'); heading.append(el('span', 'status-dot'), el('h3', '', STATUS[status]), el('span', 'column-count', estado.total ?? `${estado.itens.length}${estado.cursor ? '+' : ''}`));
      const lista = el('div', 'ticket-list');
      for (const item of estado.itens) lista.append(this.card(item, cursos));
      if (!estado.itens.length && !estado.erro) lista.append(vazio(estado.loading ? 'Carregando...' : 'Nenhum chamado', estado.loading ? 'Consultando atendimentos.' : 'Os atendimentos deste status aparecerão aqui.'));
      if (estado.erro) {
        const erro = vazio('Consulta indisponível', estado.erro, 'warning');
        const tentar = button('Tentar novamente'); tentar.dataset.retryStatus = status; erro.append(tentar); lista.append(erro);
      }
      section.append(heading, lista);
      if (estado.cursor) {
        const mais = button(estado.loading ? 'Carregando...' : 'Carregar mais', 'button button-secondary button-small column-more');
        mais.dataset.moreStatus = status; mais.disabled = estado.loading; section.append(mais);
      }
      section.setAttribute('aria-busy', String(estado.loading));
      return section;
    });
    $('#ticket-board').replaceChildren(...nodes); this.atualizarAbas();
  }

  atualizarAbas() {
    const general = this.status === 'geral';
    $('#ticket-board').dataset.view = this.status; $('#ticket-board').classList.toggle('is-focused', !general);
    document.querySelectorAll('[data-column-status]').forEach(node => { node.hidden = !general && node.dataset.columnStatus !== this.status; });
    document.querySelectorAll('[data-ticket-status]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.ticketStatus === this.status)));
    const states = Object.values(this.colunas), complete = states.length === Object.keys(STATUS).length && states.every(s => Number.isInteger(s.total) && !s.erro);
    for (const [status, state] of Object.entries(this.colunas)) $(`[data-status-count="${status}"]`).textContent = state.erro ? '—' : state.total ?? '…';
    $('[data-status-count="geral"]').textContent = complete ? states.reduce((sum, s) => sum + s.total, 0) : '—';
    const selected = general ? states : [this.colunas[this.status]].filter(Boolean);
    const loaded = selected.reduce((sum, s) => sum + s.itens.length, 0), total = selected.reduce((sum, s) => sum + (s.total ?? 0), 0);
    $('#board-view-title').textContent = general ? 'Todos os atendimentos' : { aberto: 'Chamados abertos', em_andamento: 'Atendimentos em andamento', aguardando_aluno: 'Aguardando retorno do aluno', resolvido: 'Atendimentos resolvidos' }[this.status];
    $('#board-view-summary').textContent = !selected.length || selected.some(s => s.loading) ? 'Atualizando os chamados…' : selected.some(s => s.erro) ? 'Há uma consulta indisponível. Tente carregar o grupo novamente.' : `${total} atendimento${total === 1 ? '' : 's'} neste recorte${loaded < total ? ` · ${loaded} carregados; use Carregar mais` : ''}. ${general ? 'Selecione um status para concentrar sua visualização.' : 'Use Quadro geral para ver todos os status.'}`;
    if(!general)$('#board-view-title').textContent=STATUS[this.status];
    attendanceTable(this.colunas,this.cursos||new Map(),this.status);
  }

  reiniciar() {
    attendanceMetrics(null);
    $('#ticket-search').value='';$('#ticket-order').value='risco';$('#ticket-unassigned').checked=false;
    this.status = 'geral'; this.colunas = {}; this.atualizarAbas();
    document.querySelectorAll('[data-status-count]').forEach(node => { node.textContent = '—'; });
    $('#detail-risk')?.replaceChildren();
    $('#detail-risk-evolution')?.replaceChildren();
  }

  card(item, cursos) {
    const parado = !['resolvido','encerrado'].includes(item.status) && Date.now() - Date.parse(item.ultimaAtividadeEm) > 48 * 3600000;
    const nivel = item.riscoAcademico?.nivel || 'sem_avaliacao';
    const card = button('', `ticket-card card-risk-${nivel}${parado ? ' card-stalled' : ''}`); card.dataset.ticketId = item.id; card.dataset.risk = nivel;
    const protocolo = el('span', 'card-protocol'); protocolo.append(el('span', '', item.protocolo), icon('chevron'));
    card.append(protocolo, risco(item), el('span', 'card-title', item.titulo), el('span', 'card-course', cursos.get(item.cursoId) || 'Curso vinculado'), el('span', 'badge', CATEGORIAS[item.categoria] || item.categoria));
    if(item.evolucaoRisco?.variacao!=null)card.append(el('span','risk-change '+item.evolucaoRisco.direcao,changeLabel(item.evolucaoRisco)));
    if (item.alunoNome) {
      const student=el('span','card-student',item.alunoNome);
      card.append(student,el('span','card-course','Matrícula '+item.matricula));
      if (item.consentimentoRevogado) card.append(el('span', 'badge', 'Consentimento revogado'));
    }
    const footer = el('span', 'card-footer');
    footer.append(el('span', 'avatar', item.responsavel ? iniciais(item.responsavel.nome) : '—'), el('span', 'owner', item.responsavel?.nome || 'Sem responsável'), el('span', '', relativo(item.abertoEm)));
    card.append(footer);
    if (parado) { const alerta = el('span', 'stalled-text'); alerta.append(icon('clock'), el('span', '', 'Mais de 48h sem atividade')); card.append(alerta); }
    return card;
  }

  abrirDetalhe() {
    $('#detail-content').hidden = true; $('#ticket-detail-title').textContent = 'Carregando atendimento...';
    $('#detail-protocol').textContent = ''; $('#detail-badges').replaceChildren();
    $('#detail-risk').replaceChildren();
    $('#detail-risk-evolution').replaceChildren();
    $('#detail-metadata').replaceChildren(); $('#detail-description').textContent = ''; $('#timeline').replaceChildren();
    $('#ticket-action-form').reset(); $('#ticket-action-error').hidden = true;
    this.estadoDetalhe('Carregando os dados do atendimento.');
    if (!$('#ticket-dialog').open) $('#ticket-dialog').showModal();
  }

  estadoDetalhe(mensagem, erro = false) {
    const node = $('#detail-state'); node.textContent = mensagem || ''; node.hidden = !mensagem;
    node.className = erro ? 'alert alert-error' : 'alert';
    if (erro) { $('#detail-content').hidden = true; $('#ticket-detail-title').textContent = 'Atendimento indisponível'; }
  }

  detalhe(item, estudante, cursos, responsaveis, sessao) {
    this.item = item;
    $('#detail-protocol').textContent = item.protocolo; $('#ticket-detail-title').textContent = item.titulo;
    $('#detail-badges').replaceChildren(el('span', `badge status status-${item.status}`, STATUS[item.status]), el('span', 'badge', CATEGORIAS[item.categoria] || item.categoria));
    $('#detail-risk').replaceChildren(risco(item, true));
    const canContact=item.whatsappSimuladoUrl && !['diretor_campus','atendente_academico'].includes(sessao.perfil);
    const contact = el(canContact ? 'a' : 'span', 'button whatsapp-contact');
    const whatsappIcon = el('i', 'fa-brands fa-whatsapp'); whatsappIcon.setAttribute('aria-hidden','true');
    contact.append(whatsappIcon, el('span', '', 'Conversar no WhatsApp'));
    if (canContact) {
      contact.href = item.whatsappSimuladoUrl; contact.target = '_blank'; contact.rel = 'noopener';
      contact.setAttribute('aria-label', 'Conversar no WhatsApp simulado com '+(estudante?.nome || item.alunoNome || 'o aluno'));
      contact.title = 'Abrir a conversa deste aluno no WhatsApp simulado';
    } else {
      contact.setAttribute('aria-disabled','true'); contact.title = 'Aluno indisponível ou sem vínculo ativo para a simulação.';
    }
    $('#detail-risk').append(contact);
    $('#detail-risk-evolution').replaceChildren(renderRiskHistory(item.evolucaoRisco));
    const origens = { aluno: 'Aluno', equipe: 'Equipe', inatividade: 'Inatividade' };
    metadata($('#detail-metadata'), [
      ['Curso', cursos.get(item.cursoId) || 'Curso vinculado'], ['Aluno', estudante?.nome || 'Cadastro indisponível'],
      ...(estudante?.matricula ? [['Matrícula', estudante.matricula], ['Situação acadêmica', estudante.status]] : []),
      ['Responsável', item.responsavel?.nome || 'Não atribuído'], ['Abertura', data(item.abertoEm)],
      ['Última atividade', data(item.ultimaAtividadeEm)], ['Tempo de resolução', duracao(item.tempoResolucaoMin)],
      ...(item.aguardandoAlunoEm ? [['Aguardando aluno desde', data(item.aguardandoAlunoEm)]] : []),
      ...(item.resolvidoEm ? [['Resolução', data(item.resolvidoEm)], ['Encerrado por', origens[item.encerradoPor] || item.encerradoPor]] : []),
    ]);
    $('#detail-description').textContent = item.descricao;
    let checkins=$('#detail-checkins');
    if(!checkins){checkins=el('section','timeline-section');checkins.id='detail-checkins';$('#detail-description').after(checkins);}
    checkins.replaceChildren();checkins.hidden=item.origem!=='whatsapp_simulado';
    if(item.origem==='whatsapp_simulado'){
      checkins.append(el('h3','','Respostas do WhatsApp simulado'));
      if(item.consentimentoRevogado)checkins.append(el('p','muted','O consentimento foi revogado. As respostas e os indicadores derivados foram removidos; o histórico do atendimento permanece.'));
      const finances={'não sinto dificuldade':'Sem dificuldade','dificuldade leve':'Dificuldade leve','dificuldade significativa':'Dificuldade significativa','considerando trancar por motivo financeiro':'Considerando trancar por motivo financeiro'};
      const emotions={1:'Muito ruim',2:'Ruim',3:'Regular',4:'Bom',5:'Muito bom'};
      for(const response of item.questionarios||[]){
        checkins.append(el('h4','subheading','Questionário de '+data(response.data_avaliacao)));
        const values=el('dl','metadata-grid');
        metadata(values,[['Situação financeira',finances[response.resposta_financeira]||response.resposta_financeira],['Bem-estar emocional',emotions[response.resposta_psicologica]],['Média',response.nota_media],['Frequência',response.frequencia==null?'Não informada':response.frequencia+'%'],['Índice de risco',response.indice_risco==null?'Sem índice':formatIndex(response.indice_risco)+' / 100'],['Classificação',response.classificacao_risco||'Dados acadêmicos insuficientes']]);
        checkins.append(values);
        if(response.limitacao)checkins.append(el('p','muted small-text',response.limitacao));
      }
    }
    const manager=['admin_geral','admin_tecnico','gestor_curso','coordenador_curso'].includes(sessao.perfil),closed=['resolvido','encerrado'].includes(item.status);
    $('#assume-ticket').hidden = true;
    $('#ticket-action-panel').hidden = sessao.perfil==='diretor_campus' || (closed&&!manager);
    $('#ticket-resolved-note').hidden = !closed;
    options($('#ticket-action-type'),[{id:'comentario',nome:'Registrar observação ou providência'},{id:'status',nome:'Atualizar andamento ou resolução'},...(manager&&!closed?[{id:'classificacao',nome:'Categoria e prioridade'},{id:'responsavel',nome:'Atribuir, transferir ou remover responsável'}]:[])],null);
    options($('#action-status'), (TRANSICOES[item.status] || []).filter(id=>manager||!['reaberto','encerrado'].includes(id)).map(id => ({ id, nome: STATUS[id] })), null);
    options($('#action-category'), Object.entries(CATEGORIAS).map(([id, nome]) => ({ id, nome })), null, item.categoria);
    if(!$('#action-priority')){const label=el('label','field');label.id='action-priority-field';label.append(el('span','','Prioridade operacional'));const select=el('select');select.id='action-priority';label.append(select);$('#action-category-field').after(label);}
    options($('#action-priority'),[{id:'alta',nome:'Alta'},{id:'normal',nome:'Normal'},{id:'baixa',nome:'Baixa'}],null,item.prioridade||'normal');
    const pessoas = responsaveis.filter(u => u.perfil==='atendente_academico' && (u.cursoIds||[u.cursoId]).includes(item.cursoId));
    options($('#action-responsible'), pessoas.map(u => ({ id: u.uid, nome: u.nome })), 'Sem responsável / remover atribuição', item.responsavel?.uid || '');
    this.camposAcao(); this.estadoDetalhe(''); $('#detail-content').hidden = false;
  }

  camposAcao() {
    const acao = $('#ticket-action-type').value;
    $('#action-status-field').hidden = acao !== 'status'; $('#action-status').required = acao === 'status';
    $('#action-category-field').hidden = acao !== 'classificacao'; $('#action-category').required = acao === 'classificacao';
    if($('#action-priority-field'))$('#action-priority-field').hidden=acao!=='classificacao';
    $('#action-responsible-field').hidden = acao !== 'responsavel'; $('#action-responsible').required = false;
    $('#action-text-field').hidden = false; $('#action-text').required = true;
    $('#action-visible-field').hidden = acao !== 'comentario';
    $('#action-text-label').textContent = acao === 'status' && $('#action-status').value === 'aguardando_aluno' ? 'Explique o que o aluno deve fazer' : acao === 'classificacao' ? 'Explique a classificação' : 'Descreva a ação realizada';
    if(acao==='responsavel')$('#action-text-label').textContent='Motivo da atribuição, transferência ou remoção';
    $('#action-help').textContent = acao === 'status' && $('#action-status').value === 'resolvido' ? 'Descreva a solução. A resolução preserva o histórico e não altera o risco acadêmico.' : acao === 'responsavel' ? 'Selecione um atendente habilitado para este curso e câmpus. A transferência revoga o acesso do responsável anterior.' : 'O registro será acrescentado ao histórico com sua identificação e a data do servidor.';
    $('#ticket-action-save').textContent = ({ comentario: 'Registrar ação', status: 'Atualizar status', classificacao: 'Salvar classificação', responsavel: 'Atribuir responsável' })[acao];
  }

  historico(eventos, cursor, carregando = false) {
    const ordem = { abertura: 0, classificacao: 1, acao: 2, validacao: 3, encerramento: 4 };
    const lista = [...eventos].sort((a, b) => a.criadoEm === b.criadoEm ? (ordem[a.tipo] ?? 2) - (ordem[b.tipo] ?? 2) : Date.parse(a.criadoEm) - Date.parse(b.criadoEm));
    $('#timeline').replaceChildren(...lista.map(evento => {
      const [tipo, nomeIcone] = TIPOS[evento.tipo] || ['Registro', 'comment'];
      const node = el('li', 'timeline-event'); const marker = el('span', 'timeline-marker'); marker.append(icon(nomeIcone));
      const content = el('div'); const heading = el('div', 'timeline-title');
      const time = el('time', '', data(evento.criadoEm)); time.dateTime = evento.criadoEm;
      heading.append(el('span', '', tipo), time);
      const autor = el('div', 'timeline-author'); autor.append(el('span', '', evento.autor?.nome || 'RADACHE'), el('span', 'badge', evento.visivelAoAluno ? 'Visível ao aluno' : 'Interno'));
      content.append(heading, el('p', 'preserve-lines', evento.texto), autor); node.append(marker, content); return node;
    }));
    if (!lista.length) $('#timeline').append(vazio(carregando ? 'Carregando histórico...' : 'Nenhum evento disponível', carregando ? 'Consultando os registros do atendimento.' : 'Os registros deste atendimento aparecerão aqui.', 'comment'));
    $('#more-history').hidden = !cursor; $('#more-history').disabled = carregando;
    $('#more-history').textContent = carregando ? 'Carregando...' : 'Carregar mais eventos';
  }
}
