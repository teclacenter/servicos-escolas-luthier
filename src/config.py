"""Caminhos e constantes da Fase 1. Ponto único de verdade."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "Receita-cnpj-dados"   # CSVs já descompactados (não há ZIPs nesta máquina)
EXTRAIDOS = RAIZ / "extraidos"         # os mesmos CSVs em UTF-8, sem bytes de controle
SQL = RAIZ / "sql"
SAIDA = RAIZ / "saida"
TMP = RAIZ / "tmp"
DB = RAIZ / "cnpj.duckdb"

SAFRA = "2026-08"          # arquivos D60808 -> 2026-08-08
SAFRA_DATA = "2026-08-08"  # usada como <lastmod> no sitemap
MEMORY_LIMIT = "8GB"

# Sufixos dos arquivos da RFB (não têm extensão .csv)
GLOBS = {
    "empresas":           "*.EMPRECSV",
    "estabelecimentos":   "*.ESTABELE",
    "simples":            "*.SIMPLES.CSV.*",
    "cnaes":              "*.CNAECSV",
    "municipios_rfb":     "*.MUNICCSV",
    "motivos":            "*.MOTICSV",
    "naturezas":          "*.NATJUCSV",
    "paises":             "*.PAISCSV",
    "qualificacoes":      "*.QUALSCSV",
}

# ---------------------------------------------------------------------------
# Site estático. Tudo o que é de marca ou de endereço vive aqui: trocar o hex
# ou o domínio é uma linha, e depois `make site` regenera.
# ---------------------------------------------------------------------------
# Sigla -> nome do estado. Vive aqui porque o gerador do site, o coletor de
# marcas e os testes precisam da mesma tabela.
UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins",
}

# "em" + nome do estado, já contraído. Tabela fixa porque a contração depende
# do artigo do nome próprio ("no Rio de Janeiro", "na Bahia", "em São Paulo") e
# não há regra a derivar: é vocabulário, não gramática.
UF_EM = {
    "AC": "no Acre", "AL": "em Alagoas", "AM": "no Amazonas", "AP": "no Amapá",
    "BA": "na Bahia", "CE": "no Ceará", "DF": "no Distrito Federal",
    "ES": "no Espírito Santo", "GO": "em Goiás", "MA": "no Maranhão",
    "MG": "em Minas Gerais", "MS": "no Mato Grosso do Sul",
    "MT": "no Mato Grosso", "PA": "no Pará", "PB": "na Paraíba",
    "PE": "em Pernambuco", "PI": "no Piauí", "PR": "no Paraná",
    "RJ": "no Rio de Janeiro", "RN": "no Rio Grande do Norte",
    "RO": "em Rondônia", "RR": "em Roraima", "RS": "no Rio Grande do Sul",
    "SC": "em Santa Catarina", "SE": "em Sergipe", "SP": "em São Paulo",
    "TO": "no Tocantins",
}

SITE = RAIZ / "site"                    # saída do gerador (gitignore)
SITE_URL = "https://servicos.teclacenter.com.br"   # confirmado em 2026-08-24
SITE_NOME = "Teclacenter Serviços"
SITE_DESCRICAO = (
    "Diretório de assistência técnica, luthiers, escolas de música, estúdios de "
    "gravação e locação de som e palco no Brasil, por cidade e estado."
)
SITE_EMAIL_CONTATO = "teclacenter@teclacenter.com.br"   # canal de correção e remoção
POR_PAGINA = 100                        # fichas por página; controla o peso do HTML

# Paleta do site. O vermelho e o cinza foram AMOSTRADOS dos pixels opacos do
# próprio logotipo em ativos/ (não estimados a olho): #ca1010 é a cor de
# "SERVIÇOS" e do monograma, #a9abae é a de "center". Os demais tons derivam da
# captura de tela da loja. Este é o único lugar a mudar.
PALETA = {
    "vermelho":        "#ca1010",   # amostrado do logotipo
    "vermelho_escuro": "#a10d0d",   # hover
    "texto":           "#3f3f3f",
    "texto_suave":     "#6e7276",
    "cinza":           "#a9abae",   # amostrado do logotipo
    "barra":           "#eef1f5",   # faixa de navegação
    "borda":           "#e2e6ea",
    "fundo":           "#ffffff",
    "fundo_suave":     "#f7f9fb",
    # Faixa do logotipo. O arquivo enviado é a variante para FUNDO ESCURO: a
    # palavra "Tecla" e parte do monograma são brancas (#fefefe, medido), e em
    # cabeçalho branco ficariam invisíveis. Daí a faixa escura só atrás do logo;
    # o resto do site segue claro, como a loja.
    "topo":            "#2f3133",
}

ATIVOS = RAIZ / "ativos"        # logotipo e afins; copiados para site/estatico/
LOGO = "logo-teclacenter-servicos.png"
# Favicon. O gerador aceita, opcionalmente, ativos/favicon-180.png (apple-touch)
# e ativos/favicon-512.png (ícone de alta densidade) e os declara se existirem.
FAVICON = "favicon.png"

# Rótulo e texto de apoio de cada vertical, usados em título, H1 e meta description.
VERTICAIS = {
    "assistencia-tecnica": {
        "rotulo": "Assistência técnica",
        "h1": "Assistência técnica de instrumentos musicais e equipamentos de áudio",
        "curto": "assistência técnica",
    },
    "lojas-de-instrumentos-musicais": {
        "rotulo": "Lojas de instrumentos musicais",
        "h1": "Lojas de instrumentos musicais e acessórios",
        "curto": "comércio de instrumentos musicais",
    },
    "luthier": {
        "rotulo": "Luthiers",
        "h1": "Luthiers e fabricação de instrumentos musicais",
        "curto": "luthieria",
    },
    "escolas-de-musica": {
        "rotulo": "Escolas de música",
        "h1": "Escolas e professores de música",
        "curto": "ensino de música",
    },
    "estudios-de-gravacao": {
        "rotulo": "Estúdios de gravação",
        "h1": "Estúdios de gravação e edição de som",
        "curto": "gravação de som",
    },
    "locacao-som-palco": {
        "rotulo": "Palcos, som e locação",
        "h1": "Locação de som, iluminação e palcos",
        "curto": "locação de som e palco",
    },
}
