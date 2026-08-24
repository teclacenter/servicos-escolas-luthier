-- Estabelecimentos-alvo e a relação N:N com as verticais.
-- Nenhum registro é descartado por dado ruim: telefone inválido, e-mail ausente
-- ou município sem IBGE viram NULL, e a linha continua na base.

-- 1. Todo par (estabelecimento ativo, cnae alvo), com a origem do CNAE.
--    O CNAE secundário é uma lista separada por vírgula: filtrar só pelo
--    principal perderia a maior parte da base.
CREATE OR REPLACE TABLE estabelecimento_cnae_alvo AS
WITH ativos AS (
    SELECT cnpj_basico, cnpj_ordem, cnpj_dv,
           cnae_fiscal_principal, cnae_fiscal_secundaria
    FROM estabelecimentos
    WHERE situacao_cadastral = '02'
),
pelo_principal AS (
    SELECT cnpj_basico, cnpj_ordem, cnpj_dv,
           cnae_fiscal_principal AS cnae, 'principal' AS origem
    FROM ativos
    WHERE cnae_fiscal_principal IN (SELECT cnae FROM vertical_cnae)
),
pelo_secundario AS (
    SELECT a.cnpj_basico, a.cnpj_ordem, a.cnpj_dv,
           trim(x) AS cnae, 'secundario' AS origem
    FROM ativos a, unnest(str_split(a.cnae_fiscal_secundaria, ',')) AS t(x)
    WHERE a.cnae_fiscal_secundaria IS NOT NULL
      AND a.cnae_fiscal_secundaria <> ''
      AND trim(x) IN (SELECT cnae FROM vertical_cnae)
)
SELECT * FROM pelo_principal
UNION ALL
SELECT * FROM pelo_secundario;

-- 2. Estabelecimento x vertical (N:N). origem_cnae = 'principal' quando ao menos
--    um CNAE daquela vertical é o principal do estabelecimento.
CREATE OR REPLACE TABLE estabelecimento_vertical AS
SELECT
    e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS id,
    v.vertical,
    v.rotulo,
    CASE WHEN bool_or(e.origem = 'principal') THEN 'principal' ELSE 'secundario' END
        AS origem_cnae,
    string_agg(DISTINCT e.cnae, ',' ORDER BY e.cnae) AS cnaes_da_vertical
FROM estabelecimento_cnae_alvo e
JOIN vertical_cnae v ON v.cnae = e.cnae
GROUP BY 1, 2, 3;

-- 3. Uma linha por estabelecimento-alvo, com tudo normalizado e já formatado
--    para publicação. As colunas *_fmt e 'ficha' existem para que a geração de
--    páginas seja um SELECT puro: nenhuma formatação em tempo de servir.
CREATE OR REPLACE TABLE estabelecimentos_alvo AS
WITH alvo AS (
    SELECT DISTINCT cnpj_basico, cnpj_ordem, cnpj_dv FROM estabelecimento_cnae_alvo
),
bruto AS (
    SELECT
        est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv,
        est.nome_fantasia, est.identificador_matriz_filial, est.situacao_cadastral,
        est.tipo_logradouro, est.logradouro, est.numero, est.complemento,
        est.bairro, est.cep, est.uf, est.correio_eletronico,
        est.cnae_fiscal_principal, est.cnae_fiscal_secundaria,
        est.data_inicio_atividade,
        -- os dois telefones da RFB, cada um validado por conta própria
        telefone_e164(est.ddd_1, est.telefone_1) AS tel1,
        telefone_e164(est.ddd_2, est.telefone_2) AS tel2,
        emp.razao_social, emp.porte,
        sim.opcao_mei,
        mun.municipio, mun.municipio_slug, mun.ibge,
        cna.descricao AS cnae_principal_desc
    FROM estabelecimentos est
    JOIN alvo USING (cnpj_basico, cnpj_ordem, cnpj_dv)
    LEFT JOIN empresas   emp ON emp.cnpj_basico = est.cnpj_basico
    LEFT JOIN simples    sim ON sim.cnpj_basico = est.cnpj_basico
    LEFT JOIN municipios mun ON mun.codigo_rfb  = est.municipio
    LEFT JOIN cnaes      cna ON cna.codigo      = est.cnae_fiscal_principal
),
montado AS (
    SELECT
        cnpj_basico || cnpj_ordem || cnpj_dv AS id,
        cnpj_basico[1:2] || '.' || cnpj_basico[3:5] || '.' || cnpj_basico[6:8]
            || '/' || cnpj_ordem || '-' || cnpj_dv                AS cnpj_formatado,

        -- Os dois nomes, sempre. A ficha mostra fantasia e razão social; quando
        -- não há fantasia, a razão social aparece uma única vez.
        -- Os dois nomes passam por texto_nome: fora o CPF colado no fim, fora a
        -- base do CNPJ colada no início, e fora nome que seja só dígitos.
        texto_nome(nome_fantasia)                                 AS nome_fantasia,
        trim(razao_social)                                        AS razao_social,
        texto_nome(razao_social)                                  AS razao_social_publicavel,
        coalesce(texto_nome(nome_fantasia), texto_nome(razao_social),
                 'CNPJ ' || cnpj_basico[1:2] || '.' || cnpj_basico[3:5] || '.'
                 || cnpj_basico[6:8] || '/' || cnpj_ordem || '-' || cnpj_dv) AS nome,

        abreviar_logradouro(titulo_caso(logradouro_completo(tipo_logradouro, logradouro)))
            AS logradouro,
        nullif(upper(trim(numero)), '')                           AS numero,
        titulo_caso(complemento)                                  AS complemento,
        titulo_caso(bairro)                                       AS bairro,
        nullif(regexp_replace(coalesce(cep, ''), '[^0-9]', '', 'g'), '') AS cep,
        cep_formatado(cep)                                        AS cep_formatado,

        municipio, municipio_slug, ibge, uf,
        municipio || '-' || uf                                    AS cidade_uf,

        -- Os dois telefones da Receita, cada um com seu tipo e nos dois
        -- formatos. A base só tem 8 dígitos (medido: zero números de 9 dígitos),
        -- então o móvel sai também com o 9 acrescentado pela regra de migração,
        -- em coluna PRÓPRIA, sem sobrescrever o número original.
        tel1                                                      AS telefone,
        tipo_telefone(tel1)                                       AS telefone_tipo,
        telefone_exibicao(tel1)                                   AS telefone_formatado,
        telefone_com_nono_digito(tel1)                            AS telefone_9,
        telefone_exibicao(telefone_com_nono_digito(tel1))         AS telefone_9_formatado,
        tel2                                                      AS telefone_2,
        tipo_telefone(tel2)                                       AS telefone_2_tipo,
        telefone_exibicao(tel2)                                   AS telefone_2_formatado,
        telefone_com_nono_digito(tel2)                            AS telefone_2_9,
        telefone_exibicao(telefone_com_nono_digito(tel2))         AS telefone_2_9_formatado,

        lower(nullif(trim(correio_eletronico), ''))               AS email,
        dominio_email(correio_eletronico)                         AS dominio_email,
        dominio_provedor(dominio_email(correio_eletronico))       AS dominio_provedor,
        CASE WHEN NOT dominio_provedor(dominio_email(correio_eletronico))
             THEN 'https://' || dominio_email(correio_eletronico) END AS site_candidato,

        cnae_fiscal_principal                                     AS cnae_principal,
        cnae_principal_desc,
        nullif(cnae_fiscal_secundaria, '')                        AS cnaes_secundarios,

        try_strptime(data_inicio_atividade, '%Y%m%d')::DATE       AS data_abertura,
        porte                                                     AS porte_codigo,
        CASE porte WHEN '00' THEN 'não informado'
                   WHEN '01' THEN 'microempresa'
                   WHEN '03' THEN 'empresa de pequeno porte'
                   WHEN '05' THEN 'demais' END                    AS porte,
        coalesce(opcao_mei = 'S', false)                          AS mei,
        identificador_matriz_filial = '1'                         AS matriz,
        situacao_cadastral,
        '{SAFRA}'                                                 AS safra,
        CAST(NULL AS DOUBLE) AS lat,   -- sem geocodificação nesta fase, por escopo
        CAST(NULL AS DOUBLE) AS lng
    FROM bruto
)
SELECT *,
    -- Endereço publicado: "Av. Princesa Isabel, 935 - Sao Caetano".
    -- O complemento fica FORA da linha publicada, por dois motivos: é o formato
    -- que o cliente especificou, e o campo vem sujo na origem — 21.114 registros
    -- têm complemento acima de 40 caracteres, com repetição do tipo
    -- 'TERREO TERREO;TERREO TERREO;TERREO TERREO;TERREO'. Nada se perde: o
    -- complemento continua em coluna própria e em endereco_com_complemento.
    concat_ws(' - ', concat_ws(', ', logradouro, numero), bairro) AS endereco,
    concat_ws(' - ', concat_ws(', ', logradouro, numero, complemento), bairro)
                                                                  AS endereco_com_complemento,
    -- Ficha pronta para publicar. concat_ws descarta os NULL, e '||' propaga NULL,
    -- então um rótulo sem valor ("Tel: ") nunca sobra na saída.
    concat_ws(chr(10),
        nome_fantasia,
        razao_social_publicavel,
        concat_ws(' - ', concat_ws(', ', logradouro, numero), bairro),
        municipio || '-' || uf,
        'CEP: ' || cep_formatado,
        linha_telefone(telefone),
        linha_telefone(telefone_2),
        email
    )                                                             AS ficha
FROM montado;

-- 4. Suspeita de duplicata: mesmo endereço exato e nome muito parecido.
--    Só MARCA. Nunca apaga — a decisão é humana.
CREATE OR REPLACE TABLE duplicata_suspeita AS
WITH base AS (
    SELECT id, uf, municipio_slug, cep, slug(logradouro) AS lg,
           upper(coalesce(numero, '')) AS num, slug(nome) AS nm
    FROM estabelecimentos_alvo
    WHERE nome IS NOT NULL AND cep IS NOT NULL AND logradouro IS NOT NULL
)
SELECT DISTINCT a.id
FROM base a
JOIN base b
  ON  a.uf = b.uf AND a.municipio_slug = b.municipio_slug
  AND a.cep = b.cep AND a.lg = b.lg AND a.num = b.num
  AND a.id <> b.id
  AND jaro_winkler_similarity(a.nm, b.nm) >= 0.90;

ALTER TABLE estabelecimentos_alvo ADD COLUMN suspeita_duplicata BOOLEAN;
UPDATE estabelecimentos_alvo SET suspeita_duplicata =
    id IN (SELECT id FROM duplicata_suspeita);
