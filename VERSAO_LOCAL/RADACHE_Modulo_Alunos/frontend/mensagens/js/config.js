/** Configuração única da integração; nenhum módulo de UI conhece o fetch. */
export const API_CONFIG = Object.freeze({
  // BACK-END: substitua SOMENTE esta URL pelo endpoint real (ex.: /api/mensagens).
  // O padrão usa um mock HTTP local; não grava no banco e não contata a Meta.
  endpoint: '/mock-api/mensagens',
  modo: 'mock', // Ao conectar o endpoint real, altere para 'real'.
  timeoutMs: 10000,
});

export const CHAT_CONFIG = Object.freeze({
  idRemetente: 1, // Identificador fictício da coordenação; em produção vem da sessão.
  limiteTexto: 4000,
});
