"""Testa as macros SQL de normalização chamando o próprio DuckDB.
Uma implementação só: se a macro mudar, o teste acompanha."""
import sys
from pathlib import Path

import duckdb
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from db import dividir_sql  # noqa: E402  mesmo parser usado na carga


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    for stmt in dividir_sql((RAIZ / "sql" / "20_macros.sql").read_text(encoding="utf-8")):
        c.execute(stmt)
    return c


def um(con, expr, *args):
    return con.execute(f"SELECT {expr}", list(args)).fetchone()[0]


# ---------------------------------------------------------------- telefone
@pytest.mark.parametrize("ddd,num,esperado", [
    ("11", "988887777", "+5511988887777"),   # celular 9 dígitos
    ("85", "88717829",  "+558588717829"),    # fixo 8 dígitos (linha real da base)
    (" 11 ", "98888-7777", "+5511988887777"),# ruído de formatação
    ("11", "9999",      None),               # curto demais
    ("20", "988887777", None),               # DDD inexistente
    ("00", "988887777", None),
    ("11", "999999999", None),               # todos os dígitos iguais
    ("11", "00000000",  None),
    ("",   "988887777", None),
    ("11", "",          None),
    (None, None,        None),
])
def test_telefone_e164(con, ddd, num, esperado):
    assert um(con, "telefone_e164(?, ?)", ddd, num) == esperado


# -------------------------------------------------------------------- slug
@pytest.mark.parametrize("nome,esperado", [
    ("São Bernardo do Campo", "sao-bernardo-do-campo"),
    ("SAO BERNARDO DO CAMPO", "sao-bernardo-do-campo"),  # RFB grava em maiúsculas
    ("Açu",                   "acu"),
    ("Mogi-Mirim",            "mogi-mirim"),
    ("Espigão D'Oeste",       "espigao-d-oeste"),
    ("Santa Bárbara d`Oeste", "santa-barbara-d-oeste"),
    ("  Belém  ",             "belem"),
    ("SEM IDENTIFICACAO",     "sem-identificacao"),
    ("",                      None),
    (None,                    None),
])
def test_slug(con, nome, esperado):
    assert um(con, "slug(?)", nome) == esperado


# ----------------------------------------------------------------- domínio
@pytest.mark.parametrize("email,esperado", [
    ("MARCELA_SHADY@HOTMAIL.COM",      "hotmail.com"),
    ("contato@luthieria-silva.com.br", "luthieria-silva.com.br"),
    (" Fulano@Escola.MUS.BR ",         "escola.mus.br"),
    ("sem-arroba.com",                 None),
    ("fulano@localhost",               None),   # sem TLD
    ("fulano@",                        None),
    ("",                               None),
    (None,                             None),
])
def test_dominio_email(con, email, esperado):
    assert um(con, "dominio_email(?)", email) == esperado


@pytest.mark.parametrize("dominio,provedor", [
    ("gmail.com",              True),
    ("hotmail.com.br",         True),
    ("yahoo.com.br",           True),
    ("uol.com.br",             True),
    ("icloud.com",             True),
    ("protonmail.com",         True),
    ("zipmail.com.br",         True),
    ("luthieria-silva.com.br", False),
    ("escolademusica.mus.br",  False),
    ("gmail.com.mx",           True),
    (None,                     True),   # sem e-mail => sem site candidato
])
def test_dominio_provedor(con, dominio, provedor):
    assert um(con, "dominio_provedor(?)", dominio) is provedor


def test_site_candidato_so_para_dominio_proprio(con):
    """Regra da fase 2: provedor gratuito nunca virá site candidato."""
    q = """
    SELECT dominio_provedor(dominio_email(e)) AS prov,
           CASE WHEN NOT dominio_provedor(dominio_email(e))
                THEN 'https://' || dominio_email(e) END AS site
    FROM (VALUES (?), (?)) AS t(e)
    """
    r = con.execute(q, ["a@gmail.com", "a@luthier.com.br"]).fetchall()
    assert (True, None) in r
    assert (False, "https://luthier.com.br") in r


# ------------------------------------------------- apresentação para publicação
@pytest.mark.parametrize("e164,esperado", [
    ("+557336135835", "fixo"),    # local começa em 3
    ("+551122334455", "fixo"),
    ("+557388717829", "movel"),   # local começa em 8
    ("+557398765432", "movel"),
    ("+557366554433", "movel"),
    ("+5573988717829", "movel"),  # 9 dígitos: só móvel tem; vem das redes
                                  # autorizadas, não da Receita
    (None,            None),
])
def test_tipo_telefone(con, e164, esperado):
    assert um(con, "tipo_telefone(?)", e164) == esperado


@pytest.mark.parametrize("e164,esperado", [
    ("+557388717829", "+5573988717829"),   # móvel ganha o 9
    ("+557336135835", None),               # fixo não ganha nada
    (None,            None),
])
def test_telefone_com_nono_digito(con, e164, esperado):
    assert um(con, "telefone_com_nono_digito(?)", e164) == esperado


@pytest.mark.parametrize("e164,esperado", [
    ("+557336135835",  "(73) 3613-5835"),
    ("+5573988717829", "(73) 98871-7829"),
    (None,             None),
])
def test_telefone_exibicao(con, e164, esperado):
    assert um(con, "telefone_exibicao(?)", e164) == esperado


def test_linha_telefone_movel_traz_os_dois_formatos(con):
    """O móvel sai com o 9 (que disca hoje) e com o original ao lado."""
    assert um(con, "linha_telefone(?)", "+557388717829") == \
        "Cel: (73) 98871-7829 ou (73) 8871-7829"


def test_linha_telefone_fixo_sai_simples(con):
    assert um(con, "linha_telefone(?)", "+557336135835") == "Tel: (73) 3613-5835"


def test_linha_telefone_movel_ja_com_nove_sai_uma_vez(con):
    """Número das redes autorizadas já vem com o 9: não há 'original' ao lado."""
    assert um(con, "linha_telefone(?)", "+5573988717829") == "Cel: (73) 98871-7829"


@pytest.mark.parametrize("cep,esperado", [
    ("45607123", "45607-123"),
    ("45607-123", "45607-123"),
    ("456071", None),
    ("", None),
    (None, None),
])
def test_cep_formatado(con, cep, esperado):
    assert um(con, "cep_formatado(?)", cep) == esperado


@pytest.mark.parametrize("bruto,esperado", [
    ("AVENIDA PRINCESA ISABEL", "Avenida Princesa Isabel"),
    ("NOSSA SENHORA DA CONCEICAO", "Nossa Senhora da Conceicao"),
    ("SAO CAETANO", "Sao Caetano"),        # não inventa acento
    ("  centro  ", "Centro"),
    ("", None),
    (None, None),
])
def test_titulo_caso(con, bruto, esperado):
    assert um(con, "titulo_caso(?)", bruto) == esperado


@pytest.mark.parametrize("tipo,nome,esperado", [
    ("RUA", "RUA 12", "RUA 12"),                    # não repete o tipo
    ("RUA", "MANOEL LUIZ", "RUA MANOEL LUIZ"),
    ("RUA", "RUA", "RUA"),
    ("", "SEM TIPO", "SEM TIPO"),
    ("RUA", "", "RUA"),
    (None, None, None),
])
def test_logradouro_completo(con, tipo, nome, esperado):
    assert um(con, "logradouro_completo(?, ?)", tipo, nome) == esperado


@pytest.mark.parametrize("bruto,esperado", [
    ("Avenida Princesa Isabel", "Av. Princesa Isabel"),
    ("Rua Aurora", "R. Aurora"),
    ("Travessa Leblon", "Tv. Leblon"),
    ("Rodovia BR-101", "Rod. BR-101"),
    ("Beco do Sapo", "Beco do Sapo"),   # tipo sem abreviação: passa intacto
    (None, None),
])
def test_abreviar_logradouro(con, bruto, esperado):
    assert um(con, "abreviar_logradouro(?)", bruto) == esperado


@pytest.mark.parametrize("bruto,esperado", [
    # CPF colado no fim da razão social de MEI: nunca vai para página pública
    ("THALITA CRISTINA GONCALVES 11916547613", "THALITA CRISTINA GONCALVES"),
    # base do CNPJ colada no início: redundante, já temos coluna de CNPJ
    ("46.696.520 RODRIGO XAVIER MONTEIRO", "RODRIGO XAVIER MONTEIRO"),
    # nomes legítimos com dígitos não podem ser mutilados
    ("3M DO BRASIL LTDA", "3M DO BRASIL LTDA"),
    ("ESCOLA 2001 LTDA", "ESCOLA 2001 LTDA"),
    ("SINAL ELETRONICA COMERCIO VAREJISTA LTDA",
     "SINAL ELETRONICA COMERCIO VAREJISTA LTDA"),
    ("46.696.520 ", None),
    ("", None),
    (None, None),
])
def test_nome_publicavel(con, bruto, esperado):
    assert um(con, "nome_publicavel(?)", bruto) == esperado


def test_nome_publicavel_nao_deixa_cpf_passar(con):
    """Trava explícita: nenhuma sequência de 11 dígitos sobrevive no fim."""
    q = ("SELECT count(*) FROM (VALUES (?),(?),(?)) t(x) "
         "WHERE regexp_matches(nome_publicavel(x), '[0-9]{11}$')")
    n = con.execute(q, ["A 11916547613", "B  07433822852", "C 63254581334"]).fetchone()[0]
    assert n == 0


@pytest.mark.parametrize("bruto,esperado", [
    ("43207072570", None),                       # CPF nu jamais vira título
    ("0630", None),                              # nome só numérico não é nome
    ("SINAL ELETRONICA", "SINAL ELETRONICA"),
    ("THALITA GONCALVES 11916547613", "THALITA GONCALVES"),
    ("3M", "3M"),                                # nome curto legítimo sobrevive
    ("", None),
    (None, None),
])
def test_texto_nome(con, bruto, esperado):
    assert um(con, "texto_nome(?)", bruto) == esperado
