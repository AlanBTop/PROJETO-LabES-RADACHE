"""Diagrama Mermaid do esquema local, consultando os arquivos somente em leitura."""
from pathlib import Path
from contextlib import closing
import re
import sqlite3

LOCAL = Path(__file__).resolve().parents[1]
OUT = LOCAL.parent / 'DOCUMENTACAO/tecnica/DIAGRAMA_BANCO_DADOS_LOCAL.md'
FILES = ('mock_sigaa.db', 'radache.db', 'radache_provisorio.db', 'alunos_mock_isolado.db')
OVERVIEW = '''flowchart TB
    subgraph A["mock_sigaa.db · cadastro fictício"]
        MA["alunos"]
        MI["migracoes"]
    end
    subgraph B["radache.db · simulação e acompanhamento"]
        S["sessoes"] -->|"sessao_id"| M["mensagens"]
        S -->|"sessao_id"| AV["avaliacoes_sim"]
        C["gestao_chamados"] -->|"chamado_id"| E["gestao_eventos"]
        C -->|"chamado_id"| GS["gestao_simulacoes"]
        AC["gestao_acoes"] -.->|"chamado_id · aplicação"| C
        GS -.->|"sessao_id · aplicação"| S
        CO["comandos"]
        PO["povoamento_universidades"]
    end
    subgraph D["radache_provisorio.db · cadastro original, gestão e equipe"]
        LA["alunos"] -->|"aluno_id"| LAE["avaliacoes"]
        LA -->|"aluno_id"| LC["checkins"]
        LA -->|"aluno_id"| LGC["gestao_chamados"]
        LGC -->|"chamado_id"| LGE["gestao_eventos"]
        LAC["gestao_acoes"] -.->|"chamado_id · aplicação"| LGC
        CA["campus"] -->|"campus_id"| CC["campus_cursos"]
        CC -->|"campus_id + curso_id"| V["atendentes_vinculos"]
        U["gestao_usuarios"] -->|"usuario_id"| V
        U -->|"usuario_id"| T["funcionarios_transferencias"]
        CA -->|"origem e destino"| T
        AU["gestao_equipe_auditoria"]
        AI["institucional_auditoria"]
        GM["gestao_meta"]
        WE["whatsapp_eventos"]
    end
    subgraph H["alunos_mock_isolado.db · sandbox anterior"]
        OLD["alunos_mock"]
    end
    OLD -.->|"importação única"| MA
    MA -.->|"aluno_id positivo · aplicação"| S
    LA -.->|"aluno_id negativo · aplicação"| S
    AV -.->|"gera ou atualiza · aplicação"| C
'''

def quote(name):
    return '"' + name.replace('"', '""') + '"'

def main():
    sections = ['''# Diagrama do banco de dados — versão local

## Visão geral para apresentação

Os quatro grupos correspondem aos arquivos SQLite da instalação. Todas as 27 tabelas de aplicação aparecem na visão geral.
Setas contínuas indicam referências por FK do registro dependente à tabela de origem, desenhadas da tabela referenciada para a dependente.
Setas pontilhadas indicam fluxos ou referências resolvidos pelo código, sem FK física. As caixas isoladas não possuem FK declarada; podem ter relações lógicas em campos JSON.

```mermaid
''', OVERVIEW, '''```

## Diagramas de entidade e relacionamento

Cada diagrama abaixo pertence a um único arquivo. Exibe todas as colunas físicas; propriedades internas de JSON estão no [dicionário de dados](DICIONARIO_BANCO_DADOS_LOCAL.md).
PK indica chave primária; FK indica chave estrangeira declarada; UK indica uma restrição UNIQUE ou índice único não parcial de uma única coluna.
Tipos como VARCHAR(150) são abreviados para VARCHAR no desenho; consulte o dicionário para a declaração SQL exata.
As relações seguem a nulabilidade declarada no SQLite: o lado da tabela referenciada é opcional quando a FK admite NULL. A quantidade mínima de dependentes é zero.

''']
    table_count = field_count = fk_count = 0
    for file in FILES:
        path = LOCAL / 'RADACHE_Modulo_Alunos/database' / file
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            conn.execute('BEGIN')
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            fields = {name: conn.execute('PRAGMA table_info(' + quote(name) + ')').fetchall() for name in tables}
            sections.append(f'### {file}\n\n```mermaid\nerDiagram\n')
            for name in tables:
                fks = conn.execute('PRAGMA foreign_key_list(' + quote(name) + ')').fetchall()
                fk_fields = {r[3] for r in fks}
                unique_cols = set()
                for idx in conn.execute('PRAGMA index_list(' + quote(name) + ')').fetchall():
                    if idx[2] and not idx[4]:
                        cols = conn.execute('PRAGMA index_info(' + quote(idx[1]) + ')').fetchall()
                        if len(cols) == 1:
                            unique_cols.add(cols[0][2])
                sections.append('    ' + name + ' {\n')
                table_count += 1
                for _, col, typ, nn, default, pk in fields[name]:
                    keys = (['PK'] if pk else []) + (['FK'] if col in fk_fields else []) + (['UK'] if col in unique_cols and not pk else [])
                    typ = re.sub(r'\(.*\)', '', typ).replace(' ', '_') or 'TEXT'
                    suffix = ' ' + ','.join(keys) if keys else ''
                    comment = ' "JSON"' if col in {'dados', 'estado', 'metadados_risco', 'antes', 'depois', 'filtros'} else ''
                    sections.append(f'        {typ} {col}{suffix}{comment}\n')
                    field_count += 1
                sections.append('    }\n')
            for name in tables:
                groups = {}
                for fk in conn.execute('PRAGMA foreign_key_list(' + quote(name) + ')'):
                    groups.setdefault(fk[0], []).append(fk)
                for fks in groups.values():
                    fk_count += 1
                    parent = fks[0][2]
                    source_cols = {r[3] for r in fks}
                    nonnull = all(next(c[3] or (c[5] and c[2].upper() == 'INTEGER') for c in fields[name] if c[1] == src) for src in source_cols)
                    pk_cols = {r[1] for r in fields[name] if r[5]}
                    unique = bool(pk_cols) and pk_cols <= source_cols
                    for idx in conn.execute('PRAGMA index_list(' + quote(name) + ')').fetchall():
                        if idx[2] and not idx[4]:
                            idx_cols = {r[2] for r in conn.execute('PRAGMA index_info(' + quote(idx[1]) + ')')}
                            if idx_cols and None not in idx_cols and idx_cols <= source_cols:
                                unique = True
                    left = '||' if nonnull else 'o|'
                    right = 'o|' if unique else 'o{'
                    label = '_'.join(r[3] for r in sorted(fks, key=lambda r:r[1]))
                    sections.append(f'    {parent} {left}--{right} {name} : {label}\n')
            sections.append('```\n\n')
    sections.append('''## Convenções importantes

- As tabelas com nomes repetidos pertencem a arquivos diferentes. Não representam uma única tabela compartilhada.
- No armazenamento da simulação (`radache.db`), aluno_id positivo identifica o cadastro fictício de mock_sigaa.db; negativo identifica o cadastro original, com inversão do sinal.
- Na visão unificada da gestão/análise e no JSON alunoId dos chamados simulados, o cadastro fictício recebe ID negativo e o original permanece positivo.
- Não existe FK entre arquivos SQLite. A aplicação resolve esses vínculos e a conversão de IDs.
- gestao_simulacoes.sessao_id tem relação lógica com sessoes, mas não possui REFERENCES no esquema atual.
- Índices únicos parciais, como vinculo_atual e avaliacao_por_origem, dependem de condições e estão detalhados no dicionário.
- sessoes representa ciclos de conversa; as sessões de autenticação da gestão ficam em memória.
- O sandbox anterior é importado para o cadastro fictício por uma migração marcada em migracoes.

## Fontes

- [Dicionário de dados completo](DICIONARIO_BANCO_DADOS_LOCAL.md).
- [Gerador dos diagramas](../../VERSAO_LOCAL/scripts/diagramar_banco.py), que consulta os quatro arquivos padrão em modo somente leitura.

Para atualizar os diagramas após uma mudança de esquema, execute na raiz do projeto:

```powershell
python VERSAO_LOCAL/scripts/diagramar_banco.py
```
''')
    OUT.write_text(''.join(sections), encoding='utf-8')
    print(f'{table_count} tabelas, {field_count} campos e {fk_count} FKs físicas documentados.')

if __name__ == '__main__':
    main()
