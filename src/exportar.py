"""Alvo 'exportar': CSV e Parquet por vertical, agregado por cidade e lista MEI.

CSV para abrir no Excel e revisar à mão; Parquet para a fase 2 consumir rápido.
"""
import sys
import time

from config import SAIDA
from db import conectar

# Ordem de colunas exatamente como pedida no briefing (seção 6.2).
COLUNAS = """id, cnpj_formatado, nome, nome_fantasia, razao_social,
logradouro, numero, complemento, bairro, cep,
municipio, municipio_slug, ibge, uf,
telefone, email, dominio_email, dominio_provedor, site_candidato,
cnae_principal, cnae_principal_desc, cnaes_secundarios, origem_cnae,
data_abertura, porte, mei, matriz, suspeita_duplicata,
vertical, safra"""


def main() -> int:
    con = conectar(read_only=True)
    (SAIDA / "csv").mkdir(parents=True, exist_ok=True)
    (SAIDA / "parquet").mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    verticais = [r[0] for r in con.execute(
        "SELECT DISTINCT vertical FROM exportacao ORDER BY vertical").fetchall()]
    if not verticais:
        print("ERRO: nenhuma vertical em 'exportacao'. Rode 'make carregar'.",
              file=sys.stderr)
        return 1

    largura = max(len(v) for v in verticais)
    for v in verticais:
        # ordem estável: sem isso o diff entre duas execuções é ruído puro
        base = (f"SELECT {COLUNAS} FROM exportacao WHERE vertical = '{v}' "
                f"ORDER BY uf, municipio_slug, nome, id")
        csv_ = SAIDA / "csv" / f"{v}.csv"
        pq = SAIDA / "parquet" / f"{v}.parquet"
        con.execute(f"COPY ({base}) TO '{csv_}' (HEADER, DELIMITER ',')")
        con.execute(f"COPY ({base}) TO '{pq}' (FORMAT PARQUET, COMPRESSION ZSTD)")

        cidade = (f"SELECT uf, municipio, municipio_slug, ibge, total, "
                  f"com_telefone, com_site_candidato "
                  f"FROM vertical_por_cidade WHERE vertical = '{v}' "
                  f"ORDER BY total DESC, uf, municipio")
        cid_csv = SAIDA / "csv" / f"{v}-por-cidade.csv"
        con.execute(f"COPY ({cidade}) TO '{cid_csv}' (HEADER, DELIMITER ',')")

        n_reg = con.execute(f"SELECT count(*) FROM exportacao WHERE vertical = '{v}'").fetchone()[0]
        n_cid = con.execute(f"SELECT count(*) FROM vertical_por_cidade WHERE vertical = '{v}'").fetchone()[0]
        n_site = con.execute(f"SELECT count(site_candidato) FROM exportacao WHERE vertical = '{v}'").fetchone()[0]
        print(f"  {v:<{largura}}  {n_reg:>7,} registros  {n_cid:>5,} cidades  "
              f"{n_site:>7,} com site candidato".replace(",", "."), flush=True)

    # MEI: pessoa física, precisa de opt-out próprio antes de qualquer publicação
    mei = SAIDA / "registros-mei.csv"
    con.execute(f"COPY (SELECT * FROM registros_mei) TO '{mei}' (HEADER, DELIMITER ',')")
    n_mei = con.execute("SELECT count(*) FROM registros_mei").fetchone()[0]
    print(f"  {'registros-mei.csv':<{largura}}  {n_mei:>7,} registros".replace(",", "."))

    print(f"exportação concluída em {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
