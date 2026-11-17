// A configuração informa somente o modo; não contém senhas, tokens ou dados pessoais.
(async () => {
  try {
    const response = await fetch('/public-config.json', {cache: 'no-store'});
    if (!response.ok || !(await response.json()).publicEvaluation) return;
    document.title = `RADACHE02/26LabES · ${document.title}`;
    document.querySelectorAll('.demo-credentials, .login-support, #panel-login + small, #login-form > small')
      .forEach(element => { element.hidden = true; });
    document.querySelectorAll('.local-badge').forEach(element => { element.textContent = 'Avaliação online'; });
    const notice = document.createElement('aside');
    notice.className = 'evaluation-notice';
    notice.setAttribute('aria-label', 'Ambiente de avaliação');
    const explanation = document.createElement('span');
    explanation.textContent = 'Avaliação pública · Use apenas dados fictícios. Os dados são compartilhados e podem ser reiniciados.';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'evaluation-demo-button';
    button.textContent = 'Entrar na demonstração';
    const feedback = document.createElement('span');
    feedback.className = 'evaluation-demo-feedback';
    feedback.setAttribute('role', 'status');
    button.addEventListener('click', async () => {
      button.disabled = true;
      feedback.textContent = ' Preparando demonstração...';
      try {
        const result = await fetch('/api/demo/login', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
        });
        const data = await result.json();
        if (!result.ok || !data.dados?.token) throw new Error('Não foi possível abrir a demonstração. Tente novamente.');
        sessionStorage.setItem('radache_token', data.dados.token);
        sessionStorage.setItem('radache_demo_publica', '1');
        if (location.pathname === '/' || location.pathname === '/index.html' ||
            location.pathname.startsWith('/assets/change-password')) location.assign('/gestao/');
        else location.reload();
      } catch (error) {
        feedback.textContent = ' ' + (error.message || 'Não foi possível abrir a demonstração.');
        button.disabled = false;
      }
    });
    notice.append(explanation, button, feedback);
    document.body.prepend(notice);
    const teamDescription = document.querySelector('a.card[href="/gestao/#usuarios"] p');
    if (teamDescription) teamDescription.textContent = 'Consulte os perfis e vínculos da equipe. Alterações de acesso são reservadas à administração.';
    const localText = document.querySelector('.login-illustration > small');
    if (localText) localText.textContent = 'Somente dados inventados. Esta avaliação usa dados compartilhados e descartáveis.';
  } catch {
    // Falha na indicação visual não concede acesso nem altera as regras do servidor.
  }
})();

