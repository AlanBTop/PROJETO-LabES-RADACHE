# RADACHE02/26LabES — publicação gratuita no Render

**Situação: configuração preparada; aplicação ainda não publicada.** O endereço pretendido é `https://radache02-26labes.onrender.com`, sujeito à disponibilidade do nome na conta. É um subdomínio da hospedagem, sem registro de domínio próprio.

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

O blueprint pede ao Render para gerar quatro senhas iniciais distintas. Nenhuma senha privada de avaliação ou token está no Git, no HTML público ou nos logs do inicializador. As contas são fictícias:

| Conta | Perfil | Variável privada no Render |
|---|---|---|
| `admin@radache.local` | Administrador técnico | `RADACHE_EVALUATION_ADMIN_PASSWORD` |
| `analista@radache.local` | Analista institucional | `RADACHE_EVALUATION_ANALYST_PASSWORD` |
| `coord@radache.local` | Gestor de Ciência da Computação, Cáceres | `RADACHE_EVALUATION_MANAGER_PASSWORD` |
| `diretor-caceres@radache.local` | Diretor de Cáceres, consulta | `RADACHE_EVALUATION_DIRECTOR_PASSWORD` |

O responsável deve consultar esses valores privadamente no painel do Render e entregar apenas os acessos necessários à professora por um canal adequado. Não colocar senhas em README, issues, screenshots ou mensagens públicas. O primeiro acesso começa em `/gestao/` e exige troca de senha; depois, entrar novamente com a senha escolhida e seguir o [guia de avaliação](GUIA_AVALIACAO.md). O administrador pode cadastrar um atendente fictício e atribuir atendimentos.

As outras contas pré-existentes recebem senhas aleatórias locais, não anunciadas ao público. As senhas de demonstração da versão local não autenticam no modo público. As dicas dessas senhas são ocultadas nas telas online.

Um reinício do processo com os mesmos arquivos preserva a senha alterada. Se os bancos forem descartados pela plataforma, o provisionamento volta às senhas iniciais privadas configuradas no Render e exige nova troca. Todas as pessoas que usam o mesmo serviço compartilham os dados, respeitadas as permissões; as sessões em memória não sobrevivem a reinícios.

## Procedimento após aprovação

1. Conferir e aprovar o commit desta configuração antes de enviá-lo ao GitHub.
2. Instalar a integração Render e conectar a conta, ou acessar o painel do provedor. Login e eventual criação de conta são ações do titular; não fornecer tokens pelo chat.
3. Após a aprovação explícita do deploy, criar o serviço pelo blueprint do repositório `AlanBTop/PROJETO-LabES-RADACHE`, branch `main`. Conferir `plan: free`, nenhum disco/banco pago e deploy automático desativado. A criação do serviço dispara o primeiro deploy, mesmo com auto-deploy desligado; não concluir essa criação antes da aprovação.
4. Conferir o nome realmente atribuído e o valor automático de `RENDER_EXTERNAL_HOSTNAME`. Não presumir que o endereço desejado esteja disponível.
5. Verificar HTTPS, `/healthz`, as sete páginas do roteiro, troca de senha inicial e permissões dos quatro perfis. Testar cadastro fictício, check-in simulado, histórico e gestão, sem mensagens externas.
6. Atualizar o guia com o endereço ativo e com os resultados observados, mantendo a alternativa local.

## Limites e verificações

O modo público permite as simulações autenticadas e bloqueia WhatsApp real e webhook. O mock de mensagens também exige sessão e perfil operacional autorizado. `/healthz` não revela caminhos físicos. O servidor limita conexões concorrentes e tem timeout de leitura; isso não constitui auditoria completa ou garantia contra abuso.

O backend continua sendo um protótipo baseado em `http.server`, que a documentação Python não recomenda para produção. O escopo é uma avaliação acadêmica temporária, com dados inventados, atrás do HTTPS da plataforma; não é uma implantação institucional. [Limitação da biblioteca](https://docs.python.org/3/library/http.server.html).

Validação da configuração: `render.yaml` foi aceito pelo [schema oficial](https://render.com/schema/render.yaml.json), com uma instância Free, zero discos pagos, zero bancos gerenciados e zero senhas literais. Os testes locais e os limites de cobertura estão em [VALIDACAO_ENTREGA.md](VALIDACAO_ENTREGA.md). A validação local não prova que o deploy público funcionará; a etapa pública precisa ser executada e verificada depois da autorização.
