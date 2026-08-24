"""Alvo 'publicar': gera saida/publicacao.sqlite.

Para que serve, se o site é estático: é o banco de consulta rápida para o que
vier depois — busca, filtro, uma API interna, regeração parcial de páginas.
SQLite e não DuckDB porque aqui o padrão de uso é o oposto do analítico: muitas
consultas pequenas por chave (área + estado + cidade). SQLite resolve isso com
índice B-tree, arquivo único, driver em qualquer linguagem, nenhum processo em
pé e consumo de memória desprezível — que era o pedido.

Só entra o que é publicável e já formatado: nenhum cálculo em tempo de servir.
"""
import sqlite3
import sys
import time

from config import SAFRA, SAIDA
from db import conectar

DESTINO = SAIDA / "publicacao.sqlite"
LOTE = 50_000

ESQUEMA = """
PRAGMA journal_mode = OFF;
PRAGMA synchronous = OFF;

CREATE TABLE estabelecimento (
    id              TEXT NOT NULL,      -- CNPJ completo sem máscara
    vertical        TEXT NOT NULL,
    uf              TEXT NOT NULL,
    municipio       TEXT NOT NULL,
    municipio_slug  TEXT NOT NULL,
    ibge            TEXT,
    nome_fantasia   TEXT,
    razao_social    TEXT,
    endereco        TEXT,
    cep             TEXT,
    cidade_uf       TEXT,
    telefone            TEXT,           -- E.164, como consta na Receita
    telefone_tipo       TEXT,           -- 'fixo' | 'movel'
    telefone_formatado  TEXT,
    telefone_9          TEXT,           -- móvel com o 9º dígito (derivado)
    telefone_9_formatado TEXT,
    telefone_2            TEXT,
    telefone_2_tipo       TEXT,
    telefone_2_formatado  TEXT,
    telefone_2_9          TEXT,
    telefone_2_9_formatado TEXT,
    email           TEXT,
    site_candidato  TEXT,
    cnpj_formatado  TEXT,
    mei             INTEGER,
    suspeita_duplicata INTEGER,
    origem_cnae     TEXT,               -- 'principal' | 'secundario'
    cnae_principal  TEXT,
    cnae_principal_desc TEXT,
    ficha           TEXT,               -- bloco pronto para exibir
    PRIMARY KEY (vertical, id)
) WITHOUT ROWID;

CREATE TABLE cidade (
    vertical       TEXT NOT NULL,
    uf             TEXT NOT NULL,
    municipio      TEXT NOT NULL,
    municipio_slug TEXT NOT NULL,
    ibge           TEXT,
    total          INTEGER NOT NULL,
    com_telefone   INTEGER NOT NULL,
    com_email      INTEGER NOT NULL,
    PRIMARY KEY (vertical, uf, municipio_slug)
) WITHOUT ROWID;

CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT);
"""

# Índice único que serve a consulta da página: área + estado + cidade.
# Cobre também os prefixos (vertical) e (vertical, uf), então dá conta das três
# profundidades de página com uma estrutura só.
INDICES = """
CREATE INDEX ix_est_lugar ON estabelecimento (vertical, uf, municipio_slug);
CREATE INDEX ix_est_uf    ON estabelecimento (uf, municipio_slug);
CREATE INDEX ix_cid_uf    ON cidade (vertical, uf);
"""


def main() -> int:
    con = conectar(read_only=True)
    n = con.execute("SELECT count(*) FROM publicacao").fetchone()[0]
    if not n:
        print("ERRO: view 'publicacao' vazia. Rode 'make carregar'.", file=sys.stderr)
        return 1
    t0 = time.time()
    SAIDA.mkdir(parents=True, exist_ok=True)
    DESTINO.unlink(missing_ok=True)
    sq = sqlite3.connect(DESTINO)
    sq.executescript(ESQUEMA)

    colunas = [d[0] for d in con.execute("SELECT * FROM publicacao LIMIT 0").description]
    marcas = ",".join("?" * len(colunas))
    inserir = f'INSERT INTO estabelecimento ({",".join(colunas)}) VALUES ({marcas})'

    cur = con.execute("SELECT * FROM publicacao")
    total = 0
    while lote := cur.fetchmany(LOTE):
        sq.executemany(inserir, lote)
        total += len(lote)
        print(f"  {total:>9,} / {n:,} fichas".replace(",", "."), end="\r", flush=True)
    sq.commit()

    sq.executemany(
        "INSERT INTO cidade (vertical,uf,municipio,municipio_slug,ibge,total,"
        "com_telefone,com_email) VALUES (?,?,?,?,?,?,?,?)",
        con.execute("""SELECT vertical, uf, municipio, municipio_slug, ibge,
                              total, com_telefone, com_email
                       FROM vertical_por_cidade WHERE uf <> 'EX'""").fetchall())
    sq.executemany("INSERT INTO meta VALUES (?,?)",
                   [("safra", SAFRA), ("fichas", str(total)),
                    ("fonte", "Receita Federal do Brasil - CNPJ")])
    sq.executescript(INDICES)
    sq.commit()
    sq.execute("ANALYZE")
    sq.execute("VACUUM")
    sq.close()

    mb = DESTINO.stat().st_size / 1e6
    print(f"  {total:,} fichas -> {DESTINO.name} ({mb:,.0f} MB) "
          f"em {time.time() - t0:.0f}s".replace(",", "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
