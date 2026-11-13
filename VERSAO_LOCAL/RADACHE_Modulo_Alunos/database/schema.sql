-- =====================================================================
-- PROJETO RADACHE — SISTEMA DE PREDIÇÃO DE EVASÃO ACADÊMICA (UNEMAT CÁCERES)
-- MÓDULO PROVISÓRIO DE GERENCIAMENTO DE ALUNOS
-- ARQUIVO: schema.sql
-- DIALETO: SQLite 3 (Compatível com PostgreSQL 14+ e MySQL 8+)
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- TABELA 1: alunos
-- Armazena os dados cadastrais mínimos necessários para o MVP.
-- Projetada para ser substituída ou sincronizada futuramente via API do SIGAA.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome VARCHAR(150) NOT NULL,
    matricula VARCHAR(20) NOT NULL UNIQUE,
    curso VARCHAR(100) NOT NULL,
    campus VARCHAR(100) NOT NULL DEFAULT 'Câmpus de Cáceres',
    periodo INTEGER NOT NULL CHECK(periodo BETWEEN 1 AND 16),
    email VARCHAR(120) NOT NULL,
    telefone VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ativo' CHECK(status IN ('ativo', 'inativo', 'formado', 'trancado')),
    status_exclusao INTEGER NOT NULL DEFAULT 0 CHECK(status_exclusao IN (0, 1)),
    data_cadastro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data_atualizacao TIMESTAMP NULL
);

-- Índices para otimização de pesquisas frequentes
CREATE INDEX IF NOT EXISTS idx_alunos_matricula ON alunos(matricula);
CREATE INDEX IF NOT EXISTS idx_alunos_curso ON alunos(curso);
CREATE INDEX IF NOT EXISTS idx_alunos_status ON alunos(status);

-- ---------------------------------------------------------------------
-- TABELA 2: avaliacoes
-- Armazena os indicadores multidimensionais e o cálculo do risco de evasão.
-- Isolada da tabela principal para não sobrecarregar dados cadastrais.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS avaliacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    nota_media REAL CHECK(nota_media >= 0.0 AND nota_media <= 10.0),
    frequencia REAL CHECK(frequencia >= 0.0 AND frequencia <= 100.0),
    situacao_financeira VARCHAR(20) NOT NULL CHECK(situacao_financeira IN ('estavel', 'moderada', 'critica')),
    situacao_psicologica VARCHAR(20) NOT NULL CHECK(situacao_psicologica IN ('estavel', 'moderada', 'critica')),
    indice_risco REAL NOT NULL CHECK(indice_risco >= 0.0 AND indice_risco <= 100.0),
    classificacao_risco VARCHAR(20) NOT NULL CHECK(classificacao_risco IN ('estavel', 'moderado', 'critico')),
    data_avaliacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resposta_financeira TEXT,
    resposta_psicologica TEXT,
    origem_dados TEXT,
    referencia_origem TEXT,
    metadados_risco TEXT,
    FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_avaliacoes_aluno ON avaliacoes(aluno_id);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_classificacao ON avaliacoes(classificacao_risco);

-- ---------------------------------------------------------------------
-- TABELA 3: checkins
-- Registra as respostas coletadas pela IA conversacional via WhatsApp.
-- Inclui controle de consentimento explícito em conformidade com a LGPD (RN02).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    consentimento_lgpd INTEGER NOT NULL DEFAULT 0 CHECK(consentimento_lgpd IN (0, 1)),
    resposta_financeira TEXT,
    resposta_psicologica TEXT,
    resposta_academica TEXT,
    data_checkin TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado_conversa TEXT NOT NULL DEFAULT 'concluido',
    ultima_interacao TIMESTAMP,
    lembrete_enviado INTEGER NOT NULL DEFAULT 0 CHECK(lembrete_enviado IN (0, 1)),
    FOREIGN KEY (aluno_id) REFERENCES alunos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_checkins_aluno ON checkins(aluno_id);

-- Resposta persistida com a transição: reentregas do webhook não avançam a pesquisa.
CREATE TABLE IF NOT EXISTS whatsapp_eventos (
    mensagem_id TEXT PRIMARY KEY,
    origem TEXT NOT NULL,
    resposta TEXT,
    enviado INTEGER NOT NULL DEFAULT 0,
    recebido_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
