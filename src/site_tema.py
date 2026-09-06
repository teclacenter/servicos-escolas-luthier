"""Tema do site: CSS e logotipo. Separado do gerador para ficar fácil de trocar.

Decisões de desempenho, que são o pedido central:
  * Zero JavaScript nas páginas de conteúdo. Nada para baixar, parsear, executar.
  * Zero webfont. Pilha de fontes do sistema, que já está na máquina do visitante.
  * Zero imagem externa. O logotipo é SVG inline, então não gera requisição.
  * Um único CSS, com hash no nome do arquivo, servido com cache imutável.
Resultado: a página é HTML + um CSS cacheado para sempre. Nada a processar no
servidor, e um CDN pode servir tudo da borda.
"""
import hashlib

from config import PALETA, SITE_NOME


def css() -> str:
    c = PALETA
    return f""":root{{
  --vermelho:{c['vermelho']};--vermelho-escuro:{c['vermelho_escuro']};
  --texto:{c['texto']};--texto-suave:{c['texto_suave']};--cinza:{c['cinza']};
  --barra:{c['barra']};--borda:{c['borda']};--fundo:{c['fundo']};--fundo-suave:{c['fundo_suave']};
  --topo:{c['topo']};
  --largura:1180px;
}}
*,*::before,*::after{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--fundo);color:var(--texto);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}}
a{{color:var(--vermelho);text-decoration:none}}
a:hover{{color:var(--vermelho-escuro);text-decoration:underline}}
.env{{max-width:var(--largura);margin:0 auto;padding:0 20px}}

/* topo — faixa escura porque o logotipo enviado é a variante clara */
.topo{{background:var(--topo)}}
.topo .env{{display:flex;align-items:center;gap:24px;min-height:74px;flex-wrap:wrap}}
.marca{{display:block;flex:0 0 auto}}
.marca svg,.marca img{{display:block;height:44px;width:auto}}
.nav{{background:var(--barra);border-bottom:1px solid var(--borda)}}
.nav ul{{max-width:var(--largura);margin:0 auto;padding:0 20px;list-style:none;
  display:flex;gap:4px;flex-wrap:wrap}}
.nav a{{display:block;padding:11px 14px;color:var(--texto);font-size:14.5px;font-weight:500}}
.nav a:hover{{color:var(--vermelho);text-decoration:none}}
.nav a[aria-current]{{color:var(--vermelho);box-shadow:inset 0 -3px 0 var(--vermelho)}}

/* trilha e cabeçalho */
.trilha{{font-size:13px;color:var(--texto-suave);padding:16px 0 0}}
.trilha ol{{list-style:none;margin:0;padding:0;display:flex;gap:7px;flex-wrap:wrap}}
.trilha li+li::before{{content:"›";margin-right:7px;color:var(--cinza)}}
h1{{font-size:clamp(22px,3.2vw,31px);line-height:1.2;margin:14px 0 6px;font-weight:650}}
h2{{font-size:19px;margin:34px 0 12px;font-weight:600}}
.resumo{{color:var(--texto-suave);margin:0 0 4px;max-width:62em}}
.fonte{{font-size:13px;color:var(--cinza);margin:10px 0 26px}}

/* grade de fichas */
.fichas{{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));
  margin:0 0 30px;padding:0;list-style:none}}
.ficha{{border:1px solid var(--borda);border-radius:6px;padding:15px 17px;background:var(--fundo)}}
.ficha:hover{{border-color:var(--cinza)}}
.ficha h3{{margin:0;font-size:16.5px;font-weight:650;line-height:1.3}}
.ficha .razao{{margin:3px 0 0;font-size:12.5px;color:var(--texto-suave);line-height:1.4}}
.ficha address{{font-style:normal;margin:10px 0 0;font-size:14px;line-height:1.5}}
.ficha .contato{{margin:10px 0 0;font-size:14px;display:flex;flex-direction:column;gap:2px}}
.ficha .contato .rot{{color:var(--texto-suave)}}
.ficha .cnpj{{margin:10px 0 0;font-size:11.5px;color:var(--cinza);letter-spacing:.02em}}
.ficha .selo{{margin:9px 0 0;padding:5px 8px;border-radius:4px;
  background:var(--barra);color:var(--texto-suave);font-size:11.5px;line-height:1.35}}

/* listas de navegação por lugar */
.lugares{{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
  list-style:none;margin:0 0 30px;padding:0}}
.lugares a{{display:flex;justify-content:space-between;gap:10px;align-items:baseline;
  padding:9px 12px;border:1px solid var(--borda);border-radius:5px;color:var(--texto)}}
.lugares a:hover{{border-color:var(--vermelho);color:var(--vermelho);text-decoration:none}}
.lugares .n{{color:var(--cinza);font-size:13px;font-variant-numeric:tabular-nums}}
/* índice A-Z das marcas: o nome em cima, quem credencia embaixo */
.lugares.az a{{align-items:center}}
.lugares small{{display:block;color:var(--cinza);font-size:11.5px;font-weight:400;
  margin-top:1px}}

/* cartões das verticais na home */
.verticais{{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));
  list-style:none;margin:0 0 34px;padding:0}}
.verticais a{{display:block;height:100%;padding:20px;border:1px solid var(--borda);
  border-radius:7px;color:var(--texto)}}
.verticais a:hover{{border-color:var(--vermelho);text-decoration:none}}
.verticais strong{{display:block;font-size:18px;color:var(--vermelho);margin-bottom:5px}}
.verticais span{{font-size:13.5px;color:var(--texto-suave)}}

/* botão de chamada (hub de marcas) */
.botao{{display:inline-block;padding:10px 18px;border-radius:5px;font-weight:600;
  background:var(--vermelho);color:#fff;font-size:14.5px}}
.botao:hover{{background:var(--vermelho-escuro);color:#fff;text-decoration:none}}

/* paginação */
.paginas{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:0 0 34px;
  padding-top:20px;border-top:1px solid var(--borda);font-size:14px}}
.paginas a,.paginas strong{{padding:7px 12px;border:1px solid var(--borda);border-radius:5px}}
.paginas strong{{background:var(--vermelho);border-color:var(--vermelho);color:#fff}}
.paginas .salto{{padding:7px 4px;color:var(--cinza)}}

/* rodapé */
.rodape{{margin-top:44px;border-top:1px solid var(--borda);background:var(--fundo-suave);
  padding:26px 0 34px;font-size:13px;color:var(--texto-suave)}}
.rodape p{{margin:0 0 8px;max-width:70em}}
@media (prefers-color-scheme:dark){{
  /* Sem tema escuro por ora: o site da loja é claro e a marca depende do branco. */
}}
"""


def logo_svg(titulo: str = SITE_NOME) -> str:
    """Logotipo em SVG inline.

    AVISO: é uma RECONSTRUÇÃO a partir da captura de tela, não o arquivo oficial.
    Para usar o original, salve-o em site/estatico/logo.svg e o gerador passa a
    referenciá-lo (ver src/site.py, funcao _marca).
    """
    v, t, g = PALETA["vermelho"], PALETA["texto"], PALETA["cinza"]
    return (
        f'<svg viewBox="0 0 372 74" role="img" aria-label="{titulo}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        # monograma: moldura vermelha aberta à esquerda + T e E
        f'<path d="M62 3H10a7 7 0 0 0-7 7v54a7 7 0 0 0 7 7h52" fill="none" '
        f'stroke="{v}" stroke-width="5"/>'
        f'<rect x="17" y="14" width="40" height="5" fill="{v}"/>'
        f'<rect x="34" y="14" width="5" height="46" fill="{v}"/>'
        f'<rect x="45" y="28" width="24" height="5" fill="{g}"/>'
        f'<rect x="45" y="40" width="24" height="5" fill="{g}"/>'
        f'<rect x="45" y="52" width="24" height="5" fill="{g}"/>'
        # wordmark
        f'<text x="86" y="46" font-family="-apple-system,Segoe UI,Roboto,Arial,sans-serif" '
        f'font-size="40" font-weight="700" fill="{t}">Tecla</text>'
        f'<text x="188" y="46" font-family="-apple-system,Segoe UI,Roboto,Arial,sans-serif" '
        f'font-size="40" font-weight="300" fill="{g}">center</text>'
        f'<text x="88" y="65" font-family="-apple-system,Segoe UI,Roboto,Arial,sans-serif" '
        f'font-size="13" font-weight="500" letter-spacing="6.6" fill="{v}">SERVIÇOS</text>'
        f"</svg>"
    )


def css_com_hash() -> tuple[str, str]:
    """Devolve (nome_do_arquivo, conteudo). Hash no nome = cache imutável."""
    texto = css()
    h = hashlib.sha256(texto.encode()).hexdigest()[:10]
    return f"tc.{h}.css", texto


def png_para_ico(png: bytes) -> bytes:
    """Empacota um PNG dentro de um contêiner ICO.

    O navegador pede /favicon.ico sozinho, mesmo havendo <link rel="icon">.
    Sem esse arquivo, todo primeiro acesso gera um 404 no log e uma requisição
    perdida. O formato ICO aceita PNG como carga desde o Windows Vista, então
    não há reamostragem nem perda: são 22 bytes de cabeçalho na frente do PNG
    original. Sem Pillow, sem dependência nova.
    """
    import struct
    largura, altura = struct.unpack(">II", png[16:24])
    # No ICO, 256 é gravado como 0. Acima disso o formato não comporta.
    if not (0 < largura <= 256 and 0 < altura <= 256):
        raise ValueError(f"ICO aceita até 256x256; recebi {largura}x{altura}")
    cabecalho = struct.pack("<HHH", 0, 1, 1)          # reservado, tipo=ícone, 1 imagem
    entrada = struct.pack(
        "<BBBBHHII",
        largura % 256, altura % 256,                  # 256 -> 0
        0, 0,                                         # paleta, reservado
        1, 32,                                        # planos, bits por pixel
        len(png), 22,                                 # tamanho e deslocamento da carga
    )
    return cabecalho + entrada + png
