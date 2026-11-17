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
    notice.textContent = 'RADACHE02/26LabES · Avaliação acadêmica. Use apenas dados fictícios. Os dados são compartilhados e podem ser reiniciados. No primeiro acesso, entre pela Gestão e altere a senha fornecida pelo responsável.';
    document.body.prepend(notice);
    const localText = document.querySelector('.login-illustration > small');
    if (localText) localText.textContent = 'Somente dados inventados. Esta avaliação usa dados compartilhados e descartáveis.';
  } catch {
    // Falha na indicação visual não concede acesso nem altera as regras do servidor.
  }
})();
