-- Redes de assistência autorizada, por marca.
--
-- Entrada: três tabelas montadas por src/carregar_marcas.py —
--   marca_posto_bruto  o CSV de dados-referencia/marcas-autorizadas.csv, cru
--   marca              o catálogo de src/marcas.py (slug, nome, fonte)
--   fonte_rede         quem publica cada rede e em que URL
--
-- Este arquivo faz três coisas que o coletor deliberadamente não faz:
--   1. casa a cidade publicada pelo fabricante com o município do IBGE, usando
--      o MESMO slug do resto do site (tabela `municipios`), senão a página da
--      marca na cidade e a página geral da cidade teriam URLs diferentes;
--   2. normaliza telefone e CEP com as macros já testadas de 20_macros.sql;
--   3. tenta casar a oficina com um CNPJ ativo da própria base, pelo telefone.
--
-- A relação (oficina x marca) é derivada da FONTE, não coletada: nenhuma das
-- redes publica qual oficina atende qual marca do portfólio. Quem credencia
-- credencia para a linha inteira.

-- ---------------------------------------------------------------------------
-- 1. Município. Duas rotas, nesta ordem, e a origem fica registrada na coluna
--    `municipio_origem` — o leitor precisa saber quando o dado foi casado e
--    quando foi lido direto.
-- ---------------------------------------------------------------------------

-- O alvo do casamento é `municipios`, não `ibge_municipios`: é `municipios` que
-- define o slug usado nas URLs do site. Casar contra outra tabela produziria
-- /roland/sp/sao-paulo/ apontando para uma cidade que a navegação não tem.
CREATE OR REPLACE VIEW municipio_alvo AS
SELECT uf, municipio_slug, any_value(municipio) AS municipio,
       any_value(ibge) AS ibge
FROM municipios
WHERE uf IS NOT NULL AND municipio_slug IS NOT NULL
GROUP BY uf, municipio_slug;   -- colisão de slug na mesma UF: ver municipios_slug_duplicado

CREATE OR REPLACE TABLE marca_posto_municipio AS
WITH direto AS (
    SELECT b.posto_id, m.municipio, m.municipio_slug, m.ibge,
           'cidade publicada pela fonte' AS municipio_origem
    FROM marca_posto_bruto b
    JOIN municipio_alvo m
      ON m.uf = b.uf_fonte AND m.municipio_slug = slug(b.cidade_fonte)
    WHERE coalesce(b.cidade_fonte, '') <> ''
),
-- Yamaha e parte da Tagima publicam o endereço em texto corrido, sem campo de
-- cidade. O nome do município aparece dentro dele ("... - MACEIO, AL"): procura-se
-- qualquer município DA MESMA UF como palavra inteira no endereço. Restringir à
-- UF é o que torna isso seguro — "Bom Jesus" existe em seis estados.
candidato AS (
    SELECT b.posto_id, m.municipio, m.municipio_slug, m.ibge,
           'nome do município no endereço' AS municipio_origem,
           row_number() OVER (
               PARTITION BY b.posto_id
               -- o município costuma vir no fim do endereço; entre dois
               -- casamentos, vence o mais à direita e depois o mais longo
               ORDER BY instr('-' || slug(b.endereco) || '-', '-' || m.municipio_slug || '-') DESC,
                        length(m.municipio_slug) DESC, m.municipio_slug
           ) AS pos
    FROM marca_posto_bruto b
    JOIN municipio_alvo m ON m.uf = b.uf_fonte
    WHERE b.posto_id NOT IN (SELECT posto_id FROM direto)
      AND instr('-' || slug(b.endereco) || '-', '-' || m.municipio_slug || '-') > 0
      -- Nome de três letras ('Jaú', 'Ipê', 'Poá') casaria com bairro e com
      -- nome de rua. Só vale quando fecha o endereço, sozinho ou antes da
      -- sigla do estado — que é onde a cidade de fato costuma estar escrita.
      AND (length(m.municipio_slug) >= 4
           OR ends_with(slug(b.endereco), '-' || m.municipio_slug)
           OR ends_with(slug(b.endereco),
                        '-' || m.municipio_slug || '-' || lower(b.uf_fonte)))
),
-- O Distrito Federal tem um município só. Endereço de DF que não casou é
-- sempre Brasília: as "cidades" do DF (Taguatinga, Ceilândia) são regiões
-- administrativas, e o IBGE não as registra como município.
distrito_federal AS (
    SELECT b.posto_id, m.municipio, m.municipio_slug, m.ibge,
           'município único do Distrito Federal' AS municipio_origem
    FROM marca_posto_bruto b
    JOIN municipio_alvo m ON m.uf = 'DF'
    WHERE b.uf_fonte = 'DF'
      AND b.posto_id NOT IN (SELECT posto_id FROM direto)
      AND b.posto_id NOT IN (SELECT posto_id FROM candidato WHERE pos = 1)
)
SELECT posto_id, municipio, municipio_slug, ibge, municipio_origem FROM direto
UNION ALL
SELECT posto_id, municipio, municipio_slug, ibge, municipio_origem
FROM candidato WHERE pos = 1
UNION ALL
SELECT posto_id, municipio, municipio_slug, ibge, municipio_origem
FROM distrito_federal;

-- O que sobrou sem município: fica na página do estado e da marca, nunca some.
CREATE OR REPLACE VIEW marca_posto_sem_municipio AS
SELECT b.fonte, b.posto_id, b.nome, b.uf_fonte, b.cidade_fonte, b.endereco
FROM marca_posto_bruto b
LEFT JOIN marca_posto_municipio m USING (posto_id)
WHERE m.posto_id IS NULL
ORDER BY b.fonte, b.uf_fonte, b.nome;

-- ---------------------------------------------------------------------------
-- 2. Telefones. A fonte publica de zero a vários; os dois primeiros válidos
--    entram na ficha, com as mesmas macros do resto do projeto.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE marca_posto_telefone AS
-- A ordem em que a fonte publicou é informação: o primeiro número costuma ser
-- o telefone principal da oficina. Por isso o corte por posição, e não por
-- valor. range(1,11) cobre com folga (o máximo observado é 4 por oficina).
WITH partido AS (
    SELECT b.posto_id, t.i AS ordem,
           so_digitos(str_split(b.telefones, '|')[t.i]) AS d
    FROM marca_posto_bruto b, range(1, 11) AS t(i)
    WHERE coalesce(b.telefones, '') <> ''
      AND t.i <= len(str_split(b.telefones, '|'))
),
normalizado AS (
    SELECT posto_id, ordem, telefone_e164(d[1:2], d[3:]) AS e164 FROM partido
),
valido AS (   -- mesmo número repetido na fonte fica com a primeira posição
    SELECT posto_id, e164, min(ordem) AS ordem
    FROM normalizado WHERE e164 IS NOT NULL GROUP BY posto_id, e164
),
ranqueado AS (
    SELECT posto_id, e164,
           row_number() OVER (PARTITION BY posto_id ORDER BY ordem, e164) AS pos
    FROM valido
)
SELECT posto_id,
       max(CASE WHEN pos = 1 THEN e164 END) AS telefone,
       max(CASE WHEN pos = 2 THEN e164 END) AS telefone_2
FROM ranqueado WHERE pos <= 2 GROUP BY posto_id;

-- ---------------------------------------------------------------------------
-- 3. Casamento com o CNPJ, pelo telefone.
--
-- Vale a pena porque muda o que a página pode afirmar: em vez de "a Roland
-- indica esta oficina", vira "a Roland indica esta oficina, que é a empresa X,
-- CNPJ Y, com cadastro ativo". Só entra o casamento INEQUÍVOCO: um telefone que
-- aponta para exatamente um estabelecimento. Telefone de rede, de call center
-- ou repetido em filiais é descartado em vez de escolher um.
--
-- Os dois lados são reduzidos ao formato com nono dígito antes de comparar: a
-- Receita guarda o móvel com 8 dígitos e o fabricante publica o de 9.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE MACRO fone_chave(e164) AS
    coalesce(telefone_com_nono_digito(e164), e164);

CREATE OR REPLACE TABLE marca_posto_cnpj AS
WITH fone_posto AS (
    SELECT posto_id, fone_chave(telefone) AS chave FROM marca_posto_telefone
    WHERE telefone IS NOT NULL
    UNION
    SELECT posto_id, fone_chave(telefone_2) FROM marca_posto_telefone
    WHERE telefone_2 IS NOT NULL
),
fone_rfb AS (
    SELECT fone_chave(telefone) AS chave, id FROM estabelecimentos_alvo
    WHERE telefone IS NOT NULL
    UNION
    SELECT fone_chave(telefone_2), id FROM estabelecimentos_alvo
    WHERE telefone_2 IS NOT NULL
),
-- telefone que serve a mais de um estabelecimento não identifica ninguém
chave_unica AS (
    SELECT chave FROM fone_rfb GROUP BY chave HAVING count(DISTINCT id) = 1
),
casado AS (
    SELECT p.posto_id, r.id
    FROM fone_posto p
    JOIN chave_unica u ON u.chave = p.chave
    JOIN fone_rfb r ON r.chave = p.chave
)
SELECT posto_id, any_value(id) AS id
FROM casado GROUP BY posto_id
HAVING count(DISTINCT id) = 1;   -- dois telefones apontando para empresas diferentes: descarta

-- ---------------------------------------------------------------------------
-- 4. A oficina pronta para publicar.
-- ---------------------------------------------------------------------------

-- Endereço em caixa natural. A ProShows publica "Rua Castro Alves, 164"; a
-- Yamaha publica "AVENIDA CHICO MENDES, 4068". Só o que veio TODO em maiúscula
-- passa por titulo_caso — mexer no que já tem minúscula estragaria "Dr." e "II".
CREATE OR REPLACE MACRO caso_natural(t) AS
    CASE WHEN nullif(trim(coalesce(t, '')), '') IS NULL THEN NULL
         WHEN regexp_matches(t, '[a-zà-ÿ]') THEN trim(t)
         ELSE titulo_caso(t) END;

CREATE OR REPLACE TABLE marca_posto AS
SELECT
    b.posto_id,
    b.fonte,
    b.coletado_em,
    b.nome,
    b.uf_fonte                                   AS uf,
    m.municipio,
    m.municipio_slug,
    m.ibge,
    m.municipio_origem,
    nullif(trim(concat_ws(' - ', caso_natural(b.endereco),
                          caso_natural(b.bairro))), '')  AS endereco,
    cep_formatado(b.cep)                         AS cep,
    CASE WHEN m.municipio IS NOT NULL
         THEN m.municipio || '-' || b.uf_fonte END       AS cidade_uf,
    t.telefone,
    tipo_telefone(t.telefone)                    AS telefone_tipo,
    telefone_exibicao(t.telefone)                AS telefone_formatado,
    telefone_com_nono_digito(t.telefone)         AS telefone_9,
    telefone_exibicao(telefone_com_nono_digito(t.telefone)) AS telefone_9_formatado,
    t.telefone_2,
    tipo_telefone(t.telefone_2)                  AS telefone_2_tipo,
    telefone_exibicao(t.telefone_2)              AS telefone_2_formatado,
    telefone_com_nono_digito(t.telefone_2)       AS telefone_2_9,
    telefone_exibicao(telefone_com_nono_digito(t.telefone_2)) AS telefone_2_9_formatado,
    nullif(lower(trim(b.email)), '')             AS email,
    nullif(trim(b.site), '')                     AS site,
    nullif(trim(b.contato), '')                  AS contato,
    nullif(trim(b.horario), '')                  AS horario,
    nullif(trim(b.segmento), '')                 AS segmento,
    c.id                                         AS cnpj,
    CASE WHEN c.id IS NOT NULL THEN
        c.id[1:2] || '.' || c.id[3:5] || '.' || c.id[6:8] || '/' ||
        c.id[9:12] || '-' || c.id[13:14] END     AS cnpj_formatado
FROM marca_posto_bruto b
LEFT JOIN marca_posto_municipio m USING (posto_id)
LEFT JOIN marca_posto_telefone  t USING (posto_id)
LEFT JOIN marca_posto_cnpj      c USING (posto_id)
WHERE b.uf_fonte IS NOT NULL AND b.uf_fonte <> '';

-- ---------------------------------------------------------------------------
-- 5. Marca x oficina, e os agregados que a navegação usa.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW publicacao_marca AS
SELECT ma.marca, ma.marca_nome, p.*
FROM marca_posto p
JOIN marca ma ON ma.fonte = p.fonte
ORDER BY ma.marca, p.uf, p.municipio_slug NULLS LAST, p.nome, p.posto_id;

CREATE OR REPLACE VIEW marca_por_uf AS
SELECT marca, uf, count(*) AS total,
       count(DISTINCT municipio_slug) AS cidades
FROM publicacao_marca GROUP BY 1, 2;

CREATE OR REPLACE VIEW marca_por_cidade AS
SELECT marca, uf, municipio, municipio_slug, ibge, count(*) AS total
FROM publicacao_marca WHERE municipio_slug IS NOT NULL
GROUP BY 1, 2, 3, 4, 5;

-- Marcas com rede em cada cidade — alimenta o bloco "por marca" que aparece na
-- página geral da cidade, ligando as duas árvores do site.
CREATE OR REPLACE VIEW cidade_com_marca AS
SELECT uf, municipio_slug, marca, total
FROM marca_por_cidade;

-- Conferência: quantas oficinas por fonte e quanto se conseguiu resolver.
CREATE OR REPLACE VIEW marca_cobertura AS
SELECT fonte,
       count(*)                                        AS oficinas,
       count(municipio_slug)                           AS com_municipio,
       count(*) FILTER (municipio_origem = 'nome do município no endereço')
                                                       AS municipio_pelo_endereco,
       count(telefone)                                 AS com_telefone,
       count(email)                                    AS com_email,
       count(cnpj)                                     AS casadas_com_cnpj,
       count(DISTINCT uf)                              AS estados,
       count(DISTINCT uf || '/' || coalesce(municipio_slug, '?')) AS cidades
FROM marca_posto GROUP BY fonte ORDER BY fonte;
