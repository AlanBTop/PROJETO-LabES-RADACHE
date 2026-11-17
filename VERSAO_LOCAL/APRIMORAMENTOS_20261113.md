# Revisão dos aprimoramentos — 13/11/2026

Aplicada à pasta `VERSAO_LOCAL`, identificada pelo inicializador principal como sistema ativo.
As versões pausadas, cópias para envio e arquivos de trabalho não receberam estas mudanças.
Os bancos da instalação não foram usados nas validações nem expurgados: os testes criam bancos temporários.

| Apontamento | Resultado |
|---|---|
| Credenciais conhecidas | Demonstração explícita com `--demo`, restrita ao loopback. Modo próprio gera senha aleatória e salt por conta, força troca no primeiro login e invalida sessões anteriores. Credenciais de exemplo encontradas no banco próprio são substituídas na migração. |
| Bem-estar 1 ou 2 | Resposta de acolhimento no WhatsApp real, alerta independente do índice na lista e ficha do painel, visível aos perfis autorizados de coordenação e NAE. Canal institucional configurável por `RADACHE_CANAL_NAE`. |
| Eventos e retenção | Telefone pseudonimizado por HMAC-SHA256, associação a aluno e check-in, exclusão dos eventos vinculados na revogação e expurgo explícito com simulação prévia. Respostas também são retiradas da avaliação derivada e seus metadados. |
| Segurança HTTP | Cinco tentativas malsucedidas em 15 minutos por IP ou identificador de login; limite compartilhado pelos três aliases. CORS aberto removido, validação de Host e de origem nas escritas, CSP e cookie Secure sob HTTPS. |
| Lembretes | Ativação explícita por `RADACHE_WHATSAPP_LEMBRETES=1`, exigindo credenciais, versão da API e os dois modelos aprovados. O comportamento padrão não envia lembretes reais. |
| Calibração | Limitações e cenários documentados em [MODELO_RISCO.md](MODELO_RISCO.md). Os pesos foram preservados; não há dados históricos para calibrar ou validar uma previsão. |
| Faixas divergentes | Limites definidos em constantes de `risk.py`; documentação gerada diretamente do motor. README corrigido. |
| Valores acadêmicos fabricados | Repositório exige os quatro componentes para uma nova avaliação e rejeita índice isolado ou divergente. Médias, respostas, pesos e classificação derivada são registrados juntos. Alterações só cadastrais preservam o histórico. |
| Reclassificação ao iniciar | Removida. Disponível apenas como migração explícita; valores históricos não mudam ao abrir o servidor. |

O relatório original dizia que `resposta_academica` nunca era preenchida, mas o seed traz três textos fictícios.
A coluna foi retirada do esquema e dos seeds novos. Bancos antigos mantêm a coluna por compatibilidade;
a revogação também limpa esse campo legado. Nenhuma migração destrutiva foi aplicada ao banco existente.
O telefone normalizado tem índice e triggers de atualização; o webhook consulta no máximo duas correspondências
e rejeita números ambíguos, sem carregar todos os alunos em Python.

O módulo legado da raiz foi movido para `ARQUIVO/estudos_e_revisoes/whatsapp_api_legada_20261113.py`.
O ramo inalcançável de cadastro HTTP foi removido. As duas fontes de credenciais usam a mesma implementação
de sessões e o mesmo registro em memória no servidor padrão, com um adaptador para testes e usuários externos.
A importação circular de `app` dentro do gerenciador local foi eliminada.

## Executar e revisar

- Apresentação fictícia: `INICIAR_RADACHE.bat`, como antes. O atalho seleciona `--demo` explicitamente.
- Credenciais próprias: `VERSAO_LOCAL/INICIAR_LOCAL.bat --secure --port 8082`.
- O modo próprio usa `radache_privado.db`, `mock_sigaa_privado.db` e `radache_sim_privado.db`.
- Senhas iniciais: arquivo `radache_privado.db.acessos-iniciais.json` na pasta `database`.
  Entre por `/gestao/` para definir sua senha. Depois da troca, a senha inicial deixa de funcionar.
  O arquivo inicial pode ser removido depois de todas as contas serem entregues e alteradas.
- Um servidor antigo já aberto continua executando o código que carregou; encerre-o e abra o atalho novamente.
  O inicializador recusa reutilizar uma porta ocupada pelo outro modo.

O modo próprio é uma separação de credenciais e bancos dentro do protótipo; não certifica prontidão institucional.
Para HTTPS terminado em proxy confiável, configure `RADACHE_HTTPS=1` e impeça acesso direto ao HTTP do backend.
O servidor não confia em `X-Forwarded-Proto` enviado por clientes. A CSP permite estilos inline porque os gráficos
existentes usam propriedades CSS dinâmicas; scripts continuam restritos à própria origem.

## Retenção e migrações

A partir de `VERSAO_LOCAL/RADACHE_Modulo_Alunos/backend`:

```powershell
python maintenance.py purge --days 365
python maintenance.py purge --days 365 --apply
python maintenance.py reclassify
python maintenance.py reclassify --apply
python risk_documentation.py --check
```

Sem `--apply`, manutenção apenas informa a operação. Escolha o banco com `RADACHE_DB` e faça backup antes
de aplicar expurgo ou migração. A chave de pseudonimização fica em `<banco>.telefone.key`; preserve-a com
o backup privado do banco. HMAC é pseudonimização: o cadastro ainda contém o telefone necessário ao contato.
O prazo de 365 dias é um exemplo configurável, a ser definido pela política institucional.
O expurgo remove respostas e eventos antigos, preservando o registro numérico de risco e a trilha mínima;
isso não equivale à exclusão integral de todos os dados do estudante.

## Validação

- 157 testes passaram em bancos temporários, com descoberta padrão do unittest e sem configurar PYTHONPATH.
- Nove novos testes cobrem credenciais próprias, troca obrigatória, revogação de sessões, limites de login,
  CSRF, headers, HMAC nos eventos, revogação, busca indexada, retenção e integridade das avaliações.
- Edge/Chromium: login demonstrativo, alerta na lista e ficha, troca obrigatória em tela de 390 px e novo login.
  Nenhum erro JavaScript ou violação de CSP observado nesse percurso.
- Evidências: [log da suíte](validacao/aprimoramentos_20261113/testes.log),
  [resultado do navegador](validacao/aprimoramentos_20261113/navegador.json).
- Após os ajustes finais, 47 testes dos módulos afetados passaram novamente; `risk_documentation.py --check` confirmou as faixas geradas.
- Cópias dos arquivos centrais anteriores estão em `validacao/aprimoramentos_20261113/original`.

Não foram enviados WhatsApps reais nem ativado o agendador na instalação.
O texto de acolhimento e o contato institucional ainda precisam ser validados pelo NAE ou equipe de psicologia.
A calibração depende de dados históricos e decisões institucionais. Essas são pendências externas à correção técnica.
