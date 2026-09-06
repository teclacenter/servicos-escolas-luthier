# Serviços Teclacenter — base CNPJ e diretório por cidade

Transforma os arquivos abertos de CNPJ da Receita Federal em seis listas de
estabelecimentos ativos, organizadas por estado e município, e gera o site
estático publicado em <https://servicos.teclacenter.com.br>.

Publica também a **rede de assistência autorizada de 43 marcas** — Roland,
Yamaha, Casio, Korg, Tagima, Behringer, Shure, Takamine e outras — coletada do
site oficial de cada fabricante ou distribuidor. Segunda origem de dados,
independente da Receita.

Pipeline determinístico: **nenhuma etapa chama IA**. Rodar `make all` duas vezes
sobre a mesma safra produz saídas byte-a-byte idênticas (verificado por checksum).
As duas etapas que tocam a rede ficam **fora de `make all`**, justamente para que
`all` continue reprodutível offline: a tabela de municípios do IBGE
(`src/ibge_para_csv.py`) e a coleta das redes por marca
(`make coletar-marcas`), cujo produto é um CSV versionado.

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
| `coletar-marcas` | rede autorizada de cada marca -> `dados-referencia/marcas-autorizadas.csv` (**rede**) |
| `carregar-marcas` | põe esse CSV no banco; segundos, sem refazer a base da RFB |
| `site` | site estático em `site/` |
| `deploy` | publica `site/` em produção (configure `deploy.env`) |
| `testes` | 130 testes: macros de normalização, coleta por marca e casamento de município |
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

## Assistência técnica por marca

Quem quebrou um teclado não procura "assistência técnica em Campinas": procura
"assistência técnica Roland" e, no máximo, "assistência técnica Roland São
Paulo". A árvore por cidade responde a segunda pergunta pela metade e a primeira,
nada. Daí uma segunda árvore, cruzada com a primeira:

```
/assistencia-tecnica/marcas/                       as 43 marcas, por distribuidor
/assistencia-tecnica/marca/roland/                 a marca no Brasil
/assistencia-tecnica/marca/roland/sp/              a marca em um estado
/assistencia-tecnica/marca/roland/sp/campinas/     a marca em uma cidade
```

São 4.992 páginas novas, a partir de **784 oficinas** de sete redes. "Assistência
por marca" é uma **categoria no menu**, logo depois de "Assistência técnica", e
tem seção própria na página inicial. Toda página de cidade da assistência técnica
ganhou o bloco "por marca", e toda página de marca em uma cidade aponta de volta
para a lista completa da cidade.

O hub em `/assistencia-tecnica/marcas/` é um índice, não uma vitrine: a lista
A-Z completa vem primeiro, com quem credencia a rede embaixo do nome e o número
de oficinas ao lado — quem chega ali já sabe a marca e quer achá-la. A explicação
das redes compartilhadas vem depois, em prosa, sem repetir as 43 marcas numa
segunda lista. Não há ranking de "mais procuradas": não temos volume de busca, e
inventar um seria o oposto do que o resto do projeto faz.

### As sete fontes, e como cada uma entrega

| Fonte | Marcas | Oficinas | Como sai |
|---|---:|---:|---|
| Yamaha Musical do Brasil | 1 | 165 | JSON do próprio localizador |
| Tagima | 1 | 164 | HTML renderizado no servidor, um estado por requisição |
| ProShows | 19 | 149 | Master Data da VTEX; 403 sem filtro de estado |
| Sonotec | 19 | 128 | página única, um bloco por estado |
| Tectrônica (Korg) | 1 | 70 | página única com `data-estado`/`data-cidade` |
| Roland Brasil | 1 | 65 | `.php` embutido que chama outro `.php` por estado |
| Casio | 1 | 43 | JSON; o Akamai exige `Referer` |

**Harman (JBL, AKG, Harman Kardon, Infinity, Lexicon, Mark Levinson, Revel) não
é coletada.** O localizador está atrás de um antibot que exige executar
JavaScript; contornar isso seria burlar um controle de acesso. A fonte fica
declarada em `src/marcas.py` com o motivo, e o hub de marcas diz ao visitante
para consultar direto na Harman.

### Decisões que valem explicar

1. **Uma fonte, N marcas, uma rede só.** ProShows e Sonotec credenciam a MESMA
   oficina para todo o portfólio — e nenhuma das duas publica qual oficina
   atende qual marca. A relação (oficina × marca) é, portanto, *derivada da
   fonte*, não coletada. As páginas dizem isso na cara, nomeando o distribuidor
   e listando as marcas irmãs: a lista de Behringer e a de Midas serem idênticas
   é o fato, não um truque de SEO.
2. **O casamento da cidade usa a tabela `municipios`**, a mesma que define os
   slugs das URLs. Casar contra outra tabela produziria
   `/marca/roland/sp/sao-paulo/` apontando para uma cidade que a navegação não
   tem. 770 das 784 oficinas casam.
3. **Yamaha não publica cidade nem estado**, só um endereço em texto corrido. O
   estado sai da sigla escrita no fim do endereço (declaração da fonte) e, se
   não houver, do DDD (inferência nossa, nessa ordem). A cidade sai do nome de
   município da mesma UF encontrado no endereço, preferindo o casamento mais à
   direita — `RUA SÃO PAULO, 45 - CENTRO - CAMPINAS, SP` é Campinas. Nome de
   três letras (`Jaú`, `Ipê`) só vale se fechar o endereço.
4. **Cidade que não casa não é chutada.** `Alagoinha` não vira `Alagoinhas`: a
   oficina fica na página do estado, e a lista dos casos sai em
   `marca_posto_sem_municipio`.
5. **276 oficinas foram casadas com um CNPJ ativo da própria base**, pelo
   telefone, e só quando o casamento é inequívoco (um telefone que aponta para
   exatamente um estabelecimento). Muda o que a página pode afirmar: em vez de
   "a Roland indica esta oficina", vira "a Roland indica esta oficina, que é a
   empresa X, CNPJ Y, com cadastro ativo".
6. **O telefone das redes já vem com o nono dígito**, ao contrário do da
   Receita. `tipo_telefone` foi generalizada para classificar os dois formatos,
   e `linha_telefone` deixou de imprimir "ou (o mesmo número)" quando não há um
   formato antigo diferente.
7. **Cada página cita a origem**: quem publica a rede, o endereço da página
   oficial e a data em que foi consultada (`coletado_em`, por fonte — coletar só
   a Roland hoje não faz o site dizer que a rede da Yamaha foi conferida hoje).

### Recoletar

```bash
make coletar-marcas                       # todas as fontes (~2 min)
$(PY) src/coletar_marcas.py --fonte roland   # só uma, mesclando com o resto
$(PY) src/coletar_marcas.py --reusar         # reparseia tmp/marcas/, sem rede
make carregar-marcas && make site
```

O HTML e o JSON crus ficam em `tmp/marcas/`, um arquivo por requisição, para
auditar de onde saiu cada linha sem repetir a coleta. O CSV sai ordenado e
deduplicado, com um `posto_id` derivado do conteúdo: entre duas coletas, o diff
mostra só o que a fonte mudou.

## Site

Estático, sem JavaScript, sem webfont, sem imagem externa além do logotipo.
Um CSS com hash no nome, cacheável para sempre. Custo por visita no servidor =
servir um arquivo.

SEO: `<title>` e `<meta description>` únicos por página, canonical, `prev`/`next`
na paginação, `sitemap.xml` fragmentado, JSON-LD `BreadcrumbList` + `ItemList` de
`LocalBusiness`, HTML semântico (`<address>`, `tel:`, `mailto:`).

GEO: `llms.txt` na raiz descrevendo as duas origens e os limites de cada uma,
frase-resumo factual no topo de cada página, e os mesmos dados em JSON-LD. Nas
páginas por marca, o JSON-LD traz `Brand` e, em cada oficina, um
`Offer`/`Service` com a marca atendida — que é o que um motor de resposta lê sem
ambiguidade quando alguém pergunta "onde consertar um teclado Roland em Campinas".

Marca e paleta em `PALETA`, em `src/config.py`. O vermelho (`#ca1010`) e o cinza
(`#a9abae`) foram amostrados dos pixels do próprio logotipo em `ativos/`.

## Estrutura

```
ativos/            logotipo (fonte, versionado)
dados-referencia/  tabela de municípios do IBGE e as redes por marca (CSV versionado)
sql/               SQL versionado, em arquivos, não em strings Python
src/               etapas do pipeline
                   marcas.py            catálogo marca -> distribuidor -> URL oficial
                   coletar_marcas.py    a coleta (rede)
                   site_moldura.py      <head>, cabeçalho e rodapé, comuns
                   site_marcas.py       as páginas por marca
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
- As redes por marca são dados de empresa publicados pelo próprio fabricante
  para que o consumidor encontre a assistência. Cada página nomeia a origem,
  linka a página oficial e diz que a lista oficial é a do fabricante.
