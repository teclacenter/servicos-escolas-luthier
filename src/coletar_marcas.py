"""Alvo 'coletar-marcas': baixa as redes de assistência autorizada por marca.

É a SEGUNDA etapa do projeto que toca a rede — a primeira foi a tabela de
municípios do IBGE — e, como aquela, fica FORA de `make all`. O motivo é o
mesmo: `make all` precisa continuar determinístico e reprodutível offline. Aqui
o resultado depende do que o site do fabricante estava publicando na hora, então
a coleta é um passo separado, explícito, cujo produto é um CSV versionado:

    dados-referencia/marcas-autorizadas.csv

O HTML e o JSON crus de cada fonte ficam em tmp/marcas/ para auditoria — dá para
conferir de onde saiu cada linha sem repetir a coleta.

O que este arquivo NÃO faz, de propósito:
  * não normaliza telefone, CEP nem nome de cidade. Isso já existe, testado, nas
    macros de sql/20_macros.sql, e duplicar a regra em Python seria criar uma
    segunda verdade. O CSV sai com o texto como a fonte publicou.
  * não decide a qual marca cada oficina atende. Nenhuma fonte publica isso: a
    ProShows e a Sonotec credenciam UMA rede para todo o portfólio. A relação
    (oficina x marca) é derivada da fonte em sql/47_marcas.sql.

Sem dependência nova: urllib e re da biblioteca padrão. As sete fontes têm
estrutura fixa e pequena; um parser de HTML completo não pagaria o custo.
"""
import argparse
import csv
import gzip
import hashlib
import html as _html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from config import RAIZ, TMP, UF_NOME
from marcas import DDD_UF, FONTES

DESTINO = RAIZ / "dados-referencia" / "marcas-autorizadas.csv"
CRUS = TMP / "marcas"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
PAUSA = 0.7   # segundos entre requisições à mesma fonte

COLUNAS = ["fonte", "coletado_em", "posto_id", "nome", "uf_fonte",
           "cidade_fonte", "bairro", "endereco", "cep", "telefones", "email",
           "site", "contato", "horario", "segmento"]

UF_POR_NOME = {}


def _norm(t: str) -> str:
    """Minúsculo, sem acento, espaço colapsado. Só para comparar, nunca exibir."""
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().lower()


for _sigla, _nome in UF_NOME.items():
    UF_POR_NOME[_norm(_nome)] = _sigla
    UF_POR_NOME[_sigla.lower()] = _sigla
UF_POR_NOME["parai­ba"] = "PB"          # grafia sem acento aparece em uma fonte
del _sigla, _nome


def uf_de(texto: str) -> str:
    """Sigla a partir de 'SP', 'São Paulo' ou 'Sao Paulo'. '' se não reconhecer."""
    return UF_POR_NOME.get(_norm(texto), "")


def uf_do_endereco(endereco: str) -> str:
    """Sigla escrita no fim do endereço ('... - NATAL - RN', '..., SP')."""
    m = re.search(r"[,\-–]\s*([A-Za-z]{2})\s*\.?\s*$", (endereco or "").strip())
    return uf_de(m.group(1)) if m else ""


def uf_do_ddd(*telefones) -> str:
    """Último recurso quando a fonte não publica o estado: o DDD do telefone."""
    for t in telefones:
        for ddd in re.findall(r"\((\d{2})\)|(?<!\d)(\d{2})\s*9?\d{4}[- ]?\d{4}", t or ""):
            d = ddd if isinstance(ddd, str) else next(filter(None, ddd), "")
            if d in DDD_UF:
                return DDD_UF[d]
    return ""


# ------------------------------------------------------------------ rede/HTML
def baixar(url: str, arquivo: str, *, cabecalhos=None, reusar=False) -> str:
    """GET com cache em tmp/marcas/. Devolve o corpo decodificado."""
    alvo = CRUS / arquivo
    if reusar and alvo.exists():
        return alvo.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Accept-Encoding": "gzip",
        **(cabecalhos or {}),
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        bruto = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            bruto = gzip.decompress(bruto)
        codec = "utf-8"
        tipo = r.headers.get("Content-Type", "")
        if m := re.search(r"charset=([\w-]+)", tipo, re.I):
            codec = m.group(1)
    texto = bruto.decode(codec, errors="replace")
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(texto, encoding="utf-8")
    time.sleep(PAUSA)
    return texto


def texto_de(fragmento: str) -> str:
    """Tira tags e resolve entidades. <br> vira quebra de linha, não some."""
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", fragmento)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = _html.unescape(t)
    t = t.replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n"))


def linhas_de(fragmento: str) -> list:
    return [l for l in texto_de(fragmento).split("\n") if l]


def _cf_email(hexadecimal: str) -> str:
    """Desobfusca o e-mail que a Cloudflare esconde em data-cfemail.

    XOR de cada byte com o primeiro byte. É um anti-spam de HTML, não um
    controle de acesso: o e-mail é publicado na página para ser lido.
    """
    chave = int(hexadecimal[:2], 16)
    return "".join(chr(int(hexadecimal[i:i + 2], 16) ^ chave)
                   for i in range(2, len(hexadecimal), 2))


def _emails(fragmento: str) -> str:
    achados = [_cf_email(h) for h in re.findall(r'data-cfemail="([0-9a-f]+)"', fragmento)]
    achados += re.findall(r"mailto:\s*([^\"'>?\s]+@[^\"'>?\s]+)", fragmento)
    achados += re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", texto_de(fragmento))
    vistos, saida = set(), []
    for e in achados:
        e = e.strip(" .,;:").lower()
        if "@" in e and e not in vistos:
            vistos.add(e)
            saida.append(e)
    return saida[0] if saida else ""


RE_FONE = re.compile(r"\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}")


def _telefones(texto: str) -> str:
    """Todos os telefones plausíveis do trecho, separados por '|'.

    A validação de verdade (DDD existente, tamanho, número repetido) é feita
    pela macro telefone_e164 na carga. Aqui só se recorta o candidato.
    """
    vistos, saida = set(), []
    for m in RE_FONE.findall(texto or ""):
        d = re.sub(r"\D", "", m)
        if len(d) in (10, 11) and d not in vistos:
            vistos.add(d)
            saida.append(d)
    return "|".join(saida)


def _cep(texto: str) -> str:
    """Primeiro CEP do trecho, no formato 00000-000.

    Aceita '57.020-260' e '57020260': a Casio grava com ponto de milhar e a
    ProShows sem separador nenhum.
    """
    m = re.search(r"(?<!\d)(\d{2})\.?(\d{3})[-. ]?(\d{3})(?!\d)", texto or "")
    return f"{m.group(1)}{m.group(2)}-{m.group(3)}" if m else ""


def _limpar_endereco(texto: str) -> str:
    """Tira do logradouro o que já tem coluna própria.

    As fontes repetem telefone e CEP dentro da linha de endereço ("Rua X, 351 -
    Centro (75) 3223-7885"). Sem essa limpeza o telefone aparece duas vezes na
    ficha, uma delas como se fosse parte da rua.
    """
    t = RE_FONE.sub(" ", texto or "")
    t = re.sub(r"(?i)\s*[-–,]?\s*CEP:?\s*\d{2}\.?\d{3}[-. ]?\d{3}", " ", t)
    t = re.sub(r"(?<!\d)\d{2}\.?\d{3}-\d{3}(?!\d)", " ", t)
    return re.sub(r"\s+", " ", t).strip(" -–,/;")


def _site(fragmento: str) -> str:
    for u in re.findall(r'href="(https?://[^"]+)"', fragmento):
        if not re.search(r"(wa\.me|whatsapp|facebook|maps\.google|google\.com/maps"
                         r"|cdn-cgi|tagima\.com|sonotec\.com|proshows\.com"
                         r"|tectronica\.com|roland\.com|yamaha\.com|casio)", u, re.I):
            return u.strip()
    # Roland e Sonotec escrevem o site como texto solto, sem <a>
    m = re.search(r"(?<![\w@./])(www\.[\w.-]+\.[a-z]{2,}(?:\.[a-z]{2})?)", texto_de(fragmento), re.I)
    return "https://" + m.group(1) if m else ""


# ------------------------------------------------------------------- coletores
# Cada coletor devolve uma lista de dicionários com as chaves de COLUNAS
# (menos fonte e posto_id, preenchidos depois).

def coletar_roland(reusar: bool) -> list:
    """Roland: a página em roland.com embute um .php do site brasileiro, que por
    sua vez pede dados_sta.php?estado=NN. NN é um código interno, não a UF."""
    base = "https://www.rolandbrasil.com.br/roland/suporte/"
    form = baixar(base + "sta.php", "roland-form.html", reusar=reusar)
    estados = [(v, _html.unescape(n)) for v, n in
               re.findall(r"<option value='(\d+)'>([^<]+)</option>", form)]
    if not estados:
        raise RuntimeError("Roland: nenhum estado no formulário (mudou o HTML?)")
    saida = []
    for codigo, nome_uf in estados:
        uf = uf_de(nome_uf)
        pagina = baixar(f"{base}dados_sta.php?estado={codigo}",
                        f"roland-{uf or codigo}.html", reusar=reusar)
        # A resposta é uma sequência plana: <span>cidade</span> ... <h5>nome</h5> ...
        # Fatia-se por <span>, e dentro de cada fatia por <h5>.
        for bloco in re.split(r"(?i)<span[^>]*font-weight:\s*bold[^>]*>", pagina)[1:]:
            cidade, _, resto = bloco.partition("</span>")
            cidade = texto_de(cidade).strip()
            for item in re.split(r"(?i)<h5[^>]*>", resto)[1:]:
                nome, _, corpo = item.partition("</h5>")
                nome = " ".join(texto_de(nome).split())
                if not nome:
                    continue
                linhas = linhas_de(corpo)
                # a linha de contato é descartada do endereço; o resto é endereço
                ruim = re.compile(r"(?i)^(cep|tel|fone|telefone|cel|celular|whats)")
                endereco = [l for l in linhas
                            if not ruim.match(l) and "@" not in l
                            and not re.match(r"(?i)^(www\.|https?:)", l)]
                saida.append({
                    "nome": nome, "uf_fonte": uf, "cidade_fonte": cidade,
                    "bairro": "", "endereco": _limpar_endereco(" ".join(endereco)),
                    "cep": _cep(corpo), "telefones": _telefones(texto_de(corpo)),
                    "email": _emails(corpo), "site": _site(corpo),
                    "contato": "", "horario": "", "segmento": "",
                })
    return saida


def coletar_yamaha(reusar: bool) -> list:
    """Yamaha: API JSON do próprio localizador. Traz lat/lng e um endereço em
    texto livre — sem campo de cidade nem de estado. O estado sai do DDD; a
    cidade é casada com a tabela do IBGE na carga (sql/47_marcas.sql)."""
    bruto = baixar("https://br.yamaha.com/api/dealer/servicecenter/",
                   "yamaha.json", cabecalhos={"Accept": "application/json"},
                   reusar=reusar)
    # contractCode -> o que a oficina atende. É a única segmentação publicada.
    rotulo = {"PI": "Pianos acústicos", "DP": "Teclados e pianos digitais",
              "GT": "Violões, guitarras e baixos", "DR": "Baterias acústicas",
              "WI": "Sopros", "PA": "Áudio profissional e home studio",
              "AV": "Áudio e vídeo"}
    saida = []
    for r in json.loads(bruto):
        nome = " ".join((r.get("name") or "").split())
        if not nome:
            continue
        fone = r.get("telephoneNumber") or ""
        endereco = " ".join((r.get("address") or "").split())
        segmentos = [rotulo.get(c, c) for c in (r.get("contractCode") or [])]
        saida.append({
            # sem estado de propósito: quem resolve é o fallback único em
            # coletar(), que prefere a sigla escrita no fim do endereço
            "nome": nome, "uf_fonte": "",
            "cidade_fonte": "", "bairro": "", "endereco": _limpar_endereco(endereco),
            "cep": _cep(endereco), "telefones": _telefones(fone),
            "email": (r.get("emailAddress") or "").strip().lower(),
            "site": (r.get("url") or "").strip(), "contato": "", "horario": "",
            "segmento": ", ".join(sorted(segmentos)),
        })
    return saida


def coletar_casio(reusar: bool) -> list:
    """Casio: JSON servido pela própria página; exige Referer (Akamai bloqueia
    o acesso direto). search1 é a UF e search2 a cidade, já separados."""
    bruto = baixar("https://www.casio-intl.com/br/pt/support/repair/emi/shop.json",
                   "casio.json", reusar=reusar, cabecalhos={
                       "Referer": "https://www.casio-intl.com/br/pt/support/repair/emi/",
                       "Accept": "application/json,*/*"})
    saida = []
    for r in json.loads(bruto).get("data", []):
        nome = " ".join((r.get("store_name") or "").split())
        if not nome:
            continue
        endereco = " ".join(texto_de(r.get("address") or "").split())
        saida.append({
            "nome": nome, "uf_fonte": uf_de(r.get("search1") or ""),
            "cidade_fonte": (r.get("search2") or "").strip(), "bairro": "",
            "endereco": _limpar_endereco(endereco), "cep": _cep(endereco),
            "telefones": _telefones(r.get("tel") or ""),
            "email": _emails(r.get("email") or ""),
            "site": _site(r.get("website") or ""), "contato": "",
            "horario": " ".join((r.get("opening_hours") or "").split()),
            "segmento": "",
        })
    return saida


def coletar_tectronica(reusar: bool) -> list:
    """Tectrônica (rede Korg): página única, um <div> por oficina, com a UF e a
    cidade em atributos data-*. É a fonte mais limpa das sete."""
    pagina = baixar("https://www.tectronica.com.br/redes-autorizadas",
                    "tectronica.html", reusar=reusar)
    saida = []
    for bloco in re.split(r'(?=<div class="[^"]*\bunidade\b)', pagina)[1:]:
        uf = (re.search(r'data-estado="([^"]*)"', bloco) or [None, ""])[1]
        cidade = (re.search(r'data-cidade="([^"]*)"', bloco) or [None, ""])[1]
        nome = re.search(r'(?is)<p class="sub-title[^"]*">(.*?)</p>', bloco)
        if not nome:
            continue
        campo = lambda r: (m.group(1).strip() if (m := re.search(  # noqa: E731
            r"(?is)<b>\s*" + r + r"\s*:\s*</b>(.*?)</p>", bloco)) else "")
        saida.append({
            "nome": " ".join(texto_de(nome.group(1)).split()),
            "uf_fonte": uf_de(uf), "cidade_fonte": _html.unescape(cidade).strip(),
            "bairro": "", "endereco": _limpar_endereco(texto_de(campo("Endereço"))),
            "cep": _cep(campo("CEP")), "telefones": _telefones(texto_de(campo("Telefone"))),
            "email": _emails(campo("E-mail")), "site": "", "contato": "",
            "horario": "", "segmento": "",
        })
    return saida


def coletar_proshows(reusar: bool) -> list:
    """ProShows: entidade 'AT' do Master Data da VTEX, filtrada por estado. Sem
    o filtro a API devolve 403, então a consulta é feita estado a estado."""
    campos = ("address,assistance,city,contact,email,neighborhood,segment,"
              "state,telephone,url,zip")
    saida = []
    for sigla, nome_uf in sorted(UF_NOME.items()):
        alvo = ("https://www.proshows.com.br/api/dataentities/AT/search?"
                + urllib.parse.urlencode({"state": nome_uf, "_fields": campos}))
        bruto = baixar(alvo, f"proshows-{sigla}.json", reusar=reusar, cabecalhos={
            "Accept": "application/vnd.vtex.ds.v10+json",
            "REST-Range": "resources=0-1000",
            "Referer": FONTES["proshows"]["pagina"]})
        for r in json.loads(bruto):
            nome = " ".join((r.get("assistance") or "").split())
            if not nome:
                continue
            saida.append({
                "nome": nome, "uf_fonte": uf_de(r.get("state") or "") or sigla,
                "cidade_fonte": (r.get("city") or "").strip(),
                "bairro": (r.get("neighborhood") or "").strip(),
                "endereco": _limpar_endereco(r.get("address") or ""),
                "cep": _cep(r.get("zip") or ""),
                "telefones": _telefones(r.get("telephone") or ""),
                "email": _emails(r.get("email") or ""),
                "site": _site(r.get("url") or ""),
                "contato": (r.get("contact") or "").strip(),
                "horario": "", "segmento": (r.get("segment") or "").strip(),
            })
    return saida


def coletar_tagima(reusar: bool) -> list:
    """Tagima: HTML renderizado no servidor, um estado por requisição. O select
    de estados mistura nome ('Santa Catarina') e sigla ('CE'), e faltam nomes
    para alguns estados — por isso a lista de consulta é a união do que o select
    oferece com as 27 siglas, e o resultado é deduplicado depois."""
    base = "https://www.tagima.com.br/pt/assistencia-tecnica"
    inicial = baixar(base, "tagima-form.html", reusar=reusar)
    valores = {v for v in re.findall(r'<option value="([^"]*)"', inicial)
               if v and "$" not in v}
    consultas = sorted(valores | set(UF_NOME))
    saida = []
    for valor in consultas:
        alvo = base + "?" + urllib.parse.urlencode({"state": valor, "city": ""})
        pagina = baixar(alvo, f"tagima-{_norm(valor).replace(' ', '-')}.html",
                        reusar=reusar)
        corpo = pagina.split("Lista de Assistências", 1)[-1]
        for bloco in re.split(r'(?=<div class="col-span-12 lg:col-span-4">)', corpo)[1:]:
            # A última ficha da página vai até o rodapé se não for cortada, e o
            # rodapé tem o Instagram da própria Tagima — que viraria "site da
            # oficina". A ficha não tem <div> aninhado: fecha no primeiro </div>.
            bloco = bloco.split("</div>", 1)[0]
            nome_m = re.search(r"(?is)<h5[^>]*>(.*?)</h5>", bloco)
            if not nome_m:
                continue
            # Um <p class="mb-1"> por campo. Só o de cidade/estado não tem
            # rótulo: é o que casa 'Cidade / Estado'.
            paragrafos = [" ".join(texto_de(x).split()) for x in
                          re.findall(r'(?is)<p class="mb-1">(.*?)</p>', bloco)]
            pega = lambda r: next(  # noqa: E731
                (x.split(":", 1)[1].strip() for x in paragrafos
                 if re.match(r"(?i)^" + r + r"\s*:", x)), "")
            endereco_bruto = pega("Endereço")
            bairro = ""
            if m := re.search(r"(?i),?\s*Bairro:\s*(.+)$", endereco_bruto):
                bairro = m.group(1).strip(" ,")
                endereco_bruto = endereco_bruto[:m.start()].strip(" ,")
            cidade, uf = "", ""
            for x in paragrafos:
                c, sep, e = x.partition("/")
                if sep and uf_de(e) and ":" not in x:
                    cidade, uf = c.strip(), uf_de(e)
                    break
            link = next((x for x in paragrafos if re.match(r"(?i)^link\s*:", x)), "")
            saida.append({
                "nome": " ".join(texto_de(nome_m.group(1)).split()),
                "uf_fonte": uf or uf_de(valor),
                "cidade_fonte": cidade, "bairro": bairro,
                "endereco": _limpar_endereco(endereco_bruto), "cep": _cep(pega("CEP")),
                "telefones": _telefones(" ".join(
                    x for x in paragrafos if re.match(r"(?i)^telefone", x))),
                "email": _emails(bloco),
                "site": _site(link.split(":", 1)[1]) if link else "",
                "contato": pega("Contato"), "horario": pega("Atendimento"),
                "segmento": "",
            })
    return saida


def coletar_sonotec(reusar: bool) -> list:
    """Sonotec: página única com um bloco por estado (<div class="selects UF">)
    e um <div class="item"> por oficina, com a cidade no <h5>."""
    pagina = baixar("https://www.sonotec.com.br/autorizadas", "sonotec.html",
                    reusar=reusar)
    saida = []
    for bloco_uf in re.split(r'(?=<div class="selects )', pagina)[1:]:
        sigla = (re.search(r'<div class="selects ([A-Z]{2})"', bloco_uf) or [None, ""])[1]
        uf = uf_de(sigla)
        if not uf:
            continue
        for item in re.split(r'(?=<div class="item">)', bloco_uf)[1:]:
            item = item.split('<div class="selects ', 1)[0]
            cidade_m = re.search(r"(?is)<h5[^>]*>(.*?)</h5>", item)
            nome_m = re.search(r"(?is)<span[^>]*>(.*?)</span>", item)
            if not (cidade_m and nome_m):
                continue
            infos = re.search(r'(?is)<div class="infos">(.*?)</div>', item)
            corpo = infos.group(1) if infos else item
            corpo_sem_nome = re.sub(r"(?is)<span[^>]*>.*?</span>", " ", corpo, count=1)
            linhas = linhas_de(corpo_sem_nome)
            endereco = [l for l in linhas
                        if "@" not in l and not RE_FONE.fullmatch(l.strip())
                        and not re.match(r"(?i)^(www\.|https?:)", l)]
            # tira do endereço o que for só telefone separado por barra
            endereco = [re.sub(r"\s*/\s*$", "", RE_FONE.sub("", l)).strip(" -/")
                        for l in endereco]
            saida.append({
                "nome": " ".join(texto_de(nome_m.group(1)).split()),
                "uf_fonte": uf,
                "cidade_fonte": " ".join(texto_de(cidade_m.group(1)).split()),
                "bairro": "", "endereco": _limpar_endereco(" ".join(endereco)),
                "cep": _cep(" ".join(linhas)),
                "telefones": _telefones(" ".join(linhas)),
                "email": _emails(corpo), "site": _site(corpo), "contato": "",
                "horario": "", "segmento": "",
            })
    return saida


COLETORES = {
    "roland": coletar_roland,
    "yamaha": coletar_yamaha,
    "casio": coletar_casio,
    "tectronica": coletar_tectronica,
    "proshows": coletar_proshows,
    "tagima": coletar_tagima,
    "sonotec": coletar_sonotec,
}


# ------------------------------------------------------------------ principal
def _identificar(fonte: str, r: dict) -> str:
    """Identificador estável do posto: hash do que a fonte publicou de fixo.

    Nome + CEP + endereço normalizados. Estável entre coletas enquanto a fonte
    não editar o cadastro, o que mantém o diff do CSV legível.
    """
    chave = "|".join(_norm(r.get(c, "")) for c in ("nome", "cep", "endereco"))
    return fonte + "-" + hashlib.sha256(chave.encode()).hexdigest()[:10]


def coletar(fontes, reusar: bool) -> list:
    hoje = date.today().isoformat()
    registros = []
    for fonte in fontes:
        meta = FONTES[fonte]
        if motivo := meta.get("bloqueada"):
            print(f"  {fonte:<12} PULADA — {motivo}")
            continue
        t0 = time.time()
        try:
            achados = COLETORES[fonte](reusar)
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError,
                json.JSONDecodeError) as erro:
            print(f"  {fonte:<12} FALHOU — {type(erro).__name__}: {erro}",
                  file=sys.stderr)
            continue
        sem_uf = 0
        for r in achados:
            if not r["uf_fonte"]:
                # A sigla escrita no fim do endereço é declaração da fonte; o
                # DDD é inferência nossa. Na Yamaha há oficina cujo DDD é de um
                # estado e o endereço, de outro — vence o que está escrito.
                r["uf_fonte"] = (uf_do_endereco(r["endereco"])
                                 or uf_do_ddd(r["telefones"], r["endereco"]))
                sem_uf += not r["uf_fonte"]
            r["fonte"] = fonte
            # data por FONTE, não por execução: coletar só a Roland hoje não
            # pode fazer o site dizer que a rede da Yamaha foi conferida hoje
            r["coletado_em"] = hoje
            r["posto_id"] = _identificar(fonte, r)
        registros += achados
        aviso = f"  {sem_uf} sem estado" if sem_uf else ""
        print(f"  {fonte:<12} {len(achados):>4} oficinas  "
              f"({time.time() - t0:.0f}s){aviso}", flush=True)
    return registros


def gravar(registros: list) -> int:
    """CSV ordenado e deduplicado. Ordem estável: duas coletas do mesmo conteúdo
    produzem o mesmo arquivo, então o diff mostra só o que a fonte mudou."""
    unicos = {}
    for r in sorted(registros, key=lambda r: (r["fonte"], r["posto_id"])):
        unicos.setdefault((r["fonte"], r["posto_id"]), r)
    linhas = sorted(unicos.values(),
                    key=lambda r: (r["fonte"], r["uf_fonte"],
                                   _norm(r["cidade_fonte"]), _norm(r["nome"]),
                                   r["posto_id"]))
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with DESTINO.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUNAS, extrasaction="ignore")
        w.writeheader()
        for r in linhas:
            w.writerow({c: r.get(c, "") for c in COLUNAS})
    return len(linhas)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--fonte", action="append", choices=sorted(FONTES),
                   help="coleta só esta fonte (pode repetir)")
    p.add_argument("--reusar", action="store_true",
                   help="reaproveita o que já está em tmp/marcas/, sem ir à rede")
    args = p.parse_args(argv)

    fontes = args.fonte or list(FONTES)
    print(f"coletando {len(fontes)} fonte(s)"
          + (" — reusando tmp/marcas/" if args.reusar else ""))
    registros = coletar(fontes, args.reusar)
    if not registros:
        print("ERRO: nenhuma oficina coletada.", file=sys.stderr)
        return 1

    # Coleta parcial não pode apagar o resto do arquivo: recarrega e mescla.
    if args.fonte and DESTINO.exists():
        novas = {r["fonte"] for r in registros}
        with DESTINO.open(encoding="utf-8") as fh:
            registros += [r for r in csv.DictReader(fh) if r["fonte"] not in novas]

    n = gravar(registros)
    print(f"\n{n} oficinas -> {DESTINO.relative_to(RAIZ)}  (coleta de {date.today()})")
    print(f"cru para auditoria em {CRUS.relative_to(RAIZ)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
