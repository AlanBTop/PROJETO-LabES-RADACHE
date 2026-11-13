/**
 * @typedef {Object} MensagemPayload
 * @property {string} id_cliente UUID mantido nas novas tentativas; chave de idempotência.
 * @property {string} conteudo_texto Texto puro, sem HTML, entre 1 e 4000 caracteres.
 * @property {number} id_remetente ID do usuário remetente.
 * @property {number} id_destinatario ID do contato destinatário.
 * @property {string} timestamp Instante ISO 8601 com fuso UTC.
 */

/**
 * Cria e valida o contrato de transporte, sem acessar DOM ou rede.
 * O servidor real deve validar novamente e obter o remetente da sessão autenticada.
 * @param {{texto: string, remetente: number, destinatario: number, limite?: number}} dados
 * @returns {Readonly<MensagemPayload>}
 * @throws {Error} Se o texto ou os identificadores forem inválidos.
 */
export function criarPayload({ texto, remetente, destinatario, limite = 4000 }) {
  const conteudo = texto.trim();
  if (!conteudo || Array.from(conteudo).length > limite) {
    throw new Error(`Escreva uma mensagem de 1 a ${limite} caracteres.`);
  }
  if (![remetente, destinatario].every(id => Number.isSafeInteger(id) && id > 0)) {
    throw new Error('Remetente e destinatário devem ter identificadores válidos.');
  }
  return Object.freeze({
    id_cliente: crypto.randomUUID(),
    conteudo_texto: conteudo,
    id_remetente: remetente,
    id_destinatario: destinatario,
    timestamp: new Date().toISOString(),
  });
}
