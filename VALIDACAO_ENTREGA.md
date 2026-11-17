# Validação da preparação local — 17/11/2026

Origem: `LAB_engenharia_radache/VERSAO_LOCAL`, preservada sem alterações. Preparação em clone separado, baseado em `main` no commit `1292570fcb63e55b0667572d51719980265b2ce8`. Backup remoto separado no mesmo commit. Push e deploy ainda não realizados.

## Resultado atual

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

A aplicação atual restringe o modo demonstrativo ao loopback; seu inicializador também define o host local. Antes do deploy é necessário tratar separadamente a configuração do servidor, Host permitido, HTTPS, permissões dos endpoints, proteção das simulações e persistência SQLite. Há código de integração real da Meta, não validado nesta entrega. O domínio próprio ainda precisa ser confirmado com a professora. Não há URL pública ativa nesta preparação.
