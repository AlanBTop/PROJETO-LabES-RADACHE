import { API_CONFIG } from '../config.js';

/** Erro de transporte com status e resposta disponíveis ao controlador. */
export class ApiError extends Error {
  constructor(mensagem, status = null, resposta = null) {
    super(mensagem);
    this.name = 'ApiError';
    this.status = status;
    this.resposta = resposta;
  }
}

/** Camada de serviço HTTP: não consulta nem modifica o DOM. */
export class ApiService {
  /** Permite injetar configuração/fetch para testes e integrações. */
  constructor(config = API_CONFIG, fetchImpl = (...args) => fetch(...args)) {
    this.config = config;
    this.fetchImpl = fetchImpl;
  }

  /**
   * Envia uma mensagem por POST HTTP com JSON. Não representa entrega ao WhatsApp.
   *
   * EQUIPE DE BACK-END: a URL real deve ser inserida em `js/config.js`, na
   * propriedade `API_CONFIG.endpoint` (ex.: '/api/mensagens'). Mantenha o contrato
   * do payload. Configure autenticação aqui, junto dos headers/credentials, quando
   * o endpoint real exigir sessão ou Bearer token; nunca inclua segredos no front.
   * Em outra origem, configure CORS no servidor. O mock atual é da mesma origem.
   *
   * O endpoint deve responder 200/201 com JSON `{sucesso: true, dados: {...}}`
   * (o mock também inclui `modo: 'mock', persistido: false`) ou 204 sem corpo.
   * `id_cliente` deve ter restrição UNIQUE no banco real para tornar o reenvio
   * seguro, inclusive após timeout com resultado incerto. Não há retry automático.
   *
   * @param {import('../models/mensagem.js').MensagemPayload} payload
   * @returns {Promise<{status: number, dados: Object|null}>} Status HTTP e JSON da resposta.
   * @throws {ApiError} Em erro HTTP, falha de rede, timeout ou resposta inválida.
   */
  async enviarMensagem(payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.config.timeoutMs);
    try {
      const response = await this.fetchImpl(this.config.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      let dados = null;
      const texto = await response.text();
      if (texto) {
        try { dados = JSON.parse(texto); }
        catch { throw new ApiError(`Resposta inválida do servidor (HTTP ${response.status}).`, response.status); }
      }
      if (!response.ok || dados?.sucesso === false) {
        throw new ApiError(dados?.erro || `O servidor recusou o envio (HTTP ${response.status}).`, response.status, dados);
      }
      if (response.status !== 204 && (!dados || dados.sucesso !== true)) {
        throw new ApiError('A API não confirmou o envio no formato esperado.', response.status, dados);
      }
      return { status: response.status, dados };
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (controller.signal.aborted) {
        throw new ApiError('O servidor não respondeu em tempo. O resultado do envio é incerto; tente novamente com o mesmo identificador.');
      }
      throw new ApiError('Não foi possível conectar à API. Verifique a conexão e tente novamente.');
    } finally {
      clearTimeout(timer);
    }
  }
}
