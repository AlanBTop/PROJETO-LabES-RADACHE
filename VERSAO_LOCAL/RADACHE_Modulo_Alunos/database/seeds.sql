-- =====================================================================
-- PROJETO RADACHE — DADOS DE TESTE (ALUNOS FICTÍCIOS)
-- ARQUIVO: seeds.sql
-- Todos os dados são fictícios em estrita observância à LGPD.
-- =====================================================================

-- Inserção de Alunos Fictícios
INSERT INTO alunos (id, nome, matricula, curso, campus, periodo, email, telefone, status, data_cadastro) VALUES
(1, 'Lucas Silva Santos', '20240182', 'Ciência da Computação', 'Câmpus de Cáceres', 3, 'lucas.santos@unemat.br', '(65) 99812-3401', 'ativo', '2026-02-15 08:30:00'),
(2, 'Camila Martins Rocha', '20250041', 'Direito', 'Câmpus de Cáceres', 1, 'camila.rocha@unemat.br', '(65) 99723-4512', 'ativo', '2026-02-16 09:15:00'),
(3, 'Carlos Eduardo Lima', '20250112', 'Ciência da Computação', 'Câmpus de Cáceres', 1, 'carlos.lima@unemat.br', '(65) 99634-5623', 'ativo', '2026-02-17 10:00:00'),
(4, 'Beatriz Gomes Costa', '20220891', 'Agronomia', 'Câmpus de Cáceres', 7, 'beatriz.costa@unemat.br', '(65) 99545-6734', 'ativo', '2026-02-18 11:20:00'),
(5, 'Amanda Oliveira Faria', '20250019', 'Ciência da Computação', 'Câmpus de Cáceres', 1, 'amanda.faria@unemat.br', '(65) 99456-7845', 'ativo', '2026-02-19 14:00:00'),
(6, 'Mariana Ribeiro Dias', '20230045', 'Pedagogia', 'Câmpus de Cáceres', 5, 'mariana.dias@unemat.br', '(65) 99367-8956', 'ativo', '2026-02-20 15:45:00'),
(7, 'Rodrigo Alves Prado', '20240219', 'Agronomia', 'Câmpus de Cáceres', 3, 'rodrigo.prado@unemat.br', '(65) 99278-9067', 'ativo', '2026-02-21 16:10:00'),
(8, 'João Victor Nogueira', '20240331', 'Enfermagem', 'Câmpus de Cáceres', 3, 'joao.nogueira@unemat.br', '(65) 99189-0178', 'inativo', '2026-02-22 17:00:00');

-- Inserção de Avaliações / Cálculo de Risco
-- Risco calculado por 4 fatores (25% cada): Notas, Frequência, Situação Financeira, Situação Psicológica
INSERT INTO avaliacoes (aluno_id, nota_media, frequencia, situacao_financeira, situacao_psicologica, indice_risco, classificacao_risco, data_avaliacao) VALUES
-- Lucas: Crítico (Notas baixas, frequência crítica, finanças críticas, emocional crítico)
(1, 4.2, 58.0, 'critica', 'critica', 89.0, 'critico', '2026-03-01 10:00:00'),

-- Camila: Crítico (Caloura, choque acadêmico, ansiedade severa e dificuldade financeira)
(2, 5.0, 65.0, 'critica', 'critica', 82.0, 'critico', '2026-03-01 10:15:00'),

-- Carlos: Moderado (Calouro, notas regulares, situação financeira apertada, psicológico moderado)
(3, 6.5, 75.0, 'moderada', 'moderada', 64.0, 'moderado', '2026-03-01 10:30:00'),

-- Beatriz: Moderado (Veterana, desmotivação com o TCC, finanças estáveis)
(4, 7.0, 78.0, 'estavel', 'moderada', 52.0, 'moderado', '2026-03-01 11:00:00'),

-- Amanda: Estável (Excelente frequência, alto rendimento, rede de apoio estruturada)
(5, 8.8, 95.0, 'estavel', 'estavel', 18.0, 'estavel', '2026-03-01 11:30:00'),

-- Mariana: Estável (Bom rendimento, estágio em andamento)
(6, 9.1, 98.0, 'estavel', 'estavel', 14.0, 'estavel', '2026-03-01 12:00:00'),

-- Rodrigo: Moderado (Trabalha no campo, conflito de horários com aulas práticas)
(7, 6.0, 72.0, 'moderada', 'estavel', 48.0, 'moderado', '2026-03-01 14:00:00'),

-- João Victor: Inativo / Trancado provisoriamente
(8, 3.5, 45.0, 'critica', 'critica', 71.0, 'critico', '2026-03-01 15:00:00');

-- Inserção de Check-ins (WhatsApp / IA Conversacional)
INSERT INTO checkins (aluno_id, consentimento_lgpd, resposta_financeira, resposta_psicologica, resposta_academica, data_checkin) VALUES
(1, 1, 'Dificuldade extrema com o custo de transporte intermunicipal até o câmpus.', 'Sensação contínua de esgotamento e desânimo generalizado.', 'Não estou conseguindo acompanhar as matérias de Cálculo e Algoritmos.', '2026-03-01 09:12:00'),
(2, 1, 'Atraso na liberação da bolsa permanência.', 'Nível elevado de estresse e crises de ansiedade na transição para o ensino superior.', 'Adaptação difícil às leituras e à rotina da faculdade.', '2026-03-01 09:25:00'),
(5, 1, 'Finanças sob controle, família reside em Cáceres.', 'Motivada e participando de grupo de iniciação científica.', 'Sem dificuldades para acompanhar o cronograma das disciplinas.', '2026-03-01 09:40:00');
