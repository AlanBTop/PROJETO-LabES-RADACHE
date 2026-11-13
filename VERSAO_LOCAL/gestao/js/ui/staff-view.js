import { $, el, button, options, data } from './dom.js';
import { CAMPI } from '../config.js';

export class StaffView {
  constructor(app){this.app=app;this.searchVersion=0;}
  setup(){
    const panel=el('section','table-card staff-panel');panel.id='staff-lookup';
    panel.append(el('h3','','Localizar funcionário existente'),el('p','muted','Pesquise no câmpus antes de criar uma conta. Selecione o funcionário para vincular seus cursos.'));
    const controls=el('div','filters'),campus=el('select');campus.id='staff-campus';campus.setAttribute('aria-label','Câmpus da busca');
    const search=el('input');search.id='staff-search';search.type='search';search.placeholder='Nome ou login';search.setAttribute('aria-label','Buscar funcionário');
    const find=button('Localizar');find.id='staff-find';controls.append(campus,search,find);
    const results=el('div');results.id='staff-results';results.setAttribute('role','status');panel.append(controls,results);$('#users-page').prepend(panel);
    find.onclick=()=>this.find();search.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();void this.find();}};
    campus.onchange=()=>{results.replaceChildren();};
    const pending=el('section','table-card staff-panel');pending.id='staff-transfers';$('#users-page').append(pending);
    this.historyDialog=this.dialog('staff-history','Histórico do funcionário');
    this.transferDialog=this.dialog('staff-transfer','Transferência de Funcionários entre Câmpus');
  }
  dialog(id,title){
    const dialog=el('dialog','modal modal-wide');dialog.id=id;
    const header=el('header','dialog-heading'),heading=el('h2','',title),close=button('Fechar');
    close.onclick=()=>dialog.close();header.append(heading,close);const content=el('div');content.dataset.content='';dialog.append(header,content);document.body.append(dialog);return dialog;
  }
  session(){
    const actor=this.app.perfil;
    options($('#staff-campus'),Object.entries(CAMPI).filter(([id])=>this.app.perm.admin||id===actor.campusId).map(([id,nome])=>({id,nome})),null,actor.campusId||'caceres');
    $('#staff-lookup').hidden=!this.app.perm.gestor;
    $('#staff-results').replaceChildren();$('#staff-search').value='';void this.transfers();
  }
  clear(){
    this.searchVersion++;$('#staff-results').replaceChildren();$('#staff-transfers').replaceChildren();$('#staff-search').value='';
    for(const d of [this.historyDialog,this.transferDialog]){d.close();d.querySelector('[data-content]').replaceChildren();}
  }
  async find(){
    const version=++this.searchVersion,epoch=this.app.epoch;$('#staff-results').textContent='Buscando…';
    try{
      const items=await this.app.api.todos('funcionarios',{campusId:$('#staff-campus').value,busca:$('#staff-search').value.trim()});
      if(epoch!==this.app.epoch||version!==this.searchVersion)return;
      $('#staff-results').replaceChildren();
      for(const user of items){const row=el('p');const open=button('Vincular / editar cursos');open.onclick=()=>this.app.abrirUsuario(user);row.append(el('span','',`${user.nome} · ${user.login} · ${user.ativo?'Ativo':'Inativo'} · ${(user.cursoIds||[]).map(c=>this.app.cursosMap.get(c)||c).join(', ')||'Sem cursos'} `),open);$('#staff-results').append(row);}
      if(!items.length)$('#staff-results').textContent='Nenhum funcionário encontrado neste câmpus. Você pode cadastrar um novo acesso.';
    }catch(error){if(epoch===this.app.epoch)$('#staff-results').textContent=error.message;}
  }
  async assignments(user,container){
    container.replaceChildren();const epoch=this.app.epoch;
    const result=await this.app.api.requisitar(`usuarios/${encodeURIComponent(user.id)}/ativos`);
    if(epoch!==this.app.epoch)return;
    container.append(el('p','muted','Se remover cursos ou desativar o funcionário, escolha substitutos para os casos afetados. Outros casos permanecem com o responsável atual.'));
    for(const ticket of result.itens){
      const members=await this.app.api.todos('responsaveis',{campusId:user.campusId,cursoId:ticket.cursoId});
      if(epoch!==this.app.epoch)return;
      const label=el('label','field');label.append(el('span','',`${ticket.protocolo} · ${this.app.cursosMap.get(ticket.cursoId)||ticket.cursoId}`));
      const select=el('select');select.dataset.reassignCase=ticket.id;
      options(select,members.filter(u=>u.id!==user.id).map(u=>({id:u.id,nome:u.nome})),'Manter responsável atual');label.append(select);container.append(label);
    }
    if(!result.itens.length)container.append(el('p','muted','Não há atendimentos ativos para redistribuir.'));
  }
  mapping(container){return Object.fromEntries([...container.querySelectorAll('[data-reassign-case]')].filter(s=>s.value).map(s=>[s.dataset.reassignCase,s.value]));}
  async history(user){
    const dialog=this.historyDialog,content=dialog.querySelector('[data-content]'),epoch=this.app.epoch;content.textContent='Carregando histórico…';dialog.showModal();
    try{
      const value=await this.app.api.requisitar(`usuarios/${encodeURIComponent(user.id)}/historico`);
      if(epoch!==this.app.epoch)return;
      content.replaceChildren(el('h3','',user.nome));
      content.append(el('h4','','Vínculos com cursos'));
      for(const row of value.vinculos)content.append(el('p','',`${CAMPI[row.campus_id]} · ${this.app.cursosMap.get(row.curso_id)||row.curso_id} · ${data(row.inicio)} até ${row.fim?data(row.fim):'atual'} · Autor: ${row.autor_id}`));
      content.append(el('h4','','Transferências de lotação'));
      for(const row of value.transferencias)content.append(el('p','',`${CAMPI[row.origem]} → ${CAMPI[row.destino]} · ${row.status} · ${data(row.criadoEm)} · ${row.motivo} · Autorizações: ${Object.values(row.autorizacoes||{}).map(a=>a.uid+' em '+data(a.data)).join('; ')}`));
      if(!value.transferencias.length)content.append(el('p','','Nenhuma transferência registrada.'));
    }catch(error){if(epoch===this.app.epoch)content.textContent=error.message;}
  }
  async transfer(user){
    const dialog=this.transferDialog,content=dialog.querySelector('[data-content]'),epoch=this.app.epoch;
    const form=el('form'),destination=el('select'),courses=el('select'),reason=el('textarea'),cases=el('section'),error=el('p','form-message error'),save=button('Confirmar transferência');save.type='submit';
    destination.id='staff-destination';courses.id='staff-destination-courses';reason.id='staff-transfer-reason';courses.multiple=true;courses.size=5;reason.required=true;reason.maxLength=3000;destination.required=true;
    options(destination,Object.entries(CAMPI).filter(([id])=>id!==user.campusId).map(([id,nome])=>({id,nome})),null,Object.keys(CAMPI).find(id=>id!==user.campusId));
    for(const [title,input] of [['Câmpus de destino',destination],['Cursos no destino (opcional)',courses],['Justificativa',reason]]){const label=el('label','field');label.append(el('span','',title),input);form.append(label);}
    form.prepend(el('p','',`${user.nome} · Origem: ${CAMPI[user.campusId]}. Redistribua todos os casos ativos. Diretores solicitam e a direção de destino confirma; o Administrador Técnico pode concluir pelos dois câmpus.`));
    form.append(cases,error,save);content.replaceChildren(form);dialog.showModal();
    let generation=0;
    const load=async()=>{const current=++generation;save.disabled=true;try{const items=await this.app.api.todos('cursos',{campusId:destination.value});if(epoch!==this.app.epoch||current!==generation)return;options(courses,items,null);error.textContent='';}catch(e){error.textContent=e.message;}finally{if(current===generation)save.disabled=false;}};
    destination.onchange=load;await load();
    try{save.disabled=true;await this.assignments(user,cases);}catch(e){error.textContent=e.message;}finally{save.disabled=false;}
    form.onsubmit=async event=>{
      event.preventDefault();if(save.disabled||!form.reportValidity())return;save.disabled=true;error.textContent='';
      try{const result=await this.app.api.requisitar('transferencias',{method:'POST',body:{usuarioId:user.id,destino:destination.value,cursoIds:[...courses.selectedOptions].map(o=>o.value),motivo:reason.value.trim(),redistribuicoes:this.mapping(cases)}});
        if(epoch!==this.app.epoch)return;dialog.close();this.app.shell.notificar(result.status==='concluida'?'Transferência concluída. Sessões antigas invalidadas.':'Solicitação registrada. Aguarda confirmação da direção de destino.');await this.app.carregarLista('usuarios');await this.transfers();
      }catch(e){if(epoch===this.app.epoch)error.textContent=e.message;}finally{save.disabled=false;}
    };
  }
  async transfers(){
    const actor=this.app.perfil,target=$('#staff-transfers'),epoch=this.app.epoch;
    target.replaceChildren();target.hidden=!this.app.perm.transferir;
    if(!this.app.perm.transferir)return;
    try{const result=await this.app.api.requisitar('transferencias');if(epoch!==this.app.epoch)return;
      target.append(el('h3','','Transferências de funcionários entre câmpus'));
      for(const record of result.itens){const row=el('p');row.append(el('span','',`${record.nome} · ${CAMPI[record.origem]} → ${CAMPI[record.destino]} · ${record.status} · ${record.motivo} `));
        if(record.status==='pendente'&&(this.app.perm.admin||actor.campusId===record.destino)){const confirm=button('Confirmar recebimento');confirm.onclick=async()=>{confirm.disabled=true;try{await this.app.api.requisitar(`transferencias/${record.id}/confirmar`,{method:'POST',body:{}});this.app.shell.notificar('Transferência concluída.');await this.transfers();await this.app.carregarLista('usuarios');}catch(e){this.app.shell.alerta(e.message);confirm.disabled=false;}};row.append(confirm);}target.append(row);}
      if(!result.itens.length)target.append(el('p','muted','Nenhuma transferência registrada.'));
    }catch(e){if(epoch===this.app.epoch)target.textContent=e.message;}
  }
}
