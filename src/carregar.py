"""Alvo 'carregar': constrói cnpj.duckdb a partir de extraidos/.

Etapas, com contagem de linhas registrada em cada filtro para dar rastro de
onde os registros somem.
"""
import sys
import time
from pathlib import Path

from config import EXTRAIDOS, RAIZ, SAIDA
from db import conectar, executar_arquivo, log_contagem

# Referência opcional do IBGE. Se não existir, a coluna ibge sai NULL — nunca
# chutada. Formato esperado: CSV com cabeçalho contendo, em qualquer ordem,
# uma coluna de código IBGE (7 dígitos), uma de nome do município e uma de UF.
REF_IBGE = RAIZ / "dados-referencia" / "ibge-municipios.csv"


def _criar_ibge_municipios(con) -> int:
    """Cria ibge_municipios. Vazia se não houver arquivo de referência."""
    con.execute("""
        CREATE OR REPLACE TABLE ibge_municipios (
            codigo_ibge VARCHAR, nome VARCHAR, uf VARCHAR, nome_slug VARCHAR
        )
    """)
    if not REF_IBGE.exists():
        print(f"[ibge] {REF_IBGE.relative_to(RAIZ)} não existe -> coluna ibge ficará NULL")
        return 0

    bruto = con.execute(
        "SELECT * FROM read_csv(?, header=true, all_varchar=true, "
        "auto_detect=true, sample_size=-1)", [str(REF_IBGE)]
    )
    colunas = [d[0] for d in bruto.description]
    achar = lambda *chaves: next(  # noqa: E731
        (c for c in colunas if any(k in c.lower() for k in chaves)), None
    )
    col_cod, col_nome, col_uf = achar("ibge", "codigo", "código"), achar("nome", "municipio", "município"), achar("uf", "sigla", "estado")
    if not all([col_cod, col_nome, col_uf]):
        raise SystemExit(
            f"[ibge] não identifiquei as colunas em {REF_IBGE.name}.\n"
            f"       colunas encontradas: {colunas}\n"
            f"       preciso de uma de código IBGE, uma de nome e uma de UF."
        )
    print(f"[ibge] usando colunas: código={col_cod!r} nome={col_nome!r} uf={col_uf!r}")
    con.execute(f"""
        INSERT INTO ibge_municipios
        SELECT regexp_replace("{col_cod}", '[^0-9]', '', 'g') AS codigo_ibge,
               "{col_nome}"                                   AS nome,
               upper(trim("{col_uf}"))                        AS uf,
               slug("{col_nome}")                             AS nome_slug
        FROM read_csv(?, header=true, all_varchar=true, auto_detect=true, sample_size=-1)
    """, [str(REF_IBGE)])
    return con.execute("SELECT count(*) FROM ibge_municipios").fetchone()[0]


def main() -> int:
    if not EXTRAIDOS.exists() or not any(EXTRAIDOS.glob("*.ESTABELE.csv")):
        print("ERRO: rode 'make preparar' primeiro.", file=sys.stderr)
        return 1
    SAIDA.mkdir(exist_ok=True)
    con = conectar()
    t0 = time.time()

    for arquivo in ("20_macros.sql", "05_views_csv.sql", "10_referencias.sql"):
        executar_arquivo(con, arquivo)
        print(f"[ok] {arquivo}  ({time.time() - t0:.0f}s)", flush=True)

    executar_arquivo(con, "30_tabelas.sql")
    print(f"[ok] 30_tabelas.sql  ({time.time() - t0:.0f}s)", flush=True)

    # --- rastro de contagens: de onde partimos e o que cada filtro corta
    log_contagem(con, "empresas (linhas carregadas)", "SELECT count(*) FROM empresas")
    log_contagem(con, "simples (linhas carregadas)", "SELECT count(*) FROM simples")
    log_contagem(con, "estabelecimentos (todas as situações)",
                 "SELECT count(*) FROM estabelecimentos")
    log_contagem(con, "estabelecimentos DISTINTOS por CNPJ completo",
                 "SELECT count(DISTINCT cnpj_basico || cnpj_ordem || cnpj_dv) FROM estabelecimentos")
    log_contagem(con, "  filtro situacao_cadastral = '02' (ativos)",
                 "SELECT count(*) FROM estabelecimentos WHERE situacao_cadastral = '02'")
    log_contagem(con, "  ativos com CNAE secundário preenchido",
                 "SELECT count(*) FROM estabelecimentos "
                 "WHERE situacao_cadastral = '02' AND coalesce(cnae_fiscal_secundaria, '') <> ''")

    # contagem por CNAE: alimenta a seção 1 do relatório e a decisão de verticais
    executar_arquivo(con, "12_contagem_por_cnae.sql")
    print(f"[ok] 12_contagem_por_cnae.sql  ({time.time() - t0:.0f}s)", flush=True)

    n_ibge = _criar_ibge_municipios(con)
    print(f"[ibge] {n_ibge} municípios de referência carregados")
    executar_arquivo(con, "40_municipios.sql")
    print(f"[ok] 40_municipios.sql  ({time.time() - t0:.0f}s)", flush=True)

    log_contagem(con, "municípios RFB", "SELECT count(*) FROM municipios")
    log_contagem(con, "  com UF resolvida", "SELECT count(*) FROM municipios WHERE uf IS NOT NULL")
    log_contagem(con, "  com código IBGE casado", "SELECT count(*) FROM municipios WHERE ibge IS NOT NULL")
    log_contagem(con, "  NÃO casados (vão para CSV)", "SELECT count(*) FROM municipios_nao_casados")
    log_contagem(con, "  colisões de slug dentro da mesma UF",
                 "SELECT count(*) FROM municipios_slug_duplicado")

    con.execute(f"""COPY (SELECT * FROM municipios_nao_casados)
                    TO '{SAIDA / "municipios-nao-casados.csv"}'
                    (HEADER, DELIMITER ',')""")
    print("[ok] saida/municipios-nao-casados.csv")

    # --- verticais e alvo
    executar_arquivo(con, "45_verticais.sql")
    invalidos = con.execute("SELECT * FROM vertical_cnae_invalido").fetchall()
    if invalidos:
        print(f"ERRO: CNAEs do mapa de verticais não existem na RFB: {invalidos}",
              file=sys.stderr)
        return 1
    log_contagem(con, "pares (vertical, cnae) no mapa", "SELECT count(*) FROM vertical_cnae")
    log_contagem(con, "CNAEs alvo distintos",
                 "SELECT count(DISTINCT cnae) FROM vertical_cnae")

    executar_arquivo(con, "50_alvo.sql")
    executar_arquivo(con, "60_relatorio.sql")
    print(f"[ok] 50_alvo.sql  ({time.time() - t0:.0f}s)", flush=True)

    log_contagem(con, "pares (estabelecimento, cnae alvo)",
                 "SELECT count(*) FROM estabelecimento_cnae_alvo")
    log_contagem(con, "  vindos do CNAE principal",
                 "SELECT count(*) FROM estabelecimento_cnae_alvo WHERE origem = 'principal'")
    log_contagem(con, "  vindos de CNAE secundário",
                 "SELECT count(*) FROM estabelecimento_cnae_alvo WHERE origem = 'secundario'")
    log_contagem(con, "pares (estabelecimento, vertical) N:N",
                 "SELECT count(*) FROM estabelecimento_vertical")
    log_contagem(con, "estabelecimentos_alvo (linhas únicas)",
                 "SELECT count(*) FROM estabelecimentos_alvo")
    log_contagem(con, "  em mais de uma vertical",
                 "SELECT count(*) FROM (SELECT id FROM estabelecimento_vertical "
                 "GROUP BY id HAVING count(*) > 1)")
    log_contagem(con, "  com telefone válido",
                 "SELECT count(*) FROM estabelecimentos_alvo WHERE telefone IS NOT NULL")
    log_contagem(con, "  com site candidato",
                 "SELECT count(*) FROM estabelecimentos_alvo WHERE site_candidato IS NOT NULL")
    log_contagem(con, "  marcados suspeita_duplicata",
                 "SELECT count(*) FROM estabelecimentos_alvo WHERE suspeita_duplicata")
    log_contagem(con, "  sem código IBGE",
                 "SELECT count(*) FROM estabelecimentos_alvo WHERE ibge IS NULL")

    print(f"carga concluída em {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
