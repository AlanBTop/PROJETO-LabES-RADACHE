> Atualização de manutenção (26/10/2026): consulte [o relatório completo](../RELATORIO_MANUTENCAO.md) para as correções, as instruções vigentes de inicialização e os limites das integrações. O modo local sem servidor é ativado pela abertura do arquivo HTML; uma falha de API durante o uso por HTTP não troca os dados por amostras.

# RADACHE — Módulo Provisório de Gerenciamento de Alunos

**Universidade do Estado de Mato Grosso (UNEMAT) — Câmpus Universitário de Cáceres**  
**Faculdade de Ciências Exatas e Tecnológicas — Curso de Bacharelado em Ciência da Computação**  
**Disciplina:** Engenharia de Software / Empreendedorismo  
**Docente:** Profa. Dra. Maricy Caregnato  
**Equipe do Projeto:** Alan Botelho, Melissa Rodrigues, Micaela Rocha, Roney Aires, Igor Tafarello  

---

## 1. Visão Geral do Módulo

O presente módulo implementa a funcionalidade de **Gerenciamento de Alunos** para o sistema **RADACHE** (*O preventor de evasão acadêmica*). Ele provê uma base de dados provisória estruturada, consistente e segura para suportar o desenvolvimento, validação e demonstração do MVP durante a Fase de Construção e Testes da disciplina.

### Princípios Arquiteturais Aplicados:
* **Desacoplamento do SIGAA:** A estrutura foi desenhada com abstração de repositório, permitindo que a base provisória seja substituída futuramente por adaptadores de integração com o SIGAA (via API REST ou web services institucionais) sem necessidade de reconstrução do sistema.
* **Segregação de Responsabilidades:** Dados cadastrais (`alunos`), indicadores de risco/evasão (`avaliacoes`) e dados de interação conversacional via WhatsApp (`checkins`) residem em tabelas distintas, evitando tabelas monolíticas.
* **Conformidade à LGPD e Auditoria:** Os dados sensíveis psicossociais contam com flag de consentimento explícito e o sistema prioriza a **Exclusão Lógica** (`status = 'inativo'`), garantindo que históricos de evasão não sejam corrompidos.
* **Zero Fricção de Execução:** O backend roda em Python 3 puro (sem `pip install`), utilizando banco relacional SQLite nativo, e o frontend funciona tanto conectado via HTTP quanto em modo standalone (*LocalStorage*).

---

## 2. Estrutura do Banco de Dados Relacional

O banco de dados provisório foi modelado no dialeto **SQLite 3** (totalmente portável para PostgreSQL 14+ ou MySQL 8+).

### 2.1 Diagrama Entidade-Relacionamento Conceitual

```
+------------------------------------+          1:N           +----------------------------------------+
|               ALUNOS               |----------------------<|               AVALIACOES               |
+------------------------------------+                        +----------------------------------------+
| PK  id               INTEGER       |                        | PK  id                   INTEGER       |
|     nome             VARCHAR(150)  |                        | FK  aluno_id             INTEGER       |
| UK  matricula        VARCHAR(20)   |                        |     nota_media           REAL          |
|     curso            VARCHAR(100)  |                        |     frequencia           REAL          |
|     campus           VARCHAR(100)  |                        |     situacao_financeira  VARCHAR(20)   |
|     periodo          INTEGER       |                        |     situacao_psicologica VARCHAR(20)   |
|     email            VARCHAR(120)  |                        |     indice_risco         REAL          |
|     telefone         VARCHAR(20)   |                        |     classificacao_risco  VARCHAR(20)   |
|     status           VARCHAR(20)   |                        |     data_avaliacao       TIMESTAMP     |
|     data_cadastro    TIMESTAMP     |                        +----------------------------------------+
|     data_atualizacao TIMESTAMP     |
+------------------------------------+
                  |
                  | 1:N
                  v
+------------------------------------+
|              CHECKINS              |
+------------------------------------+
| PK  id                   INTEGER   |
| FK  aluno_id             INTEGER   |
|     consentimento_lgpd   INTEGER   |
|     resposta_financeira  TEXT      |
|     resposta_psicologica TEXT      |
|     resposta_academica   TEXT      |
|     data_checkin         TIMESTAMP |
+------------------------------------+
```

### 2.2 Dicionário de Dados das Tabelas

#### Tabela 1: `alunos` (Dados Cadastrais Mínimos)
| Campo | Tipo | Nulo? | Chave | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | NÃO | PK (Auto) | Identificador numérico primário do aluno. |
| `nome` | VARCHAR(150) | NÃO | - | Nome completo do discente. |
| `matricula` | VARCHAR(20) | NÃO | UK (Única) | Matrícula acadêmica institucional única. |
| `curso` | VARCHAR(100) | NÃO | Index | Curso de graduação (ex: Ciência da Computação, Direito). |
| `campus` | VARCHAR(100) | NÃO | - | Câmpus universitário (Padrão: 'Câmpus de Cáceres'). |
| `periodo` | INTEGER | NÃO | - | Período letivo atual (1 a 16). |
| `email` | VARCHAR(120) | NÃO | - | E-mail de contato institucional (@unemat.br). |
| `telefone` | VARCHAR(20) | NÃO | - | Telefone com DDD para acionamento no WhatsApp. |
| `status` | VARCHAR(20) | NÃO | Index | Situação do vínculo: `'ativo'`, `'inativo'`, `'formado'`, `'trancado'`. |
| `data_cadastro` | TIMESTAMP | NÃO | - | Data e hora da inclusão no sistema (Padrão: `CURRENT_TIMESTAMP`). |
| `data_atualizacao`| TIMESTAMP | SIM | - | Data e hora da última modificação cadastral. |

#### Tabela 2: `avaliacoes` (Motor de Predição e Risco)
| Campo | Tipo | Nulo? | Chave | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | NÃO | PK (Auto) | Identificador primário da avaliação. |
| `aluno_id` | INTEGER | NÃO | FK (alunos.id)| Chave estrangeira referenciando a tabela `alunos` (ON DELETE CASCADE). |
| `nota_media` | REAL | SIM | - | Média das notas acadêmicas (0.0 a 10.0). |
| `frequencia` | REAL | SIM | - | Percentual de frequência nas aulas presenciais/virtuais (0 a 100%). |
| `situacao_financeira`| VARCHAR(20)| NÃO | - | Classificação do impacto financeiro: `'estavel'`, `'moderada'`, `'critica'`. |
| `situacao_psicologica`|VARCHAR(20)| NÃO | - | Grau de vulnerabilidade emocional: `'estavel'`, `'moderada'`, `'critica'`. |
| `indice_risco` | REAL | NÃO | - | Chance calculada de evasão em percentual (0.0% a 100.0%). |
| `classificacao_risco`| VARCHAR(20)| NÃO | Index | Categoria do risco: `'estavel'` (<35%), `'moderado'` (35-69%), `'critico'` (≥70%). |
| `data_avaliacao` | TIMESTAMP | NÃO | - | Timestamp de quando a predição foi calculada. |

#### Tabela 3: `checkins` (Respostas Conversacionais do WhatsApp)
| Campo | Tipo | Nulo? | Chave | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | NÃO | PK (Auto) | Identificador primário do check-in. |
| `aluno_id` | INTEGER | NÃO | FK (alunos.id)| Chave estrangeira referenciando a tabela `alunos`. |
| `consentimento_lgpd`| INTEGER | NÃO | - | Flag indicando consentimento ativo (1 = Autorizado, 0 = Revogado). |
| `resposta_financeira`| TEXT | SIM | - | Resposta do aluno sobre gastos de transporte, moradia e alimentação. |
| `resposta_psicologica`| TEXT | SIM | - | Resposta do aluno sobre esgotamento, ansiedade ou desmotivação. |
| `resposta_academica`| TEXT | SIM | - | Resposta do aluno sobre dificuldade de acompanhar as matérias. |
| `data_checkin` | TIMESTAMP | NÃO | - | Data e hora em que a interação ocorreu. |

---

## 3. Dados de Teste (Alunos Fictícios)

O banco é inicializado automaticamente com 8 discentes fictícios (em conformidade estrita com a LGPD, sem dados pessoais de estudantes reais da UNEMAT):

1. **Lucas Silva Santos** (Matrícula: `20240182` | Ciência da Computação, 3º Período):  
   *Classificação:* **Crítico (89%)** — Nota média 4.2, frequência 58%, situação financeira e psicológica críticas.
2. **Camila Martins Rocha** (Matrícula: `20250041` | Direito, 1º Período):  
   *Classificação:* **Crítico (82%)** — Caloura, ansiedade severa, atraso na concessão de bolsa permanência.
3. **Carlos Eduardo Lima** (Matrícula: `20250112` | Ciência da Computação, 1º Período):  
   *Classificação:* **Moderado (64%)** — Frequência 75%, notas regulares, custos apertados com deslocamento.
4. **Beatriz Gomes Costa** (Matrícula: `20220891` | Agronomia, 7º Período):  
   *Classificação:* **Moderado (52%)** — Desgaste emocional com o TCC, finanças estáveis.
5. **Rodrigo Alves Prado** (Matrícula: `20240219` | Agronomia, 3º Período):  
   *Classificação:* **Moderado (48%)** — Conflito de jornada de trabalho no campo com aulas teóricas.
6. **Amanda Oliveira Faria** (Matrícula: `20250019` | Ciência da Computação, 1º Período):  
   *Classificação:* **Estável (18%)** — Nota média 8.8, 95% de frequência, excelente integração acadêmica.
7. **Mariana Ribeiro Dias** (Matrícula: `20230045` | Pedagogia, 5º Período):  
   *Classificação:* **Estável (14%)** — Nota média 9.1, 98% de frequência, estágio curricular em dia.
8. **João Victor Nogueira** (Matrícula: `20240331` | Enfermagem, 3º Período):  
   *Status:* **Inativo (71%)** — Aluno que solicitou trancamento formal, demonstrando a exclusão lógica no sistema.

---

## 4. Política de Exclusão: Lógica vs. Física

Em sistemas de inteligência analítica voltados à retenção estudantil e submetidos à LGPD, a exclusão de dados requer distinção conceitual:

* **Exclusão Lógica (Soft Delete - Padrão do RADACHE):**  
  Altera o atributo `status` de `'ativo'` para `'inativo'`.  
  *Por que adotar?* Evita a perda do histórico longitudinal de predição do câmpus. Se um aluno trancar ou abandonar o curso, apagar seus registros apagaria as evidências de evasão utilizadas pelo modelo preditivo e pela coordenação/NAE para relatórios institucionais.
* **Exclusão Física (Hard Delete):**  
  Executa `DELETE FROM alunos WHERE id = ?`, disparando `ON DELETE CASCADE` nas tabelas de avaliações e check-ins.  
  *Quando usar?* Reservada exclusivamente para casos de erro material de digitação (cadastro indevido) ou solicitações formais de eliminação de dados pelo titular com base no Art. 18 da LGPD, quando não houver obrigação legal de retenção institucional.

Ambas as opções estão disponíveis na interface de confirmação de exclusão do módulo.

---

## 5. Instruções Passo a Passo de Execução

### Opção A — Execução Rápida via Script Batch (Recomendada no Windows)
1. Dê um duplo clique no arquivo [`iniciar_modulo.bat`](file:///C:/Users/alanb/Downloads/RADACHE_Modulo_Alunos/iniciar_modulo.bat).
2. O script detectará automaticamente o interpretador Python na máquina (incluindo o Python 3.13 do pgAdmin ou do sistema).
3. O banco SQLite será criado/inicializado e a página será aberta no navegador em `http://localhost:8080`.

### Opção B — Execução Manual no Terminal
Abra o PowerShell ou Prompt de Comando na pasta do projeto e execute:
```powershell
& "C:\Users\alanb\AppData\Local\Programs\pgAdmin 4\python\python.exe" backend\app.py
```
Acesse no seu navegador: `http://localhost:8080`

### Opção C — Execução Standalone (Sem Servidor)
Caso queira demonstrar a interface sem iniciar o servidor Python:
1. Navegue até a pasta `frontend/`.
2. Dê um duplo clique no arquivo [`index.html`](file:///C:/Users/alanb/Downloads/RADACHE_Modulo_Alunos/frontend/index.html).
3. Ao abrir pelo protocolo file:, a aplicação ativará o motor local em *LocalStorage*, carregando todos os dados fictícios para navegação interativa imediata.

---

## 6. Roteiro de Testes das Funcionalidades

1. **Testar Dashboard Superior:**  
   Verifique os cards de KPI no topo: Total de Alunos (8), Alunos Ativos (7), Risco Crítico (2), Risco Moderado (3) e Risco Estável (2).
2. **Testar Pesquisa:**  
   Digite `"Lucas"` ou `"20250041"` na barra de busca. A tabela filtra os registros instantaneamente.
3. **Testar Filtros Combinados:**  
   Selecione o curso `"Ciência da Computação"` e o risco `"Crítico"`. Observe o isolamento do aluno Lucas Silva Santos.
4. **Cadastrar Novo Aluno:**  
   Clique no botão `+ Adicionar Aluno`, preencha o formulário e clique em `Salvar Aluno`. O sistema valida a matrícula única, atualiza a tabela e recalcula os cards do dashboard em tempo real.
5. **Visualizar Ficha do Estudante:**  
   Clique no ícone de visualização (`👁️`) na coluna de ações de qualquer aluno. O modal exibirá os dados de contato e o Radar de Vulnerabilidade com as barras de notas, frequência e fatores psicossociais.
6. **Editar Aluno:**  
   Clique no ícone de edição (`✏️`) para alterar dados como telefone, período ou simulação de risco.
7. **Excluir / Inativar Aluno:**  
   Clique na lixeira (`🗑️`). O modal apresentará a opção recomendada de inativação lógica (`Inativar Aluno`) e a opção definitiva de remoção física.

---

## 7. Preparação para Integrações Futuras

| Componente Futuro | Fonte / Origem | Mecanismo de Integração Previsto no Banco de Dados |
|---|---|---|
| **SIGAA** | Dados Acadêmicos Oficiais | A tabela `alunos` espelha o modelo de identidade do SIGAA (`matricula`, `curso`, `campus`, `periodo`). Quando a integração for liberada, basta criar um script agendado (*cron job*) que substitua o `INSERT` manual por uma rotina de sincronização com o banco PostgreSQL/Oracle da UNEMAT. |
| **WhatsApp / IA** | Check-in Mensal do Aluno | A tabela `checkins` já possui os campos de consentimento LGPD, respostas psicossociais e carimbo de tempo. O webhook do provedor oficial de WhatsApp (Meta API / Evolution API) injetará os dados diretamente nesta tabela. |
| **Motor de Cálculo**| Algoritmo de Predição | A tabela `avaliacoes` recebe a saída do modelo de machine learning (baseado nos 4 fatores de 25% cada: notas, frequência, finanças e emocional), gravando o `indice_risco` e a `classificacao_risco`. |
| **Dashboard de Gestão**| Portal da Coordenação / NAE | O endpoint `GET /api/dashboard` e `GET /api/alunos` provê dados estruturados com agrupamentos e filtros para alimentar o Drawer 360° e a Central de Triagem com SLA de 24h. |

### Substituição do SQLite pelo SIGAA

As rotas HTTP chamam somente `backend/aluno_service.py` (`AlunoService`). O serviço atual delega ao módulo SQLite `database.py`. Quando a API oficial estiver disponível, implemente os mesmos métodos (`listar`, `obter`, `cadastrar`, `atualizar` e `excluir`) usando HTTP e autenticação do SIGAA, mantendo os formatos de retorno atuais. Em `app.py`, troque a instanciação `AlunoService()` pelo novo adapter. As rotas REST e o contrato do frontend permanecem iguais.

O esquema inclui `status_exclusao` (`0` visível, `1` oculto). A exclusão lógica atualiza essa flag sem apagar o histórico; a exclusão física usa as chaves estrangeiras com `ON DELETE CASCADE`.

## 8. Login e perfis (Sprint 2)

O servidor protege os endpoints `/api/*` com tokens Bearer. Os tokens expiram em 8 horas e ficam apenas na memória do processo; reiniciar o servidor encerra todas as sessões. A tela guarda o token em `sessionStorage` e o botão **Sair** o revoga.

As senhas não são configuradas em texto puro. Para gerar `salt` e `password_hash` com PBKDF2-SHA256, execute no diretório `backend`:

```powershell
& 'C:\Users\alanb\AppData\Local\Programs\pgAdmin 4\python\python.exe' hash_password.py
```

Configure a variável `RADACHE_USERS` com o JSON de contas. Use o `salt` e `password_hash` impressos pelo comando:

```powershell
$env:RADACHE_USERS = '{"coord":{"role":"coordenacao","salt":"SALT_HEX","password_hash":"HASH_HEX"},"nae":{"role":"nae","salt":"SALT_HEX","password_hash":"HASH_HEX"},"caest":{"role":"caest","salt":"SALT_HEX","password_hash":"HASH_HEX"},"prae":{"role":"prae","salt":"SALT_HEX","password_hash":"HASH_HEX"}}'
& 'C:\Users\alanb\AppData\Local\Programs\pgAdmin 4\python\python.exe' backend\app.py
```

Substitua cada salt/hash pelo par gerado para a senha de cada conta. Perfis aceitos: `coordenacao`, `nae`, `caest` e `prae`. O backend rejeita configuração com senha em texto puro. Para facilitar testes, contas podem ser omitidas, mas nesse caso o endpoint de login informa que não há usuários configurados.

Política inicial de menor privilégio: coordenação pode consultar e administrar todos os dados; NAE consulta identificação mínima, classificação/índice de risco e situação psicológica; CAEst consulta identificação mínima, média e frequência; PRAE consulta identificação mínima e situação financeira. Os três perfis setoriais são somente leitura. O servidor filtra os campos antes de responder, além de ocultá-los na interface.

Ao abrir frontend/index.html como arquivo, a demonstração com dados fictícios em LocalStorage fica disponível. Durante o uso por HTTP, uma falha do backend é informada na tela e não muda a origem dos dados.

## 9. Check-in WhatsApp (Sprint 2)

A integração usa a **WhatsApp Business Cloud API oficial da Meta**, chamada pelo módulo `backend/whatsapp.py` com `urllib` da biblioteca padrão. O webhook público é `/webhooks/whatsapp`; configure-o no painel Meta com assinatura HTTPS e assinatura de eventos de mensagens. Em ambiente de produção, publique o servidor atrás de HTTPS.

Configure no PowerShell antes de iniciar o servidor (valores obtidos no Meta for Developers):

```powershell
$env:WHATSAPP_ACCESS_TOKEN = 'TOKEN_DA_META'
$env:WHATSAPP_PHONE_NUMBER_ID = 'ID_DO_NUMERO'
$env:WHATSAPP_API_VERSION = 'VERSAO_ATIVA_DA_GRAPH_API'
$env:WHATSAPP_VERIFY_TOKEN = 'SEGREDO_DE_VERIFICACAO_ESCOLHIDO_POR_VOCE'
$env:WHATSAPP_APP_SECRET = 'APP_SECRET_DA_META'
$env:WHATSAPP_TEMPLATE_CONSENTIMENTO = 'radache_consentimento'
$env:WHATSAPP_TEMPLATE_LEMBRETE = 'radache_lembrete'
$env:WHATSAPP_TEMPLATE_IDIOMA = 'pt_BR'
```

Os modelos `radache_consentimento` e `radache_lembrete` precisam ser criados e aprovados previamente no WhatsApp Manager. O corpo do modelo de consentimento deve incluir a variável `{{1}}`, preenchida pelo sistema com o texto de consentimento detalhado; o modelo de lembrete também deve aceitar `{{1}}` para a pergunta pendente. A resposta do aluno abre a janela de conversa para as duas perguntas subsequentes. As credenciais não devem ser adicionadas ao repositório.

Com uma sessão de coordenação, inicie os convites mensais usando `POST /api/checkins/enviar` com `Authorization: Bearer <token>`. O servidor envia somente para alunos ativos sem check-in no mês. O webhook recebe SIM/NÃO e as respostas numéricas; sem consentimento, não salva as respostas nem avança às perguntas. O servidor verifica `X-Hub-Signature-256`. Lembretes de pendências são verificados de hora em hora e enviados uma vez após três dias sem interação. O RE é recalculado após a segunda resposta. Após aceitar, o aluno pode enviar `REVOGAR`, `CANCELAR` ou `SAIR`; o consentimento é desativado, as respostas psicossociais daquele check-in são removidas e a conversa termina. A recusa inicial também encerra o fluxo sem registrar respostas.

Para rodar os testes do fluxo (sem chamadas à Meta), execute na pasta `backend`:

```powershell
& 'C:\Users\alanb\AppData\Local\Programs\pgAdmin 4\python\python.exe' -m unittest tests.test_whatsapp -v
```

