# Prompt — Fase 1: extrair base CNPJ por vertical, cidade e estado

> Cole como primeira mensagem no Claude Code, no VS Code, com a pasta do projeto aberta.

---

## 0. Escopo desta fase — leia antes de tudo

O objetivo é **um só**: transformar 6 GB de CSV da Receita Federal em cinco listas limpas de
estabelecimentos ativos, organizadas por estado e município.

Essas listas vão alimentar uma **fase 2 de scraping** dos sites dos próprios estabelecimentos,
para descobrir o que cada um faz de verdade (a escola X dá aula de teclado e violino, o luthier
Y só trabalha com violão). Portanto a saída desta fase é **insumo de trabalho**, não conteúdo
de site.

### O que NÃO fazer nesta fase

- **Nenhuma chamada a IA no processamento.** Você escreve o código uma vez; depois roda por
  `make`, determinístico e reproduzível. Sem classificação por modelo, sem texto gerado,
  sem "limpeza inteligente" de nomes.
- **Nenhum corte por volume.** Não aplique threshold mínimo de registros por cidade. Quero a
  base cheia — uma cidade com 2 escolas pode virar página depois do scraping, e filtrar agora
  joga alvo fora.
- **Nenhum acesso à rede.** Sem API, sem scraping, sem consulta externa. A entrada são só os
  arquivos já no disco.
- **Nenhum JSON de site, template ou HTML.** Isso vem depois.

Se em algum ponto o único caminho for chutar ou inferir, **pare e me pergunte**. Dado faltando
eu conserto; dado inventado contamina tudo e eu não descubro.

---

## 1. Ambiente

macOS, Apple Silicon, VS Code. Raiz do projeto e dos dados:

```
/Volumes/SSD-SANDISK/SERVIDORES/servicos-teclacenter-assistencia-luthier
```

Primeira coisa, rode e me mostre:

```bash
cd "/Volumes/SSD-SANDISK/SERVIDORES/servicos-teclacenter-assistencia-luthier"
diskutil info /Volumes/SSD-SANDISK | grep -E "File System|Free Space"
ls -la dados-brutos/
```

Preciso confirmar **~40 GB livres** e que o sistema de arquivos **não é FAT32** —
`Estabelecimentos0.zip` tem 2 GB e passa do limite de 4 GB ao descompactar. Se for FAT32, pare.

**Stack:** Python 3.11+ em `.venv`, DuckDB via pip. **Sem pandas** nas tabelas grandes,
sem Docker, sem servidor. O banco é um arquivo `cnpj.duckdb`.

Em toda sessão DuckDB, obrigatoriamente:

```sql
SET memory_limit = '8GB';
SET temp_directory = '/Volumes/SSD-SANDISK/SERVIDORES/servicos-teclacenter-assistencia-luthier/tmp';
```

Sem o `temp_directory` no SSD externo, o DuckDB derrama dezenas de GB temporários no disco
interno do Mac durante os joins.

**Estrutura:**

```
├── Makefile              # alvos: extrair, carregar, exportar, all, limpar
├── dados-brutos/         # os .zip já baixados
├── extraidos/            # gitignore
├── tmp/                  # gitignore
├── cnpj.duckdb           # gitignore
├── sql/                  # SQL em arquivos versionados, não em strings Python
├── src/
└── saida/
```

---

## 2. Entrada e suas armadilhas

Em `dados-brutos/`, safra **2026-08**: `Empresas0-9.zip`, `Estabelecimentos0-9.zip`,
`Simples.zip`, `Cnaes.zip`, `Municipios.zip`, `Naturezas.zip`, `Motivos.zip`, `Paises.zip`,
`Qualificacoes.zip`. Os `Socios*.zip` não foram baixados de propósito — não são necessários.

Trate todas estas armadilhas explicitamente:

1. **Os CSVs dentro dos ZIPs não têm extensão `.csv`.** Descompactam como
   `K3241.K03200Y0.D60809.ESTABELE`, `.EMPRECSV`, `.CNAECSV`, `.MUNICCSV`, `.SIMPLES`.
   Localize por sufixo, não por extensão.
2. **Encoding `latin-1`/`cp1252`.** Sem declarar, a acentuação quebra em silêncio.
3. **Delimitador `;`**, aspas duplas, **sem cabeçalho**.
4. **A RFB mudou o layout no fim de janeiro/2026.** Não assuma o layout antigo: descompacte um
   arquivo de cada tipo, imprima as 5 primeiras linhas e a contagem de colunas, e **me mostre
   antes de carregar o resto**.
5. **Tudo `VARCHAR` na carga.** CNPJ, CEP e telefone têm zeros à esquerda que somem se tipados
   como número.
6. **O código de município da Receita não é o código IBGE.** Faça o crosswalk por nome
   normalizado + UF e **reporte quantos não casaram**; jogue as exceções em
   `saida/municipios-nao-casados.csv` para eu resolver à mão.
7. **Filtrar só pelo CNAE principal perde metade da base.** `cnae_fiscal_secundaria` é lista
   separada por vírgula. Considere os dois e registre de qual veio.
8. Ignore `.DS_Store` no glob e no git.

---

## 3. CNAEs — confirme comigo antes de rodar

Meu chute está abaixo. **Não confie nele.** Carregue `Cnaes.zip`, busque nas descrições por
`música|musical|instrumento|som|sonoriza|gravação|luthier|palco|ensino|arte`, me mostre a
lista completa e **espere minha confirmação** de quais entram em cada vertical.

| Vertical | Slug | Candidatos |
|---|---|---|
| Assistência técnica | `assistencia-tecnica` | `9529199`, `9521500`, `3319800` |
| Luthiers | `luthier` | `3220500`, `9529199` |
| Escolas de música | `escolas-de-musica` | `8592903` |
| Estúdios de gravação | `estudios-de-gravacao` | `5920100` |
| Palcos, som e locação | `locacao-som-palco` | `9001906`, `7739099`, `7729299` |

Códigos vêm sem máscara nos arquivos. Repare que `9529199` está em duas verticais: o mesmo
estabelecimento pode cair legitimamente em ambas, então a tabela final é
**estabelecimento × vertical** (N:N), não um-para-um.

---

## 4. Regras de filtro

- Só `situacao_cadastral = '02'` (ativa).
- Nome de exibição: `nome_fantasia` quando preenchido, senão `razao_social`. Manter os dois.
- Manter matriz **e** filiais, com o flag indicando qual é.
- **Telefone:** DDD + número → E.164 (`+55DDDNUMERO`). Inválidos (menos de 10 dígitos, DDD fora
  da lista oficial, todos os dígitos iguais) viram `null` — o registro não é descartado por isso.
- **Slug de município:** ASCII, minúsculo, hífen, sem acento (`São Bernardo do Campo` →
  `sao-bernardo-do-campo`). Único **por UF**, não globalmente.
- **Duplicatas:** mesmo endereço com nome muito parecido → marcar `suspeita_duplicata = true`.
  Nunca apagar automaticamente.
- Sem geocodificação. `lat`/`lng` ficam nulos.

---

## 5. Domínio do site a partir do e-mail — insumo da fase 2

A base CNPJ **não tem campo de site**. O único gancho determinístico é o e-mail. Extraia:

- Domínio de `correio_eletronico` → coluna `dominio_email`.
- Marque `dominio_provedor = true` para provedores gratuitos e genéricos: gmail, hotmail,
  outlook, live, yahoo, bol, uol, terra, ig, globo, icloud, msn, aol, protonmail, zipmail.
- Só onde `dominio_provedor = false` a coluna `site_candidato` recebe `https://{dominio}`.
  É essa lista que vai virar a fila de scraping da fase 2.
- No relatório, informe **quantos registros por vertical têm site candidato** — esse número
  dimensiona a fase 2.

**LGPD:** o e-mail pode ficar no banco e no CSV interno, mas fica registrado desde já que ele
**nunca** vai para saída pública. Gere também `saida/registros-mei.csv` com os CNPJs marcados
como MEI, porque MEI é pessoa física e vai precisar de política de opt-out própria.

---

## 6. Saídas

### 6.1 `saida/relatorio-base.md`

1. Estabelecimentos ativos por CNAE alvo, Brasil.
2. Tabela vertical × UF.
3. Top 100 municípios por vertical, com contagem.
4. Distribuição de cidades por faixa de tamanho, por vertical (quantas cidades têm 1 registro,
   2, 3–5, 6–10, 11+). **Isso é o que me diz se a vertical existe.**
5. % com telefone válido, % com nome fantasia, % com e-mail, **% com site candidato**.
6. Quantos vieram do CNAE secundário e não do principal.
7. Municípios que não casaram no crosswalk RFB→IBGE.

### 6.2 `saida/csv/{vertical}.csv` e `saida/parquet/{vertical}.parquet`

Uma linha por estabelecimento. Colunas:

```
id (cnpj sem máscara), cnpj_formatado, nome, nome_fantasia, razao_social,
logradouro, numero, complemento, bairro, cep,
municipio, municipio_slug, ibge, uf,
telefone, email, dominio_email, dominio_provedor, site_candidato,
cnae_principal, cnae_principal_desc, cnaes_secundarios, origem_cnae,
data_abertura, porte, mei, matriz, suspeita_duplicata,
vertical, safra
```

CSV para eu abrir no Excel e revisar; Parquet para a fase 2 consumir rápido.

### 6.3 `saida/csv/{vertical}-por-cidade.csv`

Agregado: `uf, municipio, municipio_slug, ibge, total, com_telefone, com_site_candidato`.
Ordenado por total decrescente. É a partir daqui que eu escolho onde começar o scraping.

### 6.4 `cnpj.duckdb`

Tabelas `empresas`, `estabelecimentos`, `municipios`, `cnaes`, `simples`, mais as views
`estabelecimentos_alvo` e `estabelecimento_vertical`.

---

## 7. Como trabalhar

Duas paradas obrigatórias — não me entregue tudo de uma vez:

1. **Ambiente + layout + lista de CNAEs encontrada.** Pare e espere minha confirmação.
2. **Carga completa + relatório + exportações.**

E ao longo de tudo:

- SQL em arquivos `.sql` comentados e versionados, não em strings dentro do Python.
- Log da contagem de linhas **em cada etapa de filtro**, para eu rastrear onde registros somem.
- Testes mínimos para normalização de telefone, geração de slug e extração de domínio.
- Se algum número parecer estranho (uma vertical com 400 mil registros ou com 12), **me avise
  em vez de seguir em frente**.
