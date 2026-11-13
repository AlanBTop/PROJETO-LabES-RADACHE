/** Helpers de apresentação: dados do usuário sempre entram via textContent. */
const elemento = (tag, classe, texto) => {
  const node = document.createElement(tag);
  if (classe) node.className = classe;
  if (texto !== undefined) node.textContent = texto;
  return node;
};
const horario = iso => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
const normalizar = texto => texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

/** Camada de apresentação: DOM/eventos, sem fetch nem decisões de persistência. */
export class ChatView {
  constructor(config) {
    this.config = config;
    this.input = document.querySelector('#message-input');
    this.lista = document.querySelector('#message-list');
    this.area = document.querySelector('#message-area');
    this.dialog = document.querySelector('#api-dialog');
    this.limiteTexto = this.input.maxLength;
    this.payloadAtual = null;
    this.buscaMensagem = '';
    this.ocupado = false;
    document.querySelector('#api-endpoint').textContent = config.endpoint;
    document.querySelector('#mode-badge').lastChild.textContent = config.modo === 'mock' ? 'API mock local' : 'API RADACHE';
    if (config.modo !== 'mock') {
      document.querySelector('.dialog-description').textContent = 'Confira o contrato enviado ao back-end e a resposta HTTP. A confirmação não indica entrega ao destinatário.';
      document.querySelector('.demo-notice span').textContent = 'Protótipo RADACHE conectado à API configurada. A confirmação HTTP não indica entrega ao WhatsApp.';
    }
    document.querySelector('#experience-link').textContent = config.simulacao ? 'Abrir teste manual da API ↗' : 'Voltar à simulação do aluno ↗';
    document.querySelector('#experience-link').href = config.simulacao ? '?modo=api' : './';
    if (config.simulacao) this.prepararSimulacao();
  }

  /** Conecta eventos a callbacks do controlador, preservando a separação das camadas. */
  conectar(acoes) {
    document.querySelector('#message-form').addEventListener('submit', event => {
      event.preventDefault();
      acoes.enviar(this.input.value);
    });
    this.input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        document.querySelector('#message-form').requestSubmit();
      }
    });
    this.input.addEventListener('input', () => {
      this.atualizarComposer();
      acoes.rascunho(this.input.value);
    });
    document.querySelector('#contact-list').addEventListener('click', event => {
      const button = event.target.closest('[data-contact-id]');
      if (button) acoes.selecionar(Number(button.dataset.contactId));
    });
    document.querySelector('#contact-search').addEventListener('input', event => acoes.buscar(event.target.value));
    document.querySelectorAll('[data-filter]').forEach(button => {
      button.addEventListener('click', () => acoes.filtrar(button.dataset.filter));
    });
    this.lista.addEventListener('click', event => {
      const button = event.target.closest('[data-retry-id]');
      if (button) acoes.reenviar(button.dataset.retryId);
    });
    const voltar = () => document.querySelector('#workspace').classList.remove('is-chat-open');
    document.querySelector('#back-button').addEventListener('click', voltar);
    document.querySelector('#show-conversations').addEventListener('click', voltar);
    document.querySelectorAll('[data-open-inspector]').forEach(button => button.addEventListener('click', () => this.dialog.showModal()));
    document.querySelector('#about-button').addEventListener('click', () => document.querySelector('#about-dialog').showModal());
    document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
    document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => {
      const rect = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
    }));
    document.querySelector('#copy-payload').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(JSON.stringify(this.payloadAtual, null, 2));
        this.notificar('JSON copiado.');
      } catch { this.notificar('Selecione o JSON no painel para copiá-lo; o navegador bloqueou a área de transferência.'); }
    });
    document.querySelector('#emoji-toggle').addEventListener('click', () => this.mostrarEmojis(document.querySelector('#emoji-picker').hidden));
    document.querySelectorAll('[data-emoji]').forEach(button => button.addEventListener('click', () => {
      const texto = button.dataset.emoji;
      const selecionado = this.input.selectionEnd - this.input.selectionStart;
      if (this.input.value.length - selecionado + texto.length > this.limiteTexto) {
        this.notificar('O limite de caracteres foi atingido.');
        return;
      }
      this.input.setRangeText(texto, this.input.selectionStart, this.input.selectionEnd, 'end');
      this.input.dispatchEvent(new Event('input', { bubbles: true }));
      this.mostrarEmojis(false);
      this.input.focus();
    }));
    document.addEventListener('click', event => {
      if (!event.target.closest('#emoji-picker, #emoji-toggle')) this.mostrarEmojis(false);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') this.mostrarEmojis(false);
    });
    document.querySelector('#chat-search-toggle').addEventListener('click', () => this.mostrarBusca(document.querySelector('#conversation-search').hidden));
    document.querySelector('#close-chat-search').addEventListener('click', () => this.mostrarBusca(false));
    document.querySelector('#message-search').addEventListener('input', event => {
      this.buscaMensagem = event.target.value;
      this.destacarResultados(true);
    });
    document.querySelector('#simulation-replies').addEventListener('click', event => {
      const button = event.target.closest('[data-answer]');
      if (button) acoes.enviar(button.dataset.answer);
    });
    document.querySelectorAll('[data-simulation-action]').forEach(button => button.addEventListener('click', () => acoes.simular?.(button.dataset.simulationAction)));
    document.querySelector('#simulate-audio').addEventListener('click', () => acoes.simular?.('audio'));
  }

  mostrarEmojis(abrir) {
    document.querySelector('#emoji-picker').hidden = !abrir;
    document.querySelector('#emoji-toggle').setAttribute('aria-expanded', String(abrir));
  }

  mostrarBusca(abrir) {
    document.querySelector('#conversation-search').hidden = !abrir;
    document.querySelector('#chat-search-toggle').setAttribute('aria-expanded', String(abrir));
    if (abrir) document.querySelector('#message-search').focus();
    else {
      document.querySelector('#message-search').value = '';
      this.buscaMensagem = '';
      this.destacarResultados();
    }
  }

  destacarResultados(rolar = false) {
    const termo = normalizar(this.buscaMensagem.trim());
    let primeiro = null;
    let total = 0;
    this.lista.querySelectorAll('.message').forEach(node => {
      const match = Boolean(termo && normalizar(node.querySelector('.message-content').textContent).includes(termo));
      node.classList.toggle('match', match);
      if (match) { total++; primeiro ??= node; }
    });
    document.querySelector('#search-results').textContent = termo ? `${total} resultado${total === 1 ? '' : 's'}` : '';
    if (rolar && primeiro) primeiro.scrollIntoView({ block: 'center' });
  }

  /** Reconstrói apenas a lista de contatos, sem tocar no histórico ou no composer. */
  renderizarContatos(contatos, historicos, selecionado, filtro, total, naoLidos) {
    const fragment = document.createDocumentFragment();
    contatos.forEach(contato => {
      const historico = historicos.get(contato.id);
      const ultima = historico?.at(-1);
      const button = elemento('button', `contact${contato.id === selecionado ? ' active' : ''}${contato.naoLidas ? ' has-unread' : ''}`);
      button.type = 'button';
      button.dataset.contactId = contato.id;
      if (contato.id === selecionado) button.setAttribute('aria-current', 'true');
      button.setAttribute('aria-label', `${contato.nome}${contato.naoLidas ? `, ${contato.naoLidas} mensagens não lidas` : ''}`);
      const avatar = elemento('span', `avatar tone-${contato.tom}`, contato.iniciais);
      avatar.setAttribute('aria-hidden', 'true');
      const content = elemento('span', 'contact-content');
      const top = elemento('span', 'contact-top');
      top.append(elemento('span', 'contact-name', contato.nome), elemento('span', 'contact-time', ultima ? horario(ultima.timestamp) : ''));
      const preview = elemento('span', 'contact-preview');
      const prefixo = ultima?.status === 'falhou' ? 'Falha · ' : ultima?.enviada ? 'Você: ' : this.config.simulacao ? 'RADACHE: ' : '';
      preview.append(elemento('span', 'contact-preview-text', ultima ? prefixo + ultima.texto : 'Inicie uma conversa'));
      if (contato.naoLidas) preview.append(elemento('span', 'unread-badge', String(contato.naoLidas)));
      content.append(top, preview);
      button.append(avatar, content);
      fragment.append(button);
    });
    if (!contatos.length) fragment.append(elemento('p', 'empty-state', 'Nenhuma conversa encontrada. Experimente outra busca ou o filtro Todas.'));
    document.querySelector('#contact-list').replaceChildren(fragment);
    document.querySelector('#all-count').textContent = total;
    document.querySelector('#unread-count').textContent = naoLidos;
    document.querySelectorAll('[data-filter]').forEach(button => {
      button.classList.toggle('active', button.dataset.filter === filtro);
      button.setAttribute('aria-pressed', String(button.dataset.filter === filtro));
    });
  }

  /** Troca o histórico visível e recupera o rascunho exclusivo do destinatário. */
  renderizarConversa(contato, mensagens, rascunho, abrir = true) {
    document.querySelector('#chat-name').textContent = this.config.simulacao ? 'RADACHE' : contato.nome;
    document.querySelector('#chat-course').textContent = this.config.simulacao ? `Simulando ${contato.nome} · aluno(a)` : `${contato.curso} · ${contato.semestre}`;
    const avatar = document.querySelector('#chat-avatar');
    avatar.className = this.config.simulacao ? 'avatar bot-avatar' : `avatar tone-${contato.tom}`;
    avatar.textContent = this.config.simulacao ? 'R·' : contato.iniciais;
    this.lista.replaceChildren();
    this.lista.append(elemento('p', 'conversation-intro', this.config.simulacao ? 'Simulação de WhatsApp · Você responde como aluno e o RADACHE conduz o check-in automaticamente.' : 'Esta é uma conversa de exemplo. Um espaço para acolher, ouvir e acompanhar a jornada de cada estudante.'));
    mensagens.forEach(mensagem => this.adicionarMensagem(mensagem, false));
    this.input.value = rascunho;
    this.atualizarComposer();
    this.mostrarBusca(false);
    this.mostrarEmojis(false);
    if (abrir) document.querySelector('#workspace').classList.add('is-chat-open');
    this.rolarAoFinal();
  }

  criarMensagem(mensagem) {
    const node = elemento('article', `message${mensagem.enviada ? ' outgoing' : ''}`);
    node.dataset.messageId = mensagem.id;
    node.dataset.status = mensagem.status;
    if (mensagem.template) node.dataset.template = mensagem.template;
    node.setAttribute('aria-label', mensagem.enviada ? 'Mensagem enviada por você' : 'Mensagem recebida');
    if (mensagem.rotulo) node.append(elemento('span', 'message-label', mensagem.rotulo));
    node.append(elemento('p', 'message-content', mensagem.texto));
    const meta = elemento('div', 'message-meta');
    const time = elemento('time', '', horario(mensagem.timestamp));
    time.dateTime = mensagem.timestamp;
    meta.append(time);
    if (mensagem.enviada) {
      const rotulos = {
        enviando: 'Enviando para a API',
        confirmado: this.config.simulacao ? 'Salva no banco local' : this.config.modo === 'mock' ? 'Aceita pelo mock; não persistida' : 'Requisição confirmada pela API; entrega não verificada',
        falhou: mensagem.erro || 'Falha ao enviar',
        exemplo: 'Mensagem fictícia de demonstração',
        obsoleto: 'Envio cancelado porque a simulação avançou para outra etapa',
      };
      const simbolos = { enviando: '◷', confirmado: '✓', falhou: '!', exemplo: '✓✓', obsoleto: '—' };
      const status = elemento('span', 'message-status', simbolos[mensagem.status]);
      status.setAttribute('aria-label', rotulos[mensagem.status]);
      status.title = rotulos[mensagem.status];
      meta.append(status);
    }
    node.append(meta);
    if (mensagem.status === 'falhou') {
      const retry = elemento('button', 'retry-button', 'Falha no envio · Tentar novamente ↻');
      retry.type = 'button';
      retry.dataset.retryId = mensagem.id;
      retry.title = mensagem.erro;
      node.append(retry);
    }
    return node;
  }

  adicionarMensagem(mensagem, rolar = true) {
    const data = new Date(mensagem.timestamp).toLocaleDateString('pt-BR');
    const ultimaData = this.lista.querySelector('.day-divider:last-of-type')?.dataset.date;
    if (ultimaData !== data) {
      const hoje = new Date().toLocaleDateString('pt-BR');
      const divider = elemento('div', 'day-divider', data === hoje ? 'HOJE' : data);
      divider.dataset.date = data;
      this.lista.append(divider);
    }
    this.lista.append(this.criarMensagem(mensagem));
    this.destacarResultados();
    if (rolar) this.rolarAoFinal();
  }

  atualizarMensagem(mensagem) {
    const node = this.lista.querySelector(`[data-message-id="${CSS.escape(mensagem.id)}"]`);
    if (node) node.replaceWith(this.criarMensagem(mensagem));
    this.destacarResultados();
  }

  atualizarComposer() {
    this.input.style.height = 'auto';
    this.input.style.height = `${Math.min(130, Math.max(40, this.input.scrollHeight))}px`;
    document.querySelector('#send-button').disabled = this.ocupado || !this.input.value.trim();
    document.querySelector('#character-count').textContent = `${this.input.value.length.toLocaleString('pt-BR')} / ${this.limiteTexto.toLocaleString('pt-BR')}`;
  }

  limparComposer() {
    this.input.value = '';
    this.atualizarComposer();
    this.mostrarEmojis(false);
    this.input.focus();
  }

  rolarAoFinal() { this.area.scrollTop = this.area.scrollHeight; }

  prepararSimulacao() {
    document.body.classList.add('simulation-mode');
    document.querySelector('#simulation-controls').hidden = false;
    document.querySelector('#simulation-replies').hidden = false;
    document.querySelector('#simulate-audio').hidden = false;
    document.querySelector('.sidebar-header h1').replaceChildren('Simulador', elemento('span', 'heading-dot', '.'));
    document.querySelector('.sidebar-header p').textContent = 'Escolha um aluno fictício para testar.';
    document.querySelector('.filters').hidden = true;
    document.querySelector('#mode-badge').lastChild.textContent = 'Simulação local';
    document.querySelector('.self-avatar').textContent = 'EU';
    document.querySelector('.self-avatar').title = 'Você responde como aluno';
    document.querySelector('.demo-notice span').textContent = 'Demonstração local com alunos e conversas persistidos em SQLite.';
    document.querySelector('#message-input').placeholder = 'Responda como aluno...';
    document.querySelector('#about-dialog p').textContent = 'Simulação acadêmica da conversa de um aluno com o assistente RADACHE, usando o roteiro de check-in fornecido pelo projeto.';
    document.querySelectorAll('#about-dialog p')[1].textContent = 'Responda às perguntas, teste recusa e revogação ou avance o relógio para demonstrar lembretes e outro mês. Cada perfil tem uma conversa independente.';
    document.querySelector('.about-note').textContent = 'Os dados fictícios e as conversas ficam nos bancos locais. Recarregar recupera o histórico; reiniciar cria uma nova sessão e preserva as anteriores.';
  }

  /** Apresenta o estado do roteiro sem decidir transições ou calcular componentes. */
  atualizarSimulacao(contato, estado, ocupado = false) {
    const etapas = { consentimento: 'Aguardando consentimento', aguardando_inicio: 'Aguardando início', financeira: 'Pergunta 1 de 2', emocional: 'Pergunta 2 de 2', concluido: 'Check-in concluído', recusado: 'Participação recusada', revogado: 'Consentimento revogado' };
    document.querySelector('#simulation-student').textContent = `${contato.nome} · ${contato.curso}`;
    document.querySelector('#simulation-stage').textContent = etapas[estado.etapa];
    document.querySelector('#simulation-stage').dataset.stage = estado.etapa;
    document.querySelector('#simulation-progress-fill').style.width = `${({ financeira: 33, emocional: 66, concluido: 100 })[estado.etapa] || 0}%`;
    document.querySelector('#simulation-date').textContent = new Date(estado.timestamp).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
    document.querySelector('#simulation-data').textContent = `Consentimento: ${estado.consentimento ? 'sim' : 'não'} · F: ${estado.F ?? '—'} · P: ${estado.P ?? '—'} · Persistência: SQLite local`;
    const formatarData = iso => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    document.querySelector('#simulation-consent').textContent = estado.dataConsentimento ?
      `Autorizado em: ${formatarData(estado.dataConsentimento)} · ${estado.consentimentoExpirado ? 'Vencido em' : 'Válido até'}: ${formatarData(estado.validadeConsentimento)}` :
      'Data do consentimento: não concedido · Validade: 12 meses a partir do aceite.';
    const respostas = {
      consentimento: [['1', '1 · Sim, aceito'], ['2', '2 · Não, obrigado(a)']],
      aguardando_inicio: [['1', '1 · Começar as perguntas']],
      financeira: [['1', '1 · Sem dificuldade'], ['2', '2 · Leve'], ['3', '3 · Significativa'], ['4', '4 · Trancar o curso']],
      emocional: [['1', '1 · Muito ruim'], ['2', '2 · Ruim'], ['3', '3 · Regular'], ['4', '4 · Bom'], ['5', '5 · Muito bom']],
      concluido: [['REVOGAR', 'REVOGAR consentimento']],
      recusado: [['INICIAR', 'INICIAR novamente']],
      revogado: [['INICIAR', 'INICIAR novamente']],
    };
    const botoes = (respostas[estado.etapa] || []).map(([valor, label]) => {
      const button = elemento('button', 'quick-reply', label);
      button.type = 'button';
      button.dataset.answer = valor;
      button.disabled = ocupado;
      return button;
    });
    document.querySelector('#simulation-replies').replaceChildren(...botoes);
    this.ocupado = ocupado;
    this.input.disabled = ocupado;
    document.querySelector('#simulate-audio').disabled = ocupado;
    document.querySelector('#emoji-toggle').disabled = ocupado;
    document.querySelector('#simulation-typing').hidden = !ocupado;
    document.querySelectorAll('[data-simulation-action]').forEach(button => { button.disabled = ocupado; });
    this.atualizarComposer();
  }

  /** Apresenta somente a tentativa mais recente, selecionada pelo controlador. */
  atualizarInspecao(registro) {
    this.payloadAtual = registro.payload;
    document.querySelector('#payload-preview').textContent = JSON.stringify(registro.payload, null, 2);
    document.querySelector('#copy-payload').disabled = false;
    const status = document.querySelector('#api-status');
    status.classList.toggle('error', registro.estado === 'falhou');
    status.textContent = registro.estado === 'enviando' ? 'Enviando…' : registro.status ? `HTTP ${registro.status}${registro.estado === 'falhou' ? ' · falha' : ''}` : 'Falha de conexão';
    document.querySelector('#response-preview').textContent = registro.estado === 'enviando' ? 'Aguardando resposta da API…' : JSON.stringify(registro.resposta ?? { erro: registro.erro }, null, 2);
  }

  anunciar(texto) { document.querySelector('#announcer').textContent = texto; }

  notificar(texto) {
    clearTimeout(this.toastTimer);
    const toast = document.querySelector('#toast');
    toast.textContent = texto;
    toast.hidden = false;
    this.toastTimer = setTimeout(() => { toast.hidden = true; }, 5000);
  }
}

export { normalizar };
