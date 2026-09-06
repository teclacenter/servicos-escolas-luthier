-- Macros de normalização. Implementação única: as tabelas grandes usam estas
-- macros e os testes em tests/ chamam exatamente as mesmas definições.

-- Só os dígitos de um texto.
CREATE OR REPLACE MACRO so_digitos(t) AS
    regexp_replace(coalesce(t, ''), '[^0-9]', '', 'g');

-- DDDs oficialmente em uso no Brasil (Plano Geral de Códigos Nacionais, Anatel).
CREATE OR REPLACE MACRO ddd_valido(d) AS
    d IN ('11','12','13','14','15','16','17','18','19',
          '21','22','24','27','28',
          '31','32','33','34','35','37','38',
          '41','42','43','44','45','46','47','48','49',
          '51','53','54','55',
          '61','62','63','64','65','66','67','68','69',
          '71','73','74','75','77','79',
          '81','82','83','84','85','86','87','88','89',
          '91','92','93','94','95','96','97','98','99');

-- DDD + número -> E.164 (+55DDDNUMERO). Devolve NULL quando inválido;
-- o registro NUNCA é descartado por telefone ruim.
CREATE OR REPLACE MACRO telefone_e164(ddd, numero) AS (
    WITH x AS (SELECT so_digitos(ddd) AS d, so_digitos(numero) AS n)
    SELECT CASE
        WHEN length(d) <> 2 THEN NULL
        WHEN NOT ddd_valido(d) THEN NULL
        WHEN length(n) NOT IN (8, 9) THEN NULL          -- +2 do DDD = mínimo 10 dígitos
        WHEN rtrim(n, substr(n, 1, 1)) = '' THEN NULL    -- 99999999, 00000000... (RE2 não tem backreference)
        ELSE '+55' || d || n
    END FROM x
);

-- Slug ASCII, minúsculo, hifenizado. Único por UF (garantido no crosswalk).
CREATE OR REPLACE MACRO slug(t) AS
    nullif(
      trim(
        regexp_replace(
          regexp_replace(lower(strip_accents(coalesce(t, ''))), '[^a-z0-9]+', '-', 'g'),
          '^-+|-+$', '', 'g'),
      '-'),
    '');

-- Domínio do e-mail, minúsculo. NULL se não houver um domínio plausível.
CREATE OR REPLACE MACRO dominio_email(email) AS (
    WITH x AS (SELECT lower(trim(coalesce(email, ''))) AS e)
    SELECT CASE
        WHEN e NOT LIKE '%@%' THEN NULL
        WHEN regexp_extract(e, '@([a-z0-9.-]+\.[a-z]{2,})$', 1) = '' THEN NULL
        ELSE regexp_extract(e, '@([a-z0-9.-]+\.[a-z]{2,})$', 1)
    END FROM x
);

-- Provedores gratuitos/genéricos: domínio de e-mail não indica site próprio.
CREATE OR REPLACE MACRO dominio_provedor(dominio) AS
    dominio IS NULL OR
    regexp_matches(dominio,
      '^(www\.)?(gmail|googlemail|hotmail|outlook|live|msn|yahoo|ymail|rocketmail|bol|uol|terra|ig|globo|globomail|icloud|me|mac|aol|protonmail|proton|pm|zipmail|zipmail\.com|oi|r7|itelefonica|superig|velox|folha|click21|onda|brturbo|pop|ibest|gmx|mail|yandex|inbox|list|hush|tutanota|fastmail|zoho|qq|163|126|naver|daum|web|t-online|libero|orange|wanadoo|free|sfr|laposte|abv|seznam|interia|wp|onet|mynet|hotmai|hotmial|gmai)\.'
      || '[a-z.]+$');

-- ---------------------------------------------------------------------------
-- Macros de apresentação, para a ficha publicável (formato pedido em 2026-08-24).
-- Tudo determinístico: nenhuma acentuação é inventada. A RFB grava logradouro e
-- bairro em MAIÚSCULA e SEM acento; devolver "São Caetano" a partir de
-- "SAO CAETANO" seria adivinhar, então o resultado é "Sao Caetano". O nome do
-- município é a exceção: vem acentuado da tabela do IBGE.
-- ---------------------------------------------------------------------------

-- "AVENIDA PRINCESA ISABEL" -> "Avenida Princesa Isabel"
CREATE OR REPLACE MACRO titulo_caso(t) AS
    nullif(array_to_string(list_transform(
        str_split(lower(trim(coalesce(t, ''))), ' '),
        x -> CASE
               WHEN x = '' THEN x
               WHEN x IN ('de','da','do','das','dos','e','em','no','na','nos',
                          'nas','a','o','com','sob','sobre','para','por') THEN x
               ELSE upper(x[1]) || x[2:]
             END), ' '), '');

-- Abreviação do tipo de logradouro. Mapa fixo e versionado, sem inferência.
CREATE OR REPLACE MACRO abreviar_logradouro(t) AS
    CASE
      WHEN t IS NULL THEN NULL
      WHEN starts_with(t, 'Avenida ')  THEN 'Av. '   || t[9:]
      WHEN starts_with(t, 'Rua ')      THEN 'R. '    || t[5:]
      WHEN starts_with(t, 'Travessa ') THEN 'Tv. '   || t[10:]
      WHEN starts_with(t, 'Praca ')    THEN 'Pç. '   || t[7:]
      WHEN starts_with(t, 'Rodovia ')  THEN 'Rod. '  || t[9:]
      WHEN starts_with(t, 'Estrada ')  THEN 'Estr. ' || t[9:]
      WHEN starts_with(t, 'Alameda ')  THEN 'Al. '   || t[9:]
      WHEN starts_with(t, 'Largo ')    THEN 'Lgo. '  || t[7:]
      ELSE t
    END;

-- 45607123 -> "45607-123". NULL se não tiver 8 dígitos.
CREATE OR REPLACE MACRO cep_formatado(cep) AS (
    WITH x AS (SELECT so_digitos(cep) AS c)
    SELECT CASE WHEN length(c) = 8 THEN c[1:5] || '-' || c[6:8] END FROM x
);

-- Tipo do telefone, a partir do primeiro dígito do número local.
-- FATO MEDIDO na safra D60808: a RFB guarda no máximo 8 dígitos e a base tem
-- ZERO números de 9 dígitos. Celular brasileiro tem 9 dígitos desde 2016, logo
-- todo móvel VINDO DA RECEITA está no formato anterior à migração.
-- Numeração brasileira: local começando em 2-5 = linha fixa; 6-9 = móvel.
-- O caso de 9 dígitos existe na outra origem de dados do projeto — as redes de
-- assistência autorizada, que publicam o número atual — e só pode ser móvel:
-- linha fixa nunca ganhou o nono dígito.
CREATE OR REPLACE MACRO tipo_telefone(e164) AS (
    WITH x AS (SELECT so_digitos(e164) AS d)
    SELECT CASE
        WHEN length(d) = 13 THEN 'movel'                -- 55 + DDD(2) + 9 dígitos
        WHEN length(d) <> 12 THEN NULL                  -- 55 + DDD(2) + 8 dígitos
        WHEN d[5:5] IN ('2','3','4','5') THEN 'fixo'
        WHEN d[5:5] IN ('6','7','8','9') THEN 'movel'
    END FROM x
);

-- Móvel de 8 dígitos com o 9º dígito acrescentado, pela regra da migração
-- nacional (todo móvel ganhou um 9 à frente do número local).
-- É DERIVAÇÃO, não dado da Receita: mora em coluna própria e o número original
-- continua publicado ao lado, para o leitor conferir.
CREATE OR REPLACE MACRO telefone_com_nono_digito(e164) AS (
    WITH x AS (SELECT so_digitos(e164) AS d)
    SELECT CASE WHEN length(d) = 12 AND d[5:5] IN ('6','7','8','9')
                THEN '+55' || d[3:4] || '9' || d[5:12] END
    FROM x
);

-- E.164 -> "(73) 3613-5835" (fixo) / "(11) 98888-7777" (celular)
CREATE OR REPLACE MACRO telefone_exibicao(e164) AS (
    WITH x AS (SELECT so_digitos(e164) AS d)
    SELECT CASE
        WHEN length(d) = 13 THEN '(' || d[3:4] || ') ' || d[5:9] || '-' || d[10:13]
        WHEN length(d) = 12 THEN '(' || d[3:4] || ') ' || d[5:8] || '-' || d[9:12]
    END FROM x
);

-- Linha de telefone da ficha. Fixo sai direto; móvel de 8 dígitos sai nos DOIS
-- formatos, o com 9 primeiro (é o que disca hoje) e o original ao lado. Móvel
-- que já veio com 9 dígitos sai uma vez só — não há um "original" diferente.
CREATE OR REPLACE MACRO linha_telefone(e164) AS
    CASE tipo_telefone(e164)
        WHEN 'fixo'  THEN 'Tel: ' || telefone_exibicao(e164)
        WHEN 'movel' THEN 'Cel: ' || coalesce(
              telefone_exibicao(telefone_com_nono_digito(e164)) || ' ou ' ||
              telefone_exibicao(e164),
              telefone_exibicao(e164))
    END;

-- tipo_logradouro + logradouro sem repetir o tipo. A RFB grava, no mesmo
-- registro, tipo_logradouro='RUA' e logradouro='RUA 12', o que concatenado
-- vira "RUA RUA 12". Se o nome já começa pelo tipo, o tipo não é prefixado.
CREATE OR REPLACE MACRO logradouro_completo(tipo, nome) AS
    nullif(trim(CASE
        WHEN coalesce(trim(nome), '') = '' THEN coalesce(trim(tipo), '')
        WHEN coalesce(trim(tipo), '') = '' THEN trim(nome)
        WHEN starts_with(upper(trim(nome)), upper(trim(tipo)) || ' ') THEN trim(nome)
        WHEN upper(trim(nome)) = upper(trim(tipo)) THEN trim(nome)
        ELSE trim(tipo) || ' ' || trim(nome)
    END), '');

-- Nome limpo para publicação.
--
-- A razão social de MEI vem contaminada em dois padrões medidos na safra D60808
-- (403.791 de 777.418 registros-alvo, 51,9 %):
--   1. CPF colado no fim: "THALITA CRISTINA GONCALVES 11916547613" — 95.441 casos.
--      CPF é dado pessoal e NÃO vai para página pública. Removido sempre.
--   2. Base do CNPJ colada no início: "46.696.520 RODRIGO XAVIER MONTEIRO" —
--      308.350 casos. Redundante: o CNPJ já aparece em campo próprio.
-- A razão social crua continua intacta na coluna razao_social, para auditoria.
CREATE OR REPLACE MACRO nome_publicavel(t) AS
    nullif(trim(regexp_replace(
        regexp_replace(coalesce(t, ''), '^[0-9]{2}\.[0-9]{3}\.[0-9]{3}\s+', '', 'g'),
        '\s*[0-9]{11}$', '', 'g')), '');

-- Nome exibível: passa por nome_publicavel e ainda recusa nome que seja só
-- dígitos. Medido: 12 registros têm nome_fantasia puramente numérico e um deles
-- é um CPF nu ('43207072570'), que não pode virar título de ficha.
CREATE OR REPLACE MACRO texto_nome(t) AS
    CASE
      WHEN nome_publicavel(t) IS NULL THEN NULL
      WHEN regexp_matches(nome_publicavel(t), '^[0-9]+$') THEN NULL
      ELSE nome_publicavel(t)
    END;
