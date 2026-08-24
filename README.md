# Serviços Teclacenter — base CNPJ e diretório por cidade

Transforma os arquivos abertos de CNPJ da Receita Federal em seis listas de
estabelecimentos ativos, organizadas por estado e município, e gera o site
estático publicado em <https://servicos.teclacenter.com.br>.

Pipeline determinístico: **nenhuma etapa chama IA**. Rodar `make all` duas vezes
sobre a mesma safra produz saídas byte-a-byte idênticas (verificado por checksum).
A única requisição de rede do projeto é a tabela de municípios do IBGE
(`src/ibge_para_csv.py`), necessária porque a base da Receita não traz código IBGE.

## Verticais

| Slug | CNAE | Estabelecimentos |
|---|---|---:|
| `locacao-som-palco` | 9001906, 7739003, 7729202 | 363.124 |
| `assistencia-tecnica` | 9521500, 3319800 | 270.465 |
| `escolas-de-musica` | 8592903 | 105.933 |
| `lojas-de-instrumentos-musicais` | 4756300 | 95.775 |
| `estudios-de-gravacao` | 5920100, 5912002 | 53.695 |
| `luthier` | 3220500 | 7.918 |

A relação estabelecimento × vertical é **N:N**: um estabelecimento com CNAE
principal em uma vertical e secundário em outra entra nas duas.

## Requisitos

- macOS ou Linux, Python 3.11+
- ~70 GB livres: 26 GB de CSV bruto, 24 GB convertido, 8 GB de banco, 1 GB de site
- Os arquivos da Receita descompactados em `Receita-cnpj-dados/`
  (`*.ESTABELE`, `*.EMPRECSV`, `*.SIMPLES.CSV.*`, `*.CNAECSV`, `*.MUNICCSV` e demais)

```bash
python3 -m venv .venv
./.venv/bin/pip install duckdb pytest
make all          # ~6 min
make servir       # http://localhost:8788
```

## Alvos

| Alvo | O que faz |
|---|---|
| `preparar` | CSV bruto → `extraidos/*.csv` em UTF-8, sem bytes de controle |
| `carregar` | monta `cnpj.duckdb`: tabelas, crosswalk de municípios, views alvo |
| `relatorio` | `saida/relatorio-base.md` |
| `exportar` | `saida/csv/*.csv`, `saida/parquet/*.parquet`, agregados por cidade |
| `publicar` | `saida/publicacao.sqlite`, indexado por vertical + UF + cidade |
| `site` | site estático em `site/` |
| `deploy` | publica `site/` em produção (configure `deploy.env`) |
| `testes` | 95 testes das macros de normalização e apresentação |
| `auditar-bytes` | lista os bytes de controle presentes nos arquivos brutos |

## Armadilhas dos dados, todas tratadas

1. **Os CSV não têm extensão `.csv`.** Descompactam como `K3241.K03200Y0.D60808.ESTABELE`.
   Localização por sufixo.
2. **Declarar `encoding='latin-1'` não basta.** O leitor do DuckDB **recusa o
   arquivo inteiro** se topar um byte de controle. A safra 2026-08 tem 33 desses
   bytes (NUL, SUB, DEL, `0x8F`) em 72,8 milhões de linhas. O alvo `preparar`
   remove só esses bytes e converte para UTF-8 — mapa de 256 bytes, sem perda.
3. **O código de município da Receita é o TOM do Ministério da Fazenda, não o
   IBGE**, e não há relação aritmética entre eles. O casamento sai por nome
   normalizado + UF, e a UF não vem na tabela de municípios: é deduzida dos
   próprios estabelecimentos. 5.554 de 5.572 casam; os 18 restantes são
   divergências reais de grafia (`PARATI`/`Paraty`, `ARES`/`Arez`) e saem em
   `saida/municipios-nao-casados.csv`.
4. **Filtrar só pelo CNAE principal perderia a maior parte da base**: 84 % dos
   pares (estabelecimento, CNAE) vêm do CNAE secundário. Ambos são considerados,
   e `origem_cnae` registra de qual veio.
5. **A razão social de MEI vem com CPF colado no fim** (`NOME DA PESSOA
   11916547613`): 95.441 registros. CPF **não** vai para saída pública —
   `nome_publicavel` remove a sequência final de 11 dígitos, e `texto_nome`
   recusa nome que seja só dígitos. A razão social crua fica em `razao_social`.
6. **O cadastro guarda telefone com 8 dígitos** e a base tem **zero** números de
   9 dígitos. 68 % são móveis no formato anterior à migração do 9º dígito. O site
   publica os dois formatos: com o 9 acrescentado pela regra nacional (é o que
   disca hoje) e o original ao lado. A derivação vive em `telefone_9` e nunca
   sobrescreve o dado da Receita.
7. **Acentuação não é inventada.** A Receita grava logradouro e bairro em
   maiúscula sem acento; a apresentação converte para caixa de título
   (`SAO CAETANO` → `Sao Caetano`) mas não devolve o acento. O nome do município
   é a exceção: vem acentuado do IBGE.
8. **A Receita repete o tipo dentro do logradouro** (`tipo='RUA'`,
   `logradouro='RUA 12'`), o que concatenado daria "RUA RUA 12".
9. **No macOS, `tar` injeta um arquivo `._*` por arquivo e diretório.** Sem
   `COPYFILE_DISABLE=1`, o deploy sobe 89.523 arquivos em vez de 29.843.

## Site

Estático, sem JavaScript, sem webfont, sem imagem externa além do logotipo.
Um CSS com hash no nome, cacheável para sempre. Custo por visita no servidor =
servir um arquivo.

SEO: `<title>` e `<meta description>` únicos por página, canonical, `prev`/`next`
na paginação, `sitemap.xml` fragmentado, JSON-LD `BreadcrumbList` + `ItemList` de
`LocalBusiness`, HTML semântico (`<address>`, `tel:`, `mailto:`).

GEO: `llms.txt` na raiz descrevendo o conjunto e os limites do dado, frase-resumo
factual no topo de cada página, e os mesmos dados em JSON-LD.

Marca e paleta em `PALETA`, em `src/config.py`. O vermelho (`#ca1010`) e o cinza
(`#a9abae`) foram amostrados dos pixels do próprio logotipo em `ativos/`.

## Estrutura

```
ativos/            logotipo (fonte, versionado)
dados-referencia/  tabela de municípios do IBGE
sql/               SQL versionado, em arquivos, não em strings Python
src/               etapas do pipeline
tests/             testes das macros
Receita-cnpj-dados/  entrada bruta (gitignore)
extraidos/         CSV em UTF-8 (gitignore)
saida/             relatório, CSV, Parquet, SQLite (gitignore)
site/              site gerado (gitignore)
```

## Escopo e dado pessoal

- Só `situacao_cadastral = '02'` (ativa). Matrizes e filiais, com flag.
- Sem corte por volume: cidade com um único registro está na base.
- Publicação de e-mail e telefone liberada pelo jurídico em 2026-08-24. CPF, não.
- `saida/registros-mei.csv` lista os 367.217 MEI, para atender pedido de remoção
  sem varrer a base inteira. MEI é pessoa física e o endereço declarado é quase
  sempre residencial.
- `suspeita_duplicata` apenas marca (mesmo CEP, logradouro e número, com nome de
  similaridade Jaro-Winkler ≥ 0,90). Nunca apaga, e não aparece no site.
- Sem geocodificação: `lat`/`lng` existem e estão nulos.
