import { PERFIS, CAMPI } from '../config.js';
import { $, el, metadata, options, data, erroFormulario, ocupar } from './dom.js';

export class FormsView {
  conectar(acoes) {
    $('#user-form').addEventListener('submit', event => { event.preventDefault(); acoes.salvarUsuario(); });
    $('#student-form').addEventListener('submit', event => { event.preventDefault(); acoes.salvarAluno(); });
    $('#confirm-form').addEventListener('submit', event => { event.preventDefault(); acoes.confirmar(); });
  }

  async usuario(usuario, cursos, sessao, perm, cursoSelecionado, staff) {
    const form = $('#user-form'); ocupar(form, false); form.reset();
    const generation=this.userGeneration=(this.userGeneration||0)+1;
    const editando = Boolean(usuario);
    const shared=editando&&!perm.admin&&(usuario.cursoIds||[]).some(c=>!(sessao.cursoIds||[sessao.cursoId]).includes(c));
    form.dataset.linksOnly=String(shared);
    $('#user-dialog-title').textContent = editando ? 'Alterar acesso' : 'Novo acesso';
    $('#user-dialog-note').textContent = editando ? `A lotação permanece em ${CAMPI[usuario.campusId]||'escopo geral'}. Use a transferência específica para mudar o câmpus. ${shared?'Os vínculos de outros gestores serão preservados.':''}` : 'Defina o login e a senha inicial. Antes de criar uma conta, localize funcionários já existentes na lista.';
    $('#user-identity-fields').hidden = false;
    for (const input of $('#user-identity-fields').querySelectorAll('input')) { input.disabled = editando && (input.name==='email'||shared); input.required = !input.disabled; if(usuario)input.value=usuario[input.name]||''; }
    const login=$('#user-identity-fields input[name="email"]');login.type='text';login.pattern='[\\w.@+\\-]+';login.previousElementSibling.textContent='Login';
    if(!$('#user-initial-password')){const label=el('label','field');label.id='user-password-field';const input=el('input');input.id='user-initial-password';input.name='senhaInicial';input.type='password';input.autocomplete='new-password';input.minLength=8;input.maxLength=128;label.append(el('span','','Senha inicial'),input);$('#user-identity-fields').after(label);}
    $('#user-password-field').hidden=editando;$('#user-initial-password').disabled=editando;$('#user-initial-password').required=!editando;$('#user-initial-password').value='';
    const perfis = perm.admin ? ['admin_tecnico','analista_institucional','diretor_campus','gestor_curso','atendente_academico'] : ['atendente_academico'];
    options($('#user-profile'), perfis.map(id => ({ id, nome: PERFIS[id] })), null, usuario?.perfil || 'atendente_academico');
    $('#user-profile').disabled = !perm.admin;
    $('#user-profile').previousElementSibling.textContent='Cargo';$('#user-campus').previousElementSibling.textContent='Câmpus de lotação';
    options($('#user-course'), []);
    options($('#user-campus'),Object.entries(CAMPI).filter(([id])=>perm.admin||id===sessao.campusId).map(([id,nome])=>({id,nome})),null,usuario?.campusId||sessao.campusId||'caceres');
    const assigned=usuario?.cursoIds||[!perm.admin?sessao.cursoId:cursoSelecionado];
    let loading=0;
    const load=async()=>{const version=++loading;let ready=false;$('#user-save').disabled=true;try{const items=await staff.app.api.todos('cursos',{campusId:$('#user-campus').value});if(generation!==this.userGeneration||version!==loading)return false;options($('#user-course'),items,null);for(const option of $('#user-course').options)option.selected=assigned.includes(option.value);erroFormulario('#user-form-error','');ready=true;}catch(error){if(generation===this.userGeneration)erroFormulario('#user-form-error',error.message);}finally{if(generation===this.userGeneration&&version===loading)$('#user-save').disabled=!ready;}return ready;};
    const update=()=>{const p=$('#user-profile').value,course=['gestor_curso','atendente_academico'].includes(p),scoped=course||p==='diretor_campus';$('#user-campus-field').hidden=!scoped;$('#user-campus').disabled=!scoped||(editando&&usuario.perfil==='atendente_academico');$('#user-campus').required=scoped;$('#user-course-field').hidden=!course;$('#user-course').disabled=!course;$('#user-course').required=course&&!editando;};
    $('#user-profile').onchange=()=>{update();void load();};$('#user-campus').onchange=load;update();
    $('#user-save').textContent = editando ? 'Salvar alteração' : 'Criar acesso local';
    erroFormulario('#user-form-error', '');
    if (!$('#user-dialog').open) $('#user-dialog').showModal();
    $('#user-redistribution')?.remove();const redistribution=el('section');redistribution.id='user-redistribution';$('#user-course-field').after(redistribution);
    if(!await load()||generation!==this.userGeneration)return;
    if(editando&&usuario.perfil==='atendente_academico'){
      $('#user-save').disabled=true;
      let ready=false;try{await staff.assignments(usuario,redistribution);ready=true;}catch(error){if(generation===this.userGeneration)erroFormulario('#user-form-error',error.message);}finally{if(generation===this.userGeneration)$('#user-save').disabled=!ready;}
    }
  }

  confirmar(titulo, mensagem, rotulo, perigo = false) {
    ocupar($('#confirm-form'), false);
    $('#confirm-title').textContent = titulo; $('#confirm-message').textContent = mensagem;
    $('#confirm-submit').textContent = rotulo;
    $('#confirm-submit').className = perigo ? 'button button-danger' : 'button button-primary';
    erroFormulario('#confirm-error', '');
    if (!$('#confirm-dialog').open) $('#confirm-dialog').showModal();
  }

  editarAluno(aluno, cursos, sessao, perm, cursoSelecionado) {
    const form = $('#student-form'); ocupar(form, false); form.reset();
    $('#student-edit-title').textContent = aluno ? 'Editar aluno' : 'Novo aluno';
    options($('#student-course'), cursos.map(c => ({ id: c.id, nome: c.nome, disabled: !c.ativo })), 'Selecione o curso', aluno?.cursoId || (!perm.admin ? sessao.cursoId : cursoSelecionado));
    $('#student-course').disabled = Boolean(aluno) || !perm.admin;
    if (aluno) for (const nome of ['nome', 'matricula', 'campus', 'periodo', 'email', 'telefone', 'status']) form.elements.namedItem(nome).value = aluno[nome] ?? '';
    erroFormulario('#student-form-error', '');
    if (!$('#student-edit-dialog').open) $('#student-edit-dialog').showModal();
  }

  abrirFicha() {
    $('#student-detail-title').textContent = 'Carregando aluno...';
    $('#student-metadata').replaceChildren(); $('#student-assessment').replaceChildren();
    $('#student-detail-content').hidden = true;
    this.estadoFicha('Carregando os dados do aluno.');
    if (!$('#student-dialog').open) $('#student-dialog').showModal();
  }

  estadoFicha(mensagem, erro = false) {
    const node = $('#student-detail-state'); node.textContent = mensagem || ''; node.hidden = !mensagem;
    node.className = erro ? 'alert alert-error' : 'alert';
    if (erro) { $('#student-detail-title').textContent = 'Aluno indisponível'; $('#student-detail-content').hidden = true; }
  }

  ficha(aluno, cursos) {
    const estado = { ativo: 'Ativo', inativo: 'Inativo', formado: 'Formado', trancado: 'Trancado' };
    const situacoes = { estavel: 'Estável', moderada: 'Moderada', critica: 'Crítica', moderado: 'Moderado', critico: 'Crítico' };
    $('#student-detail-title').textContent = aluno.nome;
    metadata($('#student-metadata'), [['Matrícula', aluno.matricula], ['Curso', cursos.get(aluno.cursoId) || 'Curso vinculado'], ['Campus', aluno.campus], ['Período', `${aluno.periodo}º período`], ['E-mail', aluno.email], ['Telefone', aluno.telefone || 'Não informado'], ['Situação', estado[aluno.status] || aluno.status], ['Cadastrado em', data(aluno.criadoEm)]]);
    const a = aluno.avaliacaoAtual || {};
    metadata($('#student-assessment'), [['Nota média', a.nota_media], ['Frequência', a.frequencia == null ? null : `${a.frequencia}%`], ['Situação financeira', situacoes[a.situacao_financeira] || a.situacao_financeira], ['Situação psicológica', situacoes[a.situacao_psicologica] || a.situacao_psicologica], ['Índice de risco', a.indice_risco == null ? null : `${a.indice_risco}%`], ['Classificação de risco', situacoes[a.classificacao_risco] || a.classificacao_risco], ['Avaliado em', a.data_avaliacao ? data(a.data_avaliacao) : null]]);
    this.estadoFicha(''); $('#student-detail-content').hidden = false;
  }
}
