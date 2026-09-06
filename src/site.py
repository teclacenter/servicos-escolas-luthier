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

A moldura das páginas (<head>, cabeçalho, rodapé) mora em site_moldura.py, e as
páginas por marca em site_marcas.py — os dois geradores compartilham a moldura.
"""
import json
import sys
import time

from config import (POR_PAGINA, SAFRA, SAFRA_DATA, SITE, SITE_DESCRICAO,
                    SITE_EMAIL_CONTATO, SITE_NOME, SITE_URL, UF_EM, UF_NOME,
                    VERTICAIS)
from db import conectar
import site_marcas
from site_marcas import carregar as carregar_marcas
from site_moldura import (FONTE, definir_nav, e, escrever, num,
                          paginas_escritas, preparar_ativos, shell,
                          trilha_ld)
from site_tema import css_com_hash

# A árvore por marca pendura só na assistência técnica: é a única vertical em
# que a pergunta "de que marca?" faz sentido.
VERTICAL_MARCAS = "assistencia-tecnica"


class _SemMarcas:
    """Objeto nulo para as outras verticais: mesma interface, nada a renderizar."""
    disponivel = False
    bloco_cidade = staticmethod(lambda *a, **k: "")
    bloco_vertical = staticmethod(lambda *a, **k: "")
    bloco_home = staticmethod(lambda *a, **k: "")


# Numeral por extenso para a frase da home. Só até dez: acima disso o algarismo
# lê melhor, e não há por que carregar uma biblioteca para isso.
_EXTENSO = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco",
            6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez"}


SEM_MARCAS = _SemMarcas()


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
def _pagina_cidade(*, vertical, uf, mun, slug, ibge, linhas, css_nome, urls, marcas):
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
        resumo = (f"{num(total)} {'estabelecimento' if total == 1 else 'estabelecimentos'} "
                  f"de {v['curto']} com cadastro ativo em {mun} ({uf}), "
                  f"com endereço, telefone e e-mail. "
                  + (f"{num(n_principal)} "
                     f"{'declara' if n_principal == 1 else 'declaram'} esta como "
                     f"atividade principal." if n_principal
                     else "Todos declaram a atividade como secundária."))
        trilha = [("Início", "/"), (v["rotulo"], f"/{vertical}/"),
                  (UF_NOME.get(uf, uf), f"/{vertical}/{uf.lower()}/"), (mun, None)]
        ld = [trilha_ld(trilha),
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
                 + pag
                 # Só na primeira página: nas seguintes seria o mesmo bloco
                 # repetido, e a página 2 não é a que compete pela busca.
                 + (marcas.bloco_cidade(uf, slug, mun) if p == 1 else ""))
        escrever(SITE / cam.strip("/") / "index.html",
                  shell(titulo=titulo, descricao=resumo, url=url, corpo=corpo,
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
    em_uf = UF_EM.get(uf, f"em {nome_uf}")
    resumo = (f"{num(total)} estabelecimentos de {v['curto']} com cadastro ativo em "
              f"{num(len(cidades))} {'cidade' if len(cidades) == 1 else 'cidades'} "
              f"de {nome_uf}.")
    trilha = [("Início", "/"), (v["rotulo"], f"/{vertical}/"), (nome_uf, None)]
    itens = "".join(
        f'<li><a href="/{vertical}/{uf.lower()}/{slug}/">'
        f'<span>{e(mun)}</span><span class="n">{num(n)}</span></a></li>'
        for mun, slug, n in cidades)
    corpo = (f"<h1>{e(v['h1'])} {e(em_uf)}</h1>"
             f'<p class="resumo">{e(resumo)}</p>'
             f'<p class="fonte">{e(FONTE)}</p>'
             f"<h2>Cidades de {e(nome_uf)}</h2>"
             f'<ul class="lugares">{itens}</ul>')
    escrever(SITE / cam.strip("/") / "index.html",
              shell(titulo=f"{v['rotulo']} {em_uf} ({uf}) | {SITE_NOME}",
                     descricao=resumo, url=SITE_URL + cam, corpo=corpo,
                     css_nome=css_nome, trilha=trilha,
                     jsonld=[trilha_ld(trilha)], vertical_atual=vertical))
    urls.append(cam)


def _pagina_vertical(*, vertical, por_uf, top_cidades, css_nome, urls, marcas):
    v = VERTICAIS[vertical]
    total = sum(n for _, n, _ in por_uf)
    cidades = sum(c for _, _, c in por_uf)
    cam = f"/{vertical}/"
    resumo = (f"{num(total)} estabelecimentos de {v['curto']} com cadastro ativo no "
              f"Brasil, em {num(cidades)} cidades e {len(por_uf)} estados.")
    trilha = [("Início", "/"), (v["rotulo"], None)]
    ufs = "".join(
        f'<li><a href="/{vertical}/{uf.lower()}/">'
        f'<span>{e(UF_NOME.get(uf, uf))}</span><span class="n">{num(n)}</span></a></li>'
        for uf, n, _ in por_uf)
    tops = "".join(
        f'<li><a href="/{vertical}/{uf.lower()}/{slug}/">'
        f'<span>{e(mun)} - {e(uf)}</span><span class="n">{num(n)}</span></a></li>'
        for uf, mun, slug, n in top_cidades)
    corpo = (f"<h1>{e(v['h1'])} no Brasil</h1>"
             f'<p class="resumo">{e(resumo)}</p>'
             f'<p class="fonte">{e(FONTE)}</p>'
             f"<h2>Maiores cidades</h2><ul class=\"lugares\">{tops}</ul>"
             f"<h2>Todos os estados</h2><ul class=\"lugares\">{ufs}</ul>"
             + marcas.bloco_vertical())
    escrever(SITE / cam.strip("/") / "index.html",
              shell(titulo=f"{v['rotulo']} no Brasil, por cidade | {SITE_NOME}",
                     descricao=resumo, url=SITE_URL + cam, corpo=corpo,
                     css_nome=css_nome, trilha=trilha,
                     jsonld=[trilha_ld(trilha)], vertical_atual=vertical))
    urls.append(cam)


def _pagina_home(*, totais, css_nome, urls, marcas):
    total = sum(t for t, _ in totais.values())
    cartoes = "".join(
        f'<li><a href="/{s}/"><strong>{e(VERTICAIS[s]["rotulo"])}</strong>'
        f'<span>{num(totais[s][0])} estabelecimentos em {num(totais[s][1])} cidades</span></a></li>'
        for s in VERTICAIS if s in totais)
    # o número de áreas era fixo no texto e ficou errado quando entrou a sexta
    areas = _EXTENSO.get(len(totais), str(len(totais)))
    resumo = (f"{num(total)} estabelecimentos com cadastro ativo na Receita Federal, "
              f"organizados em {areas} áreas de serviço, por cidade e estado."
              + (f" Mais {num(marcas.oficinas())} oficinas de assistência "
                 f"autorizada de {len(marcas.postos)} marcas."
                 if marcas.disponivel else ""))
    trilha = [("Início", None)]
    ld = [{"@context": "https://schema.org", "@type": "WebSite",
           "name": SITE_NOME, "url": SITE_URL, "description": SITE_DESCRICAO,
           "inLanguage": "pt-BR"},
          trilha_ld(trilha)]
    corpo = (f"<h1>{e(SITE_NOME)}</h1>"
             f'<p class="resumo">{e(SITE_DESCRICAO)} {e(resumo)}</p>'
             f'<p class="fonte">{e(FONTE)}</p>'
             f'<ul class="verticais">{cartoes}</ul>'
             + marcas.bloco_home())
    escrever(SITE / "index.html",
              shell(titulo=f"{SITE_NOME} — instrumentos musicais, som e ensino por cidade",
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
        escrever(SITE / f"sitemap-{i}.xml",
                  '<?xml version="1.0" encoding="UTF-8"?>'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                  f"{corpo}</urlset>")
    indice = "".join(
        f"<sitemap><loc>{SITE_URL}/sitemap-{i}.xml</loc>"
        f"<lastmod>{SAFRA_DATA}</lastmod></sitemap>" for i in range(1, len(fatias) + 1))
    escrever(SITE / "sitemap.xml",
              '<?xml version="1.0" encoding="UTF-8"?>'
              '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
              f"{indice}</sitemapindex>")
    return len(fatias)


def _robots() -> None:
    escrever(SITE / "robots.txt",
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


def _llms_txt(totais, marcas) -> None:
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
                          f"{num(totais[s][0])} estabelecimentos em "
                          f"{num(totais[s][1])} cidades.")
    linhas += marcas.linhas_llms()
    linhas += ["", "## Contato", "",
               f"Correção ou remoção de registro: {SITE_EMAIL_CONTATO}", ""]
    escrever(SITE / "llms.txt", "\n".join(linhas))


def _headers(css_nome) -> None:
    """Cache-Control para hospedagem estática (Netlify / Cloudflare Pages).

    O CSS tem hash no nome, então pode ser imutável para sempre. O HTML muda
    quando a safra muda: um dia de cache com revalidação em segundo plano deixa
    o CDN servir tudo da borda sem nunca esperar pela origem.
    """
    escrever(SITE / "_headers", f"""/estatico/{css_nome}
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
    escrever(SITE / ".htaccess", """# Gerado por src/site.py. Não editar à mão: 'make site' sobrescreve.
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
    escrever(SITE / "nginx.conf.exemplo", f"""# Trecho de exemplo. Servir site/ como raiz estática.
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
    escrever(SITE / "404.html",
              shell(titulo=f"Página não encontrada | {SITE_NOME}",
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
    # estatico/ é reescrito inteiro a cada execução (CSS, logotipo, favicons).
    # Sem limpar, cada mudança de tema deixa o arquivo com o hash ANTIGO para
    # trás — e o deploy publica os dois, porque só empacota o diretório.
    for velho in sorted((SITE / "estatico").glob("*")):
        velho.unlink()
    css_nome, css_texto = css_com_hash()
    escrever(SITE / "estatico" / css_nome, css_texto)
    preparar_ativos()
    # As redes por marca vêm de outra origem (o site de cada fabricante) e são
    # opcionais: sem 'make coletar-marcas', o site sai exatamente como antes.
    marcas = carregar_marcas(con)
    if not marcas.disponivel:
        print("  aviso: sem redes por marca no banco -> rode "
              "'make coletar-marcas && make carregar-marcas'")

    # O menu é montado uma vez, antes da primeira página. A categoria "por
    # marca" entra logo depois da vertical em que vive, para a relação entre as
    # duas ficar óbvia — e só entra se houver marca coletada, senão seria um
    # item de menu apontando para 404.
    itens_nav = [(s, v["rotulo"], f"/{s}/") for s, v in VERTICAIS.items()]
    if marcas.disponivel:
        pos = next(i for i, (s, _, _) in enumerate(itens_nav)
                   if s == VERTICAL_MARCAS) + 1
        itens_nav.insert(pos, (site_marcas.NAV_CHAVE, site_marcas.NAV_ROTULO,
                               site_marcas.HUB))
    definir_nav(itens_nav)

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
                         css_nome=css_nome, urls=urls,
                         marcas=marcas if vertical == VERTICAL_MARCAS else SEM_MARCAS)

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
                               css_nome=css_nome, urls=urls,
                               marcas=marcas if vertical == VERTICAL_MARCAS else SEM_MARCAS)
        print(f"  {vertical:<22} {num(totais[vertical][0]):>9} fichas  "
              f"{num(totais[vertical][1]):>6} cidades  "
              f"{num(paginas_escritas()):>7} arquivos até aqui", flush=True)

    marcas.gerar(css_nome=css_nome, urls=urls)
    if marcas.disponivel:
        print(f"  {'marcas':<22} {num(len(marcas.postos)):>9} marcas   "
              f"{num(len(marcas.cidades)):>6} cidades  "
              f"{num(paginas_escritas()):>7} arquivos até aqui", flush=True)

    _pagina_home(totais=totais, css_nome=css_nome, urls=urls, marcas=marcas)
    _pagina_404(css_nome)
    n_sitemaps = _sitemaps(urls)
    _robots()
    _llms_txt(totais, marcas)
    _headers(css_nome)

    tam = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"\n  {num(len(urls))} URLs em {num(paginas_escritas())} arquivos, "
          f"{n_sitemaps} sitemaps, {tam / 1e6:,.0f} MB".replace(",", "."))
    print(f"site gerado em {time.time() - t0:.0f}s  ->  {SITE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(gerar())
