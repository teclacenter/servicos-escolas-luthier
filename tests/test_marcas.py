"""Testa a coleta das redes por marca: o recorte do HTML e o casamento da cidade.

Duas metades, separadas porque falham por motivos diferentes:

  * as funções de src/coletar_marcas.py são puras e rodam sobre trechos reais
    das sete fontes, copiados aqui. Se um fabricante mudar o HTML, o parser
    quebra em produção e não aqui — o valor destes testes é impedir que uma
    refatoração quebre o que já funciona;

  * o casamento cidade -> município do IBGE roda no DuckDB de verdade, com as
    mesmas macros e o mesmo SQL da carga. É a parte que decide se a oficina
    ganha página de cidade ou fica só na de estado, e é onde um falso positivo
    mandaria a oficina para a cidade errada.
"""
import sys
from pathlib import Path

import duckdb
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from coletar_marcas import (_cep, _cf_email, _emails, _limpar_endereco,  # noqa: E402
                            _telefones, texto_de, uf_de, uf_do_ddd,
                            uf_do_endereco)
from db import dividir_sql  # noqa: E402
from marcas import FONTES, MARCAS  # noqa: E402


# ------------------------------------------------------------------ catálogo
def test_toda_marca_aponta_para_uma_fonte_declarada():
    for slug, m in MARCAS.items():
        assert m["fonte"] in FONTES, f"{slug} aponta para fonte inexistente"


def test_slug_de_marca_nao_colide_com_sigla_de_estado():
    """/assistencia-tecnica/marca/{slug}/ e /assistencia-tecnica/{uf}/ convivem
    porque o prefixo 'marca' separa as duas árvores. Mesmo assim um slug igual
    a uma sigla de estado é armadilha para a próxima reescrita de URL — e há
    slug de duas letras no catálogo ('lp'), então a checagem é sobre a sigla."""
    from config import UF_NOME
    assert not (set(MARCAS) & {s.lower() for s in UF_NOME})


def test_fonte_bloqueada_explica_o_motivo():
    for slug, f in FONTES.items():
        if "bloqueada" in f:
            assert f["bloqueada"], f"{slug} bloqueada sem motivo escrito"


# -------------------------------------------------------------------- CEP
@pytest.mark.parametrize("texto,esperado", [
    ("CEP: 13070-143", "13070-143"),
    ("CEP: 57.020-260", "57020-260"),      # a Casio grava com ponto de milhar
    ("zip 05304010", "05304-010"),         # a ProShows, sem separador nenhum
    ("Rua 12, 1640", ""),                  # número de porta não é CEP
    ("", ""),
])
def test_cep(texto, esperado):
    assert _cep(texto) == esperado


# --------------------------------------------------------------- telefones
@pytest.mark.parametrize("texto,esperado", [
    ("(19) 3579-4520 / 3579-4780", "1935794520"),          # o 2º não tem DDD
    ("(11) 3232-6188 / (11) 99338-4934", "1132326188|11993384934"),
    ("Tel:(11) 97102-1351", "11971021351"),
    ("(82) 3326-5102 / 3034-0081", "8233265102"),
    ("sem telefone", ""),
])
def test_telefones(texto, esperado):
    assert _telefones(texto) == esperado


def test_telefone_repetido_entra_uma_vez():
    assert _telefones("(11) 3232-6188 e (11) 3232-6188") == "1132326188"


# ---------------------------------------------------------------- endereço
def test_limpar_endereco_tira_telefone_grudado():
    """A Roland publica 'Rua X, 351 - Bairro (75) 3223-7885' numa linha só; sem
    limpar, o telefone apareceria como parte do logradouro."""
    assert _limpar_endereco("Rua Cristóvão Barreto, 351 - Serraria (75) 3223-7885") \
        == "Rua Cristóvão Barreto, 351 - Serraria"


def test_limpar_endereco_tira_cep_repetido():
    assert _limpar_endereco("RUA GUEDES, 278 - CENTRO - CEP: 57.020-260") \
        == "RUA GUEDES, 278 - CENTRO"


def test_limpar_endereco_preserva_numero_da_porta():
    assert _limpar_endereco("Av. Brasil, 1640 - Bonfiglioli") \
        == "Av. Brasil, 1640 - Bonfiglioli"


# --------------------------------------------------------------------- UF
@pytest.mark.parametrize("texto,esperado", [
    ("São Paulo", "SP"), ("Sao Paulo", "SP"), ("SP", "SP"),
    ("Paraiba", "PB"), ("Espírito Santo", "ES"), ("Nárnia", ""),
])
def test_uf_de(texto, esperado):
    assert uf_de(texto) == esperado


def test_uf_do_endereco_le_a_sigla_no_fim():
    assert uf_do_endereco("RUA DO ALECRIM, 352 - CENTRO - SÃO LUIZ, MA") == "MA"
    assert uf_do_endereco("AVENIDA CHICO MENDES, 4068 - RIO BRANCO, AC") == "AC"
    assert uf_do_endereco("Rua sem estado, 10") == ""


def test_uf_do_ddd():
    assert uf_do_ddd("(47) 3435-1098") == "SC"
    assert uf_do_ddd("11987654321") == "SP"
    assert uf_do_ddd("(00) 1234-5678") == ""


# ------------------------------------------------------------------- HTML
def test_texto_de_transforma_br_em_quebra_e_nao_em_cola():
    assert texto_de("Rua A, 1<br />Centro").split("\n") == ["Rua A, 1", "Centro"]


def test_email_da_cloudflare_e_decodificado():
    """A Tagima esconde o e-mail em data-cfemail (XOR com o 1º byte). É
    anti-spam de HTML, não controle de acesso: o e-mail está publicado."""
    assert _cf_email("3e545b5f5049514450575f55490f0d0b7e59535f5752105d5153") \
        == "jeanwozniakw135@gmail.com"


def test_emails_ignora_cdn_cgi_e_pega_o_endereco_real():
    bloco = ('<p>Email: <a href="/cdn-cgi/l/email-protection" '
             'data-cfemail="2a444f464943474b5804465f5e42434f6a42455e474b434604494547">'
             '[email&#160;protected]</a></p>')
    assert _emails(bloco) == "nelcimar.luthie@hotmail.com"


# ------------------------------------------------- casamento com o município
@pytest.fixture(scope="module")
def con():
    """Banco em memória com as macros, um município falso por caso e o SQL de
    casamento recortado de sql/47_marcas.sql — o mesmo texto, não uma cópia."""
    c = duckdb.connect(":memory:")
    for stmt in dividir_sql((RAIZ / "sql" / "20_macros.sql").read_text(encoding="utf-8")):
        c.execute(stmt)
    c.execute("""
        CREATE TABLE municipios (uf VARCHAR, municipio_slug VARCHAR,
                                 municipio VARCHAR, ibge VARCHAR);
        INSERT INTO municipios VALUES
            ('SP','sao-paulo','São Paulo','3550308'),
            ('SP','jau','Jaú','3525300'),
            ('SP','ipero','Iperó','3520806'),
            ('SP','campinas','Campinas','3509502'),
            ('AL','maceio','Maceió','2704302'),
            ('BA','alagoinhas','Alagoinhas','2900702'),
            ('DF','brasilia','Brasília','5300108'),
            ('PR','marechal-candido-rondon','Marechal Cândido Rondon','4114302');
    """)
    return c


def _casar(con, linhas):
    """Roda o trecho de casamento de 47_marcas.sql sobre as linhas dadas."""
    con.execute("""CREATE OR REPLACE TABLE marca_posto_bruto
                   (posto_id VARCHAR, uf_fonte VARCHAR, cidade_fonte VARCHAR,
                    endereco VARCHAR)""")
    con.executemany("INSERT INTO marca_posto_bruto VALUES (?, ?, ?, ?)", linhas)
    texto = (RAIZ / "sql" / "47_marcas.sql").read_text(encoding="utf-8")
    inicio = texto.index("CREATE OR REPLACE VIEW municipio_alvo")
    fim = texto.index("-- O que sobrou sem município")
    for stmt in dividir_sql(texto[inicio:fim]):
        con.execute(stmt)
    return dict(con.execute("SELECT posto_id, municipio_slug "
                            "FROM marca_posto_municipio").fetchall())


def test_cidade_publicada_pela_fonte_casa_mesmo_sem_acento(con):
    r = _casar(con, [("a", "AL", "MACEIO", "Rua X"),
                     ("b", "AL", "Macéio", "Rua Y")])   # erro de digitação real
    assert r == {"a": "maceio", "b": "maceio"}


def test_cidade_sai_do_endereco_quando_a_fonte_nao_publica(con):
    r = _casar(con, [("a", "PR", "", "RUA INDEPENDENCIA, 1633 - CENTRO - "
                                     "MARECHAL CANDIDO RONDON - PR")])
    assert r == {"a": "marechal-candido-rondon"}


def test_nome_curto_so_casa_no_fim_do_endereco(con):
    """'Jaú' tem três letras. No fim do endereço é a cidade; no meio de um nome
    de rua, seria falso positivo — e Iperó ficaria com oficina que não é dela."""
    r = _casar(con, [("fim", "SP", "", "RUA DOUTOR ÍTALO PECCIOLI, 203 - JAÚ, SP"),
                     ("meio", "SP", "", "RUA JAU DE OLIVEIRA, 10 - CENTRO")])
    assert r == {"fim": "jau"}


def test_vence_o_municipio_mais_a_direita(con):
    """'Rua São Paulo' em Campinas não pode virar São Paulo."""
    r = _casar(con, [("a", "SP", "", "RUA SAO PAULO, 45 - CENTRO - CAMPINAS, SP")])
    assert r == {"a": "campinas"}


def test_distrito_federal_cai_em_brasilia(con):
    """Taguatinga é região administrativa, não município: o IBGE só tem
    Brasília no DF, e o endereço é de Brasília."""
    r = _casar(con, [("a", "DF", "Taguatinga Norte", "QND 27, Lote 5")])
    assert r == {"a": "brasilia"}


def test_cidade_que_nao_existe_nao_e_chutada(con):
    """'Alagoinha' (sem s) não é Alagoinhas. Sem casamento, a oficina fica na
    página do estado — nunca numa cidade adivinhada."""
    r = _casar(con, [("a", "BA", "Alagoinha", "Rua Santos Antonio, 04")])
    assert r == {}
