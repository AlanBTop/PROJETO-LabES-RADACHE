# RADACHE — versão local

Execute `INICIAR_LOCAL.bat` e acesse http://localhost:8080/. É necessário Python 3.

## Áreas disponíveis

- Portal: `/` — reúne os acessos às páginas.
- Gestão: `/gestao/` — chamados, usuários e alunos.
- Módulo de alunos: `/alunos/`.
- Observatório: `/institucional/` — estatísticas agregadas.
- Painel analítico: `/painel-demo/`.
- Mensagens: `/mensagens/` — simulação da API.

Para demonstração local, use `admin@radache.local` e `admin123`; no observatório, `analista@radache.local` e `admin123`. Essas credenciais são somente para demonstração e não são adequadas para produção.

O banco principal SQLite é criado automaticamente com dados fictícios a partir de `database/schema.sql` e `database/seeds.sql` em `RADACHE_Modulo_Alunos/`. Os bancos de histórico e as métricas existentes em outras instalações não acompanham o repositório.

Para iniciar pelo terminal, execute `python RADACHE_Modulo_Alunos/backend/run_local.py --no-browser` a partir desta pasta. Consulte `ESTRUTURA.md` para conhecer os componentes.
