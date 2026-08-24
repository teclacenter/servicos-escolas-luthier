"""Conexão DuckDB com os pragmas obrigatórios e execução de arquivos .sql."""
import re
import sys
import duckdb

from config import DB, MEMORY_LIMIT, TMP, BRUTOS, EXTRAIDOS, SAFRA, SQL


def conectar(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    TMP.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB), read_only=read_only)
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET temp_directory = '{TMP}'")
    con.execute("SET preserve_insertion_order = false")
    return con


def executar_arquivo(con, nome: str) -> None:
    """Roda um .sql de sql/, substituindo os placeholders de caminho."""
    texto = (SQL / nome).read_text(encoding="utf-8")
    texto = texto.replace("{BRUTOS}", str(BRUTOS))
    texto = texto.replace("{EXTRAIDOS}", str(EXTRAIDOS))
    texto = texto.replace("{SAFRA}", SAFRA)
    for stmt in dividir_sql(texto):
        con.execute(stmt)


def dividir_sql(texto: str):
    """Divide por ';' fora de literais/comentários — sem dependência externa."""
    for bruto in re.split(r";\s*(?:\n|$)", texto):
        stmt = "\n".join(
            l for l in bruto.splitlines() if not l.strip().startswith("--")
        ).strip()
        if stmt:
            yield stmt


def log_contagem(con, etapa: str, sql: str) -> int:
    n = con.execute(sql).fetchone()[0]
    print(f"[contagem] {etapa:<52} {n:>12,}".replace(",", "."), flush=True)
    return n
