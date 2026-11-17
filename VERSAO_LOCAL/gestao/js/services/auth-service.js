/** Acesso exclusivamente local: sem SDK, emulador ou conexão externa. */
export class AuthService {
  constructor() { this.user = null; this.credencial = ''; this.callbacks = new Set(); }
  async preparar() {
    if (['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname)) return;
    const response = await fetch('/public-config.json', {cache:'no-store'});
    if (!response.ok || !(await response.json()).publicEvaluation) throw new Error('Use o servidor local ou o endereço autorizado de avaliação.');
    const token = sessionStorage.getItem('radache_token');
    if (sessionStorage.getItem('radache_demo_publica') === '1' && token) {
      const session = await fetch('/api/local/sessao', {headers: {Authorization: 'Bearer ' + token}, cache: 'no-store'});
      if (session.ok) {
        const payload = await session.json();
        if (payload.dados?.demonstracaoPublica) { this.credencial = token; this.user = payload.dados; return; }
      }
      sessionStorage.removeItem('radache_demo_publica');
    }
  }
  observar(callback) { this.callbacks.add(callback); callback(this.user); return () => this.callbacks.delete(callback); }
  avisar() { for (const callback of this.callbacks) callback(this.user); }
  async entrar(email, senha) {
    const response = await fetch('/api/local/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, senha }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.erro?.mensagem || 'Não foi possível entrar.');
    if(payload.dados.usuario.trocaSenhaObrigatoria){location.replace('/assets/change-password.html');return;}
    if(payload.dados.usuario.perfil==='analista_institucional'){location.replace('/institucional/');return;}
    sessionStorage.removeItem('radache_demo_publica');
    this.credencial = payload.dados.token; this.user = payload.dados.usuario;
    sessionStorage.setItem('radache_token', this.credencial); this.avisar();
  }
  async token() { if (!this.credencial) throw new Error('Entre novamente.'); return this.credencial; }
  async claims() { return this.user; }
  async sair() {
    const token = this.credencial; this.credencial = ''; this.user = null; this.avisar();
    sessionStorage.removeItem('radache_token');
    sessionStorage.removeItem('radache_demo_publica');
    if (token) await fetch('/api/local/logout', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token }, body: '{}' });
  }
  async recuperarSenha() { throw new Error('Consulte o responsável pelo cadastro para recuperar o acesso. Não há envio de e-mail nesta versão.'); }
}
export function mensagemAcesso(error) { return error.message || 'Não foi possível preparar o acesso local.'; }

