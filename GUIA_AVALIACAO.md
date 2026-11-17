# RADACHE — guia para avaliação

Protótipo acadêmico de acompanhamento estudantil. Utilize apenas dados inventados. O índice é uma heurística de triagem, sem validação como probabilidade de evasão ou diagnóstico psicológico.

## Começar

Para avaliar sem senha, abra o endereço público e clique em **Entrar na demonstração**. A sessão permite consultar os painéis e experimentar o cadastro e as conversas simuladas. Na área Equipe e acessos é possível consultar os perfis, mas a alteração de contas e permissões exige login privado. O botão aparece também nas demais páginas, para retomar a demonstração.

Qualquer visitante do endereço pode usar a demonstração; todos compartilham os mesmos dados. Use somente informações fictícias e não inclua dados pessoais reais. A hospedagem gratuita pode reiniciar ou apagar os dados.

Endereço público: **https://radache02-26labes.onrender.com**, publicado no Render Free em 17/11/2026. O nome de apresentação é **RADACHE02/26LabES**. A aceitação desse subdomínio como requisito de domínio depende do critério da professora.

Para administrar contas, acesse **https://radache02-26labes.onrender.com/gestao/** com o acesso privado fornecido pelo responsável, altere a senha inicial e entre novamente. O responsável encontra a senha inicial de `admin@radache.local` em **Environment → RADACHE_EVALUATION_ADMIN_PASSWORD**, no [painel do serviço](https://dashboard.render.com/web/srv-dbu7bglckfvc73bap9b0). As senhas públicas de exemplo abaixo são exclusivas do modo local `--demo`. No modo online, os dados são compartilhados e descartáveis; a suspensão ou reinício na hospedagem gratuita pode reiniciar a demonstração. Detalhes em [DEPLOY_RENDER.md](DEPLOY_RENDER.md).

Para seguir as páginas e o roteiro abaixo online, substitua `http://localhost:8080` por `https://radache02-26labes.onrender.com`, mantendo o caminho. As sete páginas e seus arquivos de interface responderam na verificação pública. Os fluxos autenticados do roteiro foram testados sob HTTPS local e ainda precisam de conferência no ambiente público.

No Windows, com Python 3 instalado, entre em `VERSAO_LOCAL` e abra `INICIAR_LOCAL.bat`. Mantenha a janela aberta e acesse http://localhost:8080/. Alternativa pelo terminal, dentro dessa pasta:

```powershell
python RADACHE_Modulo_Alunos/backend/run_local.py --demo --no-browser
```

O backend usa a biblioteca padrão do Python e SQLite. O modo demonstrativo é restrito ao próprio computador. Se a porta estiver ocupada, não encerre processos desconhecidos: acrescente `--port 8082` e use essa porta nos links. Para encerrar seu servidor, pressione Ctrl+C na janela correspondente.

## Páginas e acessos

Todas as contas desta tabela são fictícias e usam a senha de demonstração `admin123`, somente com `--demo`.

| Área | Caminho | Conta e finalidade |
|---|---|---|
| Portal | [Início](http://localhost:8080/) | Entrada e links para as áreas; sem login |
| Gestão | [Chamados](http://localhost:8080/gestao/#chamados) | `admin@radache.local`: chamados e acompanhamento |
| Gestão | [Usuários](http://localhost:8080/gestao/#usuarios) | Administrador: cadastro e atribuição de perfis |
| Gestão | [Alunos](http://localhost:8080/gestao/#alunos) | Administrador: consulta e acompanhamento |
| Cadastro simulado | [Alunos](http://localhost:8080/alunos/) | Administrador: criar e editar alunos fictícios |
| Indicadores | [Painel](http://localhost:8080/painel-demo/) | Administrador: cursos, avaliações e histórico individual |
| Institucional | [Observatório](http://localhost:8080/institucional/) | `analista@radache.local`: consulta agregada, sem dados individuais |
| Conversas | [Mensagens](http://localhost:8080/mensagens/) | Use a sessão administrativa no mesmo navegador: check-in simulado |
| Troca de senha | [Alterar senha](http://localhost:8080/assets/change-password.html) | Sessão autenticada; obrigatória no primeiro login de contas próprias |

Também existem diretores de câmpus (`diretor-caceres@radache.local`, `diretor-varzea-grande@radache.local`, `diretor-cuiaba@radache.local`) com escopo de consulta, gestores por curso e o perfil Atendente Acadêmico. Um exemplo de gestor é `coord@radache.local`, de Ciência da Computação em Cáceres. O administrador pode cadastrar contas fictícias e atribuir curso/câmpus em Usuários. Cada perfil possui permissões distintas; não suponha que todo usuário possa editar ou consultar todas as áreas.

## Roteiro principal

1. Abra o portal e entre em **Alunos** com a conta administrativa.
2. Clique em **Novo aluno**. Use nome `TESTE Professora Alfa`, matrícula `DEMO-AVALIACAO-01`, curso `Ciência da Computação`, período 4, média 8 e frequência 90. Deixe telefone vazio e, se necessário, use `aluno@example.com`. Salve. Se a matrícula já existir, use outro sufixo.
3. Busque o nome do aluno no filtro da lista; a avaliação online já começa com outros perfis fictícios e usa paginação. Abra **Detalhes / editar**, altere o nome para `TESTE Professora Editado` e salve.
4. Abra **Mensagens** na mesma aba e selecione esse aluno. Aceite o consentimento com **1**, responda **4** à pergunta financeira e **1** à pergunta de bem-estar. O check-in deve terminar. Com os pesos padrão, média 8 e frequência 90, o índice esperado é **57,5**, moderado; a resposta de bem-estar também demanda acolhimento independentemente do índice.
5. Recarregue Mensagens: a conversa deve continuar salva. Use o controle de **próximo mês**, aceite com **1**, responda **1** para financeiro e **5** para bem-estar. O novo índice esperado é **7,5**, estável. Não se trata do envio de um WhatsApp.
6. Abra o **Painel**, selecione o curso, busque o nome na lista de estudantes e abra o perfil do aluno. Consulte as avaliações e a evolução. Alterações no risco e estado de atendimento são conceitos distintos: resolver um chamado não garante redução do índice.
7. Entre em **Gestão → Chamados**, consulte a fila e abra um registro fictício. Observe seus dados, responsável e estado. Apenas perfis autorizados podem alterar atendimentos.
8. Em outra janela privada, acesse o **Observatório** como analista. Compare os indicadores agregados dos câmpus; esse perfil não deve acessar fichas individuais nem editar dados.
9. Volte ao portal pelo menu ou pelo endereço inicial. Termine a sessão com **Sair**.

## Dados iniciais, persistência e reinício

O primeiro início cria o banco principal com os dados fictícios de `schema.sql` e `seeds.sql`; cadastro e conversas simuladas usam mais dois bancos SQLite. O catálogo da simulação pode começar vazio. O cadastro acima prepara o roteiro sem transportar bancos existentes.

Opcionalmente, com o servidor encerrado, execute `python scripts/populate_universities.py` dentro de `VERSAO_LOCAL` e reinicie. Esse script cria dados fictícios identificados para os três câmpus, preserva registros anteriores e cria um backup local em `ARQUIVO/backups`. Os painéis refletem os dados disponíveis, não uma quantidade fixa de alunos.

Os visitantes do mesmo servidor compartilham os bancos, conforme as permissões dos perfis; não há banco separado por visitante. Recarregar a página ou encerrar o servidor não apaga os registros. A sessão de gestão na interface pode pedir novo login após recarregar. Os botões de avanço e reinício afetam a simulação selecionada; não equivalem a limpar toda a instalação.

Para repetir sem apagar dados, crie outro aluno fictício com matrícula diferente. Para uma instalação totalmente nova, extraia outro ZIP do repositório em uma pasta vazia e inicie ali. Não remova bancos da instalação original. Os testes da entrega usam bancos descartáveis.

## Limitações

- Cadastro acadêmico e conversas nesta demonstração são simulações locais; não há conexão verificada com SIGAA.
- Há código de integração com a API da Meta, mas seu funcionamento real não foi testado nesta entrega. Não configure credenciais, lembretes nem webhook para avaliar a simulação.
- O modo de contas próprias é separado da demonstração: `INICIAR_LOCAL.bat --secure --port 8082`. As senhas iniciais geradas ficam em arquivo privado junto ao banco e exigem troca no primeiro acesso em Gestão. Esse arquivo, bancos e chaves nunca devem ser publicados.
- A publicação usa um subdomínio gratuito do Render, sem domínio próprio. O serviço pode suspender por inatividade e descartar seus bancos; utilize apenas dados fictícios e mantenha a alternativa local para apresentação.
- Os resultados de testes desta preparação serão registrados em `VALIDACAO_ENTREGA.md`; a presença de uma rota no código não prova que todos os seus fluxos foram testados.

