"""
========================================================================================
RADACHE — Módulo de Gerenciamento de Alunos
Arquivo: risk.py
Camada: Motor Matemático e Analítico (Algoritmo do Índice de Risco de Evasão - RE)
========================================================================================

MODELO CONCEITUAL:
O cálculo do Índice de Risco de Evasão (RE) fundamenta-se em 4 dimensões essenciais da vida
acadêmica do estudante universitário (especialmente no contexto da UNEMAT):

1. DESEMPENHO ACADÊMICO (Notas): Média institucional de 0.0 a 10.0.
   - Normalização para Risco: Risco = 100 - (Média * 10).
   - Exemplo: Nota 10.0 -> Risco 0%; Nota 4.0 -> Risco 60%; Nota 0.0 -> Risco 100%.

2. ASSIDUIDADE (Frequência): Percentual de presença nas aulas (0% a 100%).
   - Normalização para Risco: Risco = 100 - Frequência.
   - Exemplo: Frequência 100% -> Risco 0%; Frequência 75% -> Risco 25%; 50% -> Risco 50%.

3. VULNERABILIDADE FINANCEIRA (Pesquisa WhatsApp):
   - 'Não sinto dificuldade' (ou 'estável'): Risco = 0%
   - 'Dificuldade leve': Risco = 33%
   - 'Dificuldade significativa' (ou 'moderada'): Risco = 66%
   - 'Considerando trancar por motivo financeiro' (ou 'crítica'): Risco = 100%

4. VULNERABILIDADE PSICOLÓGICA (Escala Likert de Bem-Estar 1 a 5 via WhatsApp):
   - Escala: 1 (Muito Ruim) até 5 (Muito Bom).
   - Normalização para Risco: Risco = ((5 - Resposta) / 4) * 100
   - Exemplo:
     * Resposta 5 (Muito Bom) -> Risco = 0%
     * Resposta 4 (Bom)       -> Risco = 25%
     * Resposta 3 (Regular)   -> Risco = 50%
     * Resposta 2 (Ruim)      -> Risco = 75%
     * Resposta 1 (Muito Ruim)-> Risco = 100%

FÓRMULA GERAL:
   RE = (Risco_Notas * W_notas) + (Risco_Freq * W_freq) + (Risco_Fin * W_fin) + (Risco_Psico * W_psico)
   Onde os pesos padrão são 25% (0.25) para cada pilar, customizáveis via RADACHE_RISK_WEIGHTS.

FAIXAS DE CLASSIFICAÇÃO INSTITUCIONAL:
   - [0%  a 33%]: ESTÁVEL   (Verde)   -> Aluno integrado, sem alertas imediatos.
   - [34% a 66%]: MODERADO  (Amarelo) -> Alerta preventivo, acionamento NAE/CAEst.
   - [67% a 100%]: CRÍTICO  (Vermelho)-> Risco iminente de abandono/trancamento.
"""  

import json
import os

FATORES = ("notas", "frequencia", "financeiro", "psicologico")

# Mapeamento semântico das respostas financeiras para escalas percentuais de risco
RESPOSTAS_FINANCEIRAS = {
    "não sinto dificuldade": 0,
    "nao sinto dificuldade": 0,
    "dificuldade leve": 33,
    "dificuldade significativa": 66,
    "considerando trancar por motivo financeiro": 100,
    # Compatibilidade com os valores já usados no banco na Sprint 1:
    "estavel": 0,
    "moderada": 66,
    "critica": 100,
}


def carregar_pesos(valor_json=None):
    """
    Obtém os pesos das dimensões de risco a partir do parâmetro ou da variável de ambiente.
    Por padrão, cada uma das 4 dimensões recebe peso igual de 25% (0.25).
    
    Validação de Integridade:
    - Garante que a soma de todos os pesos seja exatamente 1.0 (100%).
    - Garante que nenhum peso seja negativo.
    """
    valor_json = valor_json if valor_json is not None else os.getenv("RADACHE_RISK_WEIGHTS")
    if not valor_json:
        return {fator: 0.25 for fator in FATORES}
    try:
        pesos = json.loads(valor_json) if isinstance(valor_json, str) else dict(valor_json)
        pesos = {fator: float(pesos[fator]) for fator in FATORES}
    except (ValueError, TypeError, KeyError) as erro:
        raise ValueError("Pesos devem ser JSON com notas, frequencia, financeiro e psicologico.") from erro
    if any(not 0 <= peso <= 1 for peso in pesos.values()) or abs(sum(pesos.values()) - 1.0) > 1e-9:
        raise ValueError("Os pesos devem ser não negativos e somar 1.0.")
    return pesos


def _numero_entre(valor, minimo, maximo, nome):
    """Função utilitária defensiva para garantir que um valor numérico pertença a um intervalo."""
    try:
        numero = float(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError("{} deve ser numérico.".format(nome)) from erro
    if not minimo <= numero <= maximo:
        raise ValueError("{} deve estar entre {} e {}.".format(nome, minimo, maximo))
    return numero


def calcular_nota(media):
    """
    Converte média acadêmica do discente (0.0 a 10.0) em percentual de risco de evasão (0 a 100%).
    Fórmula invertida: Quanto maior a nota do aluno, MENOR é o seu risco.
    """
    return 100 - _numero_entre(media, 0, 10, "A média") * 10


def calcular_frequencia(frequencia):
    """
    Converte assiduidade às aulas (0% a 100%) em fator de risco.
    Fórmula invertida: Quanto maior a presença, MENOR é a probabilidade de evasão.
    """
    return 100 - _numero_entre(frequencia, 0, 100, "A frequência")


def calcular_financeiro(resposta):
    """
    Converte a resposta textual do aluno no check-in do WhatsApp para a escala percentual de risco.
    """
    if resposta is None:
        raise ValueError("A resposta financeira é obrigatória.")
    chave = " ".join(str(resposta).strip().casefold().split())
    if chave not in RESPOSTAS_FINANCEIRAS:
        raise ValueError("Resposta financeira inválida.")
    return RESPOSTAS_FINANCEIRAS[chave]


def calcular_psicologico(resposta):
    """
    Converte o índice de bem-estar (escala de 1 a 5) em fator percentual de risco de evasão.
    Resposta 5 (Muito Bom) => Risco 0%
    Resposta 1 (Muito Ruim) => Risco 100%
    """
    valor = _numero_entre(resposta, 1, 5, "A resposta psicológica")
    if not valor.is_integer():
        raise ValueError("A resposta psicológica deve ser um inteiro de 1 a 5.")
    return ((5 - valor) / 4) * 100


def calcular_indice_risco(media, frequencia, resposta_financeira, resposta_psicologica, pesos=None):
    """
    Calcula o RE (Índice de Risco de Evasão) consolidado como uma média ponderada das 4 dimensões.
    Retorno:
        float: Valor decimal arredondado com 2 casas decimais, no intervalo [0.00, 100.00].
    """
    pesos = carregar_pesos(pesos) if pesos is not None else carregar_pesos()
    componentes = {
        "notas": calcular_nota(media),
        "frequencia": calcular_frequencia(frequencia),
        "financeiro": calcular_financeiro(resposta_financeira),
        "psicologico": calcular_psicologico(resposta_psicologica),
    }
    return round(sum(componentes[fator] * pesos[fator] for fator in FATORES), 2)


def classificar_risco(indice):
    """
    Categoriza o índice numérico nas 3 faixas institucionais de triagem:
    - 'estavel': RE <= 33% (Verde)
    - 'moderado': 34% <= RE < 67% (Amarelo)
    - 'critico': RE >= 67% (Vermelho)
    """
    indice = _numero_entre(indice, 0, 100, "O índice de risco")
    if indice <= 33:
        return "estavel"
    if indice < 67:
        return "moderado"
    return "critico"

