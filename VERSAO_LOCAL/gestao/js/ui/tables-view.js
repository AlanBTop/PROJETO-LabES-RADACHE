import { PERFIS, CAMPI } from '../config.js';
import { $, el, button, vazio, iniciais, data, options } from './dom.js';

export class TablesView {
  conectar(acoes) {
    $('#create-user-button').addEventListener('click', acoes.novoUsuario);
    $('#create-student-button').addEventListener('click', acoes.novoAluno);
    $('#more-users').addEventListener('click', acoes.maisUsuarios);
    $('#more-students').addEventListener('click', acoes.maisAlunos);
    $('#user-role-filter').addEventListener('change', acoes.filtrarUsuarios);
    for (const id of ['#users-body', '#students-body']) $(id).addEventListener('click', event => {
      const target = event.target.closest('button[data-action]');
      if (target) acoes.acaoLinha(target.dataset.action, target.dataset.id);
    });
  }

  perfis(perm) {
    const header=$('#users-body').closest('table').querySelector('thead tr');header.replaceChildren(...['Pessoa / login','Cargo','Câmpus','Cursos vinculados','Ativos','Resolvidos','Situação','Último acesso','Ações'].map(title=>el('th','',title)));
    const roles = perm.admin ? ['admin_tecnico','analista_institucional','diretor_campus','gestor_curso','atendente_academico'] : ['atendente_academico'];
    options($('#user-role-filter'), roles.map(id => ({ id, nome: PERFIS[id] })), 'Todos os perfis gerenciáveis');
  }

  estado(tipo, estado) {
    const prefix = tipo === 'usuarios' ? 'users' : 'students';
    const node = $(`#${prefix}-state`);
    node.replaceChildren();
    if (estado.loading && !estado.itens.length) node.append(vazio('Carregando registros...', 'Aguarde a consulta dos dados autorizados.', 'refresh'));
    else if (estado.erro) node.append(vazio('Não foi possível carregar', estado.erro, 'warning'));
    else if (!estado.itens.length) node.append(vazio(tipo === 'usuarios' ? 'Nenhum acesso encontrado' : 'Nenhum aluno encontrado', tipo === 'usuarios' ? 'Os acessos deste escopo aparecerão aqui.' : 'Os alunos vinculados ao curso aparecerão aqui.', tipo === 'usuarios' ? 'users' : 'student'));
    $(`#${prefix}-loaded`).textContent = `${estado.itens.length} registro${estado.itens.length === 1 ? '' : 's'} carregado${estado.itens.length === 1 ? '' : 's'}`;
    $(`#more-${prefix}`).hidden = !estado.cursor;
    $(`#more-${prefix}`).disabled = estado.loading;
  }

  usuarios(estado, cursos, perm, sessao) {
    const linhas = estado.itens.map(usuario => {
      const row = el('tr'); const pessoa = el('td'); const group = el('div', 'person-cell');
      const nomes = el('div'); nomes.append(el('strong', '', usuario.nome), el('span', 'person-email', usuario.email));
      group.append(el('span', 'avatar', iniciais(usuario.nome)), nomes); pessoa.append(group);
      const situacao = el('td'); situacao.append(el('span', `badge ${usuario.ativo ? 'badge-active' : 'badge-inactive'}`, usuario.ativo ? 'Ativo' : 'Inativo'));
      const actions = el('td'); const buttons = el('div', 'table-actions');
      if (perm.gestor) buttons.append(button('Alterar acesso', undefined, 'editar-usuario', usuario.id));
      if(perm.gestor&&(perm.admin||(usuario.cursoIds||[]).every(c=>(sessao.cursoIds||[sessao.cursoId]).includes(c))))buttons.append(button(usuario.ativo ? 'Desativar' : 'Reativar', usuario.ativo ? 'button button-secondary button-small' : 'button button-primary button-small', 'estado-usuario', usuario.id));
      if(usuario.perfil==='atendente_academico'){
        buttons.append(button('Histórico',undefined,'historico-funcionario',usuario.id));
        if(perm.transferir)buttons.append(button('Transferir de câmpus',undefined,'transferir-funcionario',usuario.id));
      }
      if (usuario.id === sessao.uid) buttons.querySelectorAll('button').forEach(node => { node.disabled = true; });
      actions.append(buttons);
      row.append(pessoa, el('td', '', PERFIS[usuario.perfil] || usuario.perfil),el('td','',CAMPI[usuario.campusId]||'Todos os câmpus'), el('td', '', (usuario.cursoIds||[usuario.cursoId]).filter(Boolean).map(c=>cursos.get(c)||c).join(', ')||'Sem vínculos'),el('td','',usuario.perfil==='atendente_academico'?usuario.atendimentosAtivos??0:'—'),el('td','',usuario.perfil==='atendente_academico'?usuario.atendimentosResolvidos??0:'—'), situacao, el('td', '', usuario.ultimoAcessoEm ? data(usuario.ultimoAcessoEm) : 'Ainda não acessou'), actions);
      return row;
    });
    $('#users-body').replaceChildren(...linhas); this.estado('usuarios', estado);
  }

  alunos(estado, cursos, perm) {
    const nomesStatus = { ativo: 'Ativo', inativo: 'Inativo', formado: 'Formado', trancado: 'Trancado' };
    $('#students-body').replaceChildren(...estado.itens.map(aluno => {
      const row = el('tr'); const actions = el('td'); const buttons = el('div', 'table-actions');
      buttons.append(button('Ver ficha', undefined, 'ver-aluno', aluno.id));
      actions.append(buttons); const pessoa = el('td'); pessoa.append(el('strong', '', aluno.nome));
      const status = el('td'); status.append(el('span', `badge ${aluno.status === 'ativo' ? 'badge-active' : 'badge-inactive'}`, nomesStatus[aluno.status] || aluno.status));
      row.append(pessoa, el('td', '', aluno.matricula), el('td', '', cursos.get(aluno.cursoId) || 'Curso vinculado'), el('td', '', `${aluno.periodo}º período`), status, actions);
      return row;
    }));
    this.estado('alunos', estado);
  }
}
