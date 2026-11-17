# Modelo de risco do RADACHE

Arquivo gerado por `RADACHE_Modulo_Alunos/backend/risk_documentation.py`.
Fonte das faixas: constantes `LIMITE_ESTAVEL` e `LIMITE_CRITICO` de `risk.py`.

| Classificação | Intervalo |
|---|---|
| Estável | 0 ≤ índice ≤ 33 |
| Moderado | 33 < índice < 67 |
| Crítico | 67 ≤ índice ≤ 100 |

O índice é uma heurística de triagem, com peso padrão de 25% por dimensão.
Ele não representa probabilidade validada de evasão nem diagnóstico psicológico.
Notas usam `100 − 10 × média`; frequência usa `100 − frequência`.
Respostas financeiras usam 0, 33, 66 ou 100; bem-estar usa `(5 − resposta) / 4 × 100`.

## Sensibilidade com pesos padrão

| Cenário | Média | Frequência | Financeiro | Bem-estar (1–5) | Índice | Classe |
|---|---:|---:|---|---:|---:|---|
| Referência | 4.5 | 60% | dificuldade significativa | 2 | 59.00 | moderado |
| Somente bem-estar piora | 4.5 | 60% | dificuldade significativa | 1 | 65.25 | moderado |
| Melhora acadêmica | 8 | 90% | dificuldade significativa | 2 | 42.75 | moderado |
| Demanda de acolhimento com bom desempenho | 10 | 100% | não sinto dificuldade | 1 | 25.00 | estavel |
| Quatro fatores no máximo de risco | 0 | 0% | considerando trancar por motivo financeiro | 1 | 100.00 | critico |

Uma queda de um ponto no bem-estar aumenta o índice em 6,25 pontos com pesos padrão.
Uma melhora de um ponto na média reduz o índice em 2,5 pontos.
Dez pontos percentuais a mais de frequência reduzem o índice em 2,5 pontos.
O alerta de acolhimento para respostas 1 ou 2 independe do índice total.

## Limitações para o Blueprint e o trabalho acadêmico

Não há coorte histórica de evasão validada disponível nesta versão. Os pesos e limites
precisam ser discutidos com o NAE; alterar pesos no ambiente não equivale a calibrar o modelo.
Após obter dados adequados e autorização institucional, comparar modelos com validação
temporal, medir discriminação, calibração e erros por grupo e documentar as decisões.
Regressão logística é uma possibilidade de estudo, sem promessa de desempenho.

Avaliações novas exigem seus quatro componentes. O repositório rejeita índices isolados
ou divergentes; não fabrica nota ou frequência. A inicialização preserva classes históricas.
Reclassificar registros antigos requer comando explícito e backup prévio.
