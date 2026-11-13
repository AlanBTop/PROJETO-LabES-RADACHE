"""Baixa e compila os recursos visuais locais a partir das URLs usadas no projeto."""
import re
from pathlib import Path
from urllib.request import Request, urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
def download(url, path):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        data = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data.decode("utf-8") if path.suffix in (".css", ".js") else None

download("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css", ASSETS / "fontawesome/css/all.min.css")
download("https://raw.githubusercontent.com/FortAwesome/Font-Awesome/6.4.0/LICENSE.txt", ASSETS / "fontawesome/LICENSE.txt")
download("https://raw.githubusercontent.com/rsms/inter/master/LICENSE.txt", ASSETS / "fonts/OFL.txt")
download("https://raw.githubusercontent.com/tailwindlabs/tailwindcss/v3.4.17/LICENSE", ASSETS / "TAILWIND_LICENSE.txt")
for font in ["fa-solid-900", "fa-brands-400", "fa-regular-400", "fa-v4compatibility"]:
    download("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/" + font + ".woff2", ASSETS / ("fontawesome/webfonts/" + font + ".woff2"))
css = download("https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap", ASSETS / "fonts/inter.css")
for index, url in enumerate(dict.fromkeys(re.findall(r"url\((https://[^)]+)\)", css))):
    extension = ".woff2" if ".woff2" in url else ".ttf"
    name = "inter-" + str(index) + extension
    download(url, ASSETS / ("fonts/" + name))
    css = css.replace(url, name)
(ASSETS / "fonts/inter.css").write_text(css, encoding="utf-8")
compiler = download("https://cdn.tailwindcss.com/3.4.17", ASSETS / "tailwind-compiler.js")
tokens = set()
for path in [ROOT / "painel-demo/public/index.html", ROOT / "painel-demo/public/js/app.js"]:
    tokens.update(re.findall(r"[A-Za-z0-9_!:/#.%\[\]()-]+", path.read_text(encoding="utf-8-sig")))
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
    page = browser.new_page()
    page.set_content("<!doctype html><html><head></head><body></body></html>")
    page.add_script_tag(content=compiler)
    page.evaluate("(tokens) => { const div=document.createElement('div'); div.className=tokens.join(' '); document.body.appendChild(div); }", sorted(tokens))
    page.wait_for_timeout(1500)
    generated = page.locator("style").all_text_contents()
    assert generated and sum(map(len, generated)) > 10000, "Falha na geração do CSS"
    (ASSETS / "tailwind.css").write_text("\n".join(generated), encoding="utf-8")
    browser.close()
print("CSS compilado e fontes/ícones armazenados em assets.")

