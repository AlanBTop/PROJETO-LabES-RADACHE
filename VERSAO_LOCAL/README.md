# RADACHE local

Execute INICIAR_LOCAL.bat e abra http://localhost:8080/.
Só é necessário Python 3. Nenhum pip install, Node, Java ou emulador é necessário.

- Portal: / — reúne todas as páginas.
- Gestão: /gestao/#chamados, /gestao/#usuarios e /gestao/#alunos.
  Acessos fictícios somente no modo demonstrativo: [guia de avaliação](../GUIA_AVALIACAO.md).
  Diretores e gestores têm escopo por câmpus e cursos atribuídos. Consulte os perfis no [guia de avaliação](../GUIA_AVALIACAO.md).
- Módulo de alunos fictícios: /alunos/.
- Observatório: /institucional/. Somente estatísticas agregadas protegidas dos três câmpus.
- Painel analítico: /painel-demo/ — visão geral da universidade, comparação de cursos,
  visão por curso e histórico individual. Use a conta de administração para acesso técnico;
  diretores e gestores recebem somente os dados do seu escopo.
- Mensagens: /mensagens/ — simulação e teste manual da API mock.

SQLite: RADACHE_Modulo_Alunos/database/radache_provisorio.db.
Gestão por curso e módulo original consultam os mesmos alunos.
Usuários, chamados e histórico locais persistem nas tabelas gestao_*.
Novos acessos usam a senha inicial definida no cadastro; não há envio de convite por e-mail.
Os quatro chamados iniciais são identificados como exemplos locais.
O painel analítico compartilha a sessão do módulo original na mesma aba e permite login próprio.
O login da gestão por curso dura enquanto a página estiver aberta; recarregar pede nova entrada.

Os fontes da gestão são uma cópia independente adaptada para SQLite; nenhuma importação aponta para VERSAO_FIREBASE.
Todos os estilos, fontes e ícones são locais.

Terminal de demonstração: python RADACHE_Modulo_Alunos/backend/run_local.py --demo --no-browser
Credenciais próprias: INICIAR_LOCAL.bat --secure --port 8082 (usa três bancos separados da demonstração).
As senhas iniciais aleatórias ficam em `<banco>.acessos-iniciais.json`, fora das pastas servidas.
O primeiro login encaminha para a troca obrigatória de senha. Esse modo continua sendo um protótipo local.
Opções: --demo, --secure, --port 8080, --page /gestao/, --no-browser.
Variáveis: RADACHE_DB para outro SQLite e RADACHE_PORT para outra porta.

O protótipo isolado de mensagens continua disponível por python scripts/iniciar_mensagens.py (porta 8081).
Documentação e relatórios anteriores são históricos.

Revisão de 13/11: [correções e operação](APRIMORAMENTOS_20261113.md), [modelo e cenários](MODELO_RISCO.md).
Resultados e reprodução dos testes: [validação da entrega](../VALIDACAO_ENTREGA.md).
O modo de demonstração aceita somente acesso no próprio computador.

Dashboard, cursos e histórico de risco: consulte o [guia de avaliação](../GUIA_AVALIACAO.md) para o roteiro e [MODELO_RISCO.md](MODELO_RISCO.md) para as fórmulas e limitações.

Mapa de pastas: [ESTRUTURA.md](ESTRUTURA.md). Roteiro atual: [guia de avaliação](../GUIA_AVALIACAO.md).

As evidências históricas da auditoria de 11/11/2026 permanecem na instalação original e não integram a publicação.
Os scripts `scripts/audit_project.py`, `scripts/audit_runtime.py` e
`scripts/audit_browser_flows.py` reproduzem as verificações em bancos temporários.
