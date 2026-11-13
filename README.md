# RADACHE — versão local para avaliação

O RADACHE é um protótipo acadêmico de apoio ao acompanhamento de estudantes. Esta versão executa no próprio computador, com Python e SQLite. As telas de mensagens e a integração acadêmica são simulações: não enviam mensagens ao WhatsApp e não se conectam ao SIGAA.

## 1. Preparar o computador

- Instale **Python 3** pelo site oficial: https://www.python.org/downloads/. No Windows, marque a opção de adicionar o Python ao PATH durante a instalação.
- Baixe este repositório em **Code → Download ZIP** no GitHub e extraia o ZIP. Também é possível cloná-lo com Git.
- Não é necessário instalar bibliotecas com pip, Node.js ou configurar um banco externo para executar o sistema.

## 2. Iniciar o sistema

1. Abra a pasta extraída e entre em `VERSAO_LOCAL`.
2. No Windows, dê dois cliques em **INICIAR_LOCAL.bat**.
3. Mantenha aberta a janela do servidor enquanto estiver usando o sistema.
4. O navegador deve abrir o portal. Caso não abra, acesse http://localhost:8080/.

Pelo terminal, na pasta `VERSAO_LOCAL`, use:

```powershell
python RADACHE_Modulo_Alunos/backend/run_local.py
```

No primeiro uso, o banco principal é criado automaticamente a partir do esquema e dos dados fictícios iniciais. Alguns painéis dependem de simulações e podem aparecer vazios ou com poucos dados até que a etapa 4 seja realizada.

## 3. Contas e páginas

As contas abaixo são exclusivas para demonstração local:

| Área | Endereço | Acesso |
|---|---|---|
| Portal de entrada | http://localhost:8080/ | Acesso pelo navegador |
| Gestão: chamados, usuários e alunos | http://localhost:8080/gestao/ | `admin@radache.local` / `admin123` |
| Módulo de alunos | http://localhost:8080/alunos/ | `admin@radache.local` / `admin123` |
| Painel analítico | http://localhost:8080/painel-demo/ | `admin@radache.local` / `admin123` |
| Observatório institucional | http://localhost:8080/institucional/ | `analista@radache.local` / `admin123` |
| Mensagens e check-in simulado | http://localhost:8080/mensagens/ | Use a sessão de gestão no mesmo navegador, quando solicitada |

O perfil de analista é destinado à consulta de indicadores agregados. As credenciais são exemplos de um protótipo local e não são adequadas para produção.

## 4. Criar dados fictícios para avaliar os painéis

Para uma demonstração com dados distribuídos entre Cáceres, Várzea Grande e Cuiabá:

1. Inicie o sistema uma primeira vez e feche o servidor com **Ctrl+C** na janela do servidor.
2. Abra o terminal dentro da pasta `VERSAO_LOCAL`. No Explorador do Windows, é possível clicar na barra de endereço da pasta, digitar `powershell` e pressionar Enter.
3. Execute:

```powershell
python scripts/populate_universities.py
```

4. Aguarde a mensagem de conclusão e inicie novamente `INICIAR_LOCAL.bat`.

O script cria registros **fictícios** de alunos, respostas, histórico de avaliações e atendimentos para a demonstração. Ele identifica os registros gerados e preserva os anteriores; também cria uma cópia de segurança local. Os números podem variar conforme os dados que já existam no computador. A aplicação utiliza SQLite e salva as alterações nessa instalação.

## 5. Roteiro para testar o fluxo

1. No **Portal**, abra as áreas do sistema.
2. Em **Gestão → Alunos**, entre com a conta de administrador e consulte um aluno fictício. A área de gestão também permite acompanhar chamados e usuários.
3. Em **Mensagens**, selecione um aluno ativo e responda como estudante às perguntas do check-in, incluindo o consentimento. Os botões de avanço permitem experimentar novos períodos. O envio é apenas uma simulação.
4. Retorne ao **Painel analítico** para consultar indicadores e filtros por curso. As informações dependem dos registros e respostas disponíveis.
5. No **Observatório institucional**, acesse com a conta de analista e compare os indicadores agregados dos câmpus.
6. Em **Gestão → Chamados**, consulte os atendimentos e seus estados. Utilize apenas dados fictícios para a avaliação.

O índice de risco é um indicador do protótipo para apoiar o acompanhamento; ele não deve ser apresentado como uma probabilidade de evasão validada.

## 6. Solução de problemas

- **Python não encontrado:** instale Python 3, feche e abra o terminal novamente e verifique `python --version`. No Windows, tente `py -3 --version`.
- **Porta 8080 ocupada:** dentro de `VERSAO_LOCAL`, execute `INICIAR_LOCAL.bat --port 8082` pelo terminal e acesse http://localhost:8082/. Substitua a porta nos demais endereços também.
- **Página não abre:** confira se a janela do servidor continua aberta e se o endereço começa com `http://localhost`.
- **Sem alunos na simulação ou painel vazio:** execute a etapa 4 e reinicie o sistema. A quantidade de dados depende das operações realizadas na instalação.
- **Encerrar:** pressione Ctrl+C na janela do servidor.

Os bancos SQLite com histórico de uso e os logs não acompanham o repositório. A estrutura do código está descrita em [VERSAO_LOCAL/ESTRUTURA.md](VERSAO_LOCAL/ESTRUTURA.md).
