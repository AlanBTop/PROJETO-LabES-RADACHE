# Recursos visuais locais

As duas interfaces carregam fontes, ícones e CSS desta pasta. Não há dependência de CDN em tempo de execução.

- Font Awesome Free 6.4.0: arquivos originais de `cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/`. Licença em `fontawesome/LICENSE.txt`.
- Inter: arquivos obtidos da folha de estilos do Google Fonts. Licença em `fonts/OFL.txt`.
- Tailwind CSS 3.4.17: CSS compilado para as classes usadas pelo painel. Licença em `TAILWIND_LICENSE.txt`.

Para atualizar os recursos ou recompilar o CSS após introduzir classes novas no painel, execute `scripts/prepare_assets.py` na raiz do projeto. Esse procedimento de desenvolvimento usa Python, Playwright, Edge e acesso à internet. O aplicativo em si continua sem dependências Python externas.
