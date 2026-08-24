-- Crosswalk município RFB -> IBGE.
--
-- Três fatos incômodos sobre esses dados:
--   1. O código de município da RFB é o TOM (Tabela de Órgãos e Municípios do
--      Ministério da Fazenda), NÃO o código IBGE. Não há relação aritmética
--      entre os dois: o mapeamento só sai por nome + UF.
--   2. A tabela MUNICCSV da RFB traz código e nome, mas NÃO traz a UF. A UF tem
--      que vir dos próprios estabelecimentos.
--   3. Quando dois municípios de UFs diferentes têm o mesmo nome (Bom Jesus
--      existe em 6 estados), só o par nome+UF desambigua. Por isso o slug é
--      único POR UF, nunca globalmente.
--
-- A tabela ibge_municipios é criada por src/carregar.py: preenchida se houver
-- um arquivo de referência do IBGE em disco, VAZIA caso contrário. Vazia, a
-- coluna ibge sai NULL e todos os municípios entram em municipios-nao-casados.csv
-- — nada é inferido nem chutado.

-- UF de cada código RFB, tirada dos estabelecimentos. Se um mesmo código
-- aparecer com UFs diferentes (erro de cadastro), vence a mais frequente.
CREATE OR REPLACE TABLE municipio_uf AS
WITH pares AS (
    SELECT municipio AS codigo_rfb, uf, count(*) AS n
    FROM estabelecimentos
    WHERE municipio IS NOT NULL AND municipio <> ''
      AND uf IS NOT NULL AND length(uf) = 2
    GROUP BY 1, 2
),
ranqueado AS (
    SELECT *, row_number() OVER (PARTITION BY codigo_rfb ORDER BY n DESC, uf) AS pos,
              sum(n) OVER (PARTITION BY codigo_rfb) AS n_total
    FROM pares
)
SELECT codigo_rfb, uf, n AS n_na_uf_vencedora, n_total,
       n <> n_total AS uf_ambigua
FROM ranqueado WHERE pos = 1;

-- Tabela final de municípios, com slug e (quando possível) código IBGE.
CREATE OR REPLACE TABLE municipios AS
SELECT
    m.codigo_rfb,
    -- Nome apresentável: o IBGE grava com acento e caixa correta ("São Bernardo
    -- do Campo"), a RFB grava tudo em maiúscula e sem acento. O slug é o mesmo
    -- nos dois, por construção do join, então trocar o rótulo é seguro.
    coalesce(i.nome, m.nome_rfb)     AS municipio,
    m.nome_rfb                       AS municipio_rfb,
    u.uf,
    slug(m.nome_rfb)                 AS municipio_slug,
    i.codigo_ibge                    AS ibge,
    u.uf_ambigua,
    u.n_total                        AS estabelecimentos_no_municipio
FROM municipios_rfb m
LEFT JOIN municipio_uf u ON u.codigo_rfb = m.codigo_rfb
LEFT JOIN ibge_municipios i
       ON i.uf = u.uf
      AND i.nome_slug = slug(m.nome_rfb);

-- Sanidade: o par (uf, slug) precisa ser único, senão o agregado por cidade soma
-- municípios diferentes na mesma linha.
CREATE OR REPLACE VIEW municipios_slug_duplicado AS
SELECT uf, municipio_slug, count(*) AS n,
       string_agg(codigo_rfb || '=' || municipio, ' | ') AS colisoes
FROM municipios
WHERE municipio_slug IS NOT NULL AND uf IS NOT NULL
GROUP BY 1, 2 HAVING count(*) > 1;

-- Exceções para resolver à mão.
CREATE OR REPLACE VIEW municipios_nao_casados AS
SELECT codigo_rfb, municipio, municipio_slug, uf, estabelecimentos_no_municipio,
       CASE
         WHEN uf IS NULL THEN 'sem UF: nenhum estabelecimento usa este código'
         WHEN ibge IS NULL THEN 'sem correspondência IBGE por nome+UF'
       END AS motivo
FROM municipios
WHERE ibge IS NULL OR uf IS NULL
ORDER BY estabelecimentos_no_municipio DESC NULLS LAST;
