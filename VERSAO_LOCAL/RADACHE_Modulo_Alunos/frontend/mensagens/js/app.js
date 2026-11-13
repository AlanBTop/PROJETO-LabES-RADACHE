import { API_CONFIG, CHAT_CONFIG } from './config.js';
import { CONTATOS_DEMO, criarHistoricosDemo } from './data/demo.js';
import { criarPayload } from './models/mensagem.js';
import { ApiService } from './services/api-service.js';
import { ChatView, normalizar } from './ui/chat-view.js';
import { SimulationController } from './persistent-controller.js';
import { CheckinSimulator } from './services/checkin-simulator.js';

/**
 * Controlador da aplicação: coordena estado, domínio, serviço e apresentação.
 * Mantém mensagens/rascunhos por destinatário e correlaciona respostas por UUID.
 * Nenhum histórico é persistido no navegador ou no banco durante o mock.
 */
class ChatController {
  constructor(api, view) {
    this.api = api;
    this.view = view;
    this.contatos = CONTATOS_DEMO.map(contato => ({ ...contato }));
    this.historicos = criarHistoricosDemo();
    this.rascunhos = new Map();
    this.selecionado = this.contatos[0].id;
    this.filtro = 'all';
    this.busca = '';
    this.ultimaRequisicao = null;
  }

  iniciar() {
    this.view.conectar({
      enviar: texto => this.enviar(texto),
      selecionar: id => this.selecionar(id),
      buscar: termo => { this.busca = termo; this.listarContatos(); },
      filtrar: filtro => { this.filtro = filtro; this.listarContatos(); },
      reenviar: id => this.reenviar(id),
      rascunho: texto => this.rascunhos.set(this.selecionado, texto),
    });
    this.selecionar(this.selecionado, false);
  }

  listarContatos() {
    const termo = normalizar(this.busca.trim());
    const contatos = this.contatos.filter(contato =>
      (this.filtro !== 'unread' || contato.naoLidas > 0) &&
      normalizar(`${contato.nome} ${contato.curso}`).includes(termo),
    );
    this.view.renderizarContatos(contatos, this.historicos, this.selecionado, this.filtro,
      this.contatos.length, this.contatos.filter(contato => contato.naoLidas > 0).length);
  }

  selecionar(id, abrir = true) {
    const contato = this.contatos.find(item => item.id === id);
    if (!contato) return;
    this.selecionado = id;
    contato.naoLidas = 0;
    this.listarContatos();
    this.view.renderizarConversa(contato, this.historicos.get(id), this.rascunhos.get(id) || '', abrir);
  }

  /**
   * Atualização otimista: insere no DOM ANTES de iniciar o POST, sem aguardar a rede.
   * O payload captura o destinatário atual; trocar de conversa não altera o envio.
   * @param {string} texto Texto do composer.
   */
  enviar(texto) {
    if (!texto.trim()) return;
    let payload;
    try {
      payload = criarPayload({ texto, remetente: CHAT_CONFIG.idRemetente, destinatario: this.selecionado, limite: CHAT_CONFIG.limiteTexto });
    } catch (error) {
      this.view.notificar(error.message);
      return;
    }
    const mensagem = {
      id: payload.id_cliente, texto: payload.conteudo_texto, timestamp: payload.timestamp,
      enviada: true, status: 'enviando', payload,
    };
    this.historicos.get(this.selecionado).push(mensagem);
    this.rascunhos.delete(this.selecionado);
    this.view.adicionarMensagem(mensagem);
    this.view.limparComposer();
    this.listarContatos();
    void this.transmitir(mensagem);
  }

  reenviar(id) {
    const mensagem = this.historicos.get(this.selecionado).find(item => item.id === id);
    if (!mensagem || mensagem.status !== 'falhou') return;
    mensagem.status = 'enviando';
    mensagem.erro = null;
    this.view.atualizarMensagem(mensagem);
    this.listarContatos();
    // Reutiliza o mesmo payload e id_cliente; não cria uma segunda bolha.
    void this.transmitir(mensagem);
  }

  /**
   * Correlaciona a resposta com a mensagem original, mesmo em envios concorrentes.
   * A falha mantém a bolha visível e permite retry explícito com o mesmo UUID.
   * @param {Object} mensagem Estado da mensagem e seu payload imutável.
   * @returns {Promise<void>}
   */
  async transmitir(mensagem) {
    const registro = { payload: mensagem.payload, estado: 'enviando' };
    this.ultimaRequisicao = registro;
    this.view.atualizarInspecao(registro);
    try {
      const resposta = await this.api.enviarMensagem(mensagem.payload);
      mensagem.status = 'confirmado';
      mensagem.idServidor = resposta.dados?.dados?.id_mensagem ?? null;
      Object.assign(registro, { estado: 'confirmado', status: resposta.status, resposta: resposta.dados });
      this.view.anunciar(API_CONFIG.modo === 'mock' ? 'Mensagem aceita pelo mock. Dados não persistidos.' : 'Requisição confirmada pela API.');
    } catch (error) {
      mensagem.status = 'falhou';
      mensagem.erro = error.message;
      Object.assign(registro, { estado: 'falhou', status: error.status, resposta: error.resposta, erro: error.message });
      this.view.anunciar('Falha no envio da mensagem. Você pode tentar novamente.');
    }
    // Uma resposta antiga não deve sobrescrever a inspeção de um envio mais recente.
    if (this.ultimaRequisicao === registro) this.view.atualizarInspecao(registro);
    if (this.selecionado === mensagem.payload.id_destinatario) this.view.atualizarMensagem(mensagem);
    this.listarContatos();
  }
}

if (new URLSearchParams(location.search).get('modo') === 'api') {
  new ChatController(new ApiService(), new ChatView(API_CONFIG)).iniciar();
} else {
  // A experiência padrão é sempre local, mesmo se a API manual for reconfigurada.
  const configSimulacao = { endpoint: '/simulation-api', timeoutMs: 10000, modo: 'local', simulacao: true };
  new SimulationController(new ApiService(configSimulacao), new CheckinSimulator(), new ChatView(configSimulacao)).iniciar();
}
