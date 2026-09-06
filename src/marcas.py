"""Catálogo das redes de assistência autorizada, por marca.

Por que existe um arquivo só de configuração: os dados de marca NÃO vêm da
Receita Federal. Vêm do site oficial de cada fabricante ou distribuidor, que é
quem credencia a oficina. O que muda com o tempo é a lista de oficinas, não a
relação marca -> distribuidor -> URL oficial. Essa relação fica versionada aqui,
em texto, e o coletor (src/coletar_marcas.py) só busca as oficinas.

Regra editorial: nada de descrição inventada. `sobre` só é preenchido quando o
que a marca fabrica é verificável na própria página oficial da fonte. Sem isso,
a página se apresenta pelo distribuidor, que é o fato que temos.

Uma FONTE atende N MARCAS com a MESMA rede de oficinas — é o caso da ProShows e
da Sonotec, que distribuem dezenas de marcas e credenciam uma oficina só. Por
isso a relação (oficina x marca) é derivada da fonte, e não coletada: a fonte
não publica qual oficina atende qual marca do portfólio.
"""

# --------------------------------------------------------------------- fontes
# `pagina` é a URL que o visitante deve abrir para conferir o dado na origem —
# sempre a página institucional, nunca o endpoint interno usado pelo coletor.
FONTES = {
    "roland": {
        "titular": "Roland Brasil",
        "pagina": "https://www.roland.com/br/sta/",
        "termo": "STA — Serviço Técnico Autorizado",
    },
    "yamaha": {
        "titular": "Yamaha Musical do Brasil",
        "pagina": "https://br.yamaha.com/pt/support/service-centers/",
        "termo": "Postos Autorizados",
    },
    "casio": {
        "titular": "Casio",
        "pagina": "https://www.casio-intl.com/br/pt/support/repair/emi/",
        "termo": "rede de reparo de instrumentos musicais eletrônicos",
    },
    "tectronica": {
        "titular": "Tectrônica",
        "pagina": "https://www.tectronica.com.br/redes-autorizadas",
        "termo": "Redes Autorizadas",
    },
    "proshows": {
        "titular": "ProShows",
        "pagina": "https://www.proshows.com.br/assistencias-tecnicas",
        "termo": "Assistências Técnicas Autorizadas",
    },
    "tagima": {
        "titular": "Tagima",
        "pagina": "https://www.tagima.com.br/pt/assistencia-tecnica",
        "termo": "Assistência Técnica",
    },
    "sonotec": {
        "titular": "Sonotec",
        "pagina": "https://www.sonotec.com.br/autorizadas",
        "termo": "Autorizadas",
    },
    "harman": {
        "titular": "Harman do Brasil",
        "pagina": "https://support.harmanaudio.com/br/pt/service-center-locator/",
        "termo": "Service Center Locator",
        # O localizador da Harman fica atrás de um antibot que exige executar
        # JavaScript. Contornar isso seria burlar um controle de acesso, então
        # a fonte fica declarada e sem coleta: as marcas dela não geram página.
        "bloqueada": "localizador protegido por antibot; requer execução de JavaScript",
    },
}

# --------------------------------------------------------------------- marcas
# slug -> nome de exibição, fonte, e os campos opcionais:
#   aliases  grafias alternativas que as pessoas digitam na busca
#   linhas   linhas de produto atendidas pela mesma rede (evita uma página
#            quase idêntica por linha, que é o que a lista do fabricante sugere)
#   sobre    o que a marca fabrica — só quando verificável na fonte oficial
#   destaque a marca que representa a rede quando o distribuidor tem várias.
#            Serve só para escolher o que citar em texto curto (chamada na home
#            da vertical, llms.txt); não muda nenhuma página. Sem isso, o
#            desempate seria alfabético e a ProShows apareceria representada por
#            "Aston Microphones" em vez de Behringer.
def _m(nome, fonte, *, aliases=(), linhas=(), sobre=None, destaque=False):
    return {"nome": nome, "fonte": fonte, "aliases": list(aliases),
            "linhas": list(linhas), "sobre": sobre, "destaque": destaque}


MARCAS = {
    # ---- redes de um fabricante só
    "roland": _m("Roland", "roland", aliases=["Roland Brasil"], destaque=True, sobre=(
        "pianos digitais, sintetizadores, teclados, baterias eletrônicas, "
        "amplificadores, instrumentos de sopro eletrônicos e equipamentos de "
        "áudio e vídeo profissional")),
    "yamaha": _m("Yamaha", "yamaha", aliases=["Yamaha Musical"], destaque=True, sobre=(
        "pianos acústicos e digitais, teclados e sintetizadores, violões, "
        "guitarras e baixos, baterias, instrumentos de sopro e de arco, "
        "percussão e equipamentos de áudio profissional")),
    "casio": _m("Casio", "casio", aliases=["Casiotone"], destaque=True, sobre=(
        "teclados, pianos digitais e sintetizadores da linha de instrumentos "
        "musicais eletrônicos")),
    "korg": _m("Korg", "tectronica", destaque=True, sobre=(
        "sintetizadores, workstations, teclados arranjadores, pianos digitais, "
        "controladores, afinadores e equipamentos de DJ")),
    "tagima": _m("Tagima", "tagima", destaque=True, sobre=(
        "guitarras, baixos, violões e amplificadores")),

    # ---- rede ProShows (uma oficina atende todo o portfólio)
    "behringer": _m("Behringer", "proshows", destaque=True, sobre=(
        "mesas de som analógicas e digitais, interfaces de áudio, "
        "amplificadores, caixas acústicas e processadores de sinal")),
    "midas": _m("Midas", "proshows", sobre=(
        "mesas de som digitais e pré-amplificadores de microfone para áudio "
        "profissional")),
    "klark-teknik": _m("Klark Teknik", "proshows", sobre=(
        "processadores de áudio, equalizadores e unidades de efeito")),
    "tc-electronic": _m("TC Electronic", "proshows", aliases=["TC"], sobre=(
        "pedais de efeito, processadores de áudio e amplificação para "
        "instrumentos")),
    "turbosound": _m("Turbosound", "proshows", sobre=(
        "caixas acústicas e sistemas de sonorização")),
    "tannoy": _m("Tannoy", "proshows", sobre=(
        "caixas acústicas e monitores de estúdio")),
    "marshall": _m("Marshall", "proshows", sobre=(
        "amplificadores e caixas para guitarra")),
    "shure": _m("Shure", "proshows", sobre=(
        "microfones, sistemas sem fio e fones de ouvido")),
    "novation": _m("Novation", "proshows", sobre=(
        "sintetizadores, controladores MIDI e controladores de grade")),
    "focusrite": _m("Focusrite", "proshows", sobre=(
        "interfaces de áudio e pré-amplificadores de microfone")),
    "hohner": _m("Hohner", "proshows", sobre=(
        "gaitas, acordeões e melódicas")),
    "aston-microphones": _m("Aston Microphones", "proshows", aliases=["Aston"],
                            sobre="microfones de estúdio"),
    "ghs-strings": _m("GHS Strings", "proshows", aliases=["GHS"], sobre=(
        "cordas para guitarra, baixo, violão e outros instrumentos")),
    "benson": _m("Benson", "proshows"),
    "kolt": _m("Költ", "proshows", aliases=["Kolt"]),
    "guitar-shop": _m("Guitar Shop", "proshows"),
    "lexsen": _m("Lexsen", "proshows"),
    "dbr": _m("DBR", "proshows"),
    "pls": _m("PLS", "proshows"),

    # ---- rede Sonotec (idem: uma oficina para todo o portfólio)
    "takamine": _m("Takamine", "sonotec", destaque=True, sobre=(
        "violões e violões eletroacústicos")),
    "gretsch": _m("Gretsch", "sonotec", sobre=("guitarras, baixos e baterias")),
    "lp": _m("LP", "sonotec", aliases=["Latin Percussion", "LP Latin Percussion"],
             sobre="instrumentos de percussão latina"),
    "karsect": _m("Karsect", "sonotec", sobre=(
        "microfones com fio e sistemas sem fio")),
    "strinberg": _m("Strinberg", "sonotec", sobre=(
        "guitarras, baixos, violões e baterias")),
    "vokal": _m("Vokal", "sonotec", sobre=("microfones e equipamentos de áudio")),
    "zeus": _m("Zeus", "sonotec", aliases=["Zeus Cymbals"], sobre=(
        "pratos para bateria")),
    "antares": _m("Antares", "sonotec", aliases=["Antares Drumheads"], sobre=(
        "peles para bateria")),
    "orleans": _m("Orleans", "sonotec", aliases=["Orleans Harmonicas"], sobre=(
        "gaitas")),
    "premium-drums": _m("Premium Drums", "sonotec", aliases=["Premium"],
                        sobre="baterias e ferragens"),
    "d-one": _m("D-One", "sonotec", aliases=["DOne", "D One"],
                linhas=["D-One", "D-One Percussion"]),
    "d-tech": _m("D-Tech", "sonotec", aliases=["D-Tech E-Drums", "DTech"],
                 sobre="baterias eletrônicas"),
    "concert": _m("Concert", "sonotec",
                  linhas=["Concert Guitars", "Concert Keys", "Concert Kids",
                          "Concert Classical Accessories"]),
    "vivace": _m("Vivace", "sonotec",
                 linhas=["Vivace Classical Instruments", "Vivace Wind Instruments"]),
    "musimax": _m("Musimax", "sonotec"),
    "sonotec": _m("Sonotec", "sonotec"),
    "cadenza": _m("Cadenza", "sonotec"),
    "overtone": _m("Overtone", "sonotec"),
    "rockwave": _m("Rockwave", "sonotec"),

    # ---- rede Harman: declarada, sem coleta (ver FONTES['harman']['bloqueada'])
    "jbl": _m("JBL", "harman", sobre=(
        "caixas acústicas, sistemas de sonorização e fones de ouvido")),
    "akg": _m("AKG", "harman", sobre=("microfones e fones de ouvido")),
    "harman-kardon": _m("Harman Kardon", "harman", sobre=("áudio residencial")),
    "infinity": _m("Infinity", "harman", sobre=("caixas acústicas")),
    "lexicon": _m("Lexicon", "harman", sobre=("processadores de efeito e reverb")),
    "mark-levinson": _m("Mark Levinson", "harman", sobre=("áudio residencial")),
    "revel": _m("Revel", "harman", sobre=("caixas acústicas")),
}


def marcas_coletaveis() -> dict:
    """Só as marcas cuja fonte não está bloqueada."""
    return {s: m for s, m in MARCAS.items()
            if not FONTES[m["fonte"]].get("bloqueada")}


def marcas_da_fonte(fonte: str) -> list:
    """Slugs das marcas atendidas por uma fonte, em ordem de exibição."""
    return sorted((s for s, m in MARCAS.items() if m["fonte"] == fonte),
                  key=lambda s: MARCAS[s]["nome"].lower())


# ------------------------------------------------------------- DDD -> estado
# Cada DDD do Plano Geral de Códigos Nacionais pertence a um único estado. É o
# que salva o registro quando o endereço publicado pelo fabricante não traz a
# cidade — dá para saber o estado sem inventar nada.
DDD_UF = {}
for _uf, _ddds in {
    "SP": "11 12 13 14 15 16 17 18 19", "RJ": "21 22 24", "ES": "27 28",
    "MG": "31 32 33 34 35 37 38", "PR": "41 42 43 44 45 46",
    "SC": "47 48 49", "RS": "51 53 54 55", "DF": "61", "GO": "62 64",
    "TO": "63", "MT": "65 66", "MS": "67", "AC": "68", "RO": "69",
    "BA": "71 73 74 75 77", "SE": "79", "PE": "81 87", "AL": "82",
    "PB": "83", "RN": "84", "CE": "85 88", "PI": "86 89",
    "PA": "91 93 94", "AM": "92 97", "RR": "95", "AP": "96", "MA": "98 99",
}.items():
    for _d in _ddds.split():
        DDD_UF[_d] = _uf
del _uf, _ddds, _d
