"""Páginas de assistência técnica POR MARCA.

Por que uma árvore separada: quem quebrou um teclado não procura "assistência
técnica em Campinas", procura "assistência técnica Roland" e, no máximo,
"assistência técnica Roland São Paulo". A árvore por cidade que o site já tinha
responde a segunda pergunta pela metade e a primeira, nada. Estas páginas
respondem as duas, e as duas árvores se cruzam: toda página de cidade ganha a
lista de marcas com rede ali, e toda página de marca em uma cidade aponta de
volta para a lista completa da cidade.

    /assistencia-tecnica/marcas/                       todas as marcas
    /assistencia-tecnica/marca/roland/                 a marca no Brasil
    /assistencia-tecnica/marca/roland/sp/              a marca em um estado
    /assistencia-tecnica/marca/roland/sp/campinas/     a marca em uma cidade

O prefixo `marca/` existe para não competir com /assistencia-tecnica/{uf}/: hoje
nenhuma marca tem slug de duas letras, mas depender disso seria deixar uma
armadilha para quem cadastrar a próxima.

Sobre conteúdo repetido: ProShows e Sonotec credenciam UMA rede para dezenas de
marcas, então a lista de oficinas de Behringer e a de Midas são a mesma. Isso é
o fato, não um truque — e as páginas dizem isso na cara, nomeando o distribuidor
e listando as marcas irmãs. Esconder a coincidência é que seria enganoso.

Cada página cita a origem: quem publica a rede, o endereço da página oficial e a
data em que foi consultada. É o que permite ao leitor (e a um motor de resposta)
conferir, e é o que separa um diretório de uma cópia.
"""
import json

from config import SITE, SITE_NOME, SITE_URL, UF_EM, UF_NOME
from marcas import FONTES, MARCAS, marcas_da_fonte
from site_moldura import e, escrever, num, q, shell, trilha_ld

VERTICAL = "assistencia-tecnica"        # a árvore de marcas pendura aqui
RAIZ_MARCAS = f"/{VERTICAL}/marca"
HUB = f"/{VERTICAL}/marcas/"
ROTULO_VERTICAL = "Assistência técnica"

# A categoria no menu. Chave própria (e não a da vertical) para que o item
# marcado como corrente seja "Assistência por marca", não "Assistência técnica".
NAV_CHAVE = "marcas"
NAV_ROTULO = "Assistência por marca"


def _data_br(d) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


# ------------------------------------------------------------------- carregar
def carregar(con):
    """Lê tudo de uma vez. São ~800 oficinas e ~6.000 pares: cabe na memória, e
    consultar o banco por página custaria milhares de idas para nada."""
    if not con.execute("SELECT count(*) FROM duckdb_tables() "
                       "WHERE table_name = 'marca_posto'").fetchone()[0]:
        return Marcas({}, {}, {})
    colunas = [d[0] for d in
               con.execute("SELECT * FROM publicacao_marca LIMIT 0").description]
    postos = {}          # marca -> uf -> municipio_slug|None -> [ficha]
    cidades = {}         # (uf, slug) -> [(marca, total)]
    nomes = {}           # (uf, slug) -> nome do município
    for linha in con.execute("SELECT * FROM publicacao_marca").fetchall():
        r = dict(zip(colunas, linha))
        postos.setdefault(r["marca"], {}).setdefault(r["uf"], {}) \
              .setdefault(r["municipio_slug"], []).append(r)
        if r["municipio_slug"]:
            nomes[(r["uf"], r["municipio_slug"])] = r["municipio"]
    for marca, por_uf in postos.items():
        for uf, por_cidade in por_uf.items():
            for slug, fichas in por_cidade.items():
                if slug:
                    cidades.setdefault((uf, slug), []).append((marca, len(fichas)))
    for chave in cidades:
        cidades[chave].sort(key=lambda x: MARCAS[x[0]]["nome"].lower())
    return Marcas(postos, cidades, nomes)


class Marcas:
    def __init__(self, postos, cidades, nomes):
        self.postos = postos
        self.cidades = cidades       # (uf, slug) -> [(marca, total)]
        self.nomes = nomes

    @property
    def disponivel(self) -> bool:
        return bool(self.postos)

    def total(self, marca) -> int:
        return sum(len(f) for uf in self.postos[marca].values() for f in uf.values())

    def ordenadas(self):
        """Marcas com rede, da maior para a menor. Empate: nome."""
        return sorted(self.postos, key=lambda m: (-self.total(m),
                                                  MARCAS[m]["nome"].lower()))

    # --------------------------------------------------------------- fragmentos
    def bloco_cidade(self, uf, slug, municipio) -> str:
        """Bloco 'por marca' para a página geral da cidade. '' se não houver."""
        lista = self.cidades.get((uf, slug))
        if not lista:
            return ""
        itens = "".join(
            f'<li><a href="{RAIZ_MARCAS}/{m}/{uf.lower()}/{slug}/">'
            f'<span>{e(MARCAS[m]["nome"])}</span><span class="n">{n}</span></a></li>'
            for m, n in lista)
        return (f'<h2 id="por-marca">Assistência autorizada por marca em '
                f'{e(municipio)}</h2>'
                f'<p class="resumo">{len(lista)} '
                f'{"marca tem" if len(lista) == 1 else "marcas têm"} oficina '
                f'credenciada em {e(municipio)}, segundo a rede publicada pelo '
                f'próprio fabricante ou distribuidor. O número ao lado é a '
                f'quantidade de oficinas.</p>'
                f'<ul class="lugares">{itens}</ul>')

    def bloco_vertical(self) -> str:
        """Chamada para o hub de marcas, na página nacional da vertical."""
        if not self.disponivel:
            return ""
        # uma marca por distribuidor: citar sete da ProShows seguidas daria a
        # impressão de sete redes onde há uma
        vistos, exemplos = set(), []
        for m in self.destaques():
            fonte = MARCAS[m]["fonte"]
            if fonte not in vistos:
                vistos.add(fonte)
                exemplos.append(MARCAS[m]["nome"])
        return (f'<h2>Assistência autorizada por marca</h2>'
                f'<p class="resumo">Além da lista por cidade, o site publica a '
                f'rede credenciada de {len(self.postos)} marcas — '
                f'{e(", ".join(exemplos))} e outras — com o que o próprio '
                f'fabricante ou distribuidor informa.</p>'
                f'<p><a class="botao" href="{HUB}">Ver as '
                f'{len(self.postos)} marcas</a></p>')

    def destaques(self) -> list:
        """Marcas reconhecíveis pelo nome, em ordem alfabética.

        Alfabética de propósito: não temos volume de busca, e ordenar por
        "mais procuradas" seria inventar um dado. O número de oficinas, que é
        medido, aparece ao lado de cada uma.
        """
        return sorted((m for m in self.postos if MARCAS[m]["destaque"]),
                      key=lambda m: MARCAS[m]["nome"].lower())

    def bloco_home(self) -> str:
        """Seção da página inicial. A categoria entra na home como as verticais,
        mas com o número que faz sentido aqui: marcas e oficinas, não CNPJ."""
        if not self.disponivel:
            return ""
        oficinas = self.oficinas()
        itens = "".join(
            f'<li><a href="{RAIZ_MARCAS}/{m}/"><span>{e(MARCAS[m]["nome"])}</span>'
            f'<span class="n">{num(self.total(m))}</span></a></li>'
            for m in self.destaques())
        return (f'<h2>Assistência técnica autorizada por marca</h2>'
                f'<p class="resumo">{num(oficinas)} oficinas credenciadas por '
                f'{len(self.postos)} marcas de instrumentos musicais e áudio, '
                f'por estado e cidade. Origem separada da Receita Federal: é o '
                f'que cada fabricante ou distribuidor publica no próprio site. '
                f'O número ao lado é a quantidade de oficinas da marca.</p>'
                f'<ul class="lugares">{itens}</ul>'
                f'<p><a class="botao" href="{HUB}">Ver as '
                f'{len(self.postos)} marcas</a></p>')

    def oficinas(self) -> int:
        """Oficinas distintas. Não é a soma por marca: uma oficina da ProShows
        conta uma vez, e não dezenove."""
        return len({p["posto_id"] for m in self.postos
                    for uf in self.postos[m].values()
                    for fichas in uf.values() for p in fichas})

    def linhas_llms(self) -> list:
        """Trecho do llms.txt. Motor de resposta lê isto antes das páginas."""
        if not self.disponivel:
            return []
        linhas = [
            "", "## Assistência técnica autorizada, por marca", "",
            "Segunda origem de dados do site, INDEPENDENTE da Receita Federal: a "
            "rede de assistência credenciada que cada fabricante ou distribuidor "
            "publica no próprio site. Cada página nomeia a origem, o endereço "
            "oficial consultado e a data da consulta.", "",
            "- `/assistencia-tecnica/marcas/` — todas as marcas",
            "- `/assistencia-tecnica/marca/{marca}/` — a marca no Brasil",
            "- `/assistencia-tecnica/marca/{marca}/{uf}/` — a marca em um estado",
            "- `/assistencia-tecnica/marca/{marca}/{uf}/{cidade}/` — a marca em uma cidade",
            "",
            "Limite que vale citar junto: distribuidor que representa várias "
            "marcas credencia UMA rede para todas elas. A lista de oficinas de "
            "marcas do mesmo distribuidor é, portanto, a mesma lista.", "",
        ]
        for m in self.ordenadas():
            info = MARCAS[m]
            n = self.total(m)
            linhas.append(
                f"- [{info['nome']}]({SITE_URL}{RAIZ_MARCAS}/{m}/): {n} "
                f"{'oficina' if n == 1 else 'oficinas'} autorizadas, rede "
                f"publicada por {FONTES[info['fonte']]['titular']}.")
        return linhas

    # ------------------------------------------------------------------ páginas
    def gerar(self, *, css_nome, urls) -> None:
        if not self.disponivel:
            return
        self._hub(css_nome, urls)
        for marca in self.ordenadas():
            self._marca(marca, css_nome, urls)
            for uf in sorted(self.postos[marca]):
                self._marca_uf(marca, uf, css_nome, urls)
                for slug, fichas in sorted(self.postos[marca][uf].items(),
                                           key=lambda x: x[0] or ""):
                    if slug:
                        self._marca_cidade(marca, uf, slug, fichas, css_nome, urls)

    # --------------------------------------------------------------- utilidades
    def _fonte_frase(self, marca) -> str:
        """A frase de proveniência, igual em toda página da marca."""
        info = MARCAS[marca]
        f = FONTES[info["fonte"]]
        datas = {p["coletado_em"] for uf in self.postos[marca].values()
                 for fichas in uf.values() for p in fichas}
        data = _data_br(max(d for d in datas if d)) if any(datas) else ""
        return (f"Rede publicada por {f['titular']} em {f['pagina']}"
                + (f", consultada em {data}." if data else ".")
                + " Este site reproduz a lista para facilitar a busca; a lista "
                  "oficial é a do fabricante.")

    def _irmas(self, marca) -> list:
        return [s for s in marcas_da_fonte(MARCAS[marca]["fonte"])
                if s != marca and s in self.postos]

    def _sobre(self, marca) -> str:
        """Parágrafo do que a marca é e de quem responde pela rede no Brasil."""
        info = MARCAS[marca]
        f = FONTES[info["fonte"]]
        partes = []
        if info["sobre"]:
            partes.append(f"A {info['nome']} fabrica {info['sobre']}.")
        if info["linhas"]:
            partes.append("A mesma rede atende as linhas "
                          + ", ".join(info["linhas"]) + ".")
        irmas = self._irmas(marca)
        if irmas:
            # o fato central destas páginas: a rede é compartilhada
            partes.append(
                f"No Brasil quem credencia a assistência é {f['titular']}, que "
                f"distribui {info['nome']} e mais {len(irmas)} "
                f"{'marca' if len(irmas) == 1 else 'marcas'} — a mesma oficina "
                f"autorizada atende todas elas.")
        else:
            partes.append(f"A rede é credenciada por {f['titular']}, sob o nome "
                          f"“{f['termo']}”.")
        return " ".join(partes)

    def _ficha(self, r) -> str:
        partes = [f'<h3>{e(r["nome"])}</h3>']
        end = [x for x in (r["endereco"], r["cidade_uf"]) if x]
        if r["cep"]:
            end.append("CEP: " + r["cep"])
        if end:
            partes.append("<address>" + "<br>".join(e(x) for x in end) + "</address>")

        contato = []
        for e164, tipo, fmt, e164_9, fmt_9 in (
            (r["telefone"], r["telefone_tipo"], r["telefone_formatado"],
             r["telefone_9"], r["telefone_9_formatado"]),
            (r["telefone_2"], r["telefone_2_tipo"], r["telefone_2_formatado"],
             r["telefone_2_9"], r["telefone_2_9_formatado"]),
        ):
            if not e164:
                continue
            rot = "Cel:" if tipo == "movel" else "Tel:"
            # aqui o número já vem do fabricante no formato atual; quando ainda
            # tiver 8 dígitos, o com 9 é mostrado na frente, como no resto do site
            alvo, mostra = (e164_9, fmt_9) if e164_9 else (e164, fmt)
            extra = (f'<span class="rot">ou {e(fmt)} (formato antigo)</span>'
                     if e164_9 else "")
            contato.append(f'<a href="tel:{e(alvo)}"><span class="rot">{rot}</span> '
                           f'{e(mostra)}</a>{extra}')
        if r["email"]:
            contato.append(f'<a href="mailto:{e(r["email"])}">{e(r["email"])}</a>')
        if r["site"]:
            rotulo = r["site"].removeprefix("https://").removeprefix("http://")
            contato.append(f'<a href="{e(r["site"])}" rel="nofollow noopener">'
                           f'{e(rotulo.rstrip("/"))}</a>')
        if contato:
            partes.append('<p class="contato">' + "".join(contato) + "</p>")
        if r["contato"]:
            partes.append(f'<p class="razao">Falar com {e(r["contato"])}</p>')
        if r["horario"]:
            partes.append(f'<p class="razao">Atendimento: {e(r["horario"])}</p>')
        if r["segmento"]:
            partes.append(f'<p class="selo">Atende: {e(r["segmento"])}</p>')
        if r["cnpj_formatado"]:
            # casamento por telefone com a base da Receita: diz que a oficina
            # existe como empresa ativa, e liga a ficha à outra árvore do site
            partes.append(
                f'<p class="cnpj">CNPJ {e(r["cnpj_formatado"])} — cadastro ativo '
                f'na Receita Federal</p>')
        return '<li class="ficha"><article>' + "".join(partes) + "</article></li>"

    def _ficha_ld(self, r, marca, pos) -> dict:
        neg = {"@type": "LocalBusiness", "name": r["nome"],
               "makesOffer": {
                   "@type": "Offer",
                   "itemOffered": {
                       "@type": "Service",
                       "name": f"Assistência técnica autorizada {MARCAS[marca]['nome']}",
                       "serviceType": "Assistência técnica autorizada",
                       "brand": {"@type": "Brand", "name": MARCAS[marca]["nome"]}}}}
        endereco = {"@type": "PostalAddress", "addressCountry": "BR",
                    "addressRegion": r["uf"]}
        if r["endereco"]:
            endereco["streetAddress"] = r["endereco"]
        if r["municipio"]:
            endereco["addressLocality"] = r["municipio"]
        if r["cep"]:
            endereco["postalCode"] = r["cep"]
        neg["address"] = endereco
        fone = r["telefone_9"] or r["telefone"]
        if fone:
            neg["telephone"] = fone
        if r["email"]:
            neg["email"] = r["email"]
        if r["site"]:
            neg["url"] = r["site"]
        if r["cnpj_formatado"]:
            neg["identifier"] = r["cnpj_formatado"]
        return {"@type": "ListItem", "position": pos, "item": neg}

    def _lista(self, fichas, marca, titulo=None) -> str:
        cabeca = f"<h2>{e(titulo)}</h2>" if titulo else ""
        return (cabeca + '<ul class="fichas">'
                + "".join(self._ficha(r) for r in fichas) + "</ul>")

    def _rodape_marca(self, marca) -> str:
        """Marcas irmãs e volta para o hub. Fecha a malha de links internos."""
        irmas = self._irmas(marca)
        if not irmas:
            return f'<p class="fonte"><a href="{HUB}">Todas as marcas</a></p>'
        itens = "".join(
            f'<li><a href="{RAIZ_MARCAS}/{s}/"><span>{e(MARCAS[s]["nome"])}</span>'
            f'<span class="n">{num(self.total(s))}</span></a></li>' for s in irmas)
        return (f'<h2>Mesma rede autorizada</h2>'
                f'<p class="resumo">Estas marcas são atendidas pelas mesmas '
                f'oficinas, porque têm o mesmo distribuidor no Brasil.</p>'
                f'<ul class="lugares">{itens}</ul>'
                f'<p class="fonte"><a href="{HUB}">Todas as marcas</a></p>')

    # ------------------------------------------------------------------- hub
    def _hub(self, css_nome, urls) -> None:
        """A página da categoria.

        O trabalho dela é um só: quem chega aqui sabe a marca e quer achá-la.
        Por isso a lista A-Z completa vem primeiro, com o distribuidor embaixo
        do nome — e a explicação das redes compartilhadas vem depois, em prosa,
        sem repetir as 43 marcas numa segunda lista.
        """
        oficinas = self.oficinas()
        cidades = len({(uf, s) for m in self.postos
                       for uf, c in self.postos[m].items() for s in c if s})
        resumo = (f"Rede de assistência técnica autorizada de {len(self.postos)} "
                  f"marcas de instrumentos musicais e áudio no Brasil: "
                  f"{num(oficinas)} oficinas credenciadas em {num(cidades)} "
                  f"cidades, com endereço e telefone, como o próprio fabricante "
                  f"ou distribuidor publica.")
        trilha = [("Início", "/"), (ROTULO_VERTICAL, f"/{VERTICAL}/"),
                  ("Por marca", None)]

        # --- A-Z: o índice, que é o que a página existe para ser
        def _linha_az(m):
            nome = MARCAS[m]["nome"]
            titular = FONTES[MARCAS[m]["fonte"]]["titular"]
            # "Casio / Casio" não informa nada: o distribuidor só aparece
            # quando é outro nome que o da marca
            legenda = f"<small>{e(titular)}</small>" if nome not in titular else ""
            return (f'<li><a href="{RAIZ_MARCAS}/{m}/">'
                    f'<span>{e(nome)}{legenda}</span>'
                    f'<span class="n">{num(self.total(m))}</span></a></li>')

        az = "".join(_linha_az(m) for m in
                     sorted(self.postos, key=lambda m: MARCAS[m]["nome"].lower()))

        # --- quem credencia: prosa, uma vez por distribuidor
        redes = []
        for fonte in sorted(FONTES, key=lambda f: FONTES[f]["titular"].lower()):
            desta = [m for m in self.postos if MARCAS[m]["fonte"] == fonte]
            if not desta:
                continue
            f = FONTES[fonte]
            n = num(self.total(desta[0]))
            if len(desta) == 1:
                # quando o distribuidor É a marca, "credencia a rede de Casio"
                # depois de "Casio" fica redundante
                marca_nome = MARCAS[desta[0]]["nome"]
                de_quem = ("a própria rede" if marca_nome in f["titular"]
                           else f"a rede de {e(marca_nome)}")
                texto = (f"<strong>{e(f['titular'])}</strong> credencia {de_quem}: "
                         f"{n} oficinas, sob o nome “{e(f['termo'])}”.")
            else:
                texto = (f"<strong>{e(f['titular'])}</strong> distribui "
                         f"{len(desta)} marcas e credencia UMA rede para todas: "
                         f"as mesmas {n} oficinas atendem o portfólio inteiro. "
                         f"É por isso que a lista de "
                         f"{e(MARCAS[self._representante(fonte)]['nome'])} e a de "
                         f"{e(MARCAS[self._representante(fonte, 1)]['nome'])} são "
                         f"a mesma lista.")
            redes.append(f'<p class="resumo">{texto} '
                         f'<a href="{e(f["pagina"])}" rel="nofollow noopener">'
                         f'Página oficial</a>.</p>')

        nao_publicadas = sorted(MARCAS[s]["nome"] for s, m in MARCAS.items()
                                if FONTES[m["fonte"]].get("bloqueada"))
        aviso = ""
        if nao_publicadas:
            bloqueada = next(f for f in FONTES.values() if f.get("bloqueada"))
            aviso = (f'<h2>Marcas que ainda não publicamos</h2>'
                     f'<p class="resumo">{e(", ".join(nao_publicadas))}. '
                     f'O localizador oficial dessas marcas não permite leitura '
                     f'automatizada, e não vamos contornar isso. Consulte direto '
                     f'em <a href="{e(bloqueada["pagina"])}" '
                     f'rel="nofollow noopener">{e(bloqueada["titular"])}</a>.</p>')

        ld = [trilha_ld(trilha),
              {"@context": "https://schema.org", "@type": "ItemList",
               "name": "Marcas com assistência técnica autorizada no Brasil",
               "numberOfItems": len(self.postos),
               "itemListElement": [
                   {"@type": "ListItem", "position": i,
                    "url": SITE_URL + f"{RAIZ_MARCAS}/{m}/",
                    "item": {"@type": "Brand", "name": MARCAS[m]["nome"]}}
                   for i, m in enumerate(
                       sorted(self.postos, key=lambda m: MARCAS[m]["nome"].lower()), 1)]}]

        corpo = (f"<h1>Assistência técnica autorizada por marca</h1>"
                 f'<p class="resumo">{e(resumo)}</p>'
                 f'<p class="fonte">Esta seção NÃO vem da Receita Federal: cada '
                 f'rede é a lista publicada pelo fabricante ou pelo distribuidor '
                 f'oficial, e cada página diz qual é a origem e quando foi '
                 f'consultada.</p>'
                 f'<h2>Todas as marcas, de A a Z</h2>'
                 f'<p class="resumo">O nome menor é quem credencia a rede no '
                 f'Brasil; o número é a quantidade de oficinas autorizadas.</p>'
                 f'<ul class="lugares az">{az}</ul>'
                 f'<h2>Quem credencia cada rede</h2>'
                 + "".join(redes) + aviso)
        escrever(SITE / HUB.strip("/") / "index.html",
                 shell(titulo=f"Assistência técnica autorizada por marca — "
                              f"{len(self.postos)} marcas | {SITE_NOME}",
                       descricao=resumo, url=SITE_URL + HUB, corpo=corpo,
                       css_nome=css_nome, trilha=trilha, jsonld=ld,
                       vertical_atual=NAV_CHAVE))
        urls.append(HUB)

    def _representante(self, fonte, pos=0) -> str:
        """Marca que representa o distribuidor num exemplo. Prefere as
        reconhecíveis; sem elas, a ordem alfabética do catálogo."""
        desta = [m for m in marcas_da_fonte(fonte) if m in self.postos]
        preferidas = [m for m in desta if MARCAS[m]["destaque"]] or desta
        return preferidas[pos % len(preferidas)]

    # ----------------------------------------------------------- marca (Brasil)
    def _marca(self, marca, css_nome, urls) -> None:
        info = MARCAS[marca]
        nome = info["nome"]
        por_uf = self.postos[marca]
        total = self.total(marca)
        n_cidades = len({(uf, s) for uf, c in por_uf.items() for s in c if s})
        cam = f"{RAIZ_MARCAS}/{marca}/"
        resumo = (f"{num(total)} {'oficina' if total == 1 else 'oficinas'} de "
                  f"assistência técnica autorizada {nome} no Brasil, em "
                  f"{num(n_cidades)} {'cidade' if n_cidades == 1 else 'cidades'} "
                  f"e {len(por_uf)} {'estado' if len(por_uf) == 1 else 'estados'}, "
                  f"com endereço e telefone.")
        trilha = [("Início", "/"), (ROTULO_VERTICAL, f"/{VERTICAL}/"),
                  ("Por marca", HUB), (nome, None)]

        estados = "".join(
            f'<li><a href="{cam}{uf.lower()}/"><span>{e(UF_NOME.get(uf, uf))}</span>'
            f'<span class="n">{num(sum(len(f) for f in c.values()))}</span></a></li>'
            for uf, c in sorted(por_uf.items(),
                                key=lambda x: (-sum(len(f) for f in x[1].values()), x[0])))
        maiores = sorted(
            ((uf, s, len(f)) for uf, c in por_uf.items() for s, f in c.items() if s),
            key=lambda x: (-x[2], x[0], x[1]))[:24]
        tops = "".join(
            f'<li><a href="{cam}{uf.lower()}/{s}/">'
            f'<span>{e(self.nomes[(uf, s)])} - {e(uf)}</span>'
            f'<span class="n">{n}</span></a></li>' for uf, s, n in maiores)

        ld = [trilha_ld(trilha),
              {"@context": "https://schema.org", "@type": "Brand", "name": nome,
               "description": info["sobre"] or
               f"Marca distribuída no Brasil por {FONTES[info['fonte']]['titular']}.",
               "subjectOf": {"@type": "WebPage", "@id": SITE_URL + cam,
                             "name": f"Assistência técnica {nome} autorizada"}}]
        corpo = (f"<h1>Assistência técnica {e(nome)} autorizada no Brasil</h1>"
                 f'<p class="resumo">{e(resumo)}</p>'
                 f'<p class="resumo">{e(self._sobre(marca))}</p>'
                 f'<p class="fonte">{e(self._fonte_frase(marca))}</p>'
                 + (f'<h2>Cidades com mais oficinas {e(nome)}</h2>'
                    f'<ul class="lugares">{tops}</ul>' if tops else "")
                 + f"<h2>Assistência {e(nome)} por estado</h2>"
                 f'<ul class="lugares">{estados}</ul>'
                 + self._rodape_marca(marca))
        escrever(SITE / cam.strip("/") / "index.html",
                 shell(titulo=f"Assistência técnica {nome} autorizada — rede no "
                              f"Brasil | {SITE_NOME}",
                       descricao=resumo, url=SITE_URL + cam, corpo=corpo,
                       css_nome=css_nome, trilha=trilha, jsonld=ld,
                       vertical_atual=NAV_CHAVE))
        urls.append(cam)

    # -------------------------------------------------------------- marca + UF
    def _marca_uf(self, marca, uf, css_nome, urls) -> None:
        nome = MARCAS[marca]["nome"]
        nome_uf = UF_NOME.get(uf, uf)
        por_cidade = self.postos[marca][uf]
        fichas = [r for s in sorted(por_cidade, key=lambda x: x or "￿")
                  for r in sorted(por_cidade[s], key=lambda r: r["nome"])]
        total = len(fichas)
        com_cidade = [s for s in por_cidade if s]
        cam = f"{RAIZ_MARCAS}/{marca}/{uf.lower()}/"
        em_uf = UF_EM.get(uf, f"em {nome_uf}")
        resumo = (f"{num(total)} {'oficina' if total == 1 else 'oficinas'} de "
                  f"assistência técnica autorizada {nome} {em_uf}, em "
                  f"{len(com_cidade)} "
                  f"{'cidade' if len(com_cidade) == 1 else 'cidades'}, com "
                  f"endereço e telefone de cada uma.")
        trilha = [("Início", "/"), (ROTULO_VERTICAL, f"/{VERTICAL}/"),
                  ("Por marca", HUB), (nome, f"{RAIZ_MARCAS}/{marca}/"),
                  (nome_uf, None)]
        cidades = "".join(
            f'<li><a href="{cam}{s}/"><span>{e(self.nomes[(uf, s)])}</span>'
            f'<span class="n">{len(por_cidade[s])}</span></a></li>'
            for s in sorted(com_cidade, key=lambda s: self.nomes[(uf, s)]))
        ld = [trilha_ld(trilha),
              {"@context": "https://schema.org", "@type": "ItemList",
               "name": f"Assistência técnica {nome} autorizada em {nome_uf}",
               "numberOfItems": total,
               "itemListElement": [self._ficha_ld(r, marca, i)
                                   for i, r in enumerate(fichas, 1)]}]
        corpo = (f"<h1>Assistência técnica {e(nome)} autorizada {e(em_uf)} "
                 f"({e(uf)})</h1>"
                 f'<p class="resumo">{e(resumo)}</p>'
                 f'<p class="fonte">{e(self._fonte_frase(marca))}</p>'
                 + (f'<h2>Cidades de {e(nome_uf)}</h2>'
                    f'<ul class="lugares">{cidades}</ul>' if cidades else "")
                 + self._lista(fichas, marca, f"Oficinas {nome} {em_uf}")
                 + f'<p class="fonte"><a href="/{VERTICAL}/{uf.lower()}/">Todas as '
                 f'assistências técnicas de {e(nome_uf)}</a>, de qualquer marca.</p>'
                 + self._rodape_marca(marca))
        escrever(SITE / cam.strip("/") / "index.html",
                 shell(titulo=f"Assistência técnica {nome} {em_uf} ({uf}) — "
                              f"rede autorizada | {SITE_NOME}",
                       descricao=resumo, url=SITE_URL + cam, corpo=corpo,
                       css_nome=css_nome, trilha=trilha, jsonld=ld,
                       vertical_atual=NAV_CHAVE))
        urls.append(cam)

    # ---------------------------------------------------------- marca + cidade
    def _marca_cidade(self, marca, uf, slug, fichas, css_nome, urls) -> None:
        nome = MARCAS[marca]["nome"]
        municipio = self.nomes[(uf, slug)]
        nome_uf = UF_NOME.get(uf, uf)
        fichas = sorted(fichas, key=lambda r: r["nome"])
        total = len(fichas)
        cam = f"{RAIZ_MARCAS}/{marca}/{uf.lower()}/{slug}/"
        resumo = (f"{num(total)} {'oficina' if total == 1 else 'oficinas'} de "
                  f"assistência técnica autorizada {nome} em {municipio} ({uf}), "
                  f"com endereço, telefone e e-mail.")
        trilha = [("Início", "/"), (ROTULO_VERTICAL, f"/{VERTICAL}/"),
                  ("Por marca", HUB), (nome, f"{RAIZ_MARCAS}/{marca}/"),
                  (nome_uf, f"{RAIZ_MARCAS}/{marca}/{uf.lower()}/"),
                  (municipio, None)]
        ld = [trilha_ld(trilha),
              {"@context": "https://schema.org", "@type": "ItemList",
               "name": f"Assistência técnica {nome} autorizada em {municipio}, {uf}",
               "numberOfItems": total,
               "itemListElement": [self._ficha_ld(r, marca, i)
                                   for i, r in enumerate(fichas, 1)]}]
        # Numa página de cidade, o link útil para outra marca é o dela NESTA
        # cidade, não a página nacional. Por isso aqui não entra o rodapé de
        # marcas irmãs: um bloco só, com tudo que tem rede aqui.
        vizinhas = [m for m, _ in self.cidades.get((uf, slug), []) if m != marca]
        outras = ""
        if vizinhas:
            itens = "".join(
                f'<li><a href="{RAIZ_MARCAS}/{m}/{uf.lower()}/{slug}/">'
                f'<span>{e(MARCAS[m]["nome"])}</span>'
                f'<span class="n">{len(self.postos[m][uf][slug])}</span></a></li>'
                for m in vizinhas)
            outras = (f'<h2>Outras marcas com assistência autorizada em '
                      f'{e(municipio)}</h2>'
                      f'<p class="resumo">Marcas com oficina credenciada na '
                      f'mesma cidade. Distribuidor que representa várias marcas '
                      f'credencia uma rede só, então algumas destas listas '
                      f'repetem as mesmas oficinas.</p>'
                      f'<ul class="lugares">{itens}</ul>')
        corpo = (f"<h1>Assistência técnica {e(nome)} em {e(municipio)} - {e(uf)}</h1>"
                 f'<p class="resumo">{e(resumo)}</p>'
                 f'<p class="resumo">{e(self._sobre(marca))}</p>'
                 f'<p class="fonte">{e(self._fonte_frase(marca))}</p>'
                 + self._lista(fichas, marca)
                 + f'<p class="fonte"><a href="/{VERTICAL}/{uf.lower()}/{slug}/">'
                 f'Todas as assistências técnicas de {e(municipio)}</a>, de '
                 f'qualquer marca, com dados da Receita Federal.</p>'
                 + outras
                 + f'<p class="fonte"><a href="{HUB}">Todas as marcas</a> · '
                 f'<a href="{RAIZ_MARCAS}/{marca}/">Rede {e(nome)} no Brasil</a></p>')
        escrever(SITE / cam.strip("/") / "index.html",
                 shell(titulo=f"Assistência técnica {nome} em {municipio}, {uf} — "
                              f"autorizada | {SITE_NOME}",
                       descricao=resumo, url=SITE_URL + cam, corpo=corpo,
                       css_nome=css_nome, trilha=trilha, jsonld=ld,
                       vertical_atual=NAV_CHAVE))
        urls.append(cam)
