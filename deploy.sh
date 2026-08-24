#!/usr/bin/env bash
# Publica site/ em produção. Idempotente: pode rodar quantas vezes quiser.
#
# Autenticação: chave SSH. Sem senha em arquivo, sem senha em variável.
# Configuração: copie deploy.env.exemplo para deploy.env e ajuste. deploy.env
# está no .gitignore de propósito — endereço de servidor não vai para o git.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$RAIZ/deploy.env" ] && . "$RAIZ/deploy.env"

: "${DEPLOY_HOST:?defina DEPLOY_HOST (veja deploy.env.exemplo)}"
: "${DEPLOY_USER:?defina DEPLOY_USER}"
: "${DEPLOY_PATH:?defina DEPLOY_PATH}"
DEPLOY_URL="${DEPLOY_URL:-}"

SITE="$RAIZ/site"
[ -d "$SITE/estatico" ] || { echo "ERRO: rode 'make site' primeiro." >&2; exit 1; }

n_arq=$(find "$SITE" -type f | wc -l | tr -d ' ')
echo "==> empacotando $n_arq arquivos de site/"

# COPYFILE_DISABLE=1 é obrigatório no macOS: sem isso o tar injeta um arquivo
# AppleDouble '._nome' para CADA arquivo e diretório, o que aqui triplicaria a
# contagem (29.843 -> 89.523) e despejaria lixo binário no docroot público.
TAR="$(mktemp -t site-servicos).tar.gz"
trap 'rm -f "$TAR"' EXIT
COPYFILE_DISABLE=1 tar --exclude '.DS_Store' --exclude '._*' \
    -czf "$TAR" -C "$SITE" .
echo "==> $(du -h "$TAR" | cut -f1) comprimido"

echo "==> enviando para $DEPLOY_USER@$DEPLOY_HOST"
scp -q -o StrictHostKeyChecking=accept-new "$TAR" \
    "$DEPLOY_USER@$DEPLOY_HOST:/tmp/site-servicos.tar.gz"

echo "==> trocando o conteúdo do docroot"
# Extrai em diretório novo e troca por rename: o site nunca fica meio publicado.
# .well-known é preservado porque é onde o cPanel valida o certificado SSL.
ssh -o StrictHostKeyChecking=accept-new "$DEPLOY_USER@$DEPLOY_HOST" \
    "DEPLOY_PATH='$DEPLOY_PATH' bash -s" <<'REMOTO'
set -euo pipefail
novo="${DEPLOY_PATH%/}.novo.$$"
antigo="${DEPLOY_PATH%/}.antigo.$$"
rm -rf "$novo"; mkdir -p "$novo"
tar -xzf /tmp/site-servicos.tar.gz -C "$novo"
find "$novo" -name '._*' -delete 2>/dev/null || true
find "$novo" -name '.DS_Store' -delete 2>/dev/null || true
find "$novo" -type d -exec chmod 755 {} +
find "$novo" -type f -exec chmod 644 {} +
if [ -d "${DEPLOY_PATH%/}/.well-known" ]; then
  cp -a "${DEPLOY_PATH%/}/.well-known" "$novo/" 2>/dev/null || true
fi
if [ -d "${DEPLOY_PATH%/}" ]; then mv "${DEPLOY_PATH%/}" "$antigo"; fi
mv "$novo" "${DEPLOY_PATH%/}"
rm -rf "$antigo" /tmp/site-servicos.tar.gz
echo "    arquivos publicados: $(find "${DEPLOY_PATH%/}" -type f | wc -l)"
echo "    tamanho: $(du -sh "${DEPLOY_PATH%/}" | cut -f1)"
REMOTO

if [ -n "$DEPLOY_URL" ]; then
  echo "==> verificando"
  UA='Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
  for u in / /robots.txt /sitemap.xml /luthier/; do
    printf '    %-16s ' "$u"
    curl -sS -o /dev/null -m 30 -A "$UA" -w '%{http_code}\n' "$DEPLOY_URL$u"
  done
fi
echo "==> pronto"
