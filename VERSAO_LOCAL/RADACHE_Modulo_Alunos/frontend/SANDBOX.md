# Controle isolado de alunos fictícios

Página: `/alunos/`, iniciada com `INICIAR_LOCAL.bat`; conta de demonstração `coord` / `admin123`.

A página permite listar, incluir e excluir alunos fictícios e publicá-los **nas duas versões**. A fonte compartilhada agora é o Mock SIGAA PostgreSQL. Inclusões não criam tickets. As consultas locais leem uma projeção dos mesmos alunos; IDs negativos diferenciam os fictícios dos registros SQLite existentes. Nenhum registro do cadastro SQLite original é alterado.

O serviço administrativo `VERSAO_INTEGRACAO/demo_catalog.py` possui credencial de seed separada e permite apenas criação/exclusão de registros marcados em `academico.demo_managed`. As APIs acadêmicas do RADACHE e do Mock continuam somente leitura. O backend operacional da integração C não recebe a credencial administrativa.

`INICIAR_LOCAL.bat` também inicia a integração C, necessária para consultar o catálogo. Excluir um aluno o remove das consultas das duas versões; tickets previamente registrados na C preservam o histórico. O SQLite anterior `database/alunos_mock_isolado.db` é preservado, mas seus registros não são promovidos automaticamente: cadastre-os novamente escolhendo um dos cursos de demonstração quando desejar publicá-los.

Os campos são somente nome (`TESTE ...`), matrícula (`TESTE-...`) e curso fictícios. Não coletar dados pessoais reais. O prefixo é uma convenção de identificação, não uma garantia automática de anonimização.

Endpoints: GET/POST `/api/mock-alunos`; DELETE `/api/mock-alunos/{id}`. Todas as operações exigem sessão e perfil de coordenação. PUT/PATCH são recusados; a ferramenta administrativa também não oferece UPDATE. Campos extras são rejeitados. Não há modo de edição nem armazenamento de alunos em localStorage. O token de sessão local fica em sessionStorage para permitir a navegação ao painel com a mesma conta, como no fluxo original; o logout o remove.

A interface oferece matrícula sugerida, prefixo TESTE automático, seleção de curso, busca e botão de três exemplos prontos. Computação e Pedagogia correspondem aos cursos provisionados no Mock e aos escopos dos usuários de demonstração. O atendente da C vê Computação; a coordenação vê ambos.

As rotas antigas de escrita em `/api/alunos` e as operações POST/PATCH em `/api/local/alunos` e `/api/v1/alunos` foram bloqueadas. A gestão por curso continua com consulta de alunos; seus controles de inclusão/edição foram desabilitados. O banco original foi preservado.

`RADACHE_ENV=production` (ou qualquer valor diferente de `development`) desabilita todas as operações do sandbox. Sem a variável, a versão local assume desenvolvimento. Em implantação institucional, declarar o ambiente explicitamente e não publicar o sandbox. Dados oficiais continuam sendo consultados por integração autorizada, sem CRUD acadêmico operacional.

Código: `index.html`, `app.js`, `sandbox.css` e `../backend/mock_alunos.py`. O backend desta versão é Python, não PHP. Cópias dos arquivos principais anteriores estão em `revisao_mock_backup` na raiz do projeto, fora do diretório servido pelo módulo.

Validação: quatro testes passaram em servidor/bancos temporários, incluindo navegador Edge. Conferidos: inclusão/exclusão sem alteração no banco original, negação de UPDATE por SQL/HTTP, bloqueio das rotas antigas e aliases, autenticação, modo produção e layout em 320/390/1280px. Testes antigos que esperavam CRUD acadêmico completo representam o contrato anterior e precisam de revisão antes de integrar esta mudança a uma suíte global.
