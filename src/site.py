"""Alvo 'site': gera o site estático em site/, a partir da view `publicacao`.

Por que estático, e não um app:
  * Custo de servidor por visita = servir um arquivo. Nenhum SQL, nenhuma
    renderização, nenhum processo em pé. Um CDN serve tudo da borda.
  * Cache trivial: o HTML muda só quando a safra muda; o CSS tem hash no nome e
    pode ser imutável para sempre.
  * Nenhuma API e nenhuma IA no caminho da requisição.

SEO: um <title>/description único por página, canonical, prev/next na paginação,
JSON-LD (BreadcrumbList + ItemList de LocalBusiness), sitemap fragmentado e
HTML semântico (<address>, tel:, mailto:).

GEO (ser citado por motor de resposta): llms.txt na raiz descrevendo o conjunto,
uma frase-resumo factual no topo de cada página com número e fonte, e os mesmos
dados em JSON-LD — que é o que os rastreadores de LLM leem sem ambiguidade.
"""
import html
import json
import os
import sys
import time
from pathlib import Path

from config import (ATIVOS, FAVICON, LOGO, POR_PAGINA, SAFRA, SAFRA_DATA, SITE,
                    SITE_DESCRICAO, SITE_EMAIL_CONTATO, SITE_NOME, SITE_URL,
                    VERTICAIS)
from db import conectar
from site_tema import css_com_hash, logo_svg, png_para_ico

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins",
}
FONTE = (f"Fonte: Cadastro Nacional da Pessoa Jurídica, Receita Federal do Brasil, "
         f"safra {SAFRA}. Somente estabelecimentos com situação cadastral ativa.")

e = html.escape
_paginas_escritas = 0


def _num(v) -> str:
    return f"{v:,}".replace(",", ".")


def _escrever(caminho: Path, conteudo: str) -> None:
    global _paginas_escritas
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    _paginas_escritas += 1


# --------------------------------------------------------------------- moldura
def _dim_png(caminho: Path):
    """Largura e altura do IHDR. Sem PIL: só os 24 primeiros bytes do arquivo."""
    import struct
    with caminho.open("rb") as fh:
        cab = fh.read(24)
    if cab[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", cab[16:24])


def _preparar_marca() -> str:
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


def _marca() -> str:
    return _MARCA


def _preparar_icones() -> str:
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
    _paginas_contar()

    # /favicon.ico: o navegador pede este caminho mesmo com <link rel="icon">.
    # Sem o arquivo, todo primeiro acesso vira um 404 no log.
    try:
        (SITE / "favicon.ico").write_bytes(png_para_ico(png))
        _paginas_contar()
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
        _paginas_contar()
        tags.append(f'<link rel="{rel}" sizes="{tam}" href="/estatico/{alvo}">')
    return "".join(tags)


def _paginas_contar() -> None:
    global _paginas_escritas
    _paginas_escritas += 1


def _shell(*, titulo, descricao, url, corpo, css_nome, trilha=None,
           jsonld=None, prev=None, prox=None, vertical_atual=None) -> str:
    nav = "".join(
        f'<li><a href="/{s}/"{" aria-current=\"page\"" if s == vertical_atual else ""}>'
        f'{e(v["rotulo"])}</a></li>'
        for s, v in VERTICAIS.items())
    trilha_html = ""
    if trilha:
        itens = "".join(
            f"<li>{f'<a href={_q(u)}>{e(r)}</a>' if u else e(r)}</li>" for r, u in trilha)
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
<header class="topo"><div class="env"><a class="marca" href="/" aria-label="{e(SITE_NOME)} — início">{_marca()}</a></div></header>
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


def _q(u: str) -> str:
    return '"' + e(u) + '"'


def _trilha_ld(trilha) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": r,
                 **({"item": SITE_URL + u} if u else {})}
                for i, (r, u) in enumerate(trilha, 1)]}


# ----------------------------------------------------------------------- ficha
def _ficha(r) -> str:
    nome = r["nome_fantasia"] or r["razao_social"]
    partes = [f'<h3>{e(nome)}</h3>']
    if r["nome_fantasia"] and r["razao_social"] and r["razao_social"] != r["nome_fantasia"]:
        partes.append(f'<p class="razao">{e(r["razao_social"])}</p>')
    end = [r["endereco"], r["cidade_uf"]]
    if r["cep"]:
        end.append("CEP: " + r["cep"])
    partes.append("<address>" + "<br>".join(e(x) for x in end if x) + "</address>")

    contato = []
    for e164, tipo, fmt, e164_9, fmt_9 in (
        (r["telefone"], r["telefone_tipo"], r["telefone_formatado"],
         r["telefone_9"], r["telefone_9_formatado"]),
        (r["telefone_2"], r["telefone_2_tipo"], r["telefone_2_formatado"],
         r["telefone_2_9"], r["telefone_2_9_formatado"]),
    ):
        if not e164:
            continue
        if tipo == "movel" and e164_9:
            # o número com 9 é o que disca hoje; o original fica ao lado
            contato.append(
                f'<a href="tel:{e(e164_9)}"><span class="rot">Cel:</span> {e(fmt_9)}</a>'
                f'<span class="rot">ou {e(fmt)} (formato antigo)</span>')
        else:
            contato.append(
                f'<a href="tel:{e(e164)}"><span class="rot">Tel:</span> {e(fmt)}</a>')
    if r["email"]:
        contato.append(f'<a href="mailto:{e(r["email"])}">{e(r["email"])}</a>')
    if r["site_candidato"]:
        contato.append(f'<a href="{e(r["site_candidato"])}" rel="nofollow noopener">'
                       f'{e(r["site_candidato"].removeprefix("https://"))}</a>')
    if contato:
        partes.append('<p class="contato">' + "".join(contato) + "</p>")
    partes.append(f'<p class="cnpj">CNPJ {e(r["cnpj_formatado"])}</p>')
    # Quem entrou pelo CNAE secundário declara OUTRA atividade como principal.
    # Dizer qual é evita que a lista pareça uniforme quando não é.
    if r.get("origem_cnae") == "secundario" and r.get("cnae_principal_desc"):
        partes.append(f'<p class="selo">Atividade principal declarada: '
                      f'{e(r["cnae_principal_desc"])}</p>')
    return '<li class="ficha"><article>' + "".join(partes) + "</article></li>"


def _ficha_ld(r, pos) -> dict:
    nome = r["nome_fantasia"] or r["razao_social"]
    neg = {"@type": "LocalBusiness", "name": nome,
           "address": {"@type": "PostalAddress",
                       "streetAddress": r["endereco"],
                       "addressLocality": r["municipio"],
                       "addressRegion": r["uf"],
                       "addressCountry": "BR"},
           "identifier": r["cnpj_formatado"]}
    if r["cep"]:
        neg["address"]["postalCode"] = r["cep"]
    fone = r["telefone_9"] if r["telefone_tipo"] == "movel" else r["telefone"]
    if fone:
        neg["telephone"] = fone
    if r["email"]:
        neg["email"] = r["email"]
    if r["site_candidato"]:
        neg["url"] = r["site_candidato"]
    if r["razao_social"] and r["razao_social"] != nome:
        neg["legalName"] = r["razao_social"]
    return {"@type": "ListItem", "position": pos, "item": neg}


# --------------------------------------------------------------------- páginas
def _pagina_cidade(*, vertical, uf, mun, slug, ibge, linhas, css_nome, urls):
    v = VERTICAIS[vertical]
    total = len(linhas)
    base = f"/{vertical}/{uf.lower()}/{slug}/"
    n_paginas = max(1, -(-total // POR_PAGINA))
    for p in range(1, n_paginas + 1):
        fatia = linhas[(p - 1) * POR_PAGINA: p * POR_PAGINA]
        cam = base if p == 1 else f"{base}{p}/"
        url = SITE_URL + cam
        sufixo = "" if p == 1 else f" — página {p} de {n_paginas}"
        titulo = f"{v['rotulo']} em {mun}, {uf}{sufixo} | {SITE_NOME}"
        # frase-resumo factual: é o que um motor de resposta cita
        n_principal = sum(1 for x in linhas if x.get("origem_cnae") == "principal")
        resumo = (f"{_num(total)} {'estabelecimento' if total == 1 else 'estabelecimentos'} "
                  f"de {v['curto']} com cadastro ativo em {mun} ({uf}), "
                  f"com endereço, telefone e e-mail. "
                  + (f"{_num(n_principal)} "
                     f"{'declara' if n_principal == 1 else 'declaram'} esta como "
                     f"atividade principal." if n_principal
                     else "Todos declaram a atividade como secundária."))
        trilha = [("Início", "/"), (v["rotulo"], f"/{vertical}/"),
                  (UF_NOME.get(uf, uf), f"/{vertical}/{uf.lower()}/"), (mun, None)]
        ld = [_trilha_ld(trilha),
              {"@context": "https://schema.org", "@type": "ItemList",
               "name": f"{v['rotulo']} em {mun}, {uf}",
               "numberOfItems": total,
               "itemListElement": [_ficha_ld(r, (p - 1) * POR_PAGINA + i)
                                   for i, r in enumerate(fatia, 1)]}]
        pag = ""
        if n_paginas > 1:
            # Janela em volta da página atual. São Paulo tem 330 páginas; imprimir
            # 330 botões em cada uma delas seria peso morto em toda requisição.
            vis = sorted({1, n_paginas} | set(range(max(1, p - 2),
                                                    min(n_paginas, p + 2) + 1)))
            botoes, anterior = [], 0
            for k in vis:
                if k - anterior > 1:
                    botoes.append('<span class="salto">…</span>')
                alvo = base if k == 1 else f"{base}{k}/"
                botoes.append(f"<strong>{k}</strong>" if k == p
                              else f'<a href="{alvo}">{k}</a>')
                anterior = k
            pag = f'<nav class="paginas" aria-label="Páginas">{"".join(botoes)}</nav>'
        corpo = (f"<h1>{e(v['h1'])} em {e(mun)} - {e(uf)}</h1>"
                 f'<p class="resumo">{e(resumo)}</p>'
                 f'<p class="fonte">{e(FONTE)}'
                 + (f" Código IBGE do município: {e(ibge)}." if ibge else "")
                 + "</p>"
                 f'<ul class="fichas">{"".join(_ficha(r) for r in fatia)}</ul>'
                 + pag)
        _escrever(SITE / cam.strip("/") / "index.html",
                  _shell(titulo=titulo, descricao=resumo, url=url, corpo=corpo,
                         css_nome=css_nome, trilha=trilha, jsonld=ld,
                         vertical_atual=vertical,
                         prev=(SITE_URL + (base if p == 2 else f"{base}{p-1}/")) if p > 1 else None,
                         prox=(SITE_URL + f"{base}{p+1}/") if p < n_paginas else None))
        urls.append(cam)


def _pagina_uf(*, vertical, uf, cidades, css_nome, urls):
    v = VERTICAIS[vertical]
    total = sum(c[2] for c in cidades)
    nome_uf = UF_NOME.get(uf, uf)
    cam = f"/{vertical}/{uf.lower()}/"
    resumo = (f"{_num(total)} estabelecimentos de {v['curto']} com cadastro ativo em "
              f"{_num(len(cidades))} {'cidade' if len(cidades) == 1 else 'cidades'} "
              f"de {nome_uf}.")
    trilha = [("Início", "/"), (v["rotulo"], f"/{vertical}/"), (nome_uf, None)]
    itens = "".join(
        f'<li><a href="/{vertical}/{uf.lower()}/{slug}/">'
        f'<span>{e(mun)}</span><span class="n">{_num(n)}</span></a></li>'
        for mun, slug, n in cidades)
    corpo = (f"<h1>{e(v['h1'])} em {e(nome_uf)}</h1>"
             f'<p class="resumo">{e(resumo)}</p>'
             f'<p class="fonte">{e(FONTE)}</p>'
             f"<h2>Cidades de {e(nome_uf)}</h2>"
             f'<ul class="lugares">{itens}</ul>')
    _escrever(SITE / cam.strip("/") / "index.html",
              _shell(titulo=f"{v['rotulo']} em {nome_uf} | {SITE_NOME}",
                     descricao=resumo, url=SITE_URL + cam, corpo=corpo,
                     css_nome=css_nome, trilha=trilha,
                     jsonld=[_trilha_ld(trilha)], vertical_atual=vertical))
    urls.append(cam)


def _pagina_vertical(*, vertical, por_uf, top_cidades, css_nome, urls):
    v = VERTICAIS[vertical]
    total = sum(n for _, n, _ in por_uf)
    cidades = sum(c for _, _, c in por_uf)
    cam = f"/{vertical}/"
    resumo = (f"{_num(total)} estabelecimentos de {v['curto']} com cadastro ativo no "
              f"Brasil, em {_num(cidades)} cidades e {len(por_uf)} estados.")
    trilha = [("Início", "/"), (v["rotulo"], None)]
    ufs = "".join(
        f'<li><a href="/{vertical}/{uf.lower()}/">'
        f'<span>{e(UF_NOME.get(uf, uf))}</span><span class="n">{_num(n)}</span></a></li>'
        for uf, n, _ in por_uf)
    tops = "".join(
        f'<li><a href="/{vertical}/{uf.lower()}/{slug}/">'
        f'<span>{e(mun)} - {e(uf)}</span><span class="n">{_num(n)}</span></a></li>'
        for uf, mun, slug, n in top_cidades)
    corpo = (f"<h1>{e(v['h1'])} no Brasil</h1>"
             f'<p class="resumo">{e(resumo)}</p>'
             f'<p class="fonte">{e(FONTE)}</p>'
             f"<h2>Maiores cidades</h2><ul class=\"lugares\">{tops}</ul>"
             f"<h2>Todos os estados</h2><ul class=\"lugares\">{ufs}</ul>")
    _escrever(SITE / cam.strip("/") / "index.html",
              _shell(titulo=f"{v['rotulo']} no Brasil, por cidade | {SITE_NOME}",
                     descricao=resumo, url=SITE_URL + cam, corpo=corpo,
                     css_nome=css_nome, trilha=trilha,
                     jsonld=[_trilha_ld(trilha)], vertical_atual=vertical))
    urls.append(cam)


def _pagina_home(*, totais, css_nome, urls):
    total = sum(t for t, _ in totais.values())
    cartoes = "".join(
        f'<li><a href="/{s}/"><strong>{e(VERTICAIS[s]["rotulo"])}</strong>'
        f'<span>{_num(totais[s][0])} estabelecimentos em {_num(totais[s][1])} cidades</span></a></li>'
        for s in VERTICAIS if s in totais)
    resumo = (f"{_num(total)} estabelecimentos com cadastro ativo na Receita Federal, "
              f"organizados em cinco áreas de serviço, por cidade e estado.")
    trilha = [("Início", None)]
    ld = [{"@context": "https://schema.org", "@type": "WebSite",
           "name": SITE_NOME, "url": SITE_URL, "description": SITE_DESCRICAO,
           "inLanguage": "pt-BR"},
          _trilha_ld(trilha)]
    corpo = (f"<h1>{e(SITE_NOME)}</h1>"
             f'<p class="resumo">{e(SITE_DESCRICAO)} {e(resumo)}</p>'
             f'<p class="fonte">{e(FONTE)}</p>'
             f'<ul class="verticais">{cartoes}</ul>')
    _escrever(SITE / "index.html",
              _shell(titulo=f"{SITE_NOME} — instrumentos musicais, som e ensino por cidade",
                     descricao=resumo, url=SITE_URL + "/", corpo=corpo,
                     css_nome=css_nome, trilha=None, jsonld=ld))
    urls.append("/")


# ------------------------------------------------------- arquivos de raiz e SEO
POR_SITEMAP = 45_000   # limite do protocolo é 50.000; folga de segurança


def _sitemaps(urls) -> None:
    fatias = [urls[i:i + POR_SITEMAP] for i in range(0, len(urls), POR_SITEMAP)]
    for i, fatia in enumerate(fatias, 1):
        corpo = "".join(
            f"<url><loc>{e(SITE_URL + u)}</loc><lastmod>{SAFRA_DATA}</lastmod>"
            f"<changefreq>monthly</changefreq></url>" for u in fatia)
        _escrever(SITE / f"sitemap-{i}.xml",
                  '<?xml version="1.0" encoding="UTF-8"?>'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                  f"{corpo}</urlset>")
    indice = "".join(
        f"<sitemap><loc>{SITE_URL}/sitemap-{i}.xml</loc>"
        f"<lastmod>{SAFRA_DATA}</lastmod></sitemap>" for i in range(1, len(fatias) + 1))
    _escrever(SITE / "sitemap.xml",
              '<?xml version="1.0" encoding="UTF-8"?>'
              '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
              f"{indice}</sitemapindex>")
    return len(fatias)


def _robots() -> None:
    _escrever(SITE / "robots.txt",
              "User-agent: *\n"
              "Allow: /\n"
              "\n"
              "# Rastreadores de motor de resposta: liberados de propósito.\n"
              "# O conteúdo é dado público da Receita Federal e queremos ser citados.\n"
              "User-agent: GPTBot\nAllow: /\n"
              "User-agent: OAI-SearchBot\nAllow: /\n"
              "User-agent: ClaudeBot\nAllow: /\n"
              "User-agent: PerplexityBot\nAllow: /\n"
              "User-agent: Google-Extended\nAllow: /\n"
              "\n"
              f"Sitemap: {SITE_URL}/sitemap.xml\n")


def _llms_txt(totais) -> None:
    """llms.txt — resumo do conjunto para motor de resposta.

    É o equivalente do robots.txt para LLM: um mapa curto, em texto, do que o
    site contém e de como as URLs são formadas, para que a citação seja precisa.
    """
    linhas = [
        f"# {SITE_NOME}", "",
        f"> {SITE_DESCRICAO}", "",
        "## O que é",
        "",
        f"Diretório de empresas de serviços ligados a música e áudio no Brasil, "
        f"derivado do Cadastro Nacional da Pessoa Jurídica (CNPJ) da Receita "
        f"Federal, safra {SAFRA} (arquivos de {SAFRA_DATA}). Contém apenas "
        f"estabelecimentos com situação cadastral ativa. Cada registro traz nome "
        f"fantasia, razão social, endereço, CEP, cidade, estado, telefone e e-mail, "
        f"exatamente como constam no cadastro público.",
        "",
        "Limites que valem citar junto com o dado:",
        "",
        "- Os dados refletem o cadastro na data da safra, não uma verificação de campo.",
        "- A Receita não informa o que a empresa atende na prática, apenas o CNAE declarado.",
        "- O cadastro guarda telefone com 8 dígitos. Números móveis aparecem nos dois",
        "  formatos: com o 9º dígito acrescentado pela regra nacional de migração e",
        "  também no formato original de 8 dígitos.",
        "- Não há geocodificação: não publicamos latitude nem longitude.",
        "",
        "## Estrutura das URLs",
        "",
        "- `/{area}/` — a área de serviço no Brasil",
        "- `/{area}/{uf}/` — a área em um estado (sigla em minúsculas)",
        "- `/{area}/{uf}/{cidade}/` — a área em uma cidade (nome sem acento, com hífen)",
        "",
        "## Áreas",
        "",
    ]
    for s, v in VERTICAIS.items():
        if s in totais:
            linhas.append(f"- [{v['rotulo']}]({SITE_URL}/{s}/): {v['h1']}. "
                          f"{_num(totais[s][0])} estabelecimentos em "
                          f"{_num(totais[s][1])} cidades.")
    linhas += ["", "## Contato", "",
               f"Correção ou remoção de registro: {SITE_EMAIL_CONTATO}", ""]
    _escrever(SITE / "llms.txt", "\n".join(linhas))


def _headers(css_nome) -> None:
    """Cache-Control para hospedagem estática (Netlify / Cloudflare Pages).

    O CSS tem hash no nome, então pode ser imutável para sempre. O HTML muda
    quando a safra muda: um dia de cache com revalidação em segundo plano deixa
    o CDN servir tudo da borda sem nunca esperar pela origem.
    """
    _escrever(SITE / "_headers", f"""/estatico/{css_nome}
  Cache-Control: public, max-age=31536000, immutable

/estatico/*
  Cache-Control: public, max-age=31536000, immutable

/*.html
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400

/*
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
""")
    # Apache/cPanel — é o que serve servicos.teclacenter.com.br em produção.
    # Compressão e cache resolvidos aqui; nenhuma outra configuração é necessária,
    # porque o site é só arquivo estático.
    #
    # Deliberadamente SEM redirecionamento http->https na origem: o domínio está
    # atrás da Cloudflare, e se ela estiver em modo Flexible o redirect aqui
    # criaria laço infinito. Quem força HTTPS é a Cloudflare ("Always Use HTTPS").
    _escrever(SITE / ".htaccess", """# Gerado por src/site.py. Não editar à mão: 'make site' sobrescreve.
Options -Indexes -MultiViews
DirectoryIndex index.html
ErrorDocument 404 /404.html
AddDefaultCharset UTF-8

<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/plain text/css text/xml \\
      application/xml application/ld+json application/javascript image/svg+xml
</IfModule>

<IfModule mod_brotli.c>
  AddOutputFilterByType BROTLI_COMPRESS text/html text/plain text/css text/xml \\
      application/xml application/ld+json
</IfModule>

<IfModule mod_headers.c>
  Header always set X-Content-Type-Options "nosniff"
  Header always set Referrer-Policy "strict-origin-when-cross-origin"

  # CSS e imagem levam hash ou nunca mudam: cache imutável.
  <FilesMatch "\\.(css|png|svg|jpg|jpeg|webp|woff2)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </FilesMatch>

  # HTML muda quando a safra muda: uma hora, revalidando em segundo plano.
  <FilesMatch "\\.html$">
    Header set Cache-Control "public, max-age=3600, stale-while-revalidate=86400"
  </FilesMatch>

  <FilesMatch "^(robots\\.txt|llms\\.txt|sitemap.*\\.xml)$">
    Header set Cache-Control "public, max-age=86400"
  </FilesMatch>

  # favicon.ico tem nome fixo (o navegador pede este caminho), então não pode
  # ser imutável: uma semana.
  <FilesMatch "^favicon\\.ico$">
    Header set Cache-Control "public, max-age=604800"
  </FilesMatch>
</IfModule>

# Netlify/Cloudflare Pages leem _headers; Apache não. Não servir esses arquivos.
<FilesMatch "^(_headers|nginx\\.conf\\.exemplo)$">
  Require all denied
</FilesMatch>
""")

    # nginx equivalente, para quem for servir em VPS
    _escrever(SITE / "nginx.conf.exemplo", f"""# Trecho de exemplo. Servir site/ como raiz estática.
# Nenhum processamento por requisição: sendfile + cache de borda.
server {{
  listen 80;
  server_name {SITE_URL.removeprefix('https://')};
  root /var/www/servicos;
  index index.html;
  gzip on; gzip_types text/html text/css application/xml application/ld+json;
  gzip_min_length 512;

  location /estatico/ {{ expires max; add_header Cache-Control "public, immutable"; }}
  location / {{ try_files $uri $uri/ =404; expires 1h; }}
  error_page 404 /404.html;
}}
""")


def _pagina_404(css_nome) -> None:
    corpo = ("<h1>Página não encontrada</h1>"
             '<p class="resumo">O endereço não existe ou mudou. '
             'Comece pelas áreas de serviço no menu acima.</p>')
    _escrever(SITE / "404.html",
              _shell(titulo=f"Página não encontrada | {SITE_NOME}",
                     descricao="Página não encontrada.", url=SITE_URL + "/404.html",
                     corpo=corpo, css_nome=css_nome))


# -------------------------------------------------------------------- principal
def gerar() -> int:
    con = conectar(read_only=True)
    if not con.execute("SELECT count(*) FROM publicacao").fetchone()[0]:
        print("ERRO: view 'publicacao' vazia. Rode 'make carregar'.", file=sys.stderr)
        return 1
    t0 = time.time()
    SITE.mkdir(parents=True, exist_ok=True)
    css_nome, css_texto = css_com_hash()
    _escrever(SITE / "estatico" / css_nome, css_texto)
    global _MARCA, _ICONES
    _MARCA = _preparar_marca()
    _ICONES = _preparar_icones()

    urls, totais = [], {}
    colunas = [d[0] for d in con.execute("SELECT * FROM publicacao LIMIT 0").description]

    for vertical in VERTICAIS:
        por_uf = con.execute("""
            SELECT uf, count(*) AS n, count(DISTINCT municipio_slug) AS c
            FROM publicacao WHERE vertical = ? GROUP BY 1 ORDER BY n DESC
        """, [vertical]).fetchall()
        if not por_uf:
            print(f"  aviso: vertical {vertical} sem registros publicáveis")
            continue
        totais[vertical] = (sum(n for _, n, _ in por_uf),
                            con.execute("SELECT count(DISTINCT uf || municipio_slug) "
                                        "FROM publicacao WHERE vertical = ?",
                                        [vertical]).fetchone()[0])
        top = con.execute("""
            SELECT uf, municipio, municipio_slug, count(*) AS n
            FROM publicacao WHERE vertical = ?
            GROUP BY 1,2,3 ORDER BY n DESC, uf, municipio LIMIT 40
        """, [vertical]).fetchall()
        _pagina_vertical(vertical=vertical, por_uf=por_uf, top_cidades=top,
                         css_nome=css_nome, urls=urls)

        for uf, _n, _c in sorted(por_uf, key=lambda x: x[0]):
            cidades = con.execute("""
                SELECT municipio, municipio_slug, count(*) AS n
                FROM publicacao WHERE vertical = ? AND uf = ?
                GROUP BY 1,2 ORDER BY municipio
            """, [vertical, uf]).fetchall()
            _pagina_uf(vertical=vertical, uf=uf, cidades=cidades,
                       css_nome=css_nome, urls=urls)

            brutas = con.execute("""
                SELECT * FROM publicacao WHERE vertical = ? AND uf = ?
                ORDER BY municipio_slug, origem_cnae,
                         nome_fantasia NULLS LAST, razao_social, id
            """, [vertical, uf]).fetchall()
            grupos = {}
            for linha in brutas:
                r = dict(zip(colunas, linha))
                grupos.setdefault(r["municipio_slug"], []).append(r)
            for slug, linhas in grupos.items():
                _pagina_cidade(vertical=vertical, uf=uf, mun=linhas[0]["municipio"],
                               slug=slug, ibge=linhas[0]["ibge"], linhas=linhas,
                               css_nome=css_nome, urls=urls)
        print(f"  {vertical:<22} {_num(totais[vertical][0]):>9} fichas  "
              f"{_num(totais[vertical][1]):>6} cidades  "
              f"{_num(_paginas_escritas):>7} arquivos até aqui", flush=True)

    _pagina_home(totais=totais, css_nome=css_nome, urls=urls)
    _pagina_404(css_nome)
    n_sitemaps = _sitemaps(urls)
    _robots()
    _llms_txt(totais)
    _headers(css_nome)

    tam = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"\n  {_num(len(urls))} URLs em {_num(_paginas_escritas)} arquivos, "
          f"{n_sitemaps} sitemaps, {tam / 1e6:,.0f} MB".replace(",", "."))
    print(f"site gerado em {time.time() - t0:.0f}s  ->  {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(gerar())
