-- Tabelas de referência da RFB. Todas pequenas (< 130 KB), carga direta.
-- Sem cabeçalho, delimitador ';', encoding latin-1, tudo VARCHAR.

CREATE OR REPLACE TABLE cnaes AS
SELECT column0 AS codigo, column1 AS descricao
FROM read_csv('{EXTRAIDOS}/*.CNAECSV.csv',
     delim=';', quote='"', header=false, encoding='utf-8',
     all_varchar=true, columns={'column0':'VARCHAR','column1':'VARCHAR'});

-- Código da RFB (TOM), NÃO é o código IBGE. O crosswalk vem depois.
CREATE OR REPLACE TABLE municipios_rfb AS
SELECT column0 AS codigo_rfb, column1 AS nome_rfb
FROM read_csv('{EXTRAIDOS}/*.MUNICCSV.csv',
     delim=';', quote='"', header=false, encoding='utf-8',
     all_varchar=true, columns={'column0':'VARCHAR','column1':'VARCHAR'});

CREATE OR REPLACE TABLE motivos AS
SELECT column0 AS codigo, column1 AS descricao
FROM read_csv('{EXTRAIDOS}/*.MOTICSV.csv',
     delim=';', quote='"', header=false, encoding='utf-8',
     all_varchar=true, columns={'column0':'VARCHAR','column1':'VARCHAR'});

CREATE OR REPLACE TABLE naturezas AS
SELECT column0 AS codigo, column1 AS descricao
FROM read_csv('{EXTRAIDOS}/*.NATJUCSV.csv',
     delim=';', quote='"', header=false, encoding='utf-8',
     all_varchar=true, columns={'column0':'VARCHAR','column1':'VARCHAR'});

CREATE OR REPLACE TABLE paises AS
SELECT column0 AS codigo, column1 AS descricao
FROM read_csv('{EXTRAIDOS}/*.PAISCSV.csv',
     delim=';', quote='"', header=false, encoding='utf-8',
     all_varchar=true, columns={'column0':'VARCHAR','column1':'VARCHAR'});

CREATE OR REPLACE TABLE qualificacoes AS
SELECT column0 AS codigo, column1 AS descricao
FROM read_csv('{EXTRAIDOS}/*.QUALSCSV.csv',
     delim=';', quote='"', header=false, encoding='utf-8',
     all_varchar=true, columns={'column0':'VARCHAR','column1':'VARCHAR'});
