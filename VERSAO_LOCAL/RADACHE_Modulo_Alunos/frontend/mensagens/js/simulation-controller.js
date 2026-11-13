import { CHAT_CONFIG } from './config.js';
import { CONTATOS_DEMO } from './data/demo.js';
import { criarPayload } from './models/mensagem.js';
import { normalizar } from './ui/chat-view.js';

/** Coordena a experiência do aluno; as regras ficam em CheckinSimulator. */
export class SimulationController {
  constructor(api, simulator, view) {
    this.api = api;
    this.simulator = simulator;
    this.view = view;
    this.contatos = CONTATOS_DEMO.map(contato => ({ ...contato, naoLidas: 0 }));
    this.historicos = new Map();
    this.rascunhos = new Map();
    this.ocupados = new Set();
    this.selecionado = this.contatos[0].id;
    this.busca = '';
    this.ultimaRequisicao = null;
  }

  iniciar() {
    this.contatos.forEach(contato => {
      this.historicos.set(contato.id, []);
      this.adicionarRespostas(contato.id, this.simulator.reiniciar(contato.id), false);
    });
    this.view.conectar({
      enviar: texto => this.enviar(texto),
      selecionar: id => this.selecionar(id),
      buscar: busca => { this.busca = busca; this.listarContatos(); },
      filtrar: () => {},
      reenviar: id => this.reenviar(id),
      rascunho: texto => this.rascunhos.set(this.selecionado, texto),
      simular: acao => this.simular(acao),
    });
    this.selecionar(this.selecionado, false);
  }

  listarContatos() {
    const termo = normalizar(this.busca.trim());
    this.view.renderizarContatos(
      this.contatos.filter(c => normalizar(`${c.nome} ${c.curso}`).includes(termo)),
      this.historicos, this.selecionado, 'all', this.contatos.length, 0,
    );
  }

  selecionar(id, abrir = true) {
    const contato = this.contatos.find(c => c.id === id);
    if (!contato) return;
    this.selecionado = id;
    this.view.renderizarConversa(contato, this.historicos.get(id), this.rascunhos.get(id) || '', abrir);
    this.atualizarEstado();
    this.view.rolarAoFinal();
    this.listarContatos();
  }

  atualizarEstado() {
    this.view.atualizarSimulacao(this.contatos.find(c => c.id === this.selecionado),
      this.simulator.estado(this.selecionado), this.ocupados.has(this.selecionado));
  }

  adicionarRespostas(id, respostas, renderizar = true) {
    const timestamp = this.simulator.estado(id).timestamp;
    respostas.forEach(resposta => {
      const mensagem = { ...resposta, id: crypto.randomUUID(), timestamp, enviada: false, status: 'exemplo', payload: null };
      this.historicos.get(id).push(mensagem);
      if (renderizar && id === this.selecionado) this.view.adicionarMensagem(mensagem);
    });
  }

  /** A bolha do aluno aparece antes do POST; a resposta automática só vem após sucesso. */
  enviar(texto, tipo = 'texto') {
    const id = this.selecionado;
    if (!texto.trim() || this.ocupados.has(id)) return;
    let payload;
    try {
      const base = criarPayload({ texto, remetente: id, destinatario: CHAT_CONFIG.idRemetente, limite: CHAT_CONFIG.limiteTexto });
      payload = Object.freeze({ ...base, timestamp: this.simulator.estado(id).timestamp });
    } catch (error) { this.view.notificar(error.message); return; }
    const mensagem = {
      id: payload.id_cliente, texto: payload.conteudo_texto, timestamp: payload.timestamp,
      enviada: true, status: 'enviando', payload, tipo, alunoId: id,
    };
    this.historicos.get(id).push(mensagem);
    this.rascunhos.delete(id);
    this.view.adicionarMensagem(mensagem);
    this.view.limparComposer();
    void this.transmitir(mensagem);
  }

  reenviar(id) {
    const mensagem = this.historicos.get(this.selecionado).find(m => m.id === id);
    if (!mensagem || mensagem.status !== 'falhou' || this.ocupados.has(this.selecionado)) return;
    mensagem.status = 'enviando';
    this.view.atualizarMensagem(mensagem);
    void this.transmitir(mensagem);
  }

  /** Invalida retries de etapas antigas para não aplicar uma resposta a outra pergunta. */
  invalidarTentativas(id) {
    this.historicos.get(id).filter(m => m.status === 'falhou').forEach(m => {
      m.status = 'obsoleto';
      if (id === this.selecionado) this.view.atualizarMensagem(m);
    });
  }

  async transmitir(mensagem) {
    const id = mensagem.alunoId;
    this.ocupados.add(id);
    this.atualizarEstado();
    this.listarContatos();
    const registro = { payload: mensagem.payload, estado: 'enviando' };
    this.ultimaRequisicao = registro;
    this.view.atualizarInspecao(registro);
    try {
      const resposta = await this.api.enviarMensagem(mensagem.payload);
      mensagem.status = 'confirmado';
      Object.assign(registro, { estado: 'confirmado', status: resposta.status, resposta: resposta.dados });
      // Pequena pausa de apresentação; não substitui a requisição HTTP real.
      await new Promise(resolve => setTimeout(resolve, 300));
      const resultado = this.simulator.responder(id, mensagem.texto, mensagem.tipo);
      mensagem.sensivel = resultado.sensivel;
      if (resultado.revogado) {
        this.historicos.get(id).filter(m => m.sensivel).forEach(m => {
          m.texto = 'Resposta removida após revogação.';
          m.payload = null;
          m.sensivel = false;
          if (id === this.selecionado) this.view.atualizarMensagem(m);
        });
      }
      this.invalidarTentativas(id);
      this.adicionarRespostas(id, resultado.mensagens);
      this.view.anunciar('O RADACHE respondeu na simulação.');
    } catch (error) {
      mensagem.status = 'falhou';
      mensagem.erro = error.message;
      Object.assign(registro, { estado: 'falhou', status: error.status, resposta: error.resposta, erro: error.message });
      this.view.anunciar('Falha na comunicação com o mock. A etapa foi mantida; tente novamente.');
    } finally {
      this.ocupados.delete(id);
      if (this.ultimaRequisicao === registro) this.view.atualizarInspecao(registro);
      if (id === this.selecionado) this.view.atualizarMensagem(mensagem);
      this.atualizarEstado();
      if (id === this.selecionado) this.view.rolarAoFinal();
      this.listarContatos();
    }
  }

  simular(acao) {
    const id = this.selecionado;
    if (this.ocupados.has(id)) return;
    if (acao === 'audio') return this.enviar('🎙 Mensagem de áudio simulada · 0:05', 'audio');
    let respostas;
    if (acao === 'reiniciar') {
      this.historicos.set(id, []);
      this.rascunhos.delete(id);
      respostas = this.simulator.reiniciar(id);
    } else if (acao === 'mes') respostas = this.simulator.proximoMes(id);
    else if (acao === 'ano') respostas = this.simulator.avancarDozeMeses(id);
    else if (acao === 'dias') {
      respostas = this.simulator.avancarTresDias(id);
      this.view.notificar(respostas[0]?.template === 'radache_boas_vindas' ? 'O consentimento venceu. Boas-vindas reenviadas para renovar a autorização.' : respostas.length ? 'Três dias se passaram. Lembrete simulado recebido.' : 'Relógio avançado em três dias. Não há novo lembrete para enviar.');
    } else return;
    this.invalidarTentativas(id);
    this.adicionarRespostas(id, respostas, false);
    this.selecionar(id);
  }
}
