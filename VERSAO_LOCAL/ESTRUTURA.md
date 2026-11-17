# Estrutura da versão local

| Caminho | Responsabilidade |
|---|---|
| INICIAR_LOCAL.bat | Executa esta versão diretamente |
| portal/ | Entrada e navegação entre as áreas |
| gestao/ | Gestão de chamados, equipe e acessos |
| institucional/ | Observatório agregado |
| painel-demo/ | Painel analítico |
| assets/ | Tema, fontes e ícones compartilhados |
| RADACHE_Modulo_Alunos/frontend/ | Interface de alunos e mensagens |
| RADACHE_Modulo_Alunos/backend/ | Servidor HTTP, regras e integrações locais |
| RADACHE_Modulo_Alunos/backend/tests/ | Testes do backend |
| RADACHE_Modulo_Alunos/database/ | Esquema e seeds versionados; bancos são gerados localmente |
| scripts/ | Utilitários de manutenção e verificação |
| validacao/ | Evidências geradas localmente, fora da publicação |
| validacao/logs/ | Logs anteriores de validação |

Comece pelo [guia de avaliação](../GUIA_AVALIACAO.md).
As tabelas estão definidas em [schema.sql](RADACHE_Modulo_Alunos/database/schema.sql) e pelas migrações do backend.
Backups gerados em `ARQUIVO/backups/versao_local` ficam somente na instalação local.
Scripts de manutenção podem modificar dados; a apresentação começa pelo inicializador, sem executá-los.
