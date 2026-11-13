const $=id=>document.getElementById(id);
const dialog=$('student-dialog');
let token=sessionStorage.getItem('radache_token')||'',catalog=[],courseCatalog=[],editing=null,page=1,ascending=true,generation=0;
const pageSize=8;
const labels={ativo:'Ativo',inativo:'Inativo',trancado:'Trancado',formado:'Formado'};
const fields={nome:'name',matricula:'registration',curso:'course',campus:'campus',periodo:'period',status:'academic-status',nota_media:'average',frequencia:'attendance',email:'email',telefone:'phone'};
const normalize=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR');
const number=n=>n==null?'—':Number(n).toLocaleString('pt-BR',{maximumFractionDigits:1});
function notify(message,kind='success'){
  clearTimeout(notify.timer);$('feedback').textContent=message;$('feedback').dataset.kind=kind;$('feedback').hidden=false;
  notify.timer=setTimeout(()=>$('feedback').hidden=true,5500);
}
async function api(path,method='GET',body){
  const response=await fetch(path,{method,cache:'no-store',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(12000)});
  const result=await response.json();
  if(response.status===403&&String(result.erro).startsWith('Analista Institucional')){logout();location.replace('/institucional/');}
  if(!response.ok){if(response.status===401)logout();throw new Error(result.erro||'Não foi possível concluir a operação.');}
  return result;
}
function logout(){
  generation++;token='';sessionStorage.removeItem('radache_token');catalog=[];editing=null;
  $('login').hidden=false;$('workspace').hidden=true;$('logout').hidden=true;$('students').replaceChildren();
  if(dialog.open)dialog.close();
}
async function run(action){try{await action();}catch(error){notify(error.message,'error');}}
function showWorkspace(){$('login').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;}
function resetForm(){
  editing=null;$('create-form').reset();$('registration').value='TESTE-'+Date.now();
  $('form-title').textContent='Novo aluno';$('save-student').querySelector('span').textContent=' Cadastrar aluno fictício';
  $('created-at').hidden=true;$('form-error').hidden=true;
}
function openForm(student=null){
  resetForm();
  if(student){
    if(student.campus&&![...$('campus').options].some(o=>o.value===student.campus))$('campus').add(new Option(student.campus,student.campus));
    editing=student.id;for(const [key,id] of Object.entries(fields))$(id).value=student[key]??'';
    $('form-title').textContent='Editar aluno';$('save-student').querySelector('span').textContent=' Salvar alterações';
    $('created-at').textContent='Perfil cadastrado em '+formatDate(student.data_cadastro);$('created-at').hidden=false;
  }
  dialog.showModal();$('name').focus();
}
function formatDate(value){const d=new Date(String(value).replace(' ','T'));return Number.isNaN(d.getTime())?value:d.toLocaleDateString('pt-BR');}
async function list(){
  const current=++generation,[result,courses]=await Promise.all([api('/api/mock-alunos'),api('/api/cursos')]);
  if(current!==generation||!token)return;
  catalog=result.dados;courseCatalog=courses.dados;updateCourses();render();
}
function updateCourses(){
  const current=$('course-filter').value;
  const courses=courseCatalog.map(c=>c.nome);
  $('course-filter').replaceChildren(new Option('Todos os cursos',''),...courses.map(c=>new Option(c,c)));
  $('course-filter').value=courses.includes(current)?current:'';
  $('courses').replaceChildren(...courses.map(c=>new Option(c,c)));
}
function el(tag,className='',text){const node=document.createElement(tag);node.className=className;if(text!==undefined)node.textContent=text;return node;}
function icon(name){const node=el('i',name);node.setAttribute('aria-hidden','true');return node;}
function row(student){
  const tr=document.createElement('tr');tr.dataset.studentId=student.id;
  const personCell=el('td'),person=el('div','person');
  const cleanName=student.nome.replace(/^TESTE\s+/i,'');
  const initials=cleanName.split(/\s+/).filter(Boolean).slice(0,2).map(s=>s[0]).join('').toUpperCase();
  const avatar=el('span','student-avatar tone-'+student.id%5,initials);avatar.setAttribute('aria-hidden','true');
  const identity=el('div');identity.append(el('strong','',student.nome),el('small','',student.matricula));person.append(avatar,identity);personCell.append(person);
  const course=el('td');course.append(el('span','course-name',student.curso),el('small','course-period',student.periodo+'º semestre'),el('small','course-period',student.campus));
  const academicsCell=el('td'),academics=el('div','academics'),numbers=el('div','academic-numbers');
  const average=el('span');average.append('Média ',el('b','',number(student.nota_media)));
  const attendance=el('span','',number(student.frequencia)+(student.frequencia==null?'':'%'));attendance.title='Frequência nas aulas';
  numbers.append(average,attendance);const bar=el('div','frequency-bar'),fill=el('span',student.frequencia!=null&&student.frequencia<75?'low':'');
  fill.style.width=(student.frequencia??0)+'%';bar.append(fill);academics.append(numbers,bar);academicsCell.append(academics);
  const statusCell=el('td');statusCell.append(el('span','status status-'+student.status,labels[student.status]||student.status));
  const actionsCell=el('td'),actions=el('div','row-actions');
  const edit=el('button','edit-button','Editar');edit.type='button';edit.setAttribute('aria-label','Detalhes / editar '+student.nome);edit.onclick=()=>openForm(student);
  const chat=el('a','chat-link');chat.href='/mensagens/?aluno='+student.id;chat.title=student.status==='ativo'?'Simular conversa com '+student.nome:'Reative o aluno antes de iniciar uma conversa';chat.setAttribute('aria-label','WhatsApp simulado de '+student.nome);chat.append(icon('fa-brands fa-whatsapp'));
  if(student.status!=='ativo'){chat.removeAttribute('href');chat.setAttribute('aria-disabled','true');chat.style.opacity='.35';}
  const activate=el('button','icon-button status-button');activate.type='button';
  const inactive=student.status!=='ativo';activate.title=inactive?'Reativar aluno':'Desativar aluno';activate.setAttribute('aria-label',activate.title+' '+student.nome);
  activate.append(icon(inactive?'fa-solid fa-rotate-left':'fa-solid fa-user-slash'));
  activate.onclick=()=>run(async()=>{
    activate.disabled=true;
    try{await api('/api/mock-alunos/'+student.id,inactive?'PUT':'DELETE',inactive?{status:'ativo'}:undefined);await list();notify(inactive?'Aluno reativado. Pronto para uma nova conversa.':'Aluno desativado. Todo o histórico foi preservado.');}
    finally{activate.disabled=false;}
  });
  actions.append(edit,chat,activate);actionsCell.append(actions);tr.append(personCell,course,academicsCell,statusCell,actionsCell);return tr;
}
function render(){
  const query=normalize($('filter').value.trim()),course=$('course-filter').value,status=$('status-filter').value;
  const visible=catalog.filter(a=>(!query||normalize([a.nome,a.matricula,a.curso].join(' ')).includes(query))&&(!course||a.curso===course)&&(!status||a.status===status)).sort((a,b)=>(ascending?1:-1)*a.nome.localeCompare(b.nome,'pt-BR'));
  const pages=Math.max(1,Math.ceil(visible.length/pageSize));page=Math.max(1,Math.min(page,pages));
  const start=(page-1)*pageSize;
  $('students').replaceChildren(...visible.slice(start,start+pageSize).map(row));
  $('empty-state').hidden=visible.length>0;$('empty-message').textContent=catalog.length?'Experimente outro nome, curso ou situação.':'Cadastre seu primeiro aluno ou adicione exemplos para começar.';
  $('count').textContent=visible.length?`Mostrando ${start+1}–${Math.min(start+pageSize,visible.length)} de ${visible.length} aluno${visible.length===1?'':'s'}${visible.length!==catalog.length?' · '+catalog.length+' no total':''}`:'Nenhum aluno para exibir';
  $('page-label').textContent=page+' de '+pages;$('previous-page').disabled=page===1;$('next-page').disabled=page===pages;
  $('clear-filters').hidden=!(query||course||status);
  const active=catalog.filter(a=>a.status==='ativo').length;
  $('stat-total').textContent=catalog.length;$('catalog-badge').textContent=catalog.length;$('stat-active').textContent=active;
  $('stat-courses').textContent=new Set(catalog.map(a=>a.curso)).size;$('stat-other').textContent=catalog.length-active;
}
$('new-student').onclick=()=>openForm();
$('close-dialog').onclick=$('cancel-edit').onclick=()=>dialog.close();
dialog.addEventListener('click',event=>{const rect=dialog.getBoundingClientRect();if(event.target===dialog&&(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom))dialog.close();});
$('login-form').onsubmit=event=>{
  event.preventDefault();const button=event.submitter;button.disabled=true;
  run(async()=>{try{
    const result=await api('/api/login','POST',{usuario:$('username').value,senha:$('password').value});
    if(result.usuario?.role==='analista_institucional'){location.replace('/institucional/');return;}
    token=result.token;sessionStorage.setItem('radache_token',token);$('password').value='';await list();showWorkspace();
  }finally{button.disabled=false;}});
};
$('create-form').onsubmit=async event=>{
  event.preventDefault();$('save-student').disabled=true;$('form-error').hidden=true;
  try{
    const data={};for(const [key,id] of Object.entries(fields)){const value=$(id).value.trim();data[key]=['nota_media','frequencia'].includes(key)?(value===''?null:Number(value)):key==='periodo'?Number(value):value;}
    const wasEditing=editing;
    await api('/api/mock-alunos'+(editing?'/'+editing:''),editing?'PUT':'POST',data);
    await list();dialog.close();notify(wasEditing?'Perfil atualizado com sucesso.':'Aluno cadastrado. Você já pode iniciar uma conversa no simulador.');
  }catch(error){$('form-error').textContent=error.message;$('form-error').hidden=false;$('form-error').scrollIntoView({block:'nearest'});}
  finally{$('save-student').disabled=false;}
};
$('refresh').onclick=()=>run(async()=>{$('refresh').disabled=true;try{await list();notify('Catálogo atualizado.');}finally{$('refresh').disabled=false;}});
for(const id of ['filter','course-filter','status-filter'])$(id).addEventListener(id==='filter'?'input':'change',()=>{page=1;render();});
$('clear-filters').onclick=()=>{$('filter').value='';$('course-filter').value='';$('status-filter').value='';page=1;render();};
$('sort-name').onclick=()=>{ascending=!ascending;$('sort-name').closest('th').setAttribute('aria-sort',ascending?'ascending':'descending');page=1;render();};
$('previous-page').onclick=()=>{page--;render();};$('next-page').onclick=()=>{page++;render();};
$('logout').onclick=()=>run(async()=>{await api('/api/logout','POST',{});logout();});
$('examples').onclick=()=>run(async()=>{
  $('examples').disabled=true;
  try{
    const batch=Date.now();
    for(const [i,course] of ['Ciência da Computação','Pedagogia','Enfermagem'].entries())await api('/api/mock-alunos','POST',{nome:['TESTE Helena Duarte','TESTE Miguel Azevedo','TESTE Lara Nogueira'][i],matricula:'EX-'+batch.toString().slice(-10)+'-'+i,curso:course,periodo:i+2,nota_media:[8.5,7.2,9.1][i],frequencia:[94,83,97][i]});
    await list();notify('Três perfis fictícios adicionados ao catálogo.');
  }finally{$('examples').disabled=false;}
});
window.addEventListener('focus',()=>{if(token&&!dialog.open)run(list);});
if(token)run(async()=>{await list();if(token)showWorkspace();});
