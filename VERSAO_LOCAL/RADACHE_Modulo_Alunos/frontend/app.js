/** Sandbox sem edição, sem fallback localStorage e sem acesso ao cadastro original. */
const $ = id => document.getElementById(id);
let token = '';
let selected = null;
let epoch = 0;
let catalog = [];
function suggestRegistration() { $('registration').value = 'TESTE-' + Date.now().toString().slice(-9); }
function reset() {
  token = ''; epoch++; selected = null;
  sessionStorage.removeItem('radache_token'); catalog = [];
  $('workspace').hidden = true; $('login').hidden = false;
  $('students').replaceChildren(); $('create-form').reset(); $('password').value = '';
  if ($('delete-dialog').open) $('delete-dialog').close();
}
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, cache: 'no-store', headers: {
    Authorization: 'Bearer ' + token, ...(body ? {'Content-Type': 'application/json'} : {})
  }, body: body ? JSON.stringify(body) : undefined});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401) reset();
    throw new Error(result.erro || 'Não foi possível concluir a operação.');
  }
  return result;
}
async function run(button, action) {
  if (button.disabled) return;
  button.disabled = true; $('feedback').textContent = ''; $('feedback').dataset.kind = '';
  try { await action(); }
  catch (error) { $('feedback').textContent = error.message; $('feedback').dataset.kind = 'error'; }
  finally { button.disabled = false; if ($('feedback').textContent && !$('feedback').dataset.kind) $('feedback').dataset.kind = 'success'; }
}
async function list() {
  const generation = epoch;
  const result = await api('/api/mock-alunos');
  if (generation !== epoch) return;
  catalog = result.dados;
  renderCatalog();
}
function renderCatalog() {
  const query = $('filter').value.trim().toLocaleLowerCase();
  const visible = catalog.filter(student => [student.nome, student.matricula, student.curso].join(' ').toLocaleLowerCase().includes(query));
  $('count').textContent = `${catalog.length} aluno(s) publicado(s) nas duas versões.`;
  $('students').replaceChildren(...visible.map(student => {
    const li = document.createElement('li');
    const content = document.createElement('div');
    const name = document.createElement('strong'); name.textContent = student.nome;
    const description = document.createElement('p'); description.textContent = student.matricula + ' · ' + student.curso + ' · Local + integração C';
    content.append(name, description);
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'danger'; remove.textContent = 'Excluir fictício';
    remove.addEventListener('click', () => { selected = student.id; $('delete-name').textContent = student.nome; $('delete-dialog').showModal(); });
    li.append(content, remove); return li;
  }));
  if (!visible.length) { const li = document.createElement('li'); li.textContent = catalog.length ? 'Nenhum resultado para esta busca.' : 'Nenhum aluno fictício incluído.'; $('students').append(li); }
}
$('login-form').addEventListener('submit', event => {
  event.preventDefault(); run(event.submitter, async () => {
    const result = await api('/api/login', 'POST', {usuario: $('username').value, senha: $('password').value});
    token = result.token; sessionStorage.setItem('radache_token', token); $('password').value = '';
    try { await list(); } catch (error) { reset(); throw error; }
    $('login').hidden = true; $('workspace').hidden = false;
    suggestRegistration(); $('name').focus();
  });
});
$('create-form').addEventListener('submit', event => {
  event.preventDefault(); run(event.submitter, async () => {
    await api('/api/mock-alunos', 'POST', {nome: $('name').value.trim(), matricula: $('registration').value.trim(), curso: $('course').value.trim()});
    const course = $('course').value;
    $('create-form').reset(); $('course').value = course; suggestRegistration();
    await list(); $('name').focus(); $('feedback').textContent = 'Aluno disponível na versão local e na integração C. Nenhum chamado foi criado.';
  });
});
$('refresh').addEventListener('click', event => run(event.currentTarget, list));
$('filter').addEventListener('input', renderCatalog);
$('examples').addEventListener('click', event => run(event.currentTarget, async () => {
  for (const [index, course] of ['Ciência da Computação', 'Pedagogia', 'Ciência da Computação'].entries()) {
    await api('/api/mock-alunos', 'POST', {nome: `TESTE DEMONSTRAÇÃO ${index + 1}`, matricula: `TESTE-${Date.now()}-${index}`, curso: course});
  }
  await list(); $('feedback').textContent = 'Três alunos publicados nas duas versões, sem abrir chamados.';
}));
$('cancel').addEventListener('click', () => $('delete-dialog').close());
$('confirm').addEventListener('click', event => run(event.currentTarget, async () => {
  await api('/api/mock-alunos/' + selected, 'DELETE'); $('delete-dialog').close(); selected = null;
  await list(); $('feedback').textContent = 'Registro fictício excluído.';
}));
$('logout').addEventListener('click', event => run(event.currentTarget, async () => { await api('/api/logout', 'POST', {}); reset(); }));
