"""Converte o JSON da API de localidades do IBGE no CSV de referência.

Único ponto do projeto que tocou a rede, com autorização explícita e pontual:
a base da RFB não traz código IBGE e não havia nenhuma lista em disco.
Fonte: https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado
O JSON baixado fica em tmp/ para auditoria; o CSV gerado é versionável.
"""
import csv
import json
import sys
from pathlib import Path

from config import RAIZ

ORIGEM = RAIZ / "tmp" / "ibge-municipios.json"
DESTINO = RAIZ / "dados-referencia" / "ibge-municipios.csv"


def main() -> int:
    if not ORIGEM.exists():
        print(f"ERRO: {ORIGEM} não existe.", file=sys.stderr)
        return 1
    dados = json.loads(ORIGEM.read_text(encoding="utf-8"))
    DESTINO.parent.mkdir(exist_ok=True)
    with DESTINO.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["codigo_ibge", "nome", "uf"])
        for m in dados:
            w.writerow([m["municipio-id"], m["municipio-nome"], m["UF-sigla"]])
    print(f"{len(dados)} municípios -> {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
