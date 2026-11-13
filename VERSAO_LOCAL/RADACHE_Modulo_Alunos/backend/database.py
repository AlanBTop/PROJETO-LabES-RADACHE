"""
========================================================================================
RADACHE — Módulo de Gerenciamento de Alunos
Arquivo: database.py
Camada: Persistência de Dados e Acesso ao Banco Relacional SQLite
========================================================================================

ARQUITETURA DO BANCO DE DADOS (Conceito de Engenharia):
O RADACHE foi modelado com três entidades normalizadas para evitar tabelas monolíticas:
1. 'alunos'    : Armazena dados cadastrais estáticos (nome, matrícula, curso, status).
2. 'avaliacoes': Armazena os registros temporais de predição de risco de evasão (1:N com alunos).
3. 'checkins'  : Armazena as interações mensais do WhatsApp e flags de consentimento LGPD (1:N com alunos).

PRINCÍPIOS TÉCNICOS APLICADOS:
- Portabilidade: SQLite nativo sem drivers externos (portável diretamente para PostgreSQL ou MySQL).
- Integridade Referencial: 'PRAGMA foreign_keys = ON' ativado obrigatoriamente em cada conexão.
- Migrações Idempotentes: 'init_db' aplica 'schema.sql' e verifica automaticamente novas colunas
  (ex: 'status_exclusao', 'estado_conversa') sem perder registros de demonstrações anteriores.
- Exclusão Lógica: 'status_exclusao = 1' oculta registros sem romper a integridade histórica.
- Recálculo Automático: Ao completar um check-in válido e consentido, o sistema aciona o motor
  de risco ('risk.py') e atualiza a última avaliação do discente em tempo real.
"""

import sqlite3
import json
from datetime import datetime, timezone
import risk_history
from contextlib import closing
import os
from pathlib import Path
from risk import calcular_indice_risco, classificar_risco

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("RADACHE_DB", str(BASE_DIR / "database" / "radache_provisorio.db")))
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
SEEDS_PATH = BASE_DIR / "database" / "seeds.sql"


def get_connection():
    """
    Cria e retorna uma conexão ativa com o banco SQLite.
    
    Configurações essenciais:
    - row_factory = sqlite3.Row: Permite acessar colunas por nome como um dicionário (ex: row['nome']).
    - PRAGMA foreign_keys = ON: Garante imposição de integridade referencial nas FKs.
    """
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(force_reseed=False):
    """
    Inicializa o banco de dados criando as tabelas estruturais e aplicando migrações.
    Se a tabela 'alunos' estiver vazia (ou se force_reseed=True), injeta os 8 alunos fictícios de teste.
    """
    db_exists = DB_PATH.exists()
    conn = get_connection()
    cursor = conn.cursor()

    # Executa o DDL base (CREATE TABLE IF NOT EXISTS)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())

    # Migração idempotente: Adiciona coluna de exclusão lógica se não existir
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(alunos)").fetchall()}
    if "status_exclusao" not in columns:
        cursor.execute("ALTER TABLE alunos ADD COLUMN status_exclusao INTEGER NOT NULL DEFAULT 0")

    # Migração idempotente: Garante campos de estado conversacional do WhatsApp
    migrate_checkin_conversation(cursor)
    migrate_risk_history(cursor)

    # Verifica se há necessidade de carregar os discentes de teste (Seed)
    cursor.execute("SELECT COUNT(*) AS total FROM alunos")
    count = cursor.fetchone()["total"]

    if (not db_exists and count == 0) or force_reseed:
        with open(SEEDS_PATH, "r", encoding="utf-8") as f:
            cursor.executescript(f.read())
        print("[RADACHE] Banco provisório inicializado com sucesso e dados de teste carregados.")
    else:
        print("[RADACHE] Banco provisório já existente conectado.")

    conn.commit()
    conn.close()
    
    # Sincroniza classes legadas para obedecer às regras vigentes da Sprint 2
    reclassificar_avaliacoes()


def migrate_risk_history(cursor):
    columns={r['name'] for r in cursor.execute('PRAGMA table_info(avaliacoes)').fetchall()}
    for name in ('resposta_financeira','resposta_psicologica','origem_dados','referencia_origem','metadados_risco'):
        if name not in columns:
            cursor.execute('ALTER TABLE avaliacoes ADD COLUMN '+name+' TEXT')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS avaliacao_por_origem ON avaliacoes(origem_dados,referencia_origem) WHERE referencia_origem IS NOT NULL')


def migrate_checkin_conversation(cursor):
    """
    Adiciona colunas da máquina de estados conversacional do WhatsApp sem apagar check-ins existentes.
    """
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(checkins)").fetchall()}
    if "estado_conversa" not in columns:
        cursor.execute("ALTER TABLE checkins ADD COLUMN estado_conversa TEXT NOT NULL DEFAULT 'concluido'")
    if "ultima_interacao" not in columns:
        cursor.execute("ALTER TABLE checkins ADD COLUMN ultima_interacao TIMESTAMP")
        cursor.execute("UPDATE checkins SET ultima_interacao = data_checkin WHERE ultima_interacao IS NULL")
    if "lembrete_enviado" not in columns:
        cursor.execute("ALTER TABLE checkins ADD COLUMN lembrete_enviado INTEGER NOT NULL DEFAULT 0")


def reclassificar_avaliacoes():
    """
    Garante que todas as avaliações no banco tenham a classificação ('estavel', 'moderado', 'critico')
    perfeitamente alinhada com o índice_risco numérico registrado.
    """
    conn = get_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT id, indice_risco FROM avaliacoes").fetchall()
    for row in rows:
        cursor.execute(
            "UPDATE avaliacoes SET classificacao_risco = ? WHERE id = ?",
            (classificar_risco(row["indice_risco"]), row["id"]),
        )
    conn.commit()
    conn.close()
    return len(rows)


def recalcular_avaliacao_por_checkin(checkin_id, conn=None):
    """
    Recalcula o Índice de Risco de Evasão (RE) de um estudante após a conclusão de um check-in mensal.
    
    Regras de Segurança e LGPD:
    1. O check-in DEVE possuir consentimento_lgpd = 1 ativo.
    2. Respostas financeira e psicológica devem estar completamente preenchidas.
    3. Busca a avaliação mais recente com nota e frequência e aplica a fórmula ponderada de 'risk.py'.
    4. Acrescenta uma avaliação imutável por check-in, preservando as anteriores.
    """
    if conn is None:
        with closing(get_connection()) as nova_conn, nova_conn:
            return recalcular_avaliacao_por_checkin(checkin_id, nova_conn)
    cursor = conn.cursor()
    checkin = cursor.execute(
        """SELECT aluno_id, consentimento_lgpd, resposta_financeira, resposta_psicologica
           FROM checkins WHERE id = ?""",
        (checkin_id,),
    ).fetchone()
    if not checkin:
        raise ValueError("Check-in não encontrado.")
    if checkin["consentimento_lgpd"] != 1:
        raise ValueError("Não é permitido processar check-in sem consentimento ativo.")
    if not checkin["resposta_financeira"] or not checkin["resposta_psicologica"]:
        raise ValueError("O check-in precisa estar completo para recalcular o risco.")

    migrate_risk_history(cursor)
    existing=cursor.execute("SELECT indice_risco FROM avaliacoes WHERE origem_dados='whatsapp_checkin' AND referencia_origem=?",(str(checkin_id),)).fetchone()
    if existing:
        return existing['indice_risco']

    avaliacao = cursor.execute(
        """SELECT * FROM avaliacoes
           WHERE aluno_id = ? ORDER BY id DESC LIMIT 1""",
        (checkin["aluno_id"],),
    ).fetchone()
    if not avaliacao or avaliacao["nota_media"] is None or avaliacao["frequencia"] is None:
        raise ValueError("É necessária uma avaliação com média e frequência para calcular o risco.")

    # Executa o cálculo ponderado das 4 dimensões
    indice = calcular_indice_risco(
        avaliacao["nota_media"], avaliacao["frequencia"],
        checkin["resposta_financeira"], checkin["resposta_psicologica"],
    )
    from risk import calcular_financeiro, calcular_psicologico
    def situacao(valor):
        return "estavel" if valor <= 33 else "moderada" if valor < 67 else "critica"
    evaluation=dict(aluno_id=checkin['aluno_id'],nota_media=avaliacao['nota_media'],frequencia=avaliacao['frequencia'],
        indice_risco=indice,classificacao_risco=classificar_risco(indice),
        situacao_financeira=situacao(calcular_financeiro(checkin['resposta_financeira'])),
        situacao_psicologica=situacao(calcular_psicologico(checkin['resposta_psicologica'])),
        resposta_financeira=checkin['resposta_financeira'],resposta_psicologica=checkin['resposta_psicologica'],
        data_avaliacao=datetime.now(timezone.utc).isoformat(),origem_dados='whatsapp_checkin',referencia_origem=str(checkin_id))
    evaluation['metadados_risco']=json.dumps(risk_history.snapshot(evaluation,dict(avaliacao),'whatsapp_checkin',checkin_id),ensure_ascii=False)
    fields=list(evaluation)
    cursor.execute('INSERT INTO avaliacoes ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',[evaluation[k] for k in fields])
    return indice


def get_dashboard_metrics():
    """
    Calcula de forma consolidada e analítica as métricas-chave (KPIs) exibidas no topo do painel:
    - total_alunos   : Total de discentes visíveis (status_exclusao = 0).
    - alunos_ativos  : Total com matrícula ativa na instituição.
    - alunos_criticos: Estudantes com risco de evasão >= 67% (Alerta Vermelho).
    - alunos_moderados: Estudantes com risco entre 34% e 66% (Alerta Amarelo).
    - alunos_estaveis: Estudantes com risco <= 33% (Verde).
    
    A consulta utiliza subquery analítica para buscar apenas a avaliação mais recente de cada aluno.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT
        COUNT(DISTINCT CASE WHEN a.status_exclusao = 0 THEN a.id END) AS total_alunos,
        SUM(CASE WHEN a.status_exclusao = 0 AND a.status = 'ativo' THEN 1 ELSE 0 END) AS alunos_ativos,
        SUM(CASE WHEN a.status_exclusao = 0 AND av.classificacao_risco = 'critico' AND a.status = 'ativo' THEN 1 ELSE 0 END) AS alunos_criticos,
        SUM(CASE WHEN a.status_exclusao = 0 AND av.classificacao_risco = 'moderado' AND a.status = 'ativo' THEN 1 ELSE 0 END) AS alunos_moderados,
        SUM(CASE WHEN a.status_exclusao = 0 AND av.classificacao_risco = 'estavel' AND a.status = 'ativo' THEN 1 ELSE 0 END) AS alunos_estaveis
    FROM alunos a
    LEFT JOIN (
        SELECT aluno_id, classificacao_risco
        FROM avaliacoes
        WHERE id IN (SELECT MAX(id) FROM avaliacoes GROUP BY aluno_id)
    ) av ON a.id = av.aluno_id;
    """
    row = cursor.execute(query).fetchone()
    conn.close()

    return {
        "total_alunos": row["total_alunos"] or 0,
        "alunos_ativos": row["alunos_ativos"] or 0,
        "alunos_criticos": row["alunos_criticos"] or 0,
        "alunos_moderados": row["alunos_moderados"] or 0,
        "alunos_estaveis": row["alunos_estaveis"] or 0,
    }



def list_alunos(search_term="", curso="", periodo="", status="", classificacao_risco=""):
    """Lista os alunos com suporte a pesquisa por texto e múltiplos filtros."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        a.id, a.nome, a.matricula, a.curso, a.campus, a.periodo, 
        a.email, a.telefone, a.status, a.data_cadastro,
        av.indice_risco AS indice_risco,
        av.classificacao_risco AS classificacao_risco,
        av.nota_media, av.frequencia, av.situacao_financeira, av.situacao_psicologica
    FROM alunos a
    LEFT JOIN (
        SELECT aluno_id, indice_risco, classificacao_risco, nota_media, frequencia, situacao_financeira, situacao_psicologica
        FROM avaliacoes
        WHERE id IN (SELECT MAX(id) FROM avaliacoes GROUP BY aluno_id)
    ) av ON a.id = av.aluno_id
    WHERE a.status_exclusao = 0
    """
    params = []

    if search_term:
        query += " AND (a.nome LIKE ? OR a.matricula LIKE ? OR a.curso LIKE ?)"
        like = f"%{search_term}%"
        params.extend([like, like, like])

    if curso:
        query += " AND a.curso = ?"
        params.append(curso)

    if periodo:
        query += " AND a.periodo = ?"
        params.append(int(periodo))

    if status:
        query += " AND a.status = ?"
        params.append(status)

    if classificacao_risco:
        query += " AND av.classificacao_risco = ?"
        params.append(classificacao_risco)

    # Ordenação decrescente de risco (Críticos primeiro), seguida pelo nome
    query += """
    ORDER BY 
        CASE av.classificacao_risco 
            WHEN 'critico' THEN 1 
            WHEN 'moderado' THEN 2 
            WHEN 'estavel' THEN 3 
            ELSE 4 
        END,
        COALESCE(av.indice_risco, 0) DESC,
        a.nome ASC;
    """

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_aluno_by_id(aluno_id):
    """Obtém os dados completos de um aluno específico, incluindo histórico de avaliações e check-ins."""
    conn = get_connection()
    cursor = conn.cursor()

    aluno_row = cursor.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    if not aluno_row:
        conn.close()
        return None

    aluno = dict(aluno_row)

    # Avaliação mais recente
    av_row = cursor.execute(
        "SELECT * FROM avaliacoes WHERE aluno_id = ? ORDER BY id DESC LIMIT 1",
        (aluno_id,)
    ).fetchone()
    aluno["avaliacao_atual"] = dict(av_row) if av_row else None

    # Histórico de avaliações
    av_rows = cursor.execute(
        "SELECT * FROM avaliacoes WHERE aluno_id = ? ORDER BY id DESC",
        (aluno_id,)
    ).fetchall()
    aluno["historico_avaliacoes"] = [dict(r) for r in av_rows]

    # Histórico de check-ins do WhatsApp
    ck_rows = cursor.execute(
        "SELECT * FROM checkins WHERE aluno_id = ? ORDER BY id DESC",
        (aluno_id,)
    ).fetchall()
    aluno["historico_checkins"] = [dict(r) for r in ck_rows]

    conn.close()
    return aluno


def create_aluno(data):
    """Cadastra um novo aluno no banco provisório com validação de unicidade da matrícula."""
    with closing(get_connection()) as conn, conn:
        cursor = conn.cursor()

        # Validação de matrícula única
        cursor.execute("SELECT id FROM alunos WHERE matricula = ?", (data["matricula"].strip(),))
        if cursor.fetchone():
            raise ValueError(f"A matrícula '{data['matricula']}' já está cadastrada no sistema.")

        cursor.execute(
            """
            INSERT INTO alunos (nome, matricula, curso, campus, periodo, email, telefone, status, data_cadastro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                data["nome"].strip(),
                data["matricula"].strip(),
                data["curso"].strip(),
                data.get("campus", "Câmpus de Cáceres").strip(),
                int(data["periodo"]),
                data["email"].strip(),
                data["telefone"].strip(),
                data.get("status", "ativo").strip(),
            )
        )
        aluno_id = cursor.lastrowid

        # Sem avaliação informada, não inventa um índice inicial.
        if 'indice_risco' not in data:
            return aluno_id
        indice = float(data['indice_risco'])
        # A classe sempre deriva do índice calculado; não confiamos no valor enviado pelo cliente.
        classificacao = classificar_risco(indice)

        cursor.execute(
            """
            INSERT INTO avaliacoes (aluno_id, nota_media, frequencia, situacao_financeira, situacao_psicologica, indice_risco, classificacao_risco, data_avaliacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                aluno_id,
                data.get('nota_media'),
                data.get('frequencia'),
                data.get("situacao_financeira", "estavel"),
                data.get("situacao_psicologica", "estavel"),
                indice,
                classificacao,
            )
        )

        return aluno_id


def update_aluno(aluno_id, data):
    """Atualiza as informações cadastrais de um estudante."""
    with closing(get_connection()) as conn, conn:
        cursor = conn.cursor()

        # Verifica se a matrícula pertence a outro aluno
        cursor.execute("SELECT id FROM alunos WHERE matricula = ? AND id != ?", (data["matricula"].strip(), aluno_id))
        if cursor.fetchone():
            raise ValueError(f"A matrícula '{data['matricula']}' já pertence a outro aluno.")

        cursor.execute(
            """
            UPDATE alunos
            SET nome = ?, matricula = ?, curso = ?, campus = ?, periodo = ?, email = ?, telefone = ?, status = ?, data_atualizacao = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                data["nome"].strip(),
                data["matricula"].strip(),
                data["curso"].strip(),
                data.get("campus", "Câmpus de Cáceres").strip(),
                int(data["periodo"]),
                data["email"].strip(),
                data["telefone"].strip(),
                data.get("status", "ativo").strip(),
                aluno_id,
            )
        )

        # Se dados de avaliação foram informados na edição, registra nova avaliação
        if "indice_risco" in data:
            indice = float(data["indice_risco"])
            # A classe sempre deriva do índice calculado; não confiamos no valor enviado pelo cliente.
            classif = classificar_risco(indice)
            cursor.execute(
                """
                INSERT INTO avaliacoes (aluno_id, nota_media, frequencia, situacao_financeira, situacao_psicologica, indice_risco, classificacao_risco, data_avaliacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    aluno_id,
                    float(data.get("nota_media", 7.0)),
                    float(data.get("frequencia", 85.0)),
                    data.get("situacao_financeira", "estavel"),
                    data.get("situacao_psicologica", "estavel"),
                    indice,
                    classif
                )
            )


def delete_aluno(aluno_id, modo="logica"):
    """
    Exclui um aluno do sistema.
    - Modo 'logica' (Padrão Recomendado): Atualiza o status para 'inativo', preservando o histórico de avaliações e dados de auditoria LGPD.
    - Modo 'fisica': Remove definitivamente o registro e seus relacionamentos (CASCADE).
    """
    conn = get_connection()
    cursor = conn.cursor()

    if modo == "logica":
        cursor.execute(
            "UPDATE alunos SET status = 'inativo', data_atualizacao = CURRENT_TIMESTAMP WHERE id = ?",
            (aluno_id,)
        )
    else:
        cursor.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))

    conn.commit()
    conn.close()
