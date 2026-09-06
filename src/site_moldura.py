"""Moldura comum das páginas: <head>, cabeçalho, navegação, trilha e rodapé.

Extraído de src/site.py quando surgiu o segundo gerador de páginas (as redes
por marca, em src/site_marcas.py). Os dois precisam do MESMO <head> e do mesmo
rodapé — duplicar isso significaria, na prática, dois sites que divergem no
primeiro ajuste de canonical ou de aviso legal.

Aqui não há nenhuma regra de conteúdo: só o invólucro, o contador de arquivos
escritos e os ativos de marca (logotipo e favicon), que são preparados uma vez
por execução e reusados nas dezenas de milhares de páginas.
"""
import html
import json
from pathlib import Path

from config import (ATIVOS, FAVICON, LOGO, SAFRA, SITE, SITE_DESCRICAO,
                    SITE_EMAIL_CONTATO, SITE_NOME, SITE_URL, UF_NOME, VERTICAIS)
from site_tema import logo_svg, png_para_ico

__all__ = ["UF_NOME", "FONTE", "e", "num", "escrever", "contar",
           "paginas_escritas", "preparar_ativos", "definir_nav", "shell",
           "q", "trilha_ld"]

FONTE = (f"Fonte: Cadastro Nacional da Pessoa Jurídica, Receita Federal do Brasil, "
         f"safra {SAFRA}. Somente estabelecimentos com situação cadastral ativa.")

e = html.escape
_paginas_escritas = 0


def num(v) -> str:
    return f"{v:,}".replace(",", ".")


def escrever(caminho: Path, conteudo: str) -> None:
    global _paginas_escritas
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    _paginas_escritas += 1


def contar() -> None:
    """Registra um arquivo escrito fora de escrever() — imagem, .ico."""
    global _paginas_escritas
    _paginas_escritas += 1


def paginas_escritas() -> int:
    return _paginas_escritas


def _dim_png(caminho: Path):
    """Largura e altura do IHDR. Sem PIL: só os 24 primeiros bytes do arquivo."""
    import struct
    with caminho.open("rb") as fh:
        cab = fh.read(24)
    if cab[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", cab[16:24])


def preparar_marca() -> str:
    """Copia ativos/ para site/estatico/ e devolve o HTML do logotipo.

    O arquivo de marca vive em ativos/, FORA de site/, porque site/ é saída
    gerada e um 'make limpar-site' apagaria o logotipo junto. Chamada uma vez
    por execução: o HTML resultante é reusado nas 25 mil páginas.
    """
    destino = SITE / "estatico"
    destino.mkdir(parents=True, exist_ok=True)
    logo = ATIVOS / LOGO
    if not logo.exists():
        print(f"  aviso: {logo} não existe -> usando o logotipo SVG reconstruído")
        return logo_svg()
    destino_logo = destino / logo.name
    destino_logo.write_bytes(logo.read_bytes())
    dim = _dim_png(logo)
    # width/height explícitos evitam deslocamento de layout (CLS) no carregamento;
    # o logo está acima da dobra, então NÃO é lazy.
    tam = f' width="{dim[0]}" height="{dim[1]}"' if dim else ""
    return (f'<img src="/estatico/{logo.name}" alt="{e(SITE_NOME)}"{tam} '
            f'decoding="async" fetchpriority="high">')


_MARCA = ""
_ICONES = ""


def preparar_ativos() -> None:
    """Copia logotipo e favicon para site/estatico/ e guarda o HTML de cada um.

    Chamada uma vez por execução, antes da primeira página: o resultado entra
    em todo <head> e em todo cabeçalho, e reprocessar por página custaria uma
    leitura de arquivo e um sha256 vezes o número de páginas.
    """
    global _MARCA, _ICONES
    _MARCA = preparar_marca()
    _ICONES = preparar_icones()


def preparar_icones() -> str:
    """Copia o favicon, gera /favicon.ico e devolve as tags <link> do <head>.

    O PNG vai com hash no nome, para poder ter cache imutável. O .ico fica na
    raiz com nome fixo, porque é o caminho que o navegador pede sozinho: cache
    mais curto, já que o nome não pode mudar.
    """
    import hashlib

    origem = ATIVOS / FAVICON
    if not origem.exists():
        print(f"  aviso: {origem} não existe -> site sem favicon")
        return ""
    png = origem.read_bytes()
    h = hashlib.sha256(png).hexdigest()[:10]
    nome = f"favicon.{h}.png"
    (SITE / "estatico" / nome).write_bytes(png)
    contar()

    # /favicon.ico: o navegador pede este caminho mesmo com <link rel="icon">.
    # Sem o arquivo, todo primeiro acesso vira um 404 no log.
    try:
        (SITE / "favicon.ico").write_bytes(png_para_ico(png))
        contar()
    except ValueError as erro:
        print(f"  aviso: favicon.ico não gerado ({erro})")

    tags = [f'<link rel="icon" type="image/png" href="/estatico/{nome}">']
    # Tamanhos extras, se existirem. Ninguém precisa criá-los: são opcionais.
    for arquivo, rel, tam in (("favicon-180.png", "apple-touch-icon", "180x180"),
                              ("favicon-512.png", "icon", "512x512")):
        extra = ATIVOS / arquivo
        if not extra.exists():
            continue
        dados = extra.read_bytes()
        he = hashlib.sha256(dados).hexdigest()[:10]
        alvo = f"{arquivo.removesuffix('.png')}.{he}.png"
        (SITE / "estatico" / alvo).write_bytes(dados)
        contar()
        tags.append(f'<link rel="{rel}" sizes="{tam}" href="/estatico/{alvo}">')
    return "".join(tags)


# Itens do menu, em ordem. O padrão são as verticais; src/site.py substitui a
# lista por uma que inclui a categoria "por marca", quando há marcas coletadas.
# Cada item é (chave, rótulo, caminho) — a chave é o que shell(vertical_atual=)
# compara para marcar o item corrente.
_NAV = [(s, v["rotulo"], f"/{s}/") for s, v in VERTICAIS.items()]


def definir_nav(itens) -> None:
    global _NAV
    _NAV = list(itens)


def shell(*, titulo, descricao, url, corpo, css_nome, trilha=None,
           jsonld=None, prev=None, prox=None, vertical_atual=None) -> str:
    nav = "".join(
        f'<li><a href="{caminho}"'
        f'{" aria-current=\"page\"" if chave == vertical_atual else ""}>'
        f'{e(rotulo)}</a></li>' for chave, rotulo, caminho in _NAV)
    trilha_html = ""
    if trilha:
        itens = "".join(
            f"<li>{f'<a href={q(u)}>{e(r)}</a>' if u else e(r)}</li>" for r, u in trilha)
        trilha_html = f'<nav class="trilha" aria-label="Trilha de navegação"><ol>{itens}</ol></nav>'
    ld = "".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False, separators=(",", ":"))}</script>'
        for b in (jsonld or []))
    rel = ""
    if prev:
        rel += f'<link rel="prev" href="{e(prev)}">'
    if prox:
        rel += f'<link rel="next" href="{e(prox)}">'
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}">
<link rel="canonical" href="{e(url)}">{rel}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(SITE_NOME)}">
<meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="{e(descricao)}">
<meta property="og:url" content="{e(url)}">
<meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large">
<link rel="stylesheet" href="/estatico/{css_nome}">
{_ICONES}
{ld}</head>
<body>
<header class="topo"><div class="env"><a class="marca" href="/" aria-label="{e(SITE_NOME)} — início">{_MARCA}</a></div></header>
<nav class="nav" aria-label="Verticais"><ul>{nav}</ul></nav>
<div class="env">{trilha_html}
<main>
{corpo}
</main>
</div>
<footer class="rodape"><div class="env">
<p><strong>{e(SITE_NOME)}</strong> — {e(SITE_DESCRICAO)}</p>
<p>{e(FONTE)} Os dados são públicos e reproduzem o cadastro na data da safra; não
verificamos se a empresa continua em atividade nem o que ela atende.</p>
<p>Para correção ou remoção de um registro, escreva para
<a href="mailto:{e(SITE_EMAIL_CONTATO)}">{e(SITE_EMAIL_CONTATO)}</a>.</p>
</div></footer>
</body>
</html>
"""


def q(u: str) -> str:
    return '"' + e(u) + '"'


def trilha_ld(trilha) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": r,
                 **({"item": SITE_URL + u} if u else {})}
                for i, (r, u) in enumerate(trilha, 1)]}


