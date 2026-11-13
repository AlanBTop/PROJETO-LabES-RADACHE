"""Consolida somente evidências medidas; exige testes finais aprovados."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'validacao/auditoria_20261111'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def main():
    before = read('baseline_runtime.json'); after = read('after_runtime.json')
    suite = read('after_summary.json'); flows = read('browser_flows.json')
    assert suite['exit_code'] == 0 and suite['installation_databases_unchanged']
    assert len(flows) == 5 and all(r['exit_code'] == 0 for r in flows)
    assert all(r['scroll'] <= r['width'] for r in after['layouts'])
    baseline = read('baseline_inventory.json')
    current = {}
    for folder in ('portal', 'gestao', 'institucional', 'painel-demo', 'assets', 'RADACHE_Modulo_Alunos', 'scripts'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.js', '.css', '.html', '.sql', '.svg', '.bat', '.md') and '__pycache__' not in path.parts:
                current[str(path.relative_to(ROOT))] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
    modified = sorted(p for p in baseline.keys() & current.keys() if baseline[p]['sha256'] != current[p]['sha256'])
    added = sorted(current.keys() - baseline.keys())
    removed = sorted(baseline.keys() - current.keys())
    assert not removed
    # O coletor foi criado antes da medição inicial; README fica fora dos diretórios de código.
    diagnosis_tools = ['scripts/audit_project.py']
    documentation = ['README.md']
    changes = dict(modified=modified, added=added, removed=removed,
                   created_during_diagnosis=diagnosis_tools, documentation_updated=documentation)
    (OUT / 'changes.json').write_text(json.dumps(changes, indent=2, ensure_ascii=False), encoding='utf-8')
    (OUT / 'final_inventory.json').write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding='utf-8')
    tree = []; groups = Counter()
    for directory, subdirs, files in os.walk(ROOT.parent):
        subdirs[:] = [d for d in subdirs if not d.startswith(('.git', '.venv', '__pycache__', '.pytest_cache')) and d != 'node_modules']
        if Path(directory) == OUT:
            subdirs.clear(); continue
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(ROOT.parent)
            tree.append({'path': str(relative), 'bytes': path.stat().st_size})
            groups[relative.parts[0]] += 1
    (OUT / 'project_structure.json').write_text(json.dumps({'groups': groups, 'files': tree}, indent=2, ensure_ascii=False), encoding='utf-8')
    log = (OUT / 'after_tests.log').read_text(encoding='utf-8')
    count = int(re.search(r'Ran (\d+) tests', log)[1])
    old = before['projection']; new = after['projection']
    reduction = 100 * (1 - new['median_ms'] / old['median_ms'])
    file_list = '\n'.join('- `' + p.replace('\\', '/') + '`' for p in modified)
    new_list = '\n'.join('- `' + p.replace('\\', '/') + '`' for p in added)
    report = f'''# Auditoria e otimização do RADACHE — 11/11/2026

## Resultado

Versão local otimizada mantendo arquitetura, identidade visual, permissões e regras de negócio.
**{count} testes aprovados**, cinco cenários existentes de navegador aprovados e 60 combinações
de página/resolução/acesso verificadas sem overflow global. Nenhum erro JavaScript ou recurso
estático com falha na matriz final. Sem requisições externas nessa execução.
Os bancos da instalação permaneceram idênticos por SHA-256 antes/depois da suíte.

## 1. Diagnóstico e arquitetura

O atalho `INICIAR_RADACHE.bat` chama `VERSAO_LOCAL/INICIAR_LOCAL.bat`. Essa é a versão
efetivamente auditada e alterada. A raiz não possui repositório Git; `original/` preserva os
fontes ativos anteriores às alterações e os inventários contêm hashes para comparação.

Frontend em HTML, CSS e módulos ES, sem framework. Backend Python com biblioteca padrão,
ThreadingHTTPServer, serviços por domínio e SQLite. Sem dependências pip/npm em produção
local. Playwright já disponível no ambiente foi usado apenas para validação.

| Área | Página | Responsabilidade |
|---|---|---|
| Portal | `/` | Entrada e atalhos |
| Gestão | `/gestao/#chamados`, `#alunos`, `#usuarios` | Chamados, fichas, equipe e transferências |
| Administração fictícia | `/alunos/` | Cadastro, edição e desativação de perfis de simulação |
| Painel | `/painel-demo/` | Indicadores, filtros, cursos e histórico individual |
| Observatório | `/institucional/` | Indicadores agregados e supressão de grupos pequenos |
| Mensagens | `/mensagens/` | Conversas simuladas, consentimento e mock HTTP |

APIs mapeadas: `/api/login`, `/api/session`, `/api/logout`, `/api/alunos`, `/api/dashboard`,
`/api/cursos`, `/api/analytics`, `/api/local` (alias `/api/v1`), `/api/mock-alunos`,
`/api/institucional`, `/simulation-api`, `/mock-api/mensagens` e `/webhooks/whatsapp`.
`/healthz` é usado pelo inicializador para reconhecer a instalação.

Persistência separa cadastro legado, catálogo acadêmico fictício e estado operacional da
simulação. Os serviços de risco, histórico, funcionários e atendimentos continuam independentes.
Consultas parametrizadas, chaves estrangeiras, índices e transações existentes foram preservados.
Não houve migração de schema nem recálculo dos dados instalados durante a auditoria.

`VERSAO_INTEGRACAO Pausada` contém a alternativa PostgreSQL/psycopg;
`VERSAO_FIREBASE Pausada` contém Flask/Firebase, regras e frontend próprios.
`ARQUIVO` e `fase4_trabalho_temporario` contêm histórico/cópias. A estrutura está registrada
em `project_structure.json`; essas variantes foram inventariadas e não foram executadas,
alteradas, excluídas ou reativadas.

## 2. Problemas e plano aplicado

| Criticidade | Evidência | Tratamento |
|---|---|---|
| Média | 1 + 3N consultas na projeção dos alunos fictícios | Quatro consultas agrupadas, com ordenação e resultado preservados |
| Média | Estáticos sem validadores de cache | ETag fraco por metadados, Last-Modified e revalidação obrigatória |
| Média | Exceções internas GET/webhook divulgavam detalhes na resposta 500 | Mensagem pública genérica; nenhum segredo da exceção no log adicionado |
| Média | Sessões expiradas retidas em memória | Limpeza no login e remoção ao consultar token expirado |
| Média | Leituras HTTP podiam esperar indefinidamente | Timeout de conexão de 15 segundos |
| Média | Resposta 415 do mock podia ser abortada no Windows | Consumo limitado do corpo recusado, com timeout, antes de fechar |
| Média | Navegação do observatório desaparecia no celular | Menu em duas colunas; controles de toque maiores; filtros em uma coluna até 420px |
| Média | Oito testes antigos divergiam dos contratos vigentes | Fixtures atualizadas com senha inicial, atendente e motivo; escopo atual mantido |
| Baixa | Erros textuais da API perdiam a mensagem útil na gestão | Tratamento dos dois formatos de erro |
| Baixa | Gestão carregava cópia idêntica das fontes por outra URL | Referência ao recurso compartilhado, sem excluir os arquivos antigos |
| Baixa | Portal sem atalho de teclado ao conteúdo; tabelas sem foco | Skip link, alvo focável e regiões de tabela acessíveis por teclado |

Nenhum achado crítico comprovado. A prioridade foi confiabilidade e privacidade, seguida
de redução de consultas, transferência e melhorias de uso. Mudanças estruturais ficaram fora
da implementação de baixo risco, conforme o pedido.

## 3. Implementação e preservação

- A projeção mantém identidade negativa dos alunos fictícios, históricos completos na mesma
  ordem, última avaliação válida e última interação. Ignora históricos fora do catálogo;
  catálogo vazio continua retornando lista vazia sem exigir banco operacional inicializado.
- CSS/JS/fontes são revalidados a cada uso: alterações locais aparecem sem esperar expiração.
  APIs continuam `no-store`. HEAD estático retorna metadados sem corpo.
- Headers comuns incluem `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` e
  `X-Content-Type-Options: nosniff`, inclusive em erros e redirecionamentos do handler.
- Não foi introduzido cache de dados de alunos, SDK, biblioteca ou serviço externo.
- Permissões, consentimento, fórmula de risco, operações acadêmicas somente leitura e
  transições de atendimento não foram flexibilizados para fazer testes passarem.
- Nenhuma funcionalidade, dado real, credencial ou versão histórica foi removida.

## 4. Validação e desempenho

| Medida | Antes | Depois |
|---|---:|---:|
| SELECTs da projeção com 400 alunos | {old['selects']} | {new['selects']} |
| Mediana da projeção, sete amostras | {old['median_ms']:.3f} ms | {new['median_ms']:.3f} ms |
| Repetição condicional do CSS compartilhado | 200 / 4331 bytes de corpo | 304 / 0 bytes de corpo |
| Testes de backend | 137: seis falhas e dois erros | {count} aprovados |
| Overflow global na matriz final | — | 0 de {len(after['layouts'])} verificações |

Redução de tempo de **{reduction:.1f}%** nesse microbenchmark local. Dados: 400 alunos fictícios,
quatro conversas concluídas, mesmo computador/Python e sete chamadas por medição. Não é uma
medição de latência em produção, carregamento total da página, memória ou Lighthouse/Core Web Vitals.
O resultado varia com carga do computador e volume de históricos. Os bytes indicados são do corpo,
sem incluir cabeçalhos. Amostras brutas em `baseline_runtime.json` e `after_runtime.json`.

A suíte final levou {suite['seconds']:.2f} segundos. Onze testes novos cobrem cache/invalidação,
HEAD, headers, sigilo de erros, limpeza de sessão, equivalência de históricos, catálogo vazio,
isolamento da projeção e 20 recusas HTTP consecutivas do mock.
As oito ocorrências da suíte inicial eram expectativas/fixtures antigas; o aborto intermitente
de HTTP 415 foi observado durante a validação e corrigido no código, sem ocultar a falha.

Cenários existentes executados no Edge headless, com SQLite temporário:

- `verify_local_simulation_browser.py`: cadastro, edição, chat, recarga, ciclos e risco no painel.
- `verify_staff_ui.py`: acesso multicurso, localização de funcionário, histórico e transferência.
- `verify_attendance_ui.py`: gestor cria/atribui; atendente consulta e resolve.
- `verify_analytics_browser.py`: filtros, ordenação, paginação, busca, históricos e restrição por perfil.
- `verify_institutional_browser.py`: analista redirecionado, grupos protegidos, negação de operações
  individuais e administração técnica. A fixture passou a preencher a senha inicial já obrigatória.

Matriz de seis páginas: 320, 390, 768, 1366 e 1920 pixels, antes do acesso e após autenticação.
Na gestão, a matriz final efetua login pela interface; a inicial registrou a tela de login.
Também foram validados skip link por Tab/Enter, quatro links de navegação móvel e mensagens
de erro textuais/estruturadas. A inspeção visual das capturas motivou o ajuste final dos filtros.

## Arquivos de aplicação e testes modificados

Todos os caminhos abaixo são relativos a `VERSAO_LOCAL`.

{file_list}

Novos arquivos de testes e reprodução:

{new_list}

Além da comparação com a medição inicial, `scripts/audit_project.py` foi criado durante
o diagnóstico (antes do inventário inicial), e `README.md` recebeu links para os relatórios.

Lista mecanicamente conferida em `changes.json`. Logs e capturas estão nas subpastas de
`validacao`; os cenários existentes atualizam suas próprias evidências. Os arquivos originais
de aplicação/testes também estão no backup desta auditoria.

## 5. Limitações, pendências e recomendações

1. O resultado valida a aplicação local em Edge/Chromium no Windows. Não foram usados
   Safari/Firefox, aparelhos físicos, infraestrutura pública ou ensaio de alta concorrência.
2. WhatsApp real, e-mail, Firebase e PostgreSQL pausados não foram ativados. O webhook foi
   exercitado pelos testes existentes com mocks; não houve envio de mensagens externas.
3. As versões pausadas têm dependências próprias. Firebase declara Python >=3.12,<3.14;
   não deve usar automaticamente o Python 3.14 empregado nesta auditoria. Não houve
   atualização de versões nem auditoria de CVEs das variantes pausadas. A versão ativa não
   possui pacotes pip/npm para atualizar. Font Awesome 6.4.0 e recursos Tailwind 3.4.17
   identificados em assets foram preservados; o compilador Tailwind não é carregado nas telas atuais.
4. Os atalhos auxiliares de Firebase/integração ainda referenciam nomes sem o sufixo `Pausada`.
   Se essas variantes forem retomadas, alinhar caminhos, ambientes e documentação em uma tarefa
   própria. Os atalhos da versão local foram mantidos.
5. Há cópias históricas e assets legados no disco. Não foram eliminados por inferência de desuso;
   futuras remoções devem considerar apresentações e execução independente de cada versão.
6. Antes de exposição pública: revisar infraestrutura HTTP/TLS, credenciais de demonstração,
   limitação de tentativas, CORS e políticas de sessão/CSRF/CSP com testes de integração.
   A arquitetura local foi preservada; isso não é uma certificação de segurança nem autorização
   para produção. O servidor da biblioteca padrão tem limitações de produção documentadas pelo Python.
7. Para volumes maiores, medir históricos e memória antes de introduzir paginação de históricos
   ou limitar a projeção. Essa mudança afeta contratos e deve ser planejada, não aplicada silenciosamente.
8. Inicializar Git e CI ajudaria a revisar alterações e impedir nova defasagem entre regras e testes.

Referências técnicas consultadas: [HTTP Caching / RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html),
[headers HTTP / OWASP](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) e
[http.server / Python](https://docs.python.org/3/library/http.server.html#security-considerations).

## Reprodução

Na pasta `VERSAO_LOCAL`, com Python e Playwright já disponíveis para os testes de navegador:

```text
python scripts/audit_project.py after
python scripts/audit_runtime.py after
python scripts/audit_browser_flows.py
python scripts/audit_report.py
```

O aplicativo continua iniciando pelo atalho habitual. Reinicie o servidor local para carregar
as mudanças Python. A revalidação dos recursos estáticos passa a funcionar no servidor atualizado.
'''
    (OUT / 'RELATORIO_FINAL.md').write_text(report, encoding='utf-8')
    print(json.dumps({'tests': count, 'modified': len(modified), 'added': len(added), 'removed': len(removed), 'median_reduction_pct': round(reduction, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
