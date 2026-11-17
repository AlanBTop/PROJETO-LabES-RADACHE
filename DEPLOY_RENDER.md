# RADACHE02/26LabES — publicação gratuita no Render

**Situação: publicado e verificado em 17/11/2026.** Acesse **https://radache02-26labes.onrender.com**. É um subdomínio da hospedagem, sem registro de domínio próprio.

O deploy `dep-dbu7bh5ckfvc73bapaf0`, do commit `10993b3e36a66b61cd6fbb74344f5d50e0e53501`, ficou `live` às 15:43 UTC. O serviço pertence ao Alan's workspace, confirmado pelo titular, com uma instância `free`, deploy automático desligado e sincronização automática do blueprint desativada. [Painel do serviço](https://dashboard.render.com/web/srv-dbu7bglckfvc73bap9b0).

## Escopo e custo

`render.yaml` define **um Web Service no plano Free**, sem disco persistente, banco gerenciado ou recurso pago. Deploy automático está desativado. Não adicionar cartão, contratar excedentes nem alterar limites de cobrança. Se a conta exigir validação financeira ou qualquer recurso pago, parar a configuração e informar Alan.

O plano gratuito pode suspender o serviço após 15 minutos sem tráfego; a retomada demora aproximadamente um minuto. Os arquivos SQLite locais podem ser perdidos na suspensão, reinício ou novo deploy, e o workspace tem cotas mensais. Por isso a avaliação recria dados fictícios quando os bancos estão vazios. Não se promete disponibilidade contínua. [Condições do plano gratuito](https://render.com/docs/free).

## O que a configuração executa

- Runtime Python 3.13, selecionado por `.python-version`.
- Build: `python -m compileall -q VERSAO_LOCAL/RADACHE_Modulo_Alunos/backend`.
- Início: `python VERSAO_LOCAL/RADACHE_Modulo_Alunos/backend/run_web.py`.
- Bind em `0.0.0.0` e na variável `PORT` da plataforma, com uma única instância.
- Host público obtido de `RENDER_EXTERNAL_HOSTNAME`; hosts adicionais só entram por lista explícita em `RADACHE_ALLOWED_HOSTS`.
- SQLite, chaves e acessos iniciais no diretório privado `/tmp/radache02-26labes`, fora das pastas estáticas.
- Esquema e seeds criam o banco principal; o povoamento idempotente prepara 60 alunos fictícios, histórico e atendimentos de demonstração, sem transportar bancos existentes.
- HTTPS terminado pelo Render; cookies Secure e HttpOnly, validação de Host/Origin e proteção CSRF no backend. [Requisitos do serviço](https://render.com/docs/web-services).

## Acessos de avaliação

Além das contas privadas abaixo, a versão pública oferece o botão **Entrar na demonstração**. Ele cria uma sessão de visitante sem senha, acessível a qualquer pessoa. Os dados fictícios da simulação são compartilhados entre visitantes e contas privadas; essa sessão não pode criar ou alterar contas nem mudar senhas. Nunca utilize dados reais neste ambiente.

O blueprint pede ao Render para gerar quatro senhas iniciais distintas. Nenhuma senha privada de avaliação ou token está no Git, no HTML público ou nos logs do inicializador. As contas são fictícias:

| Conta | Perfil | Variável privada no Render |
|---|---|---|
| `admin@radache.local` | Administrador técnico | `RADACHE_EVALUATION_ADMIN_PASSWORD` |
| `analista@radache.local` | Analista institucional | `RADACHE_EVALUATION_ANALYST_PASSWORD` |
| `coord@radache.local` | Gestor de Ciência da Computação, Cáceres | `RADACHE_EVALUATION_MANAGER_PASSWORD` |
| `diretor-caceres@radache.local` | Diretor de Cáceres, consulta | `RADACHE_EVALUATION_DIRECTOR_PASSWORD` |

O responsável deve abrir o [painel do serviço](https://dashboard.render.com/web/srv-dbu7bglckfvc73bap9b0), escolher **Environment** e consultar privadamente os valores dessas variáveis. Para começar como administrador, use `admin@radache.local` e o valor de `RADACHE_EVALUATION_ADMIN_PASSWORD` em **https://radache02-26labes.onrender.com/gestao/**. Entregue apenas os acessos necessários à professora por um canal adequado. Não colocar senhas em README, issues, screenshots ou mensagens públicas. O primeiro acesso exige troca de senha; depois, entrar novamente com a senha escolhida e seguir o [guia de avaliação](GUIA_AVALIACAO.md). O administrador pode cadastrar um atendente fictício e atribuir atendimentos.

As outras contas pré-existentes recebem senhas aleatórias locais, não anunciadas ao público. As senhas de demonstração da versão local não autenticam no modo público. As dicas dessas senhas são ocultadas nas telas online.

Um reinício do processo com os mesmos arquivos preserva a senha alterada. Se os bancos forem descartados pela plataforma, o provisionamento volta às senhas iniciais privadas configuradas no Render e exige nova troca. Todas as pessoas que usam o mesmo serviço compartilham os dados, respeitadas as permissões; as sessões em memória não sobrevivem a reinícios.

## Publicação realizada e próximas atualizações

O blueprint `exs-dbu7bdkipgvc73au7btg` foi planejado e aplicado pela integração Render após as aprovações do deploy gratuito e do workspace. O Render gerou as quatro senhas privadas; seus valores não foram consultados nem publicados na validação.

Às 15:44 UTC, passaram 41 verificações no endereço público: sete páginas, 22 arquivos de interface referenciados por elas, `/healthz`, configuração pública, quatro APIs privadas sem sessão, mock de mensagens sem sessão, recusa de origem externa, recusa da senha demonstrativa local, bloqueio GET/POST do webhook e ausência de um caminho de acessos iniciais. O cliente validou o certificado HTTPS e verificou os cabeçalhos CSP, X-Content-Type-Options e X-Frame-Options nas respostas de sucesso. Nenhum erro apareceu na consulta de logs de aplicação com nível `error` após os testes.

Os testes públicos não autenticaram contas nem executaram JavaScript no navegador. Troca de senha, permissões dos quatro perfis, cadastro, check-ins e histórico passaram anteriormente sob HTTPS local; ainda precisam ser conferidos com os acessos privados no serviço público. Veja [VALIDACAO_ENTREGA.md](VALIDACAO_ENTREGA.md).

Para futuras alterações de código, enviar o commit ao GitHub e disparar um deploy manual no serviço existente. Mudanças de infraestrutura exigem planejar e revisar a sincronização do blueprint existente. Não criar outro serviço para atualizar este. Uma alteração apenas na documentação não inicia deploy com as configurações atuais.

## Limites e verificações

O modo público permite as simulações autenticadas e bloqueia WhatsApp real e webhook. O mock de mensagens também exige sessão e perfil operacional autorizado. `/healthz` não revela caminhos físicos. O servidor limita conexões concorrentes e tem timeout de leitura; isso não constitui auditoria completa ou garantia contra abuso.

O backend continua sendo um protótipo baseado em `http.server`, que a documentação Python não recomenda para produção. O escopo é uma avaliação acadêmica temporária, com dados inventados, atrás do HTTPS da plataforma; não é uma implantação institucional. [Limitação da biblioteca](https://docs.python.org/3/library/http.server.html).

Validação da configuração: `render.yaml` foi aceito pelo [schema oficial](https://render.com/schema/render.yaml.json) e pelo planejamento do Render, com uma instância Free, zero discos pagos, zero bancos gerenciados e zero senhas literais. Os testes locais, públicos e os limites de cobertura estão em [VALIDACAO_ENTREGA.md](VALIDACAO_ENTREGA.md).

