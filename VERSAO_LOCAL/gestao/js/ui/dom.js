/** Elementos com dados externos usam textContent; não há interpolação de HTML. */
export const $ = seletor => document.querySelector(seletor);
export function el(tag, classe, texto) {
  const node = document.createElement(tag);
  if (classe) node.className = classe;
  if (texto !== undefined && texto !== null) node.textContent = String(texto);
  return node;
}
export function icon(nome) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', new URL(`../../assets/icons.svg#${nome}`, import.meta.url).href);
  svg.append(use); return svg;
}
export function button(texto, classe = 'button button-secondary button-small', acao, id) {
  const node = el('button', classe, texto); node.type = 'button';
  if (acao) node.dataset.action = acao;
  if (id) node.dataset.id = id;
  return node;
}
export function options(select, itens, placeholder = null, selecionado = '') {
  const nodes = [];
  if (placeholder !== null) { const option = el('option', '', placeholder); option.value = ''; nodes.push(option); }
  for (const item of itens) { const option = el('option', '', item.nome); option.value = item.id; option.disabled = item.disabled || false; nodes.push(option); }
  select.replaceChildren(...nodes); select.value = selecionado;
}
export function metadata(node, dados) {
  node.replaceChildren(...dados.map(([label, valor]) => { const group = el('div'); group.append(el('dt', '', label), el('dd', '', valor ?? 'Não informado')); return group; }));
}
export function vazio(titulo, mensagem, icone = 'tickets') {
  const node = el('div', 'empty-state'); node.append(icon(icone), el('strong', '', titulo));
  if (mensagem) node.append(el('p', '', mensagem));
  return node;
}
export function iniciais(nome = '') { return nome.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(parte => parte[0]).join('').toUpperCase() || 'R'; }
export function data(iso, hora = true) {
  if (!iso || !Number.isFinite(Date.parse(iso))) return 'Não informado';
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', ...(hora ? { timeStyle: 'short' } : {}) }).format(new Date(iso));
}
export function duracao(minutos) {
  if (minutos === null || minutos === undefined || !Number.isFinite(Number(minutos))) return '—';
  const total = Math.max(0, Math.round(Number(minutos)));
  return total < 60 ? `${total} min` : `${Math.floor(total / 60)}h ${String(total % 60).padStart(2, '0')}min`;
}
export function relativo(iso) {
  const minutos = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 60000));
  if (!Number.isFinite(minutos)) return 'Sem data';
  if (minutos < 1) return 'Agora';
  if (minutos < 60) return `${minutos} min`;
  if (minutos < 1440) return `${Math.floor(minutos / 60)}h`;
  return `${Math.floor(minutos / 1440)}d`;
}
export function textoSelect(valor, mapa) { return mapa[valor] || valor || 'Não informado'; }
export function erroFormulario(id, mensagem) { const node = $(id); node.textContent = mensagem || ''; node.hidden = !mensagem; }
export function ocupar(form, ocupado) {
  // Guarda o estado original: campos bloqueados por perfil continuam bloqueados.
  for (const campo of form.querySelectorAll('button, input, select, textarea')) {
    if (ocupado) { campo.dataset.disabledAntes = String(campo.disabled); campo.disabled = true; }
    else { campo.disabled = campo.dataset.disabledAntes === 'true'; delete campo.dataset.disabledAntes; }
  }
  form.setAttribute('aria-busy', String(ocupado));
}
