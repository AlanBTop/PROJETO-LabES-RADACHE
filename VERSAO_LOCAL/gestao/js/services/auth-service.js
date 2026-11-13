/** Acesso exclusivamente local: sem SDK, emulador ou conexão externa. */
export class AuthService {
  constructor() { this.user = null; this.credencial = ''; this.callbacks = new Set(); }
  async preparar() {
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname)) throw new Error('Use o servidor local para abrir esta versão.');
  }
  observar(callback) { this.callbacks.add(callback); callback(this.user); return () => this.callbacks.delete(callback); }
  avisar() { for (const callback of this.callbacks) callback(this.user); }
  async entrar(email, senha) {
    const response = await fetch('/api/local/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, senha }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.erro?.mensagem || 'Não foi possível entrar.');
    if(payload.dados.usuario.perfil==='analista_institucional'){location.replace('/institucional/');return;}
    this.credencial = payload.dados.token; this.user = payload.dados.usuario; this.avisar();
  }
  async token() { if (!this.credencial) throw new Error('Entre novamente.'); return this.credencial; }
  async claims() { return this.user; }
  async sair() {
    const token = this.credencial; this.credencial = ''; this.user = null; this.avisar();
    if (token) await fetch('/api/local/logout', { method: 'POST', credentials:'omit', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token }, body: '{}' });
  }
  async recuperarSenha() { throw new Error('As contas de exemplo usam admin123. Para novos acessos, utilize a senha inicial definida no cadastro. Não há envio de e-mail.'); }
}
export function mensagemAcesso(error) { return error.message || 'Não foi possível preparar o acesso local.'; }
