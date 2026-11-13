"""Gera o dicionário da instalação local por introspecção SQLite somente leitura."""
from pathlib import Path
from contextlib import closing
from datetime import date
import json
import sqlite3

LOCAL = Path(__file__).resolve().parents[1]
PROJECT = LOCAL.parent
DBDIR = LOCAL / 'RADACHE_Modulo_Alunos/database'
OUT = PROJECT / 'DOCUMENTACAO/tecnica/DICIONARIO_BANCO_DADOS_LOCAL.md'
FILES = {
    'mock_sigaa.db': ('Cadastro acadêmico fictício', 'Cadastro editável da simulação. Configurável por `RADACHE_MOCK_DB`; definido em `simulation_store.py`.'),
    'radache.db': ('Operação da simulação', 'Conversas, avaliações simuladas e chamados associados. Configurável por `RADACHE_SIM_DB`; definido em `simulation_store.py`.'),
    'radache_provisorio.db': ('Cadastro original e administração local', 'Cadastro original, avaliações, check-ins, usuários, equipe e auditoria. Continua em uso. Configurável por `RADACHE_DB`; definido em `database.py`.'),
    'alunos_mock_isolado.db': ('Sandbox anterior', 'Origem da importação única para `mock_sigaa.db`; arquivo anterior preservado. Não é o cadastro editável atual.'),
}
TABLES = {
    'alunos': 'Cadastro dos estudantes; a versão e os campos dependem do arquivo de banco.',
    'migracoes': 'Marcadores de migrações executadas no cadastro fictício. Evita repetir a importação do sandbox anterior.',
    'sessoes': 'Ciclos de conversa do WhatsApp simulado. O estado conversacional é persistido como JSON.',
    'mensagens': 'Histórico de mensagens emitidas pelo sistema e recebidas do aluno na simulação.',
    'avaliacoes_sim': 'Avaliação gerada ao concluir um questionário simulado; uma avaliação por sessão.',
    'comandos': 'Cache de idempotência das ações da simulação: identifica a solicitação e conserva seu resultado.',
    'gestao_chamados': 'Atendimentos e chamados. Os atributos de negócio ficam no JSON `dados`.',
    'gestao_eventos': 'Histórico de eventos dos chamados, como abertura, atribuição e mudanças de situação.',
    'gestao_acoes': 'Cache de idempotência das ações sobre chamados; permite reconhecer repetições da mesma solicitação.',
    'gestao_simulacoes': 'Associa cada sessão simulada ao chamado de acompanhamento correspondente.',
    'povoamento_universidades': 'Controle do lote de estudantes fictícios criado pelo utilitário de povoamento; permite reconhecer os registros gerados.',
    'avaliacoes': 'Histórico de avaliações do cadastro original, incluindo índice, classificação, respostas e evidências do cálculo.',
    'checkins': 'Check-ins do cadastro original, com respostas, consentimento e estado da conversa.',
    'campus': 'Catálogo dos câmpus usados no controle de acesso institucional.',
    'campus_cursos': 'Oferta de cursos por câmpus, materializada a partir dos cadastros locais.',
    'atendentes_vinculos': 'Histórico dos vínculos do atendente com cursos do seu câmpus. Um vínculo atual tem `fim IS NULL`.',
    'funcionarios_transferencias': 'Registro de transferências de funcionários entre câmpus, com detalhes em JSON.',
    'gestao_equipe_auditoria': 'Auditoria de alterações de funcionários, incluindo os estados anterior e posterior.',
    'gestao_usuarios': 'Contas da gestão local, escopo de acesso e credenciais derivadas por hash.',
    'gestao_meta': 'Marcadores de inicialização e migração da gestão local.',
    'institucional_auditoria': 'Auditoria das consultas ao observatório institucional, com filtros e código HTTP do resultado.',
    'whatsapp_eventos': 'Registro de eventos recebidos pela integração de WhatsApp do módulo original; controla resposta e envio.',
    'alunos_mock': 'Cadastro restrito do sandbox anterior, usado como origem da migração para o cadastro fictício atual.',
}
FIELDS = {
    'id': 'Identificador do registro.', 'nome': 'Nome do estudante, usuário, câmpus ou curso, conforme a tabela.',
    'matricula': 'Matrícula acadêmica; identifica o estudante no cadastro.', 'curso': 'Nome do curso; normalizado pelo catálogo na aplicação.',
    'periodo': 'Período curricular do estudante.', 'status': 'Situação do vínculo acadêmico.',
    'campus': 'Nome do câmpus do estudante.', 'email': 'Endereço de e-mail.', 'telefone': 'Telefone de contato.',
    'nota_media': 'Média acadêmica, na escala de 0 a 10.', 'frequencia': 'Percentual de frequência, de 0 a 100.',
    'data_cadastro': 'Data e hora de criação do cadastro.', 'data_atualizacao': 'Data e hora da última atualização cadastral.',
    'status_exclusao': 'Indicador de exclusão lógica: 0 conserva o cadastro visível; 1 o oculta nas consultas usuais.',
    'aluno_id': 'Identificador do estudante relacionado. No banco operacional usa a convenção de sinais descrita neste documento.',
    'sessao_id': 'Identificador da sessão de conversa simulada.', 'estado': 'JSON com o estado da máquina de conversa.',
    'criado_em': 'Data e hora de criação do registro.', 'remetente': 'Origem da mensagem: `aluno` ou `sistema` na simulação.',
    'conteudo': 'Texto da mensagem.', 'timestamp': 'Data e hora da mensagem na linha de tempo simulada.',
    'pergunta': 'Etapa/pergunta da conversa associada à mensagem.', 'sensivel': 'Indicador de conteúdo sensível; a simulação usa 0 ou 1.',
    'dados': 'Objeto JSON com os atributos de negócio da entidade.',
    'assinatura': 'Representação serializada da solicitação, comparada para impedir reutilização da mesma chave com outra ação; não é assinatura criptográfica.',
    'resultado': 'Resultado persistido da operação, normalmente JSON, usado na idempotência.',
    'chamado_id': 'Identificador do chamado associado.', 'versao': 'Versão do lote de povoamento.',
    'situacao_financeira': 'Categoria financeira: `estavel`, `moderada` ou `critica`.',
    'situacao_psicologica': 'Categoria psicológica: `estavel`, `moderada` ou `critica`.',
    'indice_risco': 'Pontuação de acompanhamento, de 0 a 100; não é probabilidade validada de evasão.',
    'classificacao_risco': 'Classificação do índice: `estavel`, `moderado` ou `critico`.',
    'data_avaliacao': 'Data e hora de referência da avaliação.',
    'resposta_financeira': 'Resposta fornecida ao questionário financeiro.',
    'resposta_psicologica': 'Resposta de bem-estar emocional; no fluxo de cálculo usa a escala de 1 a 5.',
    'resposta_academica': 'Resposta acadêmica do check-in original.',
    'origem_dados': 'Identificação da fonte que originou a avaliação.', 'referencia_origem': 'Chave do registro de origem; participa do controle de duplicidade.',
    'metadados_risco': 'JSON de evidências, componentes, pesos e comparação histórica do cálculo.',
    'consentimento_lgpd': 'Indicador de consentimento do check-in: 0 ou 1. O padrão físico está indicado na coluna Padrão.',
    'data_checkin': 'Data e hora de registro do check-in.', 'estado_conversa': 'Etapa da conversa do módulo original.',
    'ultima_interacao': 'Data e hora da interação mais recente.', 'lembrete_enviado': 'Indicador de lembrete já emitido no fluxo.',
    'campus_id': 'Identificador textual do câmpus.', 'curso_id': 'Identificador textual do curso no catálogo.',
    'usuario_id': 'Identificador do usuário envolvido na ação ou vínculo.', 'inicio': 'Data e hora de início do vínculo.',
    'fim': 'Data e hora de encerramento do vínculo; NULL indica vínculo atual.',
    'autor_id': 'Identificador do autor da operação; pode conter um marcador técnico como `migracao`.',
    'origem': 'Câmpus de origem da transferência.', 'destino': 'Câmpus de destino da transferência.',
    'data': 'Data e hora da ação auditada.', 'antes': 'JSON do estado anterior; pode ser NULL em uma criação.',
    'depois': 'JSON do estado posterior à alteração.', 'chave': 'Nome do marcador técnico de inicialização/migração.',
    'salt': 'Salt individual usado na derivação da credencial; não é a senha.',
    'password_hash': 'Hash derivado da senha com PBKDF2-HMAC-SHA256, conforme `auth.py`.',
    'perfil': 'Perfil de acesso do usuário que realizou a consulta.', 'recurso': 'Caminho do recurso consultado, sem a query string.',
    'filtros': 'JSON dos filtros permitidos usados na consulta institucional.',
    'mensagem_id': 'Identificador da mensagem externa; usado para reconhecer eventos repetidos.',
    'resposta': 'Resposta associada ao evento de WhatsApp.', 'enviado': 'Indicador de envio da resposta.',
    'recebido_em': 'Data e hora em que o evento foi recebido.',
}
OVERRIDES = {
    ('migracoes', 'nome'): 'Nome único da migração aplicada, como `sandbox-anterior`.',
    ('institucional_auditoria', 'resultado'): 'Código HTTP do resultado da consulta, armazenado como inteiro.',
    ('whatsapp_eventos', 'origem'): 'Origem do evento recebido pela integração de WhatsApp.',
    ('campus', 'nome'): 'Nome de exibição do câmpus.',
    ('campus_cursos', 'nome'): 'Nome de exibição do curso oferecido no câmpus.',
}

INTRO = '''# Dicionário de dados — RADACHE, versão local

## 1. Escopo e origem

Este documento descreve os arquivos SQLite presentes em `VERSAO_LOCAL/RADACHE_Modulo_Alunos/database/`.
O esquema físico foi lido diretamente de `sqlite_master` e dos PRAGMAs de colunas, chaves estrangeiras e índices, sem executar migrações ou alterar dados.
As descrições funcionais foram conferidas no código da versão local. Não inclui os bancos PostgreSQL ou Firebase das outras versões, nem cópias da pasta ARQUIVO.

Os nomes e as estruturas abaixo pertencem aos arquivos padrão desta instalação. Se forem usadas variáveis de ambiente para apontar para outros bancos, o esquema desses arquivos deve ser conferido separadamente.

### Como ler o dicionário

- **PK**: chave primária; em chaves compostas, o número indica a posição do campo.
- **FK**: chave estrangeira declarada no SQLite. As referências apenas lógicas são indicadas separadamente.
- **NOT NULL**: reproduz a restrição explícita retornada pelo SQLite, sem inferir obrigatoriedade das regras da aplicação.
- **Padrão**: expressão SQL de `DEFAULT`; “sem DEFAULT” é diferente de uma string vazia.
- **TEXT/JSON**: JSON é serializado em colunas TEXT; não existem colunas físicas para cada propriedade interna.

No SQLite, `INTEGER PRIMARY KEY` funciona como identificador do rowid e pode ser preenchido automaticamente. Uma PK TEXT de tabela comum não implica necessariamente NOT NULL: prevalece a definição SQL apresentada.
Os tipos VARCHAR e TIMESTAMP são declarações SQLite, sem impor por si só comprimento máximo ou validação de data. Restrições CHECK, UNIQUE e COLLATE aparecem no DDL de cada tabela.
As tabelas internas `sqlite_sequence` e os índices automáticos são tratados como objetos técnicos, fora do inventário de tabelas de negócio.

## 2. Arquivos e responsabilidades

'''

RELATIONS = '''## 3. Relacionamentos e convenções

### Cadastro original e gestão — radache_provisorio.db

```mermaid
erDiagram
    alunos ||--o{ avaliacoes : possui
    alunos ||--o{ checkins : responde
    alunos o|--o{ gestao_chamados : associado
    gestao_chamados o|--o{ gestao_eventos : registra
    campus ||--o{ campus_cursos : oferece
    campus_cursos ||--o{ atendentes_vinculos : recebe
    gestao_usuarios ||--o{ atendentes_vinculos : possui
    gestao_usuarios ||--o{ funcionarios_transferencias : registra
    campus ||--o{ funcionarios_transferencias : origem_destino
```

### Operação da simulação — radache.db

```mermaid
erDiagram
    sessoes ||--o{ mensagens : contem
    sessoes ||--o| avaliacoes_sim : produz
    gestao_chamados o|--o{ gestao_eventos : registra
    gestao_chamados ||--o{ gestao_simulacoes : agrupa
```

Os diagramas mostram as referências físicas e sua cardinalidade usual; as seções de cada tabela detalham a nulabilidade real.
`gestao_simulacoes.sessao_id`, `gestao_acoes.chamado_id` e os campos de auditoria de usuário não possuem FK declarada apenas por terem nomes relacionados.

### Referências entre arquivos e sinais de aluno_id

O SQLite destes arquivos não declara FKs entre bancos. A aplicação resolve as referências:

| Contexto | ID positivo | ID negativo |
|---|---|---|
| Campos `aluno_id` de radache.db e entrada da conversa simulada | `mock_sigaa.db.alunos.id` | Módulo original: `radache_provisorio.db.alunos.id = -aluno_id` |
| IDs unificados de alunos na análise e no JSON `alunoId` dos chamados simulados | Cadastro original | Cadastro fictício: `mock_sigaa.db.alunos.id = -alunoId` |

Assim, um ID de estudante da simulação muda de sinal ao entrar na visão unificada de gestão/análise. Não faça JOIN direto usando o mesmo sinal em todos os contextos. As implementações estão em `simulation_store.conversation_student`, `simulation_followup.sync` e `analytics.source`.
O campo `povoamento_universidades.aluno_id` aponta logicamente para o cadastro fictício positivo.

As tabelas `alunos`, `gestao_chamados`, `gestao_eventos` e `gestao_acoes` podem ter nomes repetidos em arquivos diferentes. Sempre indique o arquivo ao referenciar uma delas.

## 4. Tabelas e campos físicos

'''

JSON_DOC = '''## 5. Conteúdo dos campos JSON

As propriedades abaixo pertencem a objetos serializados; não são colunas adicionais do SQLite.
Campos opcionais dependem do fluxo e podem não existir em registros antigos. A presença de JSON válido e a estrutura interna são controladas pela aplicação; o DDL não declara CHECK(json_valid(...)) nessas colunas.

### Usuário — gestao_usuarios.dados

| Propriedade | Tipo JSON usual | Significado |
|---|---|---|
| id / uid | string | Identificação da conta; uid pode aparecer em objetos associados à sessão |
| nome / email / login | string | Identificação e acesso do funcionário |
| perfil | string | Papel de acesso, como admin_tecnico, analista_institucional, diretor_campus, gestor_curso e atendente_academico |
| campusId | string | Câmpus de lotação; o escopo global pode usar string vazia |
| cursoId | string | Curso principal ou compatibilidade com cadastros anteriores |
| cursoIds | array de strings | Cursos atribuídos à conta |
| ativo | boolean | Situação de acesso |
| versaoAcesso | number inteiro | Versão usada no controle de mudanças de acesso |
| criadoEm / ultimoAcessoEm | string | Instantes de criação e acesso; último acesso é opcional |

Os campos `antes` e `depois` da auditoria de equipe guardam snapshots do objeto de usuário. Salt e hash são colunas próprias da tabela de contas.

### Chamado — gestao_chamados.dados, nos dois bancos

| Propriedade | Tipo JSON usual | Significado |
|---|---|---|
| id / protocolo | string | Identificadores interno e de apresentação |
| alunoId | string | Identificação do aluno na gestão; observar a convenção de sinais |
| cursoId | string | Curso associado ao chamado |
| titulo / descricao | string | Assunto e descrição do atendimento |
| status | string | Etapa do atendimento |
| categoria | string | academico, financeiro, ti ou outro |
| responsavel | object ou null | Responsável atribuído; uid identifica a conta |
| abertoEm / ultimaAtividadeEm | string | Instantes de abertura e atividade mais recente |
| aguardandoAlunoEm | string opcional | Instante de entrada na espera de resposta |
| resolvidoEm / encerradoPor | string ou null | Instante de resolução e identificação de quem encerrou |
| tempoResolucaoMin | number ou null | Duração registrada até a resolução, em minutos |
| reaberturas | number inteiro opcional | Quantidade de reaberturas |
| origem | string opcional | Fonte do chamado; a simulação usa whatsapp_simulado |
| demonstracao | boolean opcional | Marcador acrescentado por utilitários de demonstração |

Propriedades como `alunoNome`, `matricula`, `questionarios` e `consentimentoRevogado` também podem aparecer na resposta da API por enriquecimento em leitura. Isso não significa que sejam sempre persistidas em `dados`.

### Evento — gestao_eventos.dados

| Propriedade | Tipo JSON usual | Significado |
|---|---|---|
| id / tipo / texto | string | Identificador, natureza e descrição do evento |
| criadoEm | string | Instante do evento |
| autor | object | Identificação de quem registrou a ação |
| visivelAoAluno | boolean | Controle de visibilidade do evento |
| sessaoId | string opcional | Sessão de questionário que originou o evento |
| motivo | string opcional | Justificativa da ação |
| novoResponsavel / responsavelAnterior | object opcional | Responsáveis envolvidos numa atribuição/transferência |

### Conversa — sessoes.estado

| Propriedade | Tipo JSON usual | Significado |
|---|---|---|
| timestamp | string | Relógio da simulação, que pode avançar independentemente da data real |
| diaCalendario | number inteiro | Dia de referência para avanço de meses |
| etapa | string | consentimento, aguardando_inicio, financeira, emocional, concluido, recusado ou revogado |
| consentimento | boolean | Consentimento registrado no ciclo |
| dataConsentimento | string ou null | Instante da autorização |
| financeira | number inteiro ou null | Resposta de 1 a 4 |
| emocional | number inteiro ou null | Resposta de 1 a 5 |
| concluidoMes | string ou null | Mês já concluído, no formato AAAA-MM |
| ultimaInteracao | string | Instante da interação mais recente |
| lembreteEnviado | boolean | Indica emissão de lembrete no ciclo |
| demonstracao | boolean opcional | Marcador de registro preparado para demonstração |

`validadeConsentimento`, `consentimentoExpirado`, `F` e `P` são calculados por `snapshot()` ao responder à API e não precisam estar gravados no JSON da sessão.

### Avaliação simulada — avaliacoes_sim.dados

| Propriedade | Tipo JSON usual | Significado |
|---|---|---|
| data_avaliacao | string | Data de referência no relógio da simulação |
| nota_media / frequencia | number ou null | Evidências acadêmicas utilizadas |
| resposta_financeira | string | Texto da resposta financeira |
| resposta_psicologica | number inteiro | Resposta emocional de 1 a 5 |
| situacao_financeira / situacao_psicologica | string | Categorias estavel, moderada ou critica |
| indice_risco | number ou null | Índice calculado quando existem média e frequência |
| classificacao_risco | string ou null | estavel, moderado ou critico |
| limitacao | string opcional | Explicação da ausência de índice por dados acadêmicos incompletos |
| metadados_risco | object | Evidências e comparação histórica do cálculo |
| demonstracao | boolean opcional | Marcador de dados preparados para demonstração |

### Evidências — avaliacoes.metadados_risco e avaliacoes_sim.dados.metadados_risco

| Propriedade | Tipo JSON usual | Significado |
|---|---|---|
| origem / referencia / versao_formula | string | Rastreabilidade da avaliação e da fórmula |
| pesos | object | Pesos de notas, frequencia, financeiro e psicologico |
| componentes | object | Para cada componente disponível: nome, valor e risco |
| indice_anterior | number ou null | Índice da avaliação anterior comparável |
| variacao_pontos | number ou null | Diferença entre o índice atual e o anterior |
| direcao | string | sem_avaliacao, inicial, aumentou, diminuiu ou estavel |
| fatores | array de objects | Componentes que mudaram, valores anteriores/atuais e contribuições |
| comparacao_completa | boolean | Indica disponibilidade das quatro evidências e pesos nas duas avaliações |
| pesos_alterados | boolean | Indica mudança dos pesos entre avaliações |

### Caches, filtros e transferências

- `comandos.assinatura`: solicitação de simulação serializada, com chaves ordenadas; `resultado`: objeto com sessao_id, estado e mensagens.
- `gestao_acoes.assinatura`: descrição serializada da ação; `resultado`: snapshot do retorno do atendimento. A existência da coluna não significa haver FK para o chamado.
- `institucional_auditoria.filtros`: filtros permitidos, como campus, curso, periodo, inicio, fim e risco.
- `funcionarios_transferencias.dados`: contrato descrito a seguir, implementado em `staff.py`.

### Transferência — funcionarios_transferencias.dados

| Propriedade | Tipo JSON usual | Significado |
|---|---|---|
| id / usuarioId / nome | string | Identificação da transferência e do funcionário |
| origem / destino | string | IDs dos câmpus envolvidos |
| cursoIds | array de strings | Cursos atribuídos no destino |
| motivo | string | Justificativa da transferência |
| criadoEm / solicitadoPor | string | Instante e autor da solicitação |
| status | string | Situação da solicitação, iniciada como pendente |
| autorizacoes | object | Aprovações por câmpus, com uid e data |
| redistribuicoes | object | Plano de redistribuição dos atendimentos |
| versaoOrigem | number inteiro | Versão de acesso usada para detectar alterações posteriores |

## 6. Regras de domínio e integridade

| Tema | Regra e camada responsável |
|---|---|
| Matrícula fictícia | UNIQUE e COLLATE NOCASE em mock_sigaa.db; unicidade sem distinguir maiúsculas/minúsculas conforme a collation do SQLite |
| Situação acadêmica original | CHECK permite ativo, inativo, formado e trancado; no cadastro fictício o DDL usa TEXT sem CHECK equivalente |
| Índice de risco | `risk.py`: estavel se índice <= 33; moderado se 33 < índice < 67; critico se índice >= 67 |
| Painel analítico | Converte estavel/moderado/critico em baixo/medio/alto; sem_avaliacao identifica ausência de índice válido |
| Atendimento | `attendance.TRANSITIONS` controla aberto, em_andamento, aguardando_aluno, resolvido, encerrado e reaberto dentro do JSON |
| Vínculo atual | Índice único parcial em (usuario_id, curso_id), apenas onde fim IS NULL |
| Lotação | Triggers verificam compatibilidade de câmpus e cursos para atendentes |
| Avaliação por origem | Índice único parcial em (origem_dados, referencia_origem), quando referencia_origem não é NULL |
| Exclusão original | status_exclusao permite ocultação lógica; as FKs indicadas com CASCADE tratam exclusão física |
| Consentimento | O fluxo simulado inicia sem consentimento e exige resposta. O DEFAULT físico 1 de checkins pertence à estrutura original e não descreve a regra de início da simulação |
| Revogação simulada | simulation_store limpa respostas sensíveis, avaliações e cache de comandos conforme o fluxo; é regra da aplicação |
| Datas | O SQL usa CURRENT_TIMESTAMP em alguns campos; o código também grava ISO 8601 em UTC. A simulação possui relógio próprio |
| JSON | Tipos, perfis, transições e muitos limites são validados pelo Python; não devem ser confundidos com CHECKs do SQLite |
| Sessões de acesso | Tokens de autenticação da gestão são mantidos em memória. A tabela sessoes de radache.db contém conversas simuladas, não logins |
| Integridade referencial | As conexões de escrita dos módulos database.py e simulation_store.py ativam PRAGMA foreign_keys=ON; essa configuração é por conexão |

Não há tabela física de indicadores do observatório: `analytics.py` e `institutional.py` constroem resultados de leitura a partir dos cadastros, avaliações e atendimentos.
O catálogo de cursos também possui regras em `course_catalog.py`; `campus_cursos` materializa os vínculos utilizados pela equipe.

## 7. Fontes e atualização

O arquivo schema.sql cobre o esquema base do módulo original. Ele não descreve sozinho todas as tabelas e migrações presentes nesta instalação.

'''

def esc(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')

def quote(value):
    return '"' + value.replace('"', '""') + '"'

def schema(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as c:
        c.execute('BEGIN')
        result = []
        for name, ddl in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            columns = c.execute('PRAGMA table_info(' + quote(name) + ')').fetchall()
            for col in columns:
                assert (name, col[1]) in OVERRIDES or col[1] in FIELDS, (name, col[1])
            result.append(dict(name=name, ddl=ddl, columns=columns,
                fks=c.execute('PRAGMA foreign_key_list(' + quote(name) + ')').fetchall(),
                indices=c.execute('PRAGMA index_list(' + quote(name) + ')').fetchall()))
        objects = c.execute("SELECT type,name,sql FROM sqlite_master WHERE type IN ('index','trigger','view') AND sql IS NOT NULL ORDER BY type,name").fetchall()
        return result, objects

def main():
    all_schemas = {name: schema(DBDIR / name) for name in FILES}
    count = sum(len(tables) for tables, _ in all_schemas.values())
    fields = sum(len(t['columns']) for tables, _ in all_schemas.values() for t in tables)
    output = [INTRO, f'Inspeção: **{date.today().isoformat()}**. Inventário: **{len(FILES)} arquivos, {count} tabelas de aplicação e {fields} colunas físicas**. Nomes repetidos em bancos diferentes são contados separadamente.\n\n',
        '| Arquivo | Função | Tabelas de aplicação |\n|---|---|---|\n']
    for name, (title, _) in FILES.items():
        output.append(f'| `{name}` | {title} | {len(all_schemas[name][0])} |\n')
    output.append('\n')
    for name, (_, desc) in FILES.items():
        output.append(f'- **{name}**: {desc}\n')
    output.extend(['\n', RELATIONS])
    for number, (file, (tables, objects)) in enumerate(all_schemas.items(), 1):
        output.append(f'### 4.{number}. {file}\n\n')
        output.append('| Tabela | Finalidade |\n|---|---|\n')
        for table in tables:
            output.append(f'| `{table["name"]}` | {TABLES[table["name"]]} |\n')
        output.append('\n')
        for i, table in enumerate(tables, 1):
            name = table['name']
            output.append(f'#### 4.{number}.{i}. `{name}`\n\n{TABLES[name]}\n\n')
            output.append('| Campo | Tipo SQLite | PK | NOT NULL explícito | Padrão SQL | Descrição |\n|---|---|---|---|---|---|\n')
            for _, col, typ, nn, default, pk in table['columns']:
                desc = OVERRIDES.get((name, col), FIELDS.get(col))
                output.append(f'| `{col}` | `{typ}` | {pk or "—"} | {"Sim" if nn else "Não"} | {"`" + esc(default) + "`" if default is not None else "sem DEFAULT"} | {desc} |\n')
            output.append('\n**Chaves estrangeiras declaradas**\n\n')
            if table['fks']:
                output.append('| Grupo FK | Origem | Destino no mesmo arquivo | ON UPDATE | ON DELETE |\n|---|---|---|---|---|\n')
                for ident, seq, target, src, dst, update, delete, match in table['fks']:
                    output.append(f'| {ident} | `{src}` | `{target}.{dst}` | {update} | {delete} |\n')
                output.append('\nLinhas do mesmo grupo FK compõem uma única referência, inclusive em chaves compostas.\n')
            else:
                output.append('Nenhuma FK física declarada. Referências funcionais podem ser resolvidas pelo código.\n')
            output.append('\n**DDL efetivo, incluindo restrições**\n\n```sql\n' + table['ddl'].rstrip(';') + ';\n```\n\n')
        output.append(f'#### Objetos auxiliares de {file}\n\n')
        if objects:
            output.append('Índices e triggers definidos explicitamente nesta instalação:\n\n```sql\n')
            for _, _, sql in objects:
                output.append(sql.rstrip(';') + ';\n\n')
            output.append('```\n\n')
        else:
            output.append('Nenhum índice explícito, trigger ou view encontrado. As restrições PK/UNIQUE podem criar índices automáticos.\n\n')
        auto = [(t['name'], ix[1]) for t in tables for ix in t['indices'] if ix[1].startswith('sqlite_autoindex_')]
        if auto:
            output.append('Índices automáticos observados para PK/UNIQUE:\n\n')
            for table, index in auto:
                output.append(f'- `{index}` em `{table}`.\n')
            output.append('\n')
    output.extend([JSON_DOC])
    sources = ('simulation_store.py', 'simulation_followup.py', 'database.py', 'gestao_local.py', 'staff.py', 'attendance.py', 'institution_accounts.py', 'rbac.py', 'risk.py', 'risk_history.py', 'analytics.py', 'institutional.py', 'auth.py', 'course_catalog.py')
    for source in sources:
        output.append(f'- [{source}](../../VERSAO_LOCAL/RADACHE_Modulo_Alunos/backend/{source})\n')
    output.append('\n- [schema.sql](../../VERSAO_LOCAL/RADACHE_Modulo_Alunos/database/schema.sql)\n')
    output.append('- [Gerador deste dicionário](../../VERSAO_LOCAL/scripts/documentar_banco.py)\n')
    output.append('''
Para atualizar o inventário físico, execute na raiz do projeto:

```powershell
python VERSAO_LOCAL/scripts/documentar_banco.py
```

O gerador usa os quatro arquivos padrão, abre os bancos com `mode=ro` e lê somente metadados do esquema. Não exporta estudantes, mensagens, senhas, hashes ou outros valores das linhas.
As descrições de negócio e os contratos JSON precisam acompanhar mudanças no código. Cada arquivo é inspecionado em uma transação de leitura própria; o documento não é uma cópia transacional conjunta dos bancos.
''')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(''.join(output), encoding='utf-8')
    print(f'Documentado: {len(FILES)} bancos, {count} tabelas, {fields} colunas.')
    print(OUT)

if __name__ == '__main__':
    main()
