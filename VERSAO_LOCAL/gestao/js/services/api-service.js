export class ApiError extends Error {
  constructor(message, status = 0, incerto = false) { super(message); this.name = 'ApiError'; this.status = status; this.incerto = incerto; }
}

/** Transporte HTTP autenticado. Não consulta DOM, não altera claims e não escreve Firestore. */
export class ApiService {
  constructor(auth, config, aoExpirar) {
    this.auth = auth; this.config = config; this.aoExpirar = aoExpirar;
    this.base = new URL(config.apiBase, location.href);
    if (!this.base.pathname.endsWith('/')) this.base.pathname += '/';
    if (this.base.protocol !== 'https:' && !['127.0.0.1', 'localhost', '[::1]'].includes(this.base.hostname)) {
      throw new Error('A API institucional precisa utilizar HTTPS.');
    }
    this.controllers = new Set();
  }

  cancelarTudo() { for (const controller of this.controllers) controller.abort('cancelado'); this.controllers.clear(); }

  /**
   * URL central em js/config.js: apiBase. Envia somente ID token oficial no Bearer.
   * Escritas não têm retry automático; a interface mantém o idAcao no reenvio.
   * @returns {Promise<Object>} Dados do contrato JSON da API.
   */
  async requisitar(caminho, { method = 'GET', body, query, signal } = {}) {
    const url = new URL(caminho, this.base);
    if (url.origin !== this.base.origin || !url.pathname.startsWith(this.base.pathname)) throw new Error('Caminho de API inválido.');
    for (const [chave, valor] of Object.entries(query || {})) if (valor !== undefined && valor !== null && valor !== '') url.searchParams.set(chave, valor);
    const controller = new AbortController();
    const cancelar = () => controller.abort('cancelado');
    if (signal?.aborted) cancelar();
    else signal?.addEventListener('abort', cancelar, { once: true });
    this.controllers.add(controller);
    const timer = setTimeout(() => controller.abort('timeout'), this.config.timeoutMs);
    const escrita = method !== 'GET';
    try {
      const token = await this.auth.token();
      if (controller.signal.aborted) throw new DOMException('Cancelado', 'AbortError');
      const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      const response = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, credentials: 'omit', cache: 'no-store' });
      let payload;
      try { payload = await response.json(); }
      catch { throw new ApiError('O servidor retornou uma resposta inválida. Atualize para conferir o resultado.', response.status, escrita); }
      if (response.status === 401) {
        this.aoExpirar?.();
        throw new ApiError('Sua sessão mudou ou expirou. Entre novamente.', 401);
      }
      if (!response.ok || payload.sucesso !== true) {
        if(response.status===403&&String(payload.erro?.mensagem||payload.erro).startsWith('Analista Institucional'))location.replace('/institucional/');
        throw new ApiError(response.status === 404 ? 'Não encontrado.' : payload.erro?.mensagem || (typeof payload.erro === 'string' ? payload.erro : '') || 'Não foi possível concluir a operação.', response.status);
      }
      return payload.dados;
    } catch (error) {
      if (controller.signal.reason === 'cancelado') throw new DOMException('Cancelado', 'AbortError');
      if (error instanceof ApiError) throw error;
      throw new ApiError(escrita ? 'Não foi possível confirmar a alteração. Atualize os dados antes de tentar novamente.' : 'Não foi possível carregar os dados. Verifique sua conexão e tente novamente.', 0, escrita);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancelar);
      this.controllers.delete(controller);
    }
  }

  async todos(caminho, query = {}, signal) {
    const itens = [];
    let depois;
    for (let pagina = 0; pagina < 50; pagina++) {
      const dados = await this.requisitar(caminho, { query: { ...query, limite: 100, depois }, signal });
      itens.push(...dados.itens);
      depois = dados.proximaPagina;
      if (!depois) return itens;
    }
    throw new ApiError('Há muitos registros para esta seleção. Escolha um curso mais específico.');
  }
}
