-- Views que alimentam saida/relatorio-base.md, as exportações e o banco de
-- publicação. Uma view por seção: o Python só formata, não calcula.

-- Linha canônica de exportação: estabelecimento x vertical.
-- Ordem de colunas conforme a seção 6.2 do briefing, mais as colunas de
-- apresentação pedidas em 2026-08-24 (endereço em uma linha, CEP e telefones
-- formatados, celular separado do fixo, e a ficha pronta).
CREATE OR REPLACE VIEW exportacao AS
SELECT
    a.id, a.cnpj_formatado,
    a.nome, a.nome_fantasia, a.razao_social, a.razao_social_publicavel,
    a.logradouro, a.numero, a.complemento, a.bairro,
    a.endereco, a.endereco_com_complemento,
    a.cep, a.cep_formatado,
    a.municipio, a.municipio_slug, a.ibge, a.uf, a.cidade_uf,
    a.telefone, a.telefone_tipo, a.telefone_formatado,
    a.telefone_9, a.telefone_9_formatado,
    a.telefone_2, a.telefone_2_tipo, a.telefone_2_formatado,
    a.telefone_2_9, a.telefone_2_9_formatado,
    a.email, a.dominio_email, a.dominio_provedor, a.site_candidato,
    a.cnae_principal, a.cnae_principal_desc, a.cnaes_secundarios, v.origem_cnae,
    a.data_abertura, a.porte, a.mei, a.matriz, a.suspeita_duplicata,
    v.vertical, v.rotulo AS vertical_rotulo, a.safra,
    a.ficha
FROM estabelecimentos_alvo a
JOIN estabelecimento_vertical v USING (id);

-- 6.1.1 — ativos por CNAE alvo no Brasil, com a vertical a que serve.
CREATE OR REPLACE VIEW rel_cnae_brasil AS
SELECT v.vertical, v.cnae, c.descricao,
       cc.n_principal, cc.n_secundario,
       cc.n_principal + cc.n_secundario AS n_total_ocorrencias
FROM vertical_cnae v
JOIN cnaes c               ON c.codigo  = v.cnae
LEFT JOIN contagem_cnae cc ON cc.codigo = v.cnae
ORDER BY v.vertical, cc.n_principal DESC;

-- 6.1.2 — vertical x UF.
CREATE OR REPLACE VIEW rel_vertical_uf AS
SELECT vertical, uf, count(*) AS total
FROM exportacao
GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- 6.3 — agregado por cidade. É daqui que sai a ordem do scraping e, depois, a
-- lista de páginas a gerar.
CREATE OR REPLACE VIEW vertical_por_cidade AS
SELECT vertical, uf, municipio, municipio_slug, ibge,
       count(*)                 AS total,
       count(telefone)          AS com_telefone,
       count_if(telefone_tipo = 'fixo')  AS com_fixo,
       count_if(telefone_tipo = 'movel') AS com_movel,
       count(email)             AS com_email,
       count(site_candidato)    AS com_site_candidato
FROM exportacao
GROUP BY 1, 2, 3, 4, 5
ORDER BY vertical, total DESC, uf, municipio;

-- 6.1.3 — top 100 municípios de cada vertical.
CREATE OR REPLACE VIEW rel_top_municipios AS
SELECT * FROM (
    SELECT *, row_number() OVER (PARTITION BY vertical
                                 ORDER BY total DESC, uf, municipio) AS pos
    FROM vertical_por_cidade
) WHERE pos <= 100;

-- 6.1.4 — distribuição de cidades por faixa de tamanho. Diz se a vertical existe:
-- uma vertical com 900 cidades de 1 registro é uma vertical que não existe.
CREATE OR REPLACE VIEW rel_faixa_cidades AS
WITH faixas AS (
    SELECT vertical,
           CASE WHEN total = 1 THEN '1'
                WHEN total = 2 THEN '2'
                WHEN total BETWEEN 3 AND 5  THEN '3-5'
                WHEN total BETWEEN 6 AND 10 THEN '6-10'
                ELSE '11+' END AS faixa,
           total
    FROM vertical_por_cidade
)
SELECT vertical, faixa, count(*) AS cidades, sum(total) AS estabelecimentos
FROM faixas GROUP BY 1, 2;

-- 6.1.5 e 6.1.6 — preenchimento dos campos e origem do CNAE, por vertical.
CREATE OR REPLACE VIEW rel_qualidade AS
SELECT
    vertical,
    count(*)                                    AS total,
    count(DISTINCT municipio_slug || '/' || uf) AS cidades,
    count(telefone)                             AS com_telefone,
    count_if(telefone_tipo = 'fixo')            AS com_fixo,
    count_if(telefone_tipo = 'movel')           AS com_movel,
    count(telefone_2)                           AS com_segundo_telefone,
    count(nome_fantasia)                        AS com_nome_fantasia,
    count(email)                                AS com_email,
    count(site_candidato)                       AS com_site_candidato,
    count(endereco)                             AS com_endereco,
    count(cep_formatado)                        AS com_cep,
    count_if(origem_cnae = 'principal')         AS via_cnae_principal,
    count_if(origem_cnae = 'secundario')        AS via_cnae_secundario,
    count_if(mei)                               AS mei,
    count_if(matriz)                            AS matriz,
    count_if(suspeita_duplicata)                AS suspeita_duplicata,
    count_if(ibge IS NULL)                      AS sem_ibge
FROM exportacao
GROUP BY 1 ORDER BY total DESC;

-- Composição de cada vertical por CNAE: qual CNAE responde por qual fatia.
-- Expõe vertical dominada por catch-all, que a fase 2 teria que filtrar no braço.
CREATE OR REPLACE VIEW rel_composicao_vertical AS
WITH pares AS (
    SELECT v.vertical, a.cnae, count(*) AS n
    FROM estabelecimento_cnae_alvo a
    JOIN vertical_cnae v ON v.cnae = a.cnae
    GROUP BY 1, 2
)
SELECT p.vertical, p.cnae, c.descricao, p.n,
       round(100.0 * p.n / sum(p.n) OVER (PARTITION BY p.vertical), 1) AS pct_da_vertical
FROM pares p JOIN cnaes c ON c.codigo = p.cnae
ORDER BY p.vertical, p.n DESC;

-- Endereço no exterior: uf = 'EX'. Não tem cidade brasileira, então não entra em
-- nenhuma página por município.
CREATE OR REPLACE VIEW rel_exterior AS
SELECT vertical, count(*) AS total FROM exportacao WHERE uf = 'EX'
GROUP BY 1 ORDER BY 2 DESC;

-- MEI: continua listado à parte. A publicação de e-mail e telefone foi liberada
-- pelo jurídico do cliente em 2026-08-24, mas MEI é pessoa física e a lista
-- separada serve para atender pedido de remoção sem varrer a base toda.
CREATE OR REPLACE VIEW registros_mei AS
SELECT a.id, a.cnpj_formatado, a.nome, a.razao_social, a.uf, a.municipio,
       a.telefone_formatado, a.telefone_9_formatado, a.email,
       string_agg(DISTINCT v.vertical, ',' ORDER BY v.vertical) AS verticais
FROM estabelecimentos_alvo a
JOIN estabelecimento_vertical v USING (id)
WHERE a.mei
GROUP BY ALL
ORDER BY a.uf, a.municipio, a.nome;

-- ---------------------------------------------------------------------------
-- Publicação. Só o que vai para a página, já formatado. É esta view que
-- src/publicar.py copia para o SQLite: nenhum cálculo em tempo de servir.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW publicacao AS
SELECT
    id, vertical, uf, municipio, municipio_slug, ibge,
    nome_fantasia,
    -- só a versão limpa é publicada: CPF nunca vai para página pública
    razao_social_publicavel AS razao_social,
    endereco, cep_formatado AS cep, cidade_uf,
    telefone, telefone_tipo, telefone_formatado, telefone_9, telefone_9_formatado,
    telefone_2, telefone_2_tipo, telefone_2_formatado, telefone_2_9, telefone_2_9_formatado,
    email,
    site_candidato, cnpj_formatado, mei, suspeita_duplicata,
    -- Origem do CNAE e a atividade que a empresa declara como principal.
    -- Vai para a página: 78 % a 92 % dos registros entram pelo CNAE secundário,
    -- e sem essa informação a lista mistura loja de instrumento com papelaria
    -- que apenas declarou o CNAE. Melhor mostrar do que esconder.
    origem_cnae, cnae_principal, cnae_principal_desc,
    ficha
FROM exportacao
WHERE uf <> 'EX'            -- endereço no exterior não tem página por cidade
  AND municipio_slug IS NOT NULL
-- 'principal' < 'secundario' em ordem alfabética: quem tem a atividade como
-- principal aparece primeiro na página.
ORDER BY vertical, uf, municipio_slug, origem_cnae, nome_fantasia, razao_social, id;
