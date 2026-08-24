"""Audita bytes problemáticos nos CSVs brutos.
Motivo: o leitor latin-1 do DuckDB recusou os arquivos e 'latin-1' cobre os 256
bytes — então o problema é validação de byte, não de mapa de caracteres."""
import sys
from collections import Counter
from pathlib import Path

from config import BRUTOS

CHUNK = 64 << 20
# Suspeitos: NUL, controles C0 (menos TAB/LF/CR), DEL e o bloco C1.
SUSPEITOS = (
    {0x00}
    | set(range(0x01, 0x09)) | {0x0B, 0x0C} | set(range(0x0E, 0x20))
    | {0x7F} | set(range(0x80, 0xA0))
)


def auditar(caminho: Path) -> Counter:
    achados = Counter()
    with caminho.open("rb") as fh:
        while pedaco := fh.read(CHUNK):
            for b in set(pedaco) & SUSPEITOS:
                achados[b] += pedaco.count(bytes([b]))
    return achados


if __name__ == "__main__":
    padroes = sys.argv[1:] or ["*.ESTABELE", "*.EMPRECSV", "*.SIMPLES.CSV.*"]
    for padrao in padroes:
        for caminho in sorted(BRUTOS.glob(padrao)):
            achados = auditar(caminho)
            desc = ", ".join(f"0x{b:02X}={n}" for b, n in sorted(achados.items())) or "-"
            print(f"{caminho.name:<40} {desc}", flush=True)
