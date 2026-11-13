"""
========================================================================================
RADACHE — Módulo de Gerenciamento de Alunos
Arquivo: aluno_service.py
Camada: Service / Fachada (Design Pattern: Facade & Repository Abstraction)
========================================================================================

OBJETIVO NA ARQUITETURA:
Este módulo implementa a camada de regras de negócio e fachada de serviços (Service Layer).
Ele desacopla completamente os manipuladores de requisição HTTP (em app.py) da camada de
persistência direta no SQLite (database.py).

POR QUE ESSA DECISÃO É IMPORTANTE (JUSTIFICATIVA DE ENGENHARIA DE SOFTWARE):
1. Desacoplamento do SIGAA: Quando a UNEMAT disponibilizar a API REST oficial do SIGAA,
   basta trocar a implementação interna desta classe ou injetar um novo adaptador,
   sem alterar nenhuma rota HTTP e sem quebrar o contrato do frontend.
2. Centralização de Validações: Regras de negócio (campos obrigatórios, limites de período)
   são aplicadas aqui antes de qualquer tentativa de escrita no banco.
3. Tratamento de Exclusão Lógica vs. Física: Garante que o histórico longitudinal de evasão
   seja preservado por padrão (conformidade com LGPD e auditoria analítica).
"""
from __future__ import annotations

import math
import re

import database
import course_catalog
import mock_alunos


class AlunoService:
    """
    Classe de serviço que gerencia as operações de ciclo de vida do aluno.
    Atua como um adaptador provisório sobre o banco SQLite nativo.
    """

    def listar(self, filtros=None):
        """
        Lista estudantes cadastrados aplicando filtros opcionais.
        
        Parâmetros:
            filtros (dict, opcional): Dicionário contendo critérios como:
                - 'q': Termo de busca textual (nome, matrícula ou curso).
                - 'curso': Filtro exato por curso de graduação.
                - 'periodo': Período letivo do discente (1 a 16).
                - 'status' / 'situacao': Vínculo ('ativo', 'inativo', 'trancado', 'formado').
                - 'risco': Classificação ('critico', 'moderado', 'estavel').
                - 'campus': Câmpus universitário (ex: 'Câmpus de Cáceres').
                
        Retorno:
            list[dict]: Lista de discentes que atendem aos filtros fornecidos.
        """
        filtros = filtros or {}
        if filtros.get("periodo"):
            self._validar({"periodo": filtros["periodo"]}, obrigatorios=())
        alunos = database.list_alunos(
            search_term=filtros.get("q", ""),
            curso="",
            periodo=filtros.get("periodo", ""),
            status=filtros.get("situacao", filtros.get("status", "")),
            classificacao_risco=filtros.get("risco", ""),
        )
        demos = mock_alunos.projetados()
        for key,field in [('periodo','periodo'),('situacao','status'),('status','status'),('risco','classificacao_risco')]:
            if filtros.get(key): demos=[a for a in demos if str(a.get(field,''))==str(filtros[key])]
        if filtros.get('q'):
            query=filtros['q'].casefold()
            demos=[a for a in demos if query in ' '.join(str(a[k]) for k in ('nome','matricula','curso')).casefold()]
        alunos.extend(demos)
        for aluno in alunos:
            aluno['curso'] = course_catalog.canonical(aluno['curso'])
        if filtros.get('curso'):
            curso = course_catalog.canonical(filtros['curso'])
            alunos = [a for a in alunos if a['curso'] == curso]
        campus = filtros.get("campus", "")
        # Filtro em memória para o câmpus universitário
        return [a for a in alunos if (not campus or a.get("campus") == campus)]

    def obter(self, aluno_id):
        """
        Busca os dados detalhados de um aluno específico pelo seu ID primário.
        
        Regra de Negócio:
            Se o aluno possuir status_exclusao = 1 (oculto por exclusão lógica do sistema),
            ele é tratado como inexistente (retorna None), garantindo privacidade e isolamento.
            
        Retorno:
            dict ou None: Dados cadastrais, última avaliação e históricos de check-in.
        """
        if int(aluno_id)<0:
            return next((a for a in mock_alunos.projetados() if a['id']==int(aluno_id)),None)
        aluno = database.get_aluno_by_id(aluno_id)
        if aluno and aluno.get("status_exclusao", 0):
            return None
        if aluno:
            aluno['curso'] = course_catalog.canonical(aluno['curso'])
        return aluno

    def cadastrar(self, dados):
        """
        Cadastra um novo aluno no sistema com validações prévias.
        
        Validações aplicadas:
            1. Presença dos campos essenciais ('nome', 'matricula', 'curso').
            2. Período letivo deve ser inteiro entre 1 e 16.
            3. Unicidade da matrícula (verificada no banco).
            
        Parâmetros:
            dados (dict): Informações submetidas no formulário de cadastro.
            
        Retorno:
            int: ID gerado para o novo registro de aluno.
        """
        self._validar(dados, obrigatorios=("nome", "matricula", "curso"))
        dados = dict(dados)
        dados['curso'] = course_catalog.canonical(dados['curso'])
        # Valores padrão para campos opcionais
        dados.setdefault("periodo", 1)
        dados.setdefault("email", "")
        dados.setdefault("telefone", "")
        return database.create_aluno(dados)

    def atualizar(self, aluno_id, dados):
        """
        Atualiza os dados cadastrais de um estudante existente.
        
        Passos:
            1. Verifica se o aluno existe e não está excluído.
            2. Mescla os novos dados com os dados atuais.
            3. Valida os campos obrigatórios e integridade da matrícula.
            4. Persiste a alteração no banco de dados.
            
        Retorno:
            bool: True se atualizado com sucesso, False se o aluno não foi encontrado.
        """
        atual = self.obter(aluno_id)
        if not atual:
            return False
        # A ficha mantém os indicadores dentro de avaliacao_atual.
        # Mesclar antes de editar evita substituir notas e situações por padrões.
        avaliacao = atual.get("avaliacao_atual") or {}
        atual.update({campo: avaliacao[campo] for campo in (
            "nota_media", "frequencia", "indice_risco", "situacao_financeira", "situacao_psicologica"
        ) if campo in avaliacao})
        atual.update(dados)
        self._validar(atual, obrigatorios=("nome", "matricula", "curso"))
        atual['curso'] = course_catalog.canonical(atual['curso'])
        campos_avaliacao = {"nota_media", "frequencia", "indice_risco", "situacao_financeira", "situacao_psicologica"}
        if not any(campo in dados and dados[campo] != avaliacao.get(campo) for campo in campos_avaliacao):
            for campo in campos_avaliacao:
                atual.pop(campo, None)
        database.update_aluno(aluno_id, atual)
        return True

    def excluir(self, aluno_id, modo="logica"):
        """
        Executa a exclusão de um estudante seguindo a política do sistema.
        
        Modos disponíveis:
            - 'logica' (Padrão / Recomendado):
                Atualiza status_exclusao = 1 e status = 'inativo'.
                Justificativa: Não destrói os dados históricos de evasão usados
                pelo modelo estatístico e relatórios institucionais da UNEMAT.
            - 'fisica' (Hard Delete):
                Executa DELETE com CASCADE nas avaliações e check-ins.
                Justificativa: Casos de erro cadastral crasso ou solicitação formal
                do titular dos dados com base no Art. 18 da LGPD.
                
        Retorno:
            bool: True se a exclusão foi efetuada, False se aluno não existir.
        """
        if modo not in ("logica", "fisica"):
            raise ValueError("O modo deve ser 'logica' ou 'fisica'.")
        if not self.obter(aluno_id):
            return False
        if modo == "logica":
            conn = database.get_connection()
            # Marca o registro como oculto sem apagar o histórico de risco
            conn.execute("UPDATE alunos SET status_exclusao = 1, status = 'inativo', data_atualizacao = CURRENT_TIMESTAMP WHERE id = ?", (aluno_id,))
            conn.commit()
            conn.close()
        else:
            database.delete_aluno(aluno_id, modo="fisica")
        return True

    @staticmethod
    def _validar(dados, obrigatorios):
        """
        Método utilitário para validação defensiva de integridade de dados.
        Lança ValueError explicativo caso encontre inconsistências.
        """
        for campo in obrigatorios:
            if not isinstance(dados.get(campo), str) or not dados[campo].strip():
                raise ValueError("O campo '{}' é obrigatório.".format(campo))
        for campo, limite in {"nome": 150, "matricula": 20, "curso": 100, "campus": 100, "email": 120, "telefone": 20}.items():
            if campo in dados:
                valor = dados[campo]
                if not isinstance(valor, str) or len(valor.strip()) > limite:
                    raise ValueError("O campo '{}' deve ser texto de até {} caracteres.".format(campo, limite))
                dados[campo] = valor.strip()
        if dados.get("email") and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", dados["email"]):
            raise ValueError("Informe um e-mail válido.")
        if dados.get("telefone"):
            telefone = re.sub(r"\D", "", dados["telefone"])
            if len(telefone) not in (10, 11, 12, 13):
                raise ValueError("Informe um telefone com DDD válido.")
        if "status" in dados and dados["status"] not in ("ativo", "inativo", "formado", "trancado"):
            raise ValueError("Situação do vínculo inválida.")
        for campo in ("situacao_financeira", "situacao_psicologica"):
            if campo in dados and dados[campo] not in ("estavel", "moderada", "critica"):
                raise ValueError("Situação inválida no campo '{}'.".format(campo))
        for campo, limite in {"nota_media": 10, "frequencia": 100, "indice_risco": 100}.items():
            if campo in dados:
                try:
                    if isinstance(dados[campo], bool):
                        raise ValueError()
                    numero = float(dados[campo])
                    if not math.isfinite(numero) or not 0 <= numero <= limite:
                        raise ValueError()
                    dados[campo] = numero
                except (TypeError, ValueError):
                    raise ValueError("O campo '{}' deve estar entre 0 e {}.".format(campo, limite))
        try:
            valor = dados.get("periodo", 1)
            if isinstance(valor, bool) or not float(valor).is_integer():
                raise ValueError()
            periodo = int(valor)
        except (TypeError, ValueError):
            raise ValueError("O período deve ser um número inteiro entre 1 e 16.")
        if not 1 <= periodo <= 16:
            raise ValueError("O período deve estar entre 1 e 16.")

