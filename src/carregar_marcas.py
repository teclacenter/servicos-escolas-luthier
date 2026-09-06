"""Alvo 'carregar-marcas': põe as redes autorizadas por marca dentro do banco.

Separado de `carregar` porque o custo é outro: a base da Receita leva minutos,
isto leva segundos. Editar um rótulo em src/marcas.py ou recoletar uma fonte não
deveria obrigar a reconstruir 72 milhões de linhas.

Depende de `carregar` já ter rodado uma vez: o casamento de município usa a
tabela `municipios` (que define os slugs das URLs) e o casamento de CNPJ usa
`estabelecimentos_alvo`.
"""
import sys
import time

from config import RAIZ
from db import conectar, executar_arquivo, log_contagem
from marcas import FONTES, MARCAS

CSV = RAIZ / "dados-referencia" / "marcas-autorizadas.csv"


def _criar_catalogo(con) -> None:
    """Despeja src/marcas.py em duas tabelas.

    O catálogo é código Python porque tem texto editorial (o `sobre` de cada
    marca) e porque a relação marca -> distribuidor é revisada à mão. Aqui ele
    vira tabela para poder entrar nos joins; a fonte da verdade continua sendo
    o arquivo .py, e estas tabelas são recriadas a cada carga.
    """
    con.execute("""
        CREATE OR REPLACE TABLE fonte_rede (
            fonte VARCHAR PRIMARY KEY, titular VARCHAR, pagina VARCHAR,
            termo VARCHAR, bloqueada VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO fonte_rede VALUES (?, ?, ?, ?, ?)",
        [(s, f["titular"], f["pagina"], f["termo"], f.get("bloqueada"))
         for s, f in FONTES.items()])

    con.execute("""
        CREATE OR REPLACE TABLE marca (
            marca VARCHAR PRIMARY KEY, marca_nome VARCHAR, fonte VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO marca VALUES (?, ?, ?)",
        # marca de fonte bloqueada não entra: sem oficinas, não há o que publicar
        [(s, m["nome"], m["fonte"]) for s, m in MARCAS.items()
         if not FONTES[m["fonte"]].get("bloqueada")])


def _criar_bruto(con) -> int:
    con.execute("""
        CREATE OR REPLACE TABLE marca_posto_bruto (
            fonte VARCHAR, coletado_em DATE, posto_id VARCHAR,
            nome VARCHAR, uf_fonte VARCHAR,
            cidade_fonte VARCHAR, bairro VARCHAR, endereco VARCHAR, cep VARCHAR,
            telefones VARCHAR, email VARCHAR, site VARCHAR, contato VARCHAR,
            horario VARCHAR, segmento VARCHAR
        )
    """)
    if not CSV.exists():
        return 0
    con.execute("""
        INSERT INTO marca_posto_bruto
        SELECT fonte, try_cast(coletado_em AS DATE), posto_id, nome, uf_fonte,
               cidade_fonte, bairro, endereco, cep, telefones, email, site,
               contato, horario, segmento
        FROM read_csv(?, header=true, all_varchar=true, sample_size=-1)
        -- fonte sem marca no catálogo geraria oficina órfã, sem página
        WHERE fonte IN (SELECT fonte FROM marca)
    """, [str(CSV)])
    return con.execute("SELECT count(*) FROM marca_posto_bruto").fetchone()[0]


def carregar(con) -> int:
    """Cria as tabelas de marca. Devolve o número de oficinas publicáveis."""
    # As macros ficam gravadas no catálogo do DuckDB. Rodar só este alvo depois
    # de editar sql/20_macros.sql usaria a versão antiga, e o erro apareceria
    # como um telefone rotulado errado na página — difícil de rastrear até aqui.
    executar_arquivo(con, "20_macros.sql")
    _criar_catalogo(con)
    n = _criar_bruto(con)
    if not n:
        print(f"[marcas] {CSV.relative_to(RAIZ)} não existe ou está vazio "
              f"-> rode 'make coletar-marcas'. Site sai sem páginas por marca.")
        # As views precisam existir mesmo vazias: o gerador do site consulta
        # sempre, e um erro de tabela ausente esconderia o problema real.
        executar_arquivo(con, "47_marcas.sql")
        return 0
    executar_arquivo(con, "47_marcas.sql")

    log_contagem(con, "oficinas coletadas (marca_posto_bruto)",
                 "SELECT count(*) FROM marca_posto_bruto")
    log_contagem(con, "  publicáveis (com estado resolvido)",
                 "SELECT count(*) FROM marca_posto")
    log_contagem(con, "  com município casado",
                 "SELECT count(*) FROM marca_posto WHERE municipio_slug IS NOT NULL")
    log_contagem(con, "  sem município (só página de estado)",
                 "SELECT count(*) FROM marca_posto_sem_municipio")
    log_contagem(con, "  casadas com um CNPJ ativo",
                 "SELECT count(*) FROM marca_posto WHERE cnpj IS NOT NULL")
    log_contagem(con, "pares oficina x marca",
                 "SELECT count(*) FROM publicacao_marca")
    return con.execute("SELECT count(*) FROM marca_posto").fetchone()[0]


def main() -> int:
    con = conectar()
    if not con.execute("SELECT count(*) FROM duckdb_tables() "
                       "WHERE table_name = 'municipios'").fetchone()[0]:
        print("ERRO: tabela 'municipios' não existe. Rode 'make carregar' antes.",
              file=sys.stderr)
        return 1
    t0 = time.time()
    n = carregar(con)
    print(f"\n{n} oficinas carregadas em {time.time() - t0:.0f}s")
    cobertura = con.execute("SELECT * FROM marca_cobertura")
    titulos = [d[0] for d in cobertura.description]
    linhas = [[str(x) for x in linha] for linha in cobertura.fetchall()]
    largura = [max(len(t), *(len(l[i]) for l in linhas)) if linhas else len(t)
               for i, t in enumerate(titulos)]
    for linha in [titulos, *linhas]:
        print("  " + "  ".join(x.rjust(w) for x, w in zip(linha, largura)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
