#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# init-letsencrypt.sh
# Emite o certificado Let's Encrypt via DNS-01 challenge (Cloudflare API).
# Não requer porta 80/443 acessível externamente.
#
# Pré-requisito:
#   - Arquivo cloudflare.ini criado com seu API Token do Cloudflare
#   - Execute: ./init-letsencrypt.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

# ── Configurações ─────────────────────────────────────────────────────────────
DOMAINS=("clipbuilder.com.br" "www.clipbuilder.com.br")
EMAIL="admin@clipbuilder.com.br"   # Altere para seu e-mail
STAGING=0                          # 1 = modo teste (sem limite de requisições)
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN="${DOMAINS[0]}"
CERT_PATH="/etc/letsencrypt/live/$DOMAIN"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ClipBuilder — Inicialização Let's Encrypt (DNS-01 / Cloudflare)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Verifica se cloudflare.ini existe
if [ ! -f "./cloudflare.ini" ]; then
  echo ""
  echo "❌ Arquivo cloudflare.ini não encontrado!"
  echo ""
  echo "   Crie o arquivo com:"
  echo '   echo "dns_cloudflare_api_token = SEU_TOKEN_AQUI" > cloudflare.ini'
  echo "   chmod 600 cloudflare.ini"
  echo ""
  exit 1
fi

# Garante permissão correta no arquivo de credenciais
chmod 600 ./cloudflare.ini

# 1) Verifica se certificado real já existe
if docker compose run --rm --entrypoint sh certbot \
    -c "[ -f '$CERT_PATH/fullchain.pem' ]" 2>/dev/null; then
  echo "✅ Certificado já existe em $CERT_PATH. Nada a fazer."
  exit 0
fi

# 2) Limpa qualquer lixo anterior no diretório live para evitar conflitos no certbot
echo ""
echo "▶ Limpando tentativas anteriores..."
docker compose run --rm --entrypoint sh certbot -c "rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN" || true

# 3) Emite o certificado real via DNS-01 (Cloudflare)
echo ""
STAGING_ARG=""
if [ "$STAGING" -eq 1 ]; then
  STAGING_ARG="--staging"
  echo "⚠  Modo STAGING ativo — certificado NÃO será reconhecido pelos browsers."
fi

DOMAIN_ARGS=""
for d in "${DOMAINS[@]}"; do
  DOMAIN_ARGS="$DOMAIN_ARGS -d $d"
done

echo "▶ Solicitando certificado para: ${DOMAINS[*]}"
echo "   (via DNS-01 — pode levar ~30s para propagar o registro TXT)"
docker compose run --rm --entrypoint certbot certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /etc/cloudflare/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 30 \
  $STAGING_ARG \
  --email "$EMAIL" \
  $DOMAIN_ARGS \
  --rsa-key-size 4096 \
  --agree-tos \
  --no-eff-email \
  --non-interactive

# 4) Sobe todos os serviços (incluindo o frontend com o certificado real)
echo ""
echo "▶ Subindo todos os serviços..."
docker compose up -d

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ✅ HTTPS configurado com sucesso!"
echo ""
echo "   Próximos passos no Cloudflare:"
echo "   1. Reative o proxy (nuvem laranja) — se estava desativado"
echo "   2. SSL/TLS → mude para 'Full (Strict)'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

