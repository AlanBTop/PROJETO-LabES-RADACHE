# Validação da entrega e publicação — 17/11/2026

Origem: `LAB_engenharia_radache/VERSAO_LOCAL`, preservada sem alterações. Preparação em clone separado, baseado em `main` no commit `1292570fcb63e55b0667572d51719980265b2ce8`. Backup remoto separado no mesmo commit. A atualização local foi publicada no GitHub em `753e2141a481556805f5f5b01c72e4397b631632` e validada em clone limpo. A configuração pública foi aprovada, enviada no commit `10993b3e36a66b61cd6fbb74344f5d50e0e53501` e publicada em 17/11/2026.

## Verificação pública no Render Free

- URL: **https://radache02-26labes.onrender.com**. Serviço `srv-dbu7bglckfvc73bap9b0`, blueprint `exs-dbu7bdkipgvc73au7btg`, workspace confirmado pelo titular. Uma instância `free`, sem banco gerenciado ou disco pago, auto-deploy e auto-sync desligados.
- Deploy `dep-dbu7bh5ckfvc73bapaf0` do commit `10993b3e36a66b61cd6fbb74344f5d50e0e53501`, confirmado `live` às **15:43:09 UTC**, com Python **3.13.18** escolhido pelo Render a partir de `.python-version`.
- **41 verificações aprovadas, zero falhas**, concluídas às **15:44:19 UTC**. HTTP 200 nas sete páginas e em 22 arquivos de interface referenciados diretamente por elas. Certificado HTTPS validado pelo cliente, com CSP, X-Content-Type-Options e X-Frame-Options nas respostas de sucesso.
- `/healthz` retornou somente serviço e estado; `/public-config.json` confirmou o modo de avaliação. Quatro APIs privadas e o mock de mensagens recusaram acesso sem sessão. Origem externa recusada com 403; senha pública local recusada com 401; webhook GET/POST indisponível com 404; caminho de acessos iniciais não encontrado.
- Consulta posterior de logs de aplicação filtrados por nível `error` retornou vazia. As senhas iniciais foram geradas pelo Render e não foram lidas, alteradas ou publicadas. Nenhum WhatsApp real foi enviado.
- Relatório e auxiliar em `_validacao_local/render-public.json` e `_validacao_local/verify_render_public.py`, fora do Git. A primeira tentativa foi bloqueada pela rede do sandbox; a execução com permissão de rede passou.

Esta verificação pública usou requisições HTTP, sem executar JavaScript no navegador ou autenticar as contas. Troca de senha, permissões dos quatro perfis, cadastro, check-ins e histórico continuam cobertos pelos testes locais abaixo; esses fluxos ainda não foram repetidos no serviço público. Os testes locais não equivalem a essa validação autenticada pública.

## Preparação para Render Free — resultado mais recente

- **176 testes aprovados, zero falhas, zero erros e zero testes ignorados**, em 426 segundos, incluindo oito testes novos de configuração pública, autenticação, troca obrigatória, perfis, CSRF, arquivos privados e bloqueio do WhatsApp real. A suíte foi executada com Python 3.13.11 em bancos temporários e sem conexões externas.
- `render.yaml` validado contra o schema oficial do Render: um serviço `free`, zero discos pagos, zero bancos gerenciados, deploy automático desligado e nenhuma senha literal no blueprint.
- Edge com Python 3.14.7: sete páginas responderam sob HTTPS de teste e exibiram a indicação de avaliação. O nome de host de teste foi resolvido exclusivamente para 127.0.0.1; foi usado um certificado descartável local, sem acesso ao domínio público pretendido. Isso não valida o certificado ou a publicação no Render.
- Sob HTTPS de teste, administrador, analista, gestor e diretor completaram primeiro login, troca obrigatória e novo acesso. O analista continuou impedido de consultar dados individuais.
- Cadastro fictício, busca em lista paginada, dois check-ins, recarga, avanço de mês, busca no painel e histórico individual com índice final 7,5 passaram. A inicialização repetida com os mesmos bancos preservou a senha alterada.
- Portal, alunos, mensagens e painel em 390 e 1440 px sem transbordamento horizontal. Nenhum erro JavaScript ou requisição externa observado no roteiro. O screenshot móvel do painel foi inspecionado visualmente.
- O roteiro original local foi repetido na porta 8080 e passou: identidade do servidor, sete páginas, cadastro/edição, conversa persistente, segundo mês, painel e login na gestão. Somente os servidores criados para os testes foram encerrados.
- O comando real `python VERSAO_LOCAL/RADACHE_Modulo_Alunos/backend/run_web.py` foi iniciado em processo separado, com porta livre e três bancos temporários. `/healthz` respondeu sem caminhos físicos e a API anônima respondeu HTTP 401. O processo de teste foi encerrado ao concluir.

Os artefatos locais de validação ficam em `_validacao_local/`, fora do commit: `unittest.json`, `public-https.json`, `browser.json` e `render-schema.json`. Os auxiliares de teste não contêm credenciais reais; senhas fictícias transitórias e o certificado de teste não integram a publicação.

O teste HTTPS precisou tratar handshakes em threads para que sockets pré-abertos pelo navegador não bloqueassem o servidor de teste. O backend do Render utiliza HTTP atrás do proxy HTTPS da plataforma, sem esse adaptador TLS local. Também foram adaptadas as esperas e buscas do roteiro para o catálogo inicial com 60 alunos.

O modo público usa credenciais privadas, permite a troca inicial do analista, compartilha a sessão de navegação entre Gestão e as outras áreas, valida hosts públicos explícitos e bloqueia integrações externas. A execução local continua selecionada pelo inicializador anterior. Veja a configuração e as limitações em [DEPLOY_RENDER.md](DEPLOY_RENDER.md).

## Histórico da atualização local publicada

- Suíte completa após os ajustes aprovados: **168 executados e aprovados, zero falhas, zero erros e zero testes ignorados**, em 179 segundos. A dependência do inventário histórico ausente foi removida conforme a aprovação específica, mantendo as 20 combinações de respostas.
- Servidor iniciado com `run_local.py --demo --no-browser --port 8080`, com três bancos temporários. A porta foi verificada antes da inicialização e `/healthz` confirmou a pasta do clone de trabalho e o modo demonstrativo. Somente o processo iniciado para a verificação foi encerrado.
- HTTP 200 nas sete páginas: `/`, `/gestao/`, `/alunos/`, `/painel-demo/`, `/institucional/`, `/mensagens/` e `/assets/change-password.html`.
- Edge headless: cadastro e edição do aluno do guia, consentimento, respostas financeira/emocional, persistência após recarregar, próximo mês, histórico individual com índice final 7,5 e login na gestão aprovados.
- Portal, alunos, mensagens e painel verificados em 390 e 1440 px sem transbordamento horizontal. Nenhum erro JavaScript ou requisição externa observado nesse roteiro. Isso não representa cobertura integral de todas as telas ou perfis.
- Povoamento executado em bancos temporários: 60 novos alunos na primeira execução, zero na repetição e registros anteriores preservados. Backups e evidências gerados ficaram ignorados pelo Git.
- `risk_documentation.content()` coincide com `MODELO_RISCO.md`.
- O cenário existente `verify_attendance_ui.py` passou: gestor, cadastro de atendente, atribuição e acompanhamento de atendimento.
- O cenário `verify_institutional_browser.py` passou após o ajuste aprovado de Origin: login do analista, redirecionamento, gráficos, filtros, proteção de grupos pequenos, bloqueios a dados operacionais, recusa de escrita com HTTP 405 e criação de um perfil adicional. Desktop e telas de 390/320 px sem erros JavaScript ou requisições externas observados.

## Ajustes aprovados nos testes

Foi retirada somente a comparação com um inventário histórico ausente de `test_checkin_claro.py`, preservando a verificação das 20 combinações financeira/emocional e seus componentes de risco. Em `verify_institutional_browser.py`, a chamada POST com cookie passou a informar `Origin` local. A proteção CSRF da aplicação permaneceu ativa. Ambos os ajustes foram aprovados especificamente antes de serem aplicados.

As verificações usaram variáveis `RADACHE_DB`, `RADACHE_MOCK_DB` e `RADACHE_SIM_DB` apontando para arquivos temporários, `RADACHE_DEMO=1` e `RADACHE_USERS={}`. Variáveis herdadas `RADACHE_*` e `WHATSAPP_*` foram removidas antes de estabelecer esse ambiente. A suíte e o povoamento tiveram conexões externas bloqueadas; o roteiro de navegador bloqueou requisições fora do servidor local. Nenhum WhatsApp real foi enviado nem credencial externa usada.

## Reprodução

Para executar a suíte, use uma cópia descartável do repositório. No PowerShell, dentro da raiz dessa cópia:

```powershell
$radacheTeste = Join-Path $env:TEMP ('radache-tests-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $radacheTeste | Out-Null
$env:RADACHE_DEMO = '1'
$env:RADACHE_USERS = '{}'
$env:RADACHE_DB = Join-Path $radacheTeste 'legacy.db'
$env:RADACHE_MOCK_DB = Join-Path $radacheTeste 'academic.db'
$env:RADACHE_SIM_DB = Join-Path $radacheTeste 'operational.db'
$env:RADACHE_WHATSAPP_LEMBRETES = '0'
Set-Location VERSAO_LOCAL/RADACHE_Modulo_Alunos/backend
python -m unittest discover -s tests -v
```

Use um terminal sem credenciais externas configuradas. Os bancos descartáveis permanecem no caminho temporário escolhido; não são necessários nem permitidos no commit. Os testes de navegador existentes em `VERSAO_LOCAL/scripts` dependem de Playwright e do executável Edge indicado nesses scripts; essas dependências são exclusivas da validação, não do uso do protótipo.

## Publicação e limites

Oito e-mails institucionais declarados fictícios nos seeds foram substituídos por endereços `example.com`. Bancos, chaves, acessos iniciais gerados, `.env`, logs, evidências históricas e pastas proibidas não devem integrar o commit. A busca por padrões de segredos e a inspeção dos arquivos de demonstração são verificações parciais; não constituem auditoria completa de segurança nem prova de anonimização de bancos antigos.

A revisão do índice verificou 176 arquivos rastreados e encontrou 15 adições, 39 alterações e 1 remoção. Não identificou caminhos proibidos ou correspondências aos padrões de chaves privadas e tokens pesquisados. A única remoção é `VERSAO_LOCAL/whatsapp_api.py`, o módulo legado aprovado. Os arquivos novos incluem o guia, este relatório, os módulos de credenciais/segurança/privacidade/manutenção e a tela de troca de senha; os demais ajustes atualizam a versão local selecionada, testes e documentação.

A aplicação restringe o modo demonstrativo ao loopback; seu inicializador local define o host local. O inicializador público separado configura Host permitido, HTTPS atrás do proxy, autenticação e proteção das simulações. Os bancos SQLite no Free são descartáveis. Há código de integração real da Meta, bloqueado no modo público e não validado como integração real nesta entrega. O domínio próprio ainda precisa ser confirmado com a professora. A URL pública e os limites das verificações estão registrados no início deste relatório.
