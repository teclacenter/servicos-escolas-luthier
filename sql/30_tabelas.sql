-- Materializa os CSVs em tabelas DuckDB. Depois disto nenhuma consulta volta a
-- varrer os 29 GB de texto: o relatório e as exportações leem daqui.
-- Guardamos TODAS as situações cadastrais (não só a 02) para que o relatório
-- possa mostrar quantos registros cada filtro descarta.

CREATE OR REPLACE TABLE empresas AS SELECT * FROM empresas_csv;

CREATE OR REPLACE TABLE simples AS SELECT * FROM simples_csv;

CREATE OR REPLACE TABLE estabelecimentos AS SELECT * FROM estabelecimentos_csv;
