-- Views sobre os CSVs brutos: nomeiam as colunas sem materializar nada.
-- Layout confirmado por inspeção em 2026-08-24 (safra D60808):
--   ESTABELE = 30 colunas, EMPRECSV = 7, SIMPLES = 7.
-- Lê de extraidos/ (UTF-8, já limpo pelo alvo 'preparar'), não dos brutos latin-1:
-- o leitor latin-1 do DuckDB recusa o arquivo inteiro por causa de 33 bytes de controle.
-- all_varchar: CNPJ/CEP/telefone têm zeros à esquerda que somem se tipados como número.

CREATE OR REPLACE VIEW estabelecimentos_csv AS
SELECT * FROM read_csv('{EXTRAIDOS}/*.ESTABELE.csv',
    delim=';', quote='"', escape='"', header=false, encoding='utf-8',
    all_varchar=true, ignore_errors=false,
    columns={
      'cnpj_basico':'VARCHAR', 'cnpj_ordem':'VARCHAR', 'cnpj_dv':'VARCHAR',
      'identificador_matriz_filial':'VARCHAR', 'nome_fantasia':'VARCHAR',
      'situacao_cadastral':'VARCHAR', 'data_situacao_cadastral':'VARCHAR',
      'motivo_situacao_cadastral':'VARCHAR', 'nome_cidade_exterior':'VARCHAR',
      'pais':'VARCHAR', 'data_inicio_atividade':'VARCHAR',
      'cnae_fiscal_principal':'VARCHAR', 'cnae_fiscal_secundaria':'VARCHAR',
      'tipo_logradouro':'VARCHAR', 'logradouro':'VARCHAR', 'numero':'VARCHAR',
      'complemento':'VARCHAR', 'bairro':'VARCHAR', 'cep':'VARCHAR', 'uf':'VARCHAR',
      'municipio':'VARCHAR', 'ddd_1':'VARCHAR', 'telefone_1':'VARCHAR',
      'ddd_2':'VARCHAR', 'telefone_2':'VARCHAR', 'ddd_fax':'VARCHAR', 'fax':'VARCHAR',
      'correio_eletronico':'VARCHAR', 'situacao_especial':'VARCHAR',
      'data_situacao_especial':'VARCHAR'
    });

CREATE OR REPLACE VIEW empresas_csv AS
SELECT * FROM read_csv('{EXTRAIDOS}/*.EMPRECSV.csv',
    delim=';', quote='"', escape='"', header=false, encoding='utf-8',
    all_varchar=true, ignore_errors=false,
    columns={
      'cnpj_basico':'VARCHAR', 'razao_social':'VARCHAR', 'natureza_juridica':'VARCHAR',
      'qualificacao_responsavel':'VARCHAR', 'capital_social':'VARCHAR',
      'porte':'VARCHAR', 'ente_federativo_responsavel':'VARCHAR'
    });

CREATE OR REPLACE VIEW simples_csv AS
SELECT * FROM read_csv('{EXTRAIDOS}/*.SIMPLES.CSV.*.csv',
    delim=';', quote='"', escape='"', header=false, encoding='utf-8',
    all_varchar=true, ignore_errors=false,
    columns={
      'cnpj_basico':'VARCHAR', 'opcao_simples':'VARCHAR',
      'data_opcao_simples':'VARCHAR', 'data_exclusao_simples':'VARCHAR',
      'opcao_mei':'VARCHAR', 'data_opcao_mei':'VARCHAR', 'data_exclusao_mei':'VARCHAR'
    });
