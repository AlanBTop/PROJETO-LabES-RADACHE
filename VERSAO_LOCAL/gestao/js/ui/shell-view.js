import { CONFIG, PERFIS, CAMPI } from '../config.js';
import { $, iniciais, options, ocupar } from './dom.js';

/** Estrutura visual, navegação e mensagens; não conhece fetch ou Firebase SDK. */
export class ShellView {
  conectar(acoes) {
    $('#login-form').addEventListener('submit', event => { event.preventDefault(); acoes.entrar($('#login-email').value, $('#login-password').value); });
    $('#toggle-password').addEventListener('click', () => {
      const mostrar = $('#login-password').type === 'password';
      $('#login-password').type = mostrar ? 'text' : 'password';
      $('#toggle-password').setAttribute('aria-label', mostrar ? 'Ocultar senha' : 'Mostrar senha');
      $('#toggle-password').setAttribute('aria-pressed', String(mostrar));
    });
    $('#reset-password').addEventListener('click', () => acoes.recuperar($('#login-email').value));
    $('#retry-auth').addEventListener('click', acoes.preparar);
    $('#logout-button').addEventListener('click', acoes.sair);
    $('#refresh-button').addEventListener('click', acoes.atualizar);
    $('#retry-page').addEventListener('click', acoes.atualizar);
    $('#course-filter').addEventListener('change', event => acoes.curso(event.target.value));
    window.addEventListener('hashchange', acoes.navegar);
    document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => {
      const dialog = button.closest('dialog');
      if (!dialog.querySelector('form[aria-busy="true"]')) dialog.close();
    }));
    document.querySelectorAll('dialog').forEach(dialog => {
      dialog.addEventListener('cancel', event => { if (dialog.querySelector('form[aria-busy="true"]')) event.preventDefault(); });
      dialog.addEventListener('close', () => acoes.fecharDialog(dialog.id));
    });
    const ambiente = 'Versão local · SQLite';
    $('#login-environment').textContent = ambiente;
    $('#app-environment').textContent = ambiente;
  }

  login(mensagem = '', erro = false) {
    $('#app-shell').hidden = true; $('#login-screen').hidden = false;
    this.mensagemLogin(mensagem, erro); $('#login-password').value = ''; $('#login-password').type = 'password';
    $('#toggle-password').setAttribute('aria-label', 'Mostrar senha'); $('#toggle-password').setAttribute('aria-pressed', 'false');
  }

  mensagemLogin(mensagem, erro = false, sucesso = false) {
    $('#login-message').textContent = mensagem;
    $('#login-message').className = `form-message${erro ? ' error' : sucesso ? ' success' : ''}`;
  }

  pronto(ativo = true) {
    $('#login-submit').disabled = !ativo; $('#reset-password').disabled = !ativo;
    $('#retry-auth').hidden = ativo;
  }

  loginOcupado(ativo) { ocupar($('#login-form'), ativo); }

  limparPrivados() {
    document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    $('#detail-checkins')?.replaceChildren();
    for (const id of ['#ticket-board', '#users-body', '#students-body', '#timeline', '#detail-metadata', '#student-metadata', '#student-assessment', '#detail-badges']) $(id).replaceChildren();
    for (const id of ['#session-name', '#session-profile', '#session-avatar', '#scope-name', '#scope-description', '#detail-description', '#detail-protocol', '#ticket-detail-title', '#student-detail-title', '#users-loaded', '#students-loaded', '#last-updated']) $(id).textContent = '';
    for (const id of ['#metric-average', '#metric-stalled', '#metric-resolved']) $(id).textContent = '—';
    for (const id of ['#course-filter', '#user-course', '#student-course', '#responsible-filter', '#action-responsible']) options($(id), []);
    for (const form of document.querySelectorAll('dialog form')) { ocupar(form, false); form.reset(); }
    $('#toast').hidden = true; this.alerta('');
    $('#campus-scope-filter').value='';
  }

  sessao(usuario, cursos, perm) {
    this.usuario = usuario;
    document.body.classList.toggle('attendance-personal',perm.atendente);
    $('#session-name').textContent = usuario.nome;
    $('#session-profile').textContent = PERFIS[usuario.perfil] || usuario.perfil;
    $('#session-avatar').textContent = iniciais(usuario.nome);
    const curso = cursos.find(item => item.id === usuario.cursoId);
    $('#scope-name').textContent = perm.admin ? 'Todos os câmpus' : usuario.perfil==='diretor_campus'?CAMPI[usuario.campusId]:curso?.nome || 'Cursos atribuídos';
    $('#management-nav').hidden = !perm.usuarios;
    $('#course-filter-label').hidden = !perm.admin && usuario.perfil!=='diretor_campus' && !(usuario.cursoIds?.length>1);
    $('#campus-scope-label').hidden=!perm.admin;
    $('#campus-scope-filter').onchange=()=>$('#refresh-button').click();
    document.querySelector('a[href="/alunos/"]').hidden=!perm.admin;
    document.querySelector('a[href="/painel-demo/"]').hidden=perm.atendente;
    document.querySelector('[data-page="alunos"]').hidden=perm.atendente;
    document.querySelector('[data-page="chamados"] span').textContent=perm.atendente?'Meus Atendimentos':'Atendimentos e Equipe';
    $('#institutional-nav').hidden=!perm.admin;
    options($('#course-filter'), cursos.map(c => ({ id: c.id, nome: c.nome })), 'Todos os cursos');
    $('#scope-description').textContent = perm.admin ? 'Acesso técnico aos três câmpus.' : (CAMPI[usuario.campusId]||'Câmpus autorizado')+' · '+(usuario.perfil==='diretor_campus'?'consulta de todos os cursos do câmpus':'somente cursos atribuídos');
    $('#students-permission').textContent = perm.editarAluno ? 'Consulta e cadastro' : 'Somente consulta';
    $('#users-scope-note').textContent = perm.admin ? 'Gerencie cargos, lotações e vínculos dos três câmpus.' : usuario.perfil==='diretor_campus'?'Consulte a equipe do câmpus e autorize transferências de lotação.':'Gerencie os vínculos dos seus cursos. Contagens de atendimentos limitadas ao seu escopo.';
    $('#login-screen').hidden = true; $('#app-shell').hidden = false;
    this.ocupado(false);
    $('#login-password').value = '';
  }

  pagina(pagina, perm) {
    const titulos = {
      chamados: ['Atendimentos', 'ATENDIMENTO ESTUDANTIL', 'Acompanhamento de chamados', 'Acompanhe os atendimentos e registre as ações da equipe.'],
      usuarios: ['Equipe e acessos', 'ADMINISTRAÇÃO', 'Equipe e acessos', 'Organize as pessoas responsáveis pelo atendimento de cada curso.'],
      alunos: ['Alunos', 'ACOMPANHAMENTO ESTUDANTIL', 'Alunos do curso', 'Consulte o cadastro e os indicadores dos estudantes do seu escopo.'],
    };
    const [breadcrumb, eyebrow, titulo, descricao] = titulos[pagina] || titulos.chamados;
    $('#page-breadcrumb').textContent = breadcrumb; $('#page-eyebrow').textContent = eyebrow;
    $('#page-title').textContent = titulo; $('#page-description').textContent = descricao;
    if(pagina==='chamados'){
      $('#page-title').textContent=perm.atendente?'Meus Atendimentos':'Gestão de Atendimentos e Equipe';
      $('#page-description').textContent=perm.atendente?'Acompanhe seus casos e registre providências e resoluções.':'Distribua casos, acompanhe a equipe e consulte o histórico dos atendimentos.';
    }
    $('#tickets-page').hidden = pagina !== 'chamados' || !perm.equipe;
    $('#users-page').hidden = pagina !== 'usuarios' || !perm.usuarios;
    $('#students-page').hidden = pagina !== 'alunos' || !perm.equipe;
    $('#restricted-page').hidden = perm.equipe;
    $('#create-user-button').hidden = pagina !== 'usuarios' || !perm.gestor;
    $('#create-student-button').hidden = pagina !== 'alunos' || !perm.editarAluno;
    $('#metrics').hidden = !perm.equipe;
    document.querySelectorAll('[data-page]').forEach(link => {
      const ativo = link.dataset.page === pagina;
      link.classList.toggle('active', ativo);
      if (ativo) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    this.alerta('');
    document.title = `${titulo} — RADACHE | UNEMAT`;
  }

  ocupado(ativo) { $('#refresh-button').disabled = ativo; $('#refresh-button').setAttribute('aria-busy', String(ativo)); }
  alerta(mensagem) { $('#app-alert-text').textContent = mensagem || ''; $('#app-alert').hidden = !mensagem; }
  atualizado() { $('#last-updated').textContent = `Atualizado às ${new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`; }
  anunciar(texto) { $('#announcer').textContent = texto; }
  notificar(texto) {
    clearTimeout(this.timer);
    const toast = $('#toast'); ([...document.querySelectorAll('dialog[open]')].at(-1) || document.body).append(toast);
    toast.textContent = texto; toast.hidden = false;
    this.timer = setTimeout(() => { toast.hidden = true; }, 6000);
  }
}
