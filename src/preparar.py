"""Etapa 'preparar': normaliza os CSVs brutos para UTF-8 em extraidos/.

Por que existe (não estava no plano original, que previa descompactar ZIPs):
  1. Nesta máquina os arquivos JÁ vêm descompactados, sem ZIP nenhum — não há
     o que extrair. O que falta é normalizar.
  2. O leitor latin-1 do DuckDB RECUSA o arquivo inteiro se encontrar byte de
     controle (NUL, SUB, DEL) ou do bloco C1. A safra D60808 tem 17 desses
     bytes em ~73 milhões de linhas. Sem tratar, a carga simplesmente aborta.
  3. Convertidos para UTF-8, o DuckDB usa o caminho de leitura nativo (mais
     rápido) e a armadilha de encoding deixa de existir para todas as etapas
     seguintes. Os nomes ganham extensão .csv de brinde.

A conversão é ISO-8859-1 -> UTF-8 (mapa de 256 bytes, sem perda) e a ÚNICA
remoção é a dos bytes de controle contados e reportados abaixo. Nada é inferido.
"""
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from config import BRUTOS, GLOBS, RAIZ

EXTRAIDOS = RAIZ / "extraidos"
# Bytes removidos: NUL(00), SUB(1A), DEL(7F) e SS3(8F). Todos são controles sem
# informação — 8F é indefinido tanto em ISO-8859-1 quanto em cp1252, então não há
# ambiguidade sobre qual caractere se perde: nenhum. Contagem na safra D60808: 33.
DESCARTAR = r"\000\032\177\217"


def _converter(origem):
    destino = EXTRAIDOS / (origem.name + ".csv")
    if destino.exists() and destino.stat().st_mtime >= origem.stat().st_mtime:
        return f"{origem.name:<40} já convertido"
    parcial = destino.with_suffix(".csv.parcial")
    # tr remove os bytes de controle; iconv troca o encoding. Pipe, sem temporário.
    cmd = (
        f"LC_ALL=C tr -d '{DESCARTAR}' < '{origem}' "
        f"| iconv -f ISO-8859-1 -t UTF-8 > '{parcial}'"
    )
    r = subprocess.run(["bash", "-o", "pipefail", "-c", cmd], capture_output=True, text=True)
    if r.returncode != 0:
        parcial.unlink(missing_ok=True)
        raise RuntimeError(f"{origem.name}: {r.stderr.strip()}")
    parcial.rename(destino)          # rename atômico: nunca fica meio arquivo
    mb = destino.stat().st_size / 1e6
    return f"{origem.name:<40} -> {destino.name} ({mb:,.0f} MB)"


def main() -> int:
    EXTRAIDOS.mkdir(exist_ok=True)
    origens = sorted(
        {c for padrao in GLOBS.values() for c in BRUTOS.glob(padrao)}
    )
    if not origens:
        print(f"ERRO: nenhum arquivo encontrado em {BRUTOS}", file=sys.stderr)
        return 1
    print(f"convertendo {len(origens)} arquivos para UTF-8 em extraidos/", flush=True)
    erros = []
    with ThreadPoolExecutor(max_workers=6) as pool:   # I/O bound, não CPU
        for fut in [pool.submit(_converter, o) for o in origens]:
            try:
                print("  " + fut.result(), flush=True)
            except Exception as e:                    # noqa: BLE001
                erros.append(str(e))
                print(f"  FALHOU: {e}", file=sys.stderr, flush=True)
    if erros:
        return 1
    print("preparação concluída", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
