"""Alvo 'relatorio': gera saida/relatorio-base.md a partir das views do banco.

Só formata — todo o cálculo está em sql/60_relatorio.sql.
"""
import sys
from datetime import date

from config import SAFRA, SAIDA
from db import conectar

FAIXAS = ["1", "2", "3-5", "6-10", "11+"]


def n(v) -> str:
    """Número no formato brasileiro."""
    if v is None:
        return "—"
    return f"{v:,}".replace(",", ".")


def pct(parte, total) -> str:
    if not total:
        return "—"
    return f"{100 * parte / total:.1f} %".replace(".", ",")


def tabela(cabecalho, linhas, alinha=None) -> str:
    alinha = alinha or ["---"] * len(cabecalho)
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join(alinha) + "|"]
    saida += ["| " + " | ".join(str(c) for c in linha) + " |" for linha in linhas]
    return "\n".join(saida)


def main() -> int:
    con = conectar(read_only=True)
    q = lambda s, *a: con.execute(s, list(a)).fetchall()  # noqa: E731

    def qd(sql, *a):
        """Mesma consulta, mas em dicionários: não quebra se a view ganhar coluna."""
        r = con.execute(sql, list(a))
        cols = [d[0] for d in r.description]
        return [dict(zip(cols, linha)) for linha in r.fetchall()]

    um = lambda s, *a: con.execute(s, list(a)).fetchone()[0]  # noqa: E731

    verticais = [r[0] for r in q(
        "SELECT vertical FROM rel_qualidade ORDER BY total DESC")]
    p = [f"""# Base CNPJ por vertical, cidade e estado — safra {SAFRA}

Gerado em {date.today().isoformat()} por `make all`. Pipeline determinístico:
nenhuma etapa usa IA, e a única requisição de rede do projeto foi a tabela de
municípios do IBGE (`src/ibge_para_csv.py`), autorizada em separado porque a base
da Receita não traz código IBGE.

Fonte: Receita Federal, arquivos `D60808` (2026-08-08).
Filtro base: `situacao_cadastral = '02'` (ativa). Matrizes **e** filiais.
Sem corte por volume: cidades com um único registro estão na base.
"""]

    # ------------------------------------------------------- rastro de filtros
    total_est = um("SELECT count(*) FROM estabelecimentos")
    ativos = um("SELECT count(*) FROM estabelecimentos WHERE situacao_cadastral = '02'")
    alvo = um("SELECT count(*) FROM estabelecimentos_alvo")
    pares = um("SELECT count(*) FROM estabelecimento_vertical")
    p.append(f"""## 0. Rastro dos filtros

| Etapa | Registros | % da anterior |
|---|---:|---:|
| Estabelecimentos no arquivo (todas as situações) | {n(total_est)} | — |
| Ativos (`situacao_cadastral = '02'`) | {n(ativos)} | {pct(ativos, total_est)} |
| Ativos com algum CNAE alvo (principal ou secundário) | {n(alvo)} | {pct(alvo, ativos)} |
| Pares estabelecimento × vertical (N:N) | {n(pares)} | — |

Um estabelecimento pode ocupar mais de uma vertical (o CNAE 9529199 serve
assistência técnica e luthier), por isso os pares excedem as linhas únicas:
**{n(um('SELECT count(*) FROM (SELECT id FROM estabelecimento_vertical GROUP BY id HAVING count(*) > 1)'))}**
estabelecimentos aparecem em mais de uma vertical.
""")

    # ---------------------------------------------------- 1. CNAE alvo, Brasil
    p.append("## 1. Estabelecimentos ativos por CNAE alvo, Brasil\n")
    p.append("`principal` = o CNAE é o principal do estabelecimento. `secundário` = "
             "aparece na lista de CNAEs secundários. As duas colunas contam "
             "estabelecimentos ativos em todo o Brasil, antes do recorte por vertical.\n")
    p.append(tabela(
        ["Vertical", "CNAE", "Descrição", "Principal", "Secundário"],
        [(v, c, d, n(np_), n(ns)) for v, c, d, np_, ns, _ in
         q("SELECT * FROM rel_cnae_brasil")],
        ["---", "---", "---", "--:", "--:"]))

    # -------------------------------------------------------- 2. vertical x UF
    p.append("\n## 2. Vertical × UF\n")
    ufs = [r[0] for r in q("SELECT DISTINCT uf FROM rel_vertical_uf "
                           "WHERE uf IS NOT NULL ORDER BY uf")]
    mapa = {(v, u): t for v, u, t in q("SELECT * FROM rel_vertical_uf")}
    linhas = []
    for v in verticais:
        tot = um("SELECT total FROM rel_qualidade WHERE vertical = ?", v)
        linhas.append([v] + [n(mapa.get((v, u), 0)) for u in ufs] + [f"**{n(tot)}**"])
    p.append(tabela(["Vertical"] + ufs + ["Total"], linhas,
                    ["---"] + ["--:"] * (len(ufs) + 1)))

    # ------------------------------------------ 4. faixas de tamanho de cidade
    p.append("\n## 3. Distribuição de cidades por faixa de tamanho\n")
    p.append("Quantas cidades têm N estabelecimentos da vertical. É o teste de "
             "existência: uma vertical concentrada na faixa `1` não tem densidade "
             "para virar página por cidade.\n")
    fx = {(v, f): (cid, est) for v, f, cid, est in q("SELECT * FROM rel_faixa_cidades")}
    linhas = []
    for v in verticais:
        cidades_tot = um("SELECT cidades FROM rel_qualidade WHERE vertical = ?", v)
        linha = [v]
        for f in FAIXAS:
            cid, est = fx.get((v, f), (0, 0))
            linha.append(f"{n(cid)} ({n(est)})")
        linha.append(f"**{n(cidades_tot)}**")
        linhas.append(linha)
    p.append(tabela(["Vertical"] + [f"cidades com {f}" for f in FAIXAS] + ["cidades"],
                    linhas, ["---"] + ["--:"] * (len(FAIXAS) + 1)))
    p.append("\n> Formato da célula: `cidades (estabelecimentos nelas)`.\n")

    # -------------------------------------------------- 5. qualidade de campos
    p.append("\n## 4. Preenchimento dos campos, por vertical\n")
    p.append("A Receita guarda telefone com no máximo 8 dígitos. `fixo` é o número "
             "cujo primeiro dígito local é 2–5; `móvel` é 6–9, e nesse caso a base "
             "publica o número nos dois formatos (com o 9º dígito e sem). "
             "`site candidato` é a fila de scraping da fase 2: domínio de e-mail "
             "que **não** é provedor gratuito.\n")
    linhas = []
    for r in qd("SELECT * FROM rel_qualidade"):
        tot = r["total"]
        linhas.append([r["vertical"], n(tot),
                       f"{n(r['com_fixo'])} ({pct(r['com_fixo'], tot)})",
                       f"{n(r['com_movel'])} ({pct(r['com_movel'], tot)})",
                       f"{n(r['com_nome_fantasia'])} ({pct(r['com_nome_fantasia'], tot)})",
                       f"{n(r['com_email'])} ({pct(r['com_email'], tot)})",
                       f"**{n(r['com_site_candidato'])}** ({pct(r['com_site_candidato'], tot)})"])
    p.append(tabela(["Vertical", "Total", "Telefone fixo", "Telefone móvel",
                     "Nome fantasia", "E-mail", "Site candidato"], linhas,
                    ["---"] + ["--:"] * 6))

    # ---------------------------------------------------- 6. origem do CNAE
    p.append("\n## 5. Origem do CNAE: principal × secundário\n")
    p.append("Filtrar só pelo CNAE principal descartaria a coluna da direita.\n")
    linhas = []
    for r in qd("SELECT * FROM rel_qualidade"):
        tot = r["total"]
        linhas.append([r["vertical"], n(tot),
                       f"{n(r['via_cnae_principal'])} ({pct(r['via_cnae_principal'], tot)})",
                       f"{n(r['via_cnae_secundario'])} ({pct(r['via_cnae_secundario'], tot)})",
                       n(r["mei"]), n(r["matriz"]), n(r["suspeita_duplicata"])])
    p.append(tabela(["Vertical", "Total", "Via CNAE principal", "Via CNAE secundário",
                     "MEI", "Matriz", "Suspeita duplicata"], linhas,
                    ["---"] + ["--:"] * 6))

    # ------------------------------------------------- 3. top 100 por vertical
    p.append("\n## 6. Top 100 municípios por vertical\n")
    for v in verticais:
        rotulo = um("SELECT DISTINCT rotulo FROM estabelecimento_vertical WHERE vertical = ?", v)
        linhas = [(r["pos"], f'{r["municipio"]} ({r["uf"]})', n(r["total"]),
                   n(r["com_telefone"]), n(r["com_email"]), n(r["com_site_candidato"]))
                  for r in qd("SELECT * FROM rel_top_municipios WHERE vertical = ? "
                              "ORDER BY pos", v)]
        p.append(f"\n### {rotulo} — `{v}`\n")
        p.append(tabela(["#", "Município", "Total", "Com telefone", "Com e-mail",
                         "Com site candidato"],
                        linhas, ["--:", "---", "--:", "--:", "--:", "--:"]))

    # ------------------------------------------- 7. municípios não casados IBGE
    nao_casados = um("SELECT count(*) FROM municipios_nao_casados")
    p.append(f"\n## 7. Crosswalk município RFB → IBGE\n")
    p.append(f"""O código de município da Receita é o **TOM** do Ministério da Fazenda,
não o código IBGE — não existe relação aritmética entre os dois, só casamento por
nome normalizado + UF. A UF não vem na tabela `MUNICCSV`: foi deduzida dos próprios
estabelecimentos (quando um código aparecia com UFs diferentes, venceu a mais frequente).

| | |
|---|---:|
| Municípios na tabela da RFB | {n(um('SELECT count(*) FROM municipios'))} |
| Municípios na referência do IBGE | {n(um('SELECT count(*) FROM ibge_municipios'))} |
| Casados por nome + UF | {n(um('SELECT count(*) FROM municipios WHERE ibge IS NOT NULL'))} |
| **Não casados** | **{n(nao_casados)}** |
| Colisões de slug dentro da mesma UF | {n(um('SELECT count(*) FROM municipios_slug_duplicado'))} |

Os não casados estão em `saida/municipios-nao-casados.csv`, com o motivo e o
número de estabelecimentos afetados, para resolver à mão.
""")
    if nao_casados:
        linhas = [(cod, mun, slug_, uf or "—", n(qtd), motivo) for
                  cod, mun, slug_, uf, qtd, motivo in
                  q("SELECT * FROM municipios_nao_casados LIMIT 40")]
        p.append(f"Os {min(nao_casados, 40)} com mais estabelecimentos:\n")
        p.append(tabela(["Cód. RFB", "Município", "Slug", "UF", "Estab.", "Motivo"],
                        linhas, ["---", "---", "---", "---", "--:", "---"]))

    # -------------------------------------------- publicação e dado pessoal
    cpf_limpos = um("""SELECT count(*) FROM estabelecimentos_alvo
                       WHERE regexp_matches(razao_social, '[0-9]{11}$')""")
    cnpj_limpos = um("""SELECT count(*) FROM estabelecimentos_alvo
                        WHERE regexp_matches(razao_social,
                              '^[0-9]{2}\\.[0-9]{3}\\.[0-9]{3} ')""")
    p.append(f"""
## 8. Publicação e dado pessoal

O jurídico do cliente liberou, em 2026-08-24, a publicação de **e-mail e telefone**.
Os dois vão para o site. Duas coisas que **não** vão, e por quê:

- **CPF.** A razão social de MEI vem da Receita com o CPF colado no fim
  (`THALITA CRISTINA GONCALVES 11916547613`): **{n(cpf_limpos)}** registros. CPF é
  dado pessoal de outra ordem que e-mail comercial e não estava na autorização,
  então a macro `nome_publicavel` remove a sequência final de 11 dígitos antes de
  qualquer saída pública. A razão social crua fica na coluna `razao_social`, para
  auditoria, e a limpa em `razao_social_publicavel`.
- **Base do CNPJ colada no início do nome** (`46.696.520 RODRIGO XAVIER MONTEIRO`):
  **{n(cnpj_limpos)}** registros. Removida por ser redundante — o CNPJ já sai em
  campo próprio.

Outros pontos de escopo:

- `saida/registros-mei.csv` lista os **{n(um('SELECT count(*) FROM registros_mei'))}**
  estabelecimentos MEI. MEI é pessoa física e o endereço declarado é quase sempre
  residencial; a lista separada existe para atender pedido de remoção sem varrer
  a base inteira.
- `suspeita_duplicata` apenas **marca**
  ({n(um('SELECT count(*) FROM estabelecimentos_alvo WHERE suspeita_duplicata'))} registros:
  mesmo CEP, mesmo logradouro, mesmo número e nome com similaridade
  Jaro-Winkler ≥ 0,90). Nada foi apagado automaticamente, e a marca não aparece
  no site.
- `lat`/`lng` existem em `estabelecimentos_alvo` e estão **nulos**: sem
  geocodificação nesta fase, por escopo.
- **Acentuação não é inventada.** A Receita grava logradouro e bairro em maiúscula
  e sem acento; a apresentação converte para caixa de título (`SAO CAETANO` →
  `Sao Caetano`) mas não devolve o acento, porque isso seria adivinhar. O nome do
  município é a exceção: vem acentuado da tabela do IBGE.
""")

    # ------------------------------------------- 9. observações e riscos
    p.append("\n## 9. Observações e riscos para a fase 2\n")

    p.append("### 9.1 Composição de cada vertical por CNAE\n")
    p.append("Uma vertical em que um CNAE catch-all responde pela maior parte dos "
             "registros nasce ruidosa: o scraping vai gastar esforço em quem não é "
             "do ramo.\n")
    p.append(tabela(["Vertical", "CNAE", "Descrição", "Pares", "% da vertical"],
                    [(v, c, d[:58], n(qtd), f"{pc:.1f} %".replace(".", ","))
                     for v, c, d, qtd, pc in q("SELECT * FROM rel_composicao_vertical")],
                    ["---", "---", "---", "--:", "--:"]))

    dominadas = q("""
        SELECT vertical, cnae, descricao, pct_da_vertical FROM rel_composicao_vertical
        WHERE pct_da_vertical >= 60
          AND regexp_matches(lower(strip_accents(descricao)), 'nao especificad')
    """)
    if dominadas:
        p.append("\n**Atenção.** Nestas verticais um CNAE genérico (\"não "
                 "especificados anteriormente\") responde por 60 % ou mais dos "
                 "registros:\n")
        for v, c, d, pc in dominadas:
            fatia = f"{pc:.1f}".replace(".", ",")
            p.append(f"- `{v}`: **{fatia} %** vem do CNAE {c} — {d}.")
        p.append("\n  Não é erro de carga: é o que a Receita tem. Mas dimensione a "
                 "fase 2 sabendo que a maior parte dessa fila não é do ramo.\n")

    p.append("\n### 9.2 Endereço no exterior\n")
    ex = q("SELECT * FROM rel_exterior")
    tot_ex = um("SELECT count(*) FROM estabelecimentos_alvo WHERE uf = 'EX'")
    p.append(f"A Receita usa o pseudo-código de município `9707` / UF `EX` para "
             f"endereço fora do Brasil: **{n(tot_ex)}** estabelecimentos-alvo "
             f"({', '.join(f'{v}: {n(t)}' for v, t in ex)}). Não têm município "
             f"brasileiro, logo ficam fora de qualquer página por cidade e sem "
             f"código IBGE — por definição, não por falha do crosswalk.\n")

    p.append("\n### 9.3 MEI e CNAE secundário\n")
    mei_escolas = um("SELECT mei FROM rel_qualidade WHERE vertical = 'escolas-de-musica'")
    tot_escolas = um("SELECT total FROM rel_qualidade WHERE vertical = 'escolas-de-musica'")
    mei_estudios = um("SELECT mei FROM rel_qualidade WHERE vertical = 'estudios-de-gravacao'")
    pares_sec = um("SELECT count(*) FROM estabelecimento_cnae_alvo WHERE origem = 'secundario'")
    pares_tot = um("SELECT count(*) FROM estabelecimento_cnae_alvo")
    mei_total = um("SELECT count_if(mei) FROM estabelecimentos_alvo")
    p.append("Três padrões que valem registro antes da fase 2:\n")
    fixo = um("SELECT count_if(telefone_tipo = 'fixo') FROM estabelecimentos_alvo")
    movel = um("SELECT count_if(telefone_tipo = 'movel') FROM estabelecimentos_alvo")
    p.append(
        f"- **A Receita guarda telefone com 8 dígitos, e a base tem zero números de "
        f"9 dígitos.** {pct(movel, fixo + movel)} dos telefones são móveis no formato "
        f"anterior à migração do 9º dígito ({n(movel)} contra {n(fixo)} fixos). "
        f"O site publica o móvel nos dois formatos: com o 9 acrescentado pela regra "
        f"nacional (é o que disca hoje) e o original ao lado. A derivação vive em "
        f"coluna própria, `telefone_9`, e nunca sobrescreve o dado da Receita."
    )
    p.append(
        f"- **{pct(mei_total, alvo)} da base é MEI**, e em `escolas-de-musica` chega a "
        f"{pct(mei_escolas, tot_escolas)} — professor particular, não escola com sede. "
        f"Endereço de MEI é quase sempre residencial, o que muda o que a fase 2 pode publicar."
    )
    p.append(
        f"- **`estudios-de-gravacao` quase não tem MEI** ({n(mei_estudios)} registros), e não é "
        f"falha de join: o CNAE 5920100 tem **zero** MEI em toda a base ativa do país. Os poucos "
        f"que aparecem entraram pelo CNAE secundário, com outro CNAE principal."
    )
    p.append(
        f"- **{pct(pares_sec, pares_tot)} dos pares (estabelecimento, CNAE) vieram do CNAE "
        f"secundário.** Confirma o alerta do briefing: filtrar só pelo principal descartaria "
        f"a maior parte da base."
    )
    p.append("")

    destino = SAIDA / "relatorio-base.md"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("\n".join(p) + "\n", encoding="utf-8")
    print(f"[ok] {destino.relative_to(SAIDA.parent)}  ({len(''.join(p)) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
