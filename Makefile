# Fase 1 — base CNPJ por vertical, cidade e estado, e o site estático.
# Determinístico: nenhuma etapa chama IA. A única requisição de rede do projeto
# foi a tabela de municípios do IBGE, autorizada em separado (src/ibge_para_csv.py).

PY := ./.venv/bin/python
export PYTHONPATH := src

.PHONY: all dados preparar carregar relatorio exportar publicar site servir \
        deploy testes limpar limpar-site limpar-tudo auditar-bytes

all: dados publicar site
dados: preparar carregar relatorio exportar

## preparar — CSVs brutos -> extraidos/*.csv em UTF-8, sem bytes de controle
preparar:
	$(PY) src/preparar.py

## carregar — cria cnpj.duckdb: tabelas, crosswalk de municípios e views alvo
carregar:
	$(PY) src/carregar.py

## relatorio — saida/relatorio-base.md
relatorio:
	$(PY) src/relatorio.py

## exportar — saida/csv/*.csv, saida/parquet/*.parquet e os agregados por cidade
exportar:
	$(PY) src/exportar.py

## publicar — saida/publicacao.sqlite, indexado por área + estado + cidade
publicar:
	$(PY) src/publicar.py

## site — gera o site estático em site/ (HTML, sitemap, robots.txt, llms.txt)
site:
	$(PY) src/site.py

## deploy — publica site/ em produção (configuração em deploy.env)
deploy:
	./deploy.sh

## servir — sobe o site local em http://localhost:8788
servir:
	@echo "http://localhost:8788  (Ctrl+C para parar)"
	@cd site && $(CURDIR)/.venv/bin/python -m http.server 8788

## testes — normalização de telefone, slug, domínio e formatação da ficha
testes:
	$(PY) -m pytest tests/ -q

## auditar-bytes — mostra os bytes de controle presentes nos brutos
auditar-bytes:
	$(PY) src/auditar_bytes.py

## limpar — remove banco e saídas, preserva extraidos/ (reconverter é caro)
limpar:
	rm -f cnpj.duckdb cnpj.duckdb.wal
	rm -rf saida tmp/*.log

limpar-site:
	rm -rf site

## limpar-tudo — remove também os UTF-8 convertidos
limpar-tudo: limpar limpar-site
	rm -rf extraidos tmp
