'use strict';
document.getElementById('password-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget, message = document.getElementById('message');
  const current = document.getElementById('current'), next = document.getElementById('next');
  if (next.value !== document.getElementById('confirm').value) { message.textContent = 'As novas senhas precisam ser iguais.'; return; }
  form.querySelector('button').disabled = true;
  try {
    const response = await fetch('/api/local/senha', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({senhaAtual:current.value,novaSenha:next.value})});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.erro?.mensagem || payload.erro || 'Não foi possível alterar a senha.');
    sessionStorage.removeItem('radache_token');
    form.reset(); message.textContent = 'Senha alterada. Entre novamente com a nova senha.';
  } catch (error) { message.textContent = error.message; }
  finally { current.value = ''; form.querySelector('button').disabled = false; }
});
