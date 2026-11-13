import { normalizar } from './ui/chat-view.js';

/** O chat existente apresenta o estado confirmado pelo servidor SQLite. */
export class SimulationController {
  constructor(api, simulator, view) {
    this.view=view;
    this.contatos=[]; this.historicos=new Map(); this.rascunhos=new Map();
    this.states=new Map(); this.busca=''; this.selecionado=Number(new URLSearchParams(location.search).get('aluno'))||null; this.busy=new Set();
    this.pending=new Map(); this.generation=0;
    this.academico=this.selecionado<0 ? -this.selecionado : null;
  }
  async request(path, body) {
    const response=await fetch('/simulation-api'+path, {method:body?'POST':'GET',cache:'no-store',
      headers:body?{'Content-Type':'application/json'}:{}, body:body?JSON.stringify(body):undefined,
      signal:AbortSignal.timeout(12000)});
    const data=await response.json();
    if(response.status===401){const id=new URLSearchParams(location.search).get('aluno');location.replace('/gestao/?retorno=mensagens'+(id&&/^-?[1-9][0-9]*$/.test(id)?'&aluno='+encodeURIComponent(id):''));}
    if(response.status===403&&String(data.erro).includes('Analista Institucional'))location.replace('/institucional/');
    if (!response.ok) throw new Error(data.erro || 'Falha na persistência local.');
    return data.dados;
  }
  async iniciar() {
    this.view.conectar({enviar:texto=>this.enviar(texto), selecionar:id=>this.selecionar(id),
      buscar:busca=>{this.busca=busca;this.listarContatos();}, filtrar:()=>{},
      reenviar:()=>this.retry(),rascunho:texto=>this.rascunhos.set(this.selecionado,texto),simular:acao=>this.simular(acao)});
    document.querySelector('#experience-link').textContent='Gerenciar alunos ↗';
    document.querySelector('#experience-link').href='/alunos/';
    const followup=document.createElement('a');followup.id='followup-link';followup.href='/gestao/#chamados';
    followup.textContent='Acompanhar aluno na gestão →';followup.className='quick-reply';followup.hidden=true;
    document.querySelector('.simulation-actions').append(followup);
    window.addEventListener('focus',()=>this.refresh());
    await this.refresh();
  }
  async refresh() {
    try {
      const alunos=await this.request('/alunos');
      if(this.academico)alunos.push(await this.request(`/academicos/${this.academico}`));
      this.contatos=alunos.filter(a=>a.status==='ativo').map(a=>({...a,naoLidas:0,tom:'green',
        iniciais:a.nome.split(' ').slice(0,2).map(n=>n[0]).join(''),semestre:a.periodo+'º semestre'}));
      if (!this.contatos.some(c=>c.id===this.selecionado)) {
        const requested=new URLSearchParams(location.search).has('aluno');
        this.selecionado=requested ? null : this.contatos[0]?.id ?? null;
        if(requested)this.view.notificar('O aluno solicitado não está disponível para a simulação.');
      }
      this.listarContatos();
      if (this.selecionado) await this.selecionar(this.selecionado,false);
      else {
        this.view.lista.replaceChildren();
        document.querySelector('#chat-name').textContent='Nenhum aluno selecionado';
        document.querySelector('#chat-course').textContent='Selecione um aluno ativo para conversar.';
        document.querySelector('#message-input').disabled=true;
        document.querySelector('#send-button').disabled=true;
        document.querySelector('#simulation-replies').replaceChildren();
        document.querySelector('#simulation-student').textContent='Cadastre ou reative um aluno em Gerenciamento de Alunos.';
      }
    } catch(error) {
      if(new URLSearchParams(location.search).has('aluno')) {
        this.selecionado=null;this.view.lista.replaceChildren();
        document.querySelector('#chat-name').textContent='Aluno indisponível';
        document.querySelector('#chat-course').textContent='Confira o cadastro antes de iniciar a conversa.';
        document.querySelector('#message-input').disabled=true;
        document.querySelector('#send-button').disabled=true;
        document.querySelector('#simulation-replies').replaceChildren();
      }
      this.view.notificar(error.message);
    }
  }
  listarContatos() {
    const term=normalizar(this.busca.trim());
    this.view.renderizarContatos(this.contatos.filter(c=>normalizar(`${c.nome} ${c.matricula} ${c.curso}`).includes(term)),
      this.historicos,this.selecionado,'all',this.contatos.length,0);
  }
  accept(id,data) {
    this.states.set(id,data);
    this.historicos.set(id,data.mensagens.map(m=>({id:m.id,texto:m.conteudo,timestamp:m.timestamp,
      enviada:m.remetente==='aluno',status:'confirmado',payload:null})));
  }
  render(id,open=true) {
    if(id!==this.selecionado || !this.states.has(id)) return;
    this.view.renderizarConversa(this.contatos.find(c=>c.id===id),this.historicos.get(id),this.rascunhos.get(id)||'',open);
    this.view.atualizarSimulacao(this.contatos.find(c=>c.id===id),this.states.get(id).estado,this.busy.has(id));
    document.querySelector('#followup-link').hidden=this.states.get(id).estado.etapa!=='concluido';
    this.listarContatos();
  }
  async selecionar(id,open=true) {
    this.selecionado=id;
    const generation=++this.generation;
    try {
      const data=await this.request(`/alunos/${id}/conversa`);
      this.accept(id,data);
      if(generation===this.generation) this.render(id,open);
    } catch(error) { this.view.notificar(error.message); }
  }
  async operate(id,body) {
    if(!id || this.busy.has(id)) return;
    this.busy.add(id); this.render(id);
    this.pending.set(id,body);
    const record={payload:body,estado:'enviando'}; this.view.atualizarInspecao(record);
    try {
      const data=await this.request(`/alunos/${id}/conversa`,body);
      this.accept(id,data); this.pending.delete(id); this.rascunhos.delete(id);
      if(data.aviso)this.view.notificar(data.aviso);
      this.view.atualizarInspecao({...record,estado:'confirmado',status:200,resposta:{persistido:true,sessao_id:data.sessao_id}});
    } catch(error) {
      this.view.notificar(error.message+' Use Enviar novamente para repetir a mesma operação com segurança.');
      this.view.atualizarInspecao({...record,estado:'falhou',erro:error.message});
    } finally {this.busy.delete(id);this.render(id);}
  }
  enviar(texto,tipo='texto') {
    const id=this.selecionado;
    if(!id || !texto.trim() || this.busy.has(id) || !this.states.has(id)) return;
    const pending=this.pending.get(id);
    if(pending) return this.operate(id,pending);
    this.rascunhos.set(id,texto);
    return this.operate(id,{acao:'responder',texto,tipo,id_cliente:crypto.randomUUID(),sessao_id:this.states.get(id).sessao_id});
  }
  retry() {if(this.pending.has(this.selecionado)) return this.operate(this.selecionado,this.pending.get(this.selecionado));}
  simular(acao) {
    if(acao==='audio') return this.enviar('🎙 Mensagem de áudio simulada · 0:05','audio');
    if(this.pending.has(this.selecionado)) return this.retry();
    return this.operate(this.selecionado,{acao,id_cliente:crypto.randomUUID()});
  }
}
