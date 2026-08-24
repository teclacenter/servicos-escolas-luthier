-- Quantos estabelecimentos ATIVOS por CNAE, separando os que vieram do CNAE
-- principal dos que só aparecem na lista de secundários. É o número que decide
-- quais CNAEs entram em cada vertical -- e se a vertical existe.
CREATE OR REPLACE TABLE contagem_cnae AS
WITH ativos AS (
    SELECT cnae_fiscal_principal AS p, cnae_fiscal_secundaria AS s
    FROM estabelecimentos
    WHERE situacao_cadastral = '02'
),
principal AS (
    SELECT p AS codigo, count(*) AS n_principal FROM ativos GROUP BY 1
),
secundario AS (
    SELECT trim(x) AS codigo, count(*) AS n_secundario
    FROM ativos, unnest(str_split(s, ',')) AS t(x)
    WHERE s IS NOT NULL AND s <> '' AND trim(x) <> ''
    GROUP BY 1
)
SELECT c.codigo, c.descricao,
       coalesce(p.n_principal, 0)  AS n_principal,
       coalesce(s.n_secundario, 0) AS n_secundario
FROM cnaes c
LEFT JOIN principal  p USING (codigo)
LEFT JOIN secundario s USING (codigo);
