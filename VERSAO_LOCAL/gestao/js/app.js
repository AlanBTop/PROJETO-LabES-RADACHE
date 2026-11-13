import { CONFIG, STATUS, permissoes } from './config.js';
import { AuthService, mensagemAcesso } from './services/auth-service.js';
import { ApiService } from './services/api-service.js';
import { ShellView } from './ui/shell-view.js';
import { TablesView } from './ui/tables-view.js';
import { TicketsView } from './ui/tickets-view.js';
import { FormsView } from './ui/forms-view.js';
import { StaffView } from './ui/staff-view.js';
import { $, erroFormulario, ocupar, options } from './ui/dom.js';

const listaVazia = () => ({ itens: [], cursor: null, total: null, loading: false, erro: '' });
const colunasVazias = () => Object.fromEntries(Object.keys(STATUS).map(status => [status, listaVazia()]));
const segmento = valor => encodeURIComponent(valor);
const cancelado = error => error.name === 'AbortError';

/** Estado e coordenação. Dados privados nunca são gravados em armazenamento local. */
class Aplicacao {
  constructor() {
    this.shell = new ShellView(); this.tables = new TablesView(); this.tickets = new TicketsView(); this.forms = new FormsView();
    this.auth = new AuthService(CONFIG);
    this.staff = new StaffView(this);
    this.api = new ApiService(this.auth, CONFIG, () => this.sair('Sua sessão mudou ou expirou. Entre novamente.'));
    this.epoch = 0; this.pageEpoch = 0; this.detailEpoch = 0; this.studentEpoch = 0;
    this.perfil = null; this.cursos = []; this.curso = ''; this.pagina = 'chamados';
    this.usuarios = listaVazia(); this.alunos = listaVazia(); this.colunas = colunasVazias(); this.responsaveis = [];
    this.detalhe = null; this.eventos = []; this.historicoCursor = null;
    this.pendencias = new Map(); this.ocupados = new Set(); this.mensagemSaida = '';
  }

  async iniciar() {
    this.staff.setup();
    this.shell.conectar({ entrar: (e, s) => this.entrar(e, s), recuperar: e => this.recuperar(e), preparar: () => this.preparar(), sair: () => this.sair('Seu acesso foi encerrado.'), atualizar: () => this.carregarPagina(), curso: id => this.mudarCurso(id), navegar: () => this.navegar(), fecharDialog: id => this.fecharDialog(id) });
    this.tables.conectar({ novoUsuario: () => this.abrirUsuario(), novoAluno: () => this.editarAluno(), maisUsuarios: () => this.carregarLista('usuarios', true), maisAlunos: () => this.carregarLista('alunos', true), filtrarUsuarios: () => this.carregarLista('usuarios'), acaoLinha: (acao, id) => this.acaoLinha(acao, id) });
    this.tickets.conectar({ filtrar: () => this.carregarQuadro(), abrir: id => { location.hash = `chamados/${segmento(id)}`; }, mais: status => this.carregarColuna(status, true), recarregar: status => this.carregarColuna(status), registrar: () => this.registrarAcao(), assumir: () => this.registrarAcao(true), maisHistorico: () => this.carregarHistorico(true), copiarProtocolo: () => this.copiarProtocolo() });
    this.forms.conectar({ salvarUsuario: () => this.salvarUsuario(), salvarAluno: () => this.salvarAluno(), confirmar: () => this.confirmar() });
    this.heartbeat = setInterval(() => { if (!document.hidden) this.revalidar(); }, CONFIG.revalidacaoMs);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) { this.revalidar(); void this.atualizarAutomaticamente(); } });
    window.addEventListener('focus', () => { void this.atualizarAutomaticamente(); });
    this.followupTimer = setInterval(() => { void this.atualizarAutomaticamente(); }, 5000);
    await this.preparar();
  }

  async preparar() {
    if (this.preparando) return;
    this.preparando = true; this.shell.pronto(false); $('#retry-auth').hidden = true;
    this.shell.mensagemLogin('Preparando acesso seguro...');
    try {
      await this.auth.preparar(); this.shell.pronto(); this.shell.mensagemLogin('');
      if (!this.observador) this.observador = this.auth.observar(user => { void this.sessaoAlterada(user); });
    } catch (error) { this.shell.mensagemLogin(mensagemAcesso(error), true); this.shell.pronto(false); }
    finally { this.preparando = false; }
  }

  async entrar(email, senha) {
    if (this.autenticando) return;
    this.autenticando = true; this.shell.loginOcupado(true); this.shell.mensagemLogin('Verificando sua conta...'); this.mensagemSaida = '';
    try { await this.auth.entrar(email, senha); }
    catch (error) { this.shell.mensagemLogin(mensagemAcesso(error), true); this.autenticando = false; this.shell.loginOcupado(false); }
    finally { $('#login-password').value = ''; }
  }

  async recuperar(email) {
    if (this.autenticando) return;
    if (!email.trim() || !$('#login-email').reportValidity()) { this.shell.mensagemLogin('Informe seu e-mail para receber as instruções.', true); return; }
    this.autenticando = true; this.shell.loginOcupado(true);
    try { await this.auth.recuperarSenha(email); this.shell.mensagemLogin('Se houver uma conta para este e-mail, você receberá as instruções para redefinir a senha.', false, true); }
    catch (error) { this.shell.mensagemLogin(mensagemAcesso(error), true); }
    finally { this.autenticando = false; this.shell.loginOcupado(false); $('#login-password').value = ''; }
  }

  invalidar() {
    this.staff.clear();
    this.epoch++; this.pageEpoch++; this.detailEpoch++; this.studentEpoch++;
    this.api.cancelarTudo(); this.pageAbort?.abort(); this.detailAbort?.abort(); this.studentAbort?.abort();
    this.perfil = null; this.cursos = []; this.responsaveis = []; this.curso = '';
    this.usuarios = listaVazia(); this.alunos = listaVazia(); this.colunas = colunasVazias();
    this.detalhe = null; this.eventos = []; this.historicoCursor = null; this.confirmacao = null;
    this.usuarioEditando = null; this.alunoEditando = null; this.pendencias.clear(); this.ocupados.clear();
    this.tickets.reiniciar(); this.shell.limparPrivados();
  }

  async sessaoAlterada(user) {
    // Renovar o ID token da mesma pessoa não deve fechar um formulário em uso.
    // A nova sessão ainda é conferida no servidor; uma mudança real limpa os dados.
    if (user && this.perfil?.uid === user.uid) {
      const atual = this.epoch;
      try {
        const claims = await this.auth.claims();
        if (atual !== this.epoch) return;
        if (claims.perfil === this.perfil.perfil && claims.cursoId === this.perfil.cursoId && claims.versaoAcesso === this.perfil.versaoAcesso) {
          await this.api.requisitar('sessao'); return;
        }
      } catch (error) {
        if (!cancelado(error) && atual === this.epoch && error.status !== 401) this.shell.alerta('Não foi possível atualizar a sessão. Tente atualizar os dados.');
        return;
      }
    }
    this.invalidar(); const epoch = this.epoch;
    if (!user) { this.shell.login(this.mensagemSaida); this.autenticando = false; this.shell.loginOcupado(false); return; }
    this.shell.login('Validando seu acesso ao curso...');
    try {
      const perfil = await this.api.requisitar('sessao');
      const claims = await this.auth.claims();
      if (epoch !== this.epoch) return;
      if (perfil.uid !== user.uid || claims.perfil !== perfil.perfil || claims.cursoId !== perfil.cursoId || claims.versaoAcesso !== perfil.versaoAcesso) throw new Error('Sua permissão mudou. Entre novamente para continuar.');
      const perm = permissoes(perfil.perfil);
      const cursos = perm.equipe ? await this.api.todos('cursos') : [];
      if (epoch !== this.epoch) return;
      this.perfil = perfil; this.perm = perm; this.cursos = cursos; this.curso = perm.admin || perfil.perfil==='diretor_campus' || perfil.cursoIds?.length>1 ? '' : perfil.cursoId;
      const returnParams=new URLSearchParams(location.search);
      if(returnParams.get('retorno')==='mensagens'){const id=returnParams.get('aluno');location.replace('/mensagens/'+(id&&/^-?[1-9][0-9]*$/.test(id)?'?aluno='+encodeURIComponent(id):''));return;}
      this.shell.sessao(perfil, cursos, perm); this.tables.perfis(perm);
      this.staff.session();
      if (this.ultimoAcessoUid !== perfil.uid) {
        this.ultimoAcessoUid = perfil.uid;
        void this.api.requisitar('sessao/acesso', { method: 'POST', body: {} }).catch(error => { if (!cancelado(error) && epoch === this.epoch && error.status !== 401) this.shell.alerta('Não foi possível registrar o último acesso. Você pode continuar utilizando o sistema.'); });
      }
      await this.navegar(true);
    } catch (error) {
      if (cancelado(error) || epoch !== this.epoch) return;
      await this.sair(error.message || 'Não foi possível carregar seu acesso.');
    } finally {
      if (epoch === this.epoch) { this.autenticando = false; this.shell.loginOcupado(false); }
    }
  }

  async sair(mensagem) {
    this.mensagemSaida = mensagem; this.ultimoAcessoUid = null; this.invalidar(); this.shell.login(mensagem);
    this.autenticando = false; this.shell.loginOcupado(false);
    try { await this.auth.sair(); } catch { this.shell.login(mensagem); }
  }

  async revalidar() {
    if (!this.perfil || this.revalidando) return;
    this.revalidando = true; const epoch = this.epoch;
    try { await this.api.requisitar('sessao'); }
    catch (error) { if (!cancelado(error) && epoch === this.epoch && error.status !== 401) this.shell.alerta('Não foi possível atualizar a sessão. Tente atualizar os dados.'); }
    finally { this.revalidando = false; }
  }

  get cursosMap() { return new Map(this.cursos.map(c => [c.id, c.nome])); }
  filtrosCurso() { return { ...(this.curso ? { cursoId: this.curso } : {}),...($('#campus-scope-filter').value?{campusId:$('#campus-scope-filter').value}:{}) }; }

  async navegar(forcar = false) {
    if (!this.perfil) return;
    let [pagina, codificado] = location.hash.replace(/^#/, '').split('/');
    if (!['chamados', 'usuarios', 'alunos'].includes(pagina)) pagina = 'chamados';
    if (pagina === 'usuarios' && !this.perm.usuarios) { history.replaceState(null, '', '#chamados'); pagina = 'chamados'; this.shell.notificar('Seu perfil não permite gerenciar acessos.'); }
    const mudou = pagina !== this.pagina || forcar;
    if (mudou) { this.fecharTodos(); this.pagina = pagina; this.shell.pagina(pagina, this.perm); await this.carregarPagina(); }
    else this.shell.pagina(pagina, this.perm);
    if (!this.perm.equipe) return;
    if (codificado) {
      let id;
      try { id = decodeURIComponent(codificado); } catch { id = 'invalido'; }
      if (pagina === 'chamados' && this.detalhe?.item.id !== id) await this.abrirChamado(id);
      if (pagina === 'alunos') await this.abrirFicha(id);
    } else if ($('#ticket-dialog').open || $('#student-dialog').open) this.fecharTodos();
  }

  fecharTodos() { document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()); }

  fecharDialog(id) {
    if (id === 'ticket-dialog') { this.detailEpoch++; this.detailAbort?.abort(); this.detalhe = null; this.eventos = []; this.historicoCursor = null; }
    if (id === 'student-dialog') { this.studentEpoch++; this.studentAbort?.abort(); }
    if (id === 'confirm-dialog') this.confirmacao = null;
    if (id === 'user-dialog') this.usuarioEditando = null;
    if (id === 'student-edit-dialog') this.alunoEditando = null;
    if (['ticket-dialog', 'student-dialog'].includes(id) && location.hash.includes('/')) history.replaceState(null, '', `#${this.pagina}`);
  }

  async mudarCurso(id) {
    if (!this.perfil || !this.perm.equipe) return;
    this.curso = id; this.fecharTodos(); this.responsaveis = [];
    this.tickets.responsaveis([]); await this.carregarPagina();
  }

  async carregarPagina() {
    if (!this.perfil || !this.perm.equipe) return;
    if (this.pagina === 'chamados') return this.carregarQuadro();
    return this.carregarLista(this.pagina);
  }

  async atualizarAutomaticamente() {
    if(this.perfil&&this.detalhe&&$('#ticket-dialog').open&&!this.ocupados.size&&!this.checkingCase){
      this.checkingCase=true;
      try{await this.api.requisitar(`atendimentos/${segmento(this.detalhe.item.id)}`);}
      catch(error){if([403,404].includes(error.status)){$('#ticket-dialog').close();this.shell.notificar('Este caso deixou de estar disponível para seu acesso.');void this.carregarQuadro();}}
      finally{this.checkingCase=false;}
      return;
    }
    if (!this.perfil || !this.perm.equipe || this.pagina !== 'chamados' || document.hidden || this.autoRefreshing ||
        document.querySelector('dialog[open]') || Object.values(this.colunas).some(c => c.loading) || this.ocupados.size) return;
    this.autoRefreshing=true;
    const epoch=this.epoch;
    try {
      const cursos=await this.api.todos('cursos');
      if(epoch!==this.epoch)return;
      this.cursos=cursos;
      options($('#course-filter'),cursos.map(c=>({id:c.id,nome:c.nome})),'Todos os cursos',this.curso);
      await this.carregarQuadro(true);
    } catch(error) {
      if(!cancelado(error)&&epoch===this.epoch&&error.status!==401)this.shell.alerta('Não foi possível atualizar os chamados. Use Atualizar para tentar novamente.');
    } finally {this.autoRefreshing=false;}
  }

  async carregarQuadro(silencioso = false) {
    if (!this.perfil || !this.perm.equipe) return;
    this.pageAbort?.abort(); this.pageAbort = new AbortController();
    const signal = this.pageAbort.signal, generation = ++this.pageEpoch, epoch = this.epoch;
    const valido = () => epoch === this.epoch && generation === this.pageEpoch;
    this.shell.alerta('');
    if (!silencioso) {
      this.shell.ocupado(true); this.colunas = colunasVazias();
      for (const estado of Object.values(this.colunas)) estado.loading = true;
      this.tickets.quadro(this.colunas, this.cursosMap); this.tickets.indicadores(null);
    }
    const query = { ...this.filtrosCurso(), ...this.tickets.filtros(), categoria: $('#category-filter').value, responsavelUid: $('#responsible-filter').value, limite: 20 };
    const tarefas = Object.keys(STATUS).map(status => this.api.requisitar('atendimentos', { query: { ...query, status, limite: silencioso ? Math.min(100, Math.max(20, this.colunas[status].itens.length)) : 20 }, signal }));
    tarefas.push(this.api.todos('responsaveis', this.filtrosCurso(), signal));
    tarefas.push(this.api.requisitar('indicadores', { query: this.filtrosCurso(), signal }));
    const resultados = await Promise.allSettled(tarefas);
    if (!valido()) return;
    Object.keys(STATUS).forEach((status, index) => {
      const resultado = resultados[index]; const estado = this.colunas[status]; estado.loading = false;
      if (resultado.status === 'fulfilled') { estado.itens = resultado.value.itens; estado.cursor = resultado.value.proximaPagina; estado.total = resultado.value.total; }
      else if (!cancelado(resultado.reason)) estado.erro = resultado.reason.message;
    });
    const directory=resultados[Object.keys(STATUS).length], metrics=resultados[Object.keys(STATUS).length+1];
    if (directory.status === 'fulfilled') { this.responsaveis = directory.value; this.tickets.responsaveis(this.responsaveis, query.responsavelUid); }
    else if (!cancelado(directory.reason)) this.shell.alerta('Não foi possível atualizar a lista de responsáveis.');
    if (metrics.status === 'fulfilled') this.tickets.indicadores(metrics.value);
    else if (!cancelado(metrics.reason)) this.shell.alerta('Não foi possível carregar os indicadores. Tente atualizar.');
    this.tickets.quadro(this.colunas, this.cursosMap); this.shell.ocupado(false); this.shell.atualizado();
  }

  async carregarColuna(status, mais = false) {
    if (!this.perfil || !this.colunas[status] || this.colunas[status].loading) return;
    const epoch = this.epoch, generation = this.pageEpoch;
    const estado = this.colunas[status]; if (!mais) Object.assign(estado, listaVazia());
    estado.loading = true; estado.erro = ''; this.tickets.quadro(this.colunas, this.cursosMap);
    try {
      const dados = await this.api.requisitar('atendimentos', { query: { ...this.filtrosCurso(), ...this.tickets.filtros(), status, categoria: $('#category-filter').value, responsavelUid: $('#responsible-filter').value, limite: 20, depois: mais ? estado.cursor : undefined }, signal: this.pageAbort?.signal });
      if (epoch !== this.epoch || generation !== this.pageEpoch) return;
      estado.itens = mais ? [...estado.itens, ...dados.itens] : dados.itens; estado.cursor = dados.proximaPagina; estado.total = dados.total;
    } catch (error) { if (!cancelado(error) && epoch === this.epoch && generation === this.pageEpoch) estado.erro = error.message; }
    finally { if (epoch === this.epoch && generation === this.pageEpoch) { estado.loading = false; this.tickets.quadro(this.colunas, this.cursosMap); } }
  }

  async carregarLista(tipo, mais = false) {
    if (!this.perfil || !this.perm.equipe || (tipo === 'usuarios' && !this.perm.usuarios)) return;
    if (mais && this[tipo].loading) return;
    if(tipo==='usuarios'&&!mais){$('#staff-results').replaceChildren();void this.staff.transfers();}
    if (!mais) { this.pageAbort?.abort(); this.pageAbort = new AbortController(); this.pageEpoch++; this[tipo] = listaVazia(); }
    const epoch = this.epoch, generation = this.pageEpoch, estado = this[tipo];
    estado.loading = true; estado.erro = ''; this.shell.ocupado(true); this.shell.alerta(''); this.renderLista(tipo);
    try {
      const dados = await this.api.requisitar(tipo, { query: { ...this.filtrosCurso(), ...(tipo === 'usuarios' ? { perfil: $('#user-role-filter').value } : {}), limite: 30, depois: mais ? estado.cursor : undefined }, signal: this.pageAbort?.signal });
      if (epoch !== this.epoch || generation !== this.pageEpoch) return;
      estado.itens = mais ? [...estado.itens, ...dados.itens] : dados.itens; estado.cursor = dados.proximaPagina; this.shell.atualizado();
    } catch (error) { if (!cancelado(error) && epoch === this.epoch && generation === this.pageEpoch) estado.erro = error.message; }
    finally { if (epoch === this.epoch && generation === this.pageEpoch) { estado.loading = false; this.renderLista(tipo); this.shell.ocupado(false); } }
  }

  renderLista(tipo) {
    if (tipo === 'usuarios') this.tables.usuarios(this.usuarios, this.cursosMap, this.perm, this.perfil);
    else this.tables.alunos(this.alunos, this.cursosMap, this.perm);
  }

  acaoLinha(acao, id) {
    if (!this.perfil) return;
    if (acao === 'ver-aluno') { location.hash = `alunos/${segmento(id)}`; return; }
    if (acao === 'editar-aluno') { const aluno = this.alunos.itens.find(a => a.id === id); if (aluno) this.editarAluno(aluno); return; }
    const usuario = this.usuarios.itens.find(u => u.id === id);
    if(usuario&&acao==='historico-funcionario'){void this.staff.history(usuario);return;}
    if(usuario&&acao==='transferir-funcionario'&&this.perm.transferir){void this.staff.transfer(usuario);return;}
    if (!usuario || !this.perm.gestor) return;
    if (acao === 'editar-usuario' && this.perm.gestor) { this.abrirUsuario(usuario); return; }
    if (acao === 'estado-usuario') {
      const ativo = !usuario.ativo;
      this.confirmacao = { tipo: 'estado', usuario, ativo };
      this.forms.confirmar(`${ativo ? 'Reativar' : 'Desativar'} acesso?`, ativo ? `O acesso de ${usuario.nome} será reativado. A pessoa precisará entrar novamente.` : `${usuario.nome} perderá o acesso e as sessões atuais serão encerradas. Os históricos de atendimento serão preservados.`, ativo ? 'Reativar acesso' : 'Desativar acesso', !ativo);
    } else if (acao === 'convite-usuario') {
      this.confirmacao = { tipo: 'convite', usuario };
      this.forms.confirmar('Consultar acesso local?', `A conta ${usuario.email} usa a senha de demonstração admin123. Não há envio de e-mail nesta versão.`, 'Conferir acesso');
    }
  }

  async abrirUsuario(usuario = null) {
    if (!this.perfil || !this.perm.gestor) return;
    const epoch=this.epoch;
    try{
      if(usuario)usuario=await this.api.requisitar(`usuarios/${segmento(usuario.id)}`);
      if(epoch!==this.epoch)return;
      this.usuarioEditando = usuario; await this.forms.usuario(usuario, this.cursos, this.perfil, this.perm, this.curso, this.staff);
    }catch(error){if(epoch===this.epoch)this.shell.alerta(error.message);}
  }

  async salvarUsuario() {
    if (!this.perfil || !this.perm.gestor || this.ocupados.has('user')) return;
    const form = $('#user-form'); if (!form.reportValidity()) return;
    const epoch = this.epoch, editando = this.usuarioEditando;
    const values = Object.fromEntries(new FormData(form));
    const body = editando ? { nome:values.nome?.trim()||editando.nome, perfil: this.perm.admin ? values.perfil : 'atendente_academico', cursoId: values.cursoId } : {
      nome: values.nome.trim(), email: values.email.trim(),
      perfil: this.perm.admin ? values.perfil : 'atendente_academico',
      cursoId: this.perm.admin ? values.cursoId : this.perfil.cursoId,
    };
    if(editando&&form.dataset.linksOnly==='true')delete body.nome;
    if(!editando){body.login=values.email.trim();body.senhaInicial=values.senhaInicial;}
    body.campusId=values.campusId||editando?.campusId||'';body.cursoIds=new FormData(form).getAll('cursoIds');body.cursoId=body.cursoIds[0]||'';
    if(editando)body.redistribuicoes=this.staff.mapping($('#user-redistribution'));
    this.ocupados.add('user'); ocupar(form, true); erroFormulario('#user-form-error', '');
    let resultado;
    try {
      resultado = await this.api.requisitar(editando ? `usuarios/${segmento(editando.id)}` : 'usuarios', { method: editando ? 'PATCH' : 'POST', body });
      if (epoch !== this.epoch) return;
      $('#user-dialog').close();
      this.shell.notificar(editando ? 'Vínculos atualizados. As sessões anteriores dessa pessoa foram encerradas.' : 'Acesso criado com o login e a senha inicial informados.');
    } catch (error) {
      if (!cancelado(error) && epoch === this.epoch) erroFormulario('#user-form-error', error.message + (error.incerto ? ' Consulte a lista de acessos antes de reenviar o cadastro.' : ''));
    } finally { $('#user-initial-password').value='';if (epoch === this.epoch) { this.ocupados.delete('user'); ocupar(form, false); } }
    if (resultado && epoch === this.epoch && this.pagina === 'usuarios') await this.carregarLista('usuarios');
  }

  async confirmar() {
    if (!this.perfil || !this.perm.gestor || !this.confirmacao || this.ocupados.has('confirm')) return;
    const epoch = this.epoch, confirmacao = this.confirmacao, form = $('#confirm-form');
    this.ocupados.add('confirm'); ocupar(form, true); erroFormulario('#confirm-error', '');
    let resultado;
    try {
      resultado = await this.api.requisitar(`usuarios/${segmento(confirmacao.usuario.id)}${confirmacao.tipo === 'convite' ? '/convite' : ''}`, { method: confirmacao.tipo === 'convite' ? 'POST' : 'PATCH', body: confirmacao.tipo === 'convite' ? {} : { ativo: confirmacao.ativo } });
      if (epoch !== this.epoch) return;
      $('#confirm-dialog').close();
      this.shell.notificar(confirmacao.tipo === 'convite' ? resultado.convite === 'pendente' ? 'O envio está pendente. Tente reenviar mais tarde.' : resultado.convite === 'capturado' ? 'Convite registrado no ambiente local.' : 'Acesso local conferido. Senha de demonstração: admin123.' : confirmacao.ativo ? 'Acesso reativado. A pessoa deve entrar novamente.' : 'Acesso desativado.');
    } catch (error) { if (!cancelado(error) && epoch === this.epoch) erroFormulario('#confirm-error', error.message); }
    finally { if (epoch === this.epoch) { this.ocupados.delete('confirm'); ocupar(form, false); } }
    if (resultado && epoch === this.epoch && this.pagina === 'usuarios') await this.carregarLista('usuarios');
  }

  editarAluno(aluno = null) {
    if (!this.perfil || !this.perm.editarAluno) return;
    this.alunoEditando = aluno; this.forms.editarAluno(aluno, this.cursos, this.perfil, this.perm, this.curso);
  }

  async salvarAluno() {
    if (!this.perfil || !this.perm.editarAluno || this.ocupados.has('student')) return;
    const form = $('#student-form'); if (!form.reportValidity()) return;
    const epoch = this.epoch, editando = this.alunoEditando;
    const values = Object.fromEntries(new FormData(form));
    const body = { nome: values.nome.trim(), matricula: values.matricula.trim(), campus: values.campus.trim(), periodo: Number(values.periodo), email: values.email.trim(), telefone: values.telefone.trim(), status: values.status };
    if (!editando) body.cursoId = this.perm.admin ? values.cursoId : this.perfil.cursoId;
    this.ocupados.add('student'); ocupar(form, true); erroFormulario('#student-form-error', '');
    let resultado;
    try {
      resultado = await this.api.requisitar(editando ? `alunos/${segmento(editando.id)}` : 'alunos', { method: editando ? 'PATCH' : 'POST', body });
      if (epoch !== this.epoch) return;
      $('#student-edit-dialog').close(); this.shell.notificar(editando ? 'Cadastro do aluno atualizado.' : 'Aluno cadastrado.');
    } catch (error) { if (!cancelado(error) && epoch === this.epoch) erroFormulario('#student-form-error', error.message); }
    finally { if (epoch === this.epoch) { this.ocupados.delete('student'); ocupar(form, false); } }
    if (resultado && epoch === this.epoch && this.pagina === 'alunos') await this.carregarLista('alunos');
  }

  async abrirFicha(id) {
    if (!this.perfil || !this.perm.equipe) return;
    this.studentAbort?.abort(); this.studentAbort = new AbortController();
    const epoch = this.epoch, generation = ++this.studentEpoch;
    this.forms.abrirFicha();
    try {
      const aluno = await this.api.requisitar(`alunos/${segmento(id)}`, { signal: this.studentAbort.signal });
      if (epoch === this.epoch && generation === this.studentEpoch) this.forms.ficha(aluno, this.cursosMap);
    } catch (error) { if (!cancelado(error) && epoch === this.epoch && generation === this.studentEpoch) this.forms.estadoFicha(error.message, true); }
  }

  async abrirChamado(id) {
    if (!this.perfil || !this.perm.equipe) return;
    this.detailAbort?.abort(); this.detailAbort = new AbortController();
    const signal = this.detailAbort.signal, epoch = this.epoch, generation = ++this.detailEpoch;
    this.detalhe = null; this.eventos = []; this.historicoCursor = null;
    ocupar($('#ticket-action-form'), false); this.tickets.abrirDetalhe();
    try {
      const item = await this.api.requisitar(`atendimentos/${segmento(id)}`, { signal });
      if (epoch !== this.epoch || generation !== this.detailEpoch) return;
      const resultados = await Promise.allSettled([
        this.api.requisitar(`alunos/${segmento(item.alunoId)}`, { signal }),
        this.api.todos('responsaveis', { cursoId: item.cursoId }, signal),
        this.api.requisitar(`atendimentos/${segmento(id)}/historico`, { query: { limite: 50 }, signal }),
      ]);
      if (epoch !== this.epoch || generation !== this.detailEpoch) return;
      if (resultados[2].status !== 'fulfilled') throw resultados[2].reason;
      const aluno = resultados[0].status === 'fulfilled' ? resultados[0].value : null;
      const responsaveis = resultados[1].status === 'fulfilled' ? resultados[1].value : [];
      this.detalhe = { item, aluno, responsaveis };
      this.eventos = resultados[2].value.itens; this.historicoCursor = resultados[2].value.proximaPagina;
      this.tickets.detalhe(item, aluno, this.cursosMap, responsaveis, this.perfil);
      this.tickets.historico(this.eventos, this.historicoCursor);
      if (resultados[1].status !== 'fulfilled') this.shell.notificar('Não foi possível carregar o diretório de responsáveis. Você ainda pode assumir o atendimento.');
    } catch (error) {
      if (!cancelado(error) && epoch === this.epoch && generation === this.detailEpoch) this.tickets.estadoDetalhe(error.status === 404 ? 'Não encontrado.' : `${error.message} Feche e abra o atendimento para tentar novamente.`, true);
    }
  }

  async carregarHistorico(mais = false) {
    if (!this.detalhe || this.ocupados.has('history')) return;
    const epoch = this.epoch, generation = this.detailEpoch, id = this.detalhe.item.id;
    if (!mais) { this.eventos = []; this.historicoCursor = null; }
    this.ocupados.add('history'); this.tickets.historico(this.eventos, this.historicoCursor, true);
    try {
      const dados = await this.api.requisitar(`atendimentos/${segmento(id)}/historico`, { query: { limite: 50, depois: mais ? this.historicoCursor : undefined }, signal: this.detailAbort?.signal });
      if (epoch !== this.epoch || generation !== this.detailEpoch) return;
      this.eventos = mais ? [...this.eventos, ...dados.itens] : dados.itens; this.historicoCursor = dados.proximaPagina;
    } catch (error) {
      if (!cancelado(error) && epoch === this.epoch && generation === this.detailEpoch) {
        if (mais) this.shell.notificar(error.message); else this.tickets.estadoDetalhe('Não foi possível atualizar o histórico. Feche e abra o chamado para consultar os registros.', true);
      }
    } finally {
      if (epoch === this.epoch) this.ocupados.delete('history');
      if (epoch === this.epoch && generation === this.detailEpoch) this.tickets.historico(this.eventos, this.historicoCursor);
    }
  }

  async registrarAcao(assumir = false) {
    if (!this.perfil || !this.perm.equipe || !this.detalhe || this.ocupados.has('ticket')) return;
    const form = $('#ticket-action-form'); if (!assumir && !form.reportValidity()) return;
    const epoch = this.epoch, generation = this.detailEpoch, id = this.detalhe.item.id;
    const tipo = assumir ? 'responsavel' : $('#ticket-action-type').value;
    let body;
    if (tipo === 'responsavel') body = { uid: $('#action-responsible').value || null, texto: $('#action-text').value.trim() };
    else if (tipo === 'status') body = { status: $('#action-status').value, texto: $('#action-text').value.trim() };
    else if (tipo === 'classificacao') body = { categoria: $('#action-category').value, prioridade:$('#action-priority').value, texto: $('#action-text').value.trim() };
    else body = { texto: $('#action-text').value.trim(), visivelAoAluno: $('#action-visible').checked };
    const chave = JSON.stringify({ uid: this.perfil.uid, id, tipo, body });
    const idAcao = this.pendencias.get(chave) || crypto.randomUUID(); this.pendencias.set(chave, idAcao);
    const caminho = tipo === 'comentario' ? 'comentarios' : tipo;
    this.ocupados.add('ticket'); ocupar(form, true); $('#assume-ticket').disabled = true; erroFormulario('#ticket-action-error', '');
    let resultado;
    try {
      resultado = await this.api.requisitar(`atendimentos/${segmento(id)}/${caminho}`, { method: 'POST', body: { ...body, idAcao }, signal: this.detailAbort?.signal });
      if (epoch !== this.epoch || generation !== this.detailEpoch) return;
      this.pendencias.delete(chave); this.detalhe.item = resultado;
      $('#action-text').value = ''; $('#action-visible').checked = false;
      this.tickets.detalhe(resultado, this.detalhe.aluno, this.cursosMap, this.detalhe.responsaveis, this.perfil);
      this.shell.notificar(assumir ? 'Você assumiu o atendimento.' : 'Registro salvo no histórico.');
      await this.carregarHistorico();
    } catch (error) {
      if (!cancelado(error) && epoch === this.epoch && generation === this.detailEpoch) erroFormulario('#ticket-action-error', error.message + (error.incerto ? ' Uma nova tentativa com o mesmo texto manterá o identificador do registro.' : ''));
    } finally {
      if (epoch === this.epoch) this.ocupados.delete('ticket');
      if (epoch === this.epoch && generation === this.detailEpoch) { ocupar(form, false); $('#assume-ticket').disabled = false; }
    }
    if (resultado && epoch === this.epoch && this.pagina === 'chamados') void this.carregarQuadro();
  }

  async copiarProtocolo() {
    if (!this.detalhe) return;
    try { await navigator.clipboard.writeText(this.detalhe.item.protocolo); this.shell.notificar('Protocolo copiado.'); }
    catch { this.shell.notificar('A área de transferência está indisponível. Selecione o protocolo para copiá-lo.'); }
  }
}

try {
  const app = new Aplicacao();
  app.iniciar().catch(error => { $('#login-message').textContent = mensagemAcesso(error); $('#login-message').classList.add('error'); });
} catch (error) {
  $('#login-message').textContent = 'Não foi possível carregar a configuração do acesso.';
  $('#login-message').classList.add('error');
}
