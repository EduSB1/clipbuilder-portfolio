#!/bin/bash
# =============================================================================
# ClipBuilder — Diagnóstico de acesso ao painel Admin
# Uso: bash diagnose_admin.sh [email]
#
# Verifica todos os pontos de falha no fluxo de autenticação admin:
#   1. Containers rodando
#   2. Backend respondendo
#   3. Variáveis de ambiente críticas
#   4. Usuário no banco de dados
#   5. Clerk JWT (issuer, JWKS)
#   6. Nginx proxy
# =============================================================================

set -euo pipefail

EMAIL="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

OK="${GREEN}[OK]${RESET}"
FAIL="${RED}[FAIL]${RESET}"
WARN="${YELLOW}[WARN]${RESET}"
INFO="${CYAN}[INFO]${RESET}"

SEP="${BLUE}────────────────────────────────────────────────────────────────${RESET}"

pass=0
fail=0
warn=0

ok()   { echo -e "  $OK   $1";   ((pass++)) || true; }
fail() { echo -e "  $FAIL $1";   ((fail++)) || true; }
warn() { echo -e "  $WARN $1";   ((warn++)) || true; }
info() { echo -e "  $INFO $1"; }

section() {
  echo ""
  echo -e "$SEP"
  echo -e "  ${BOLD}${CYAN}$1${RESET}"
  echo -e "$SEP"
}

# =============================================================================
# 0. Banner
# =============================================================================
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${BLUE}║       ClipBuilder — Admin Access Diagnostic                  ║${RESET}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Executando em: $(date)"
echo -e "  Diretório:     $SCRIPT_DIR"
if [ -n "$EMAIL" ]; then
  echo -e "  Usuário alvo:  ${BOLD}$EMAIL${RESET}"
else
  echo -e "  ${YELLOW}Dica: passe o email do admin como argumento para diagnóstico completo${RESET}"
  echo -e "  ${YELLOW}Exemplo: bash diagnose_admin.sh seu@email.com${RESET}"
fi

# =============================================================================
# 1. Docker / Containers
# =============================================================================
section "1. Status dos Containers Docker"

if ! command -v docker &>/dev/null; then
  fail "Docker não encontrado no PATH"
else
  ok "Docker encontrado: $(docker --version 2>/dev/null | head -1)"

  cd "$SCRIPT_DIR"

  # backend
  BACKEND_STATUS=$(docker compose ps --format json 2>/dev/null | \
    python3 -c "
import sys, json
lines = sys.stdin.read().strip()
for line in lines.splitlines():
    try:
        d = json.loads(line)
        if 'backend' in d.get('Service','') or 'backend' in d.get('Name',''):
            print(d.get('State','unknown'))
            break
    except: pass
" 2>/dev/null || echo "")

  if [ -z "$BACKEND_STATUS" ]; then
    # fallback: usar docker compose ps texto
    BACKEND_LINE=$(docker compose ps 2>/dev/null | grep backend || echo "")
    if echo "$BACKEND_LINE" | grep -qi "up\|running"; then
      ok "Container backend: UP"
    elif [ -z "$BACKEND_LINE" ]; then
      fail "Container backend: NÃO ENCONTRADO (rode: docker compose up -d)"
    else
      fail "Container backend: $BACKEND_LINE"
    fi
  elif echo "$BACKEND_STATUS" | grep -qi "running"; then
    ok "Container backend: running"
  else
    fail "Container backend: $BACKEND_STATUS"
    info "Tente: docker compose up -d --build backend"
  fi

  # frontend
  FRONTEND_LINE=$(docker compose ps 2>/dev/null | grep frontend || echo "")
  if echo "$FRONTEND_LINE" | grep -qi "up\|running"; then
    ok "Container frontend: UP"
  elif [ -z "$FRONTEND_LINE" ]; then
    fail "Container frontend: NÃO ENCONTRADO"
  else
    fail "Container frontend: $FRONTEND_LINE"
  fi

  # db
  DB_LINE=$(docker compose ps 2>/dev/null | grep db || echo "")
  if echo "$DB_LINE" | grep -qi "up\|running\|healthy"; then
    ok "Container db: UP"
  elif [ -z "$DB_LINE" ]; then
    fail "Container db: NÃO ENCONTRADO"
  else
    fail "Container db: $DB_LINE"
  fi
fi

# =============================================================================
# 2. Backend Health Check
# =============================================================================
section "2. Backend Health Check"

BACKEND_HEALTH=""
# Tenta primeiro via porta direta (8000), depois via nginx (/api/health)
for URL in "http://localhost:8000/health" "http://localhost/api/health"; do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$URL" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    ok "Backend respondeu 200 em $URL"
    BACKEND_HEALTH="$URL"
    break
  else
    warn "Backend em $URL → HTTP $HTTP_CODE"
  fi
done

if [ -z "$BACKEND_HEALTH" ]; then
  fail "Backend não respondeu em nenhuma URL"
  info "Verifique os logs: docker compose logs --tail=50 backend"
else
  # Verifica resposta do health
  HEALTH_BODY=$(curl -s --connect-timeout 5 "$BACKEND_HEALTH" 2>/dev/null || echo "")
  if echo "$HEALTH_BODY" | grep -q '"ok"'; then
    ok "Resposta de health: $HEALTH_BODY"
  else
    warn "Resposta inesperada do health: $HEALTH_BODY"
  fi
fi

# =============================================================================
# 3. Variáveis de Ambiente no Container Backend
# =============================================================================
section "3. Variáveis de Ambiente Críticas (container backend)"

if ! docker compose ps 2>/dev/null | grep -qi "backend.*\(up\|running\)"; then
  warn "Container backend não está rodando — pulando verificação de env"
else
  check_env() {
    local VAR="$1"
    local LABEL="${2:-$VAR}"
    local VAL
    VAL=$(docker compose exec -T backend env 2>/dev/null | grep "^${VAR}=" | cut -d= -f2- || echo "")
    if [ -z "$VAL" ]; then
      fail "$LABEL: NÃO DEFINIDA ou vazia"
    elif [ ${#VAL} -lt 8 ]; then
      warn "$LABEL: definida mas muito curta (${#VAL} chars) — pode estar incorreta"
    else
      # Mostrar apenas primeiros/últimos chars para segurança
      PREVIEW="${VAL:0:6}...${VAL: -4}"
      ok "$LABEL: definida ($PREVIEW)"
    fi
  }

  check_env "CLERK_ISSUER"         "CLERK_ISSUER"
  check_env "CLERK_WEBHOOK_SECRET" "CLERK_WEBHOOK_SECRET (whsec_...)"
  check_env "DATABASE_URL"         "DATABASE_URL"

  # SECRET_KEY / LOCAL_JWT_SECRET
  LOCAL_JWT=$(docker compose exec -T backend env 2>/dev/null | grep "^LOCAL_JWT_SECRET=" | cut -d= -f2- || echo "")
  if [ -n "$LOCAL_JWT" ] && [ ${#LOCAL_JWT} -ge 8 ]; then
    ok "LOCAL_JWT_SECRET: definida (backdoor /sys habilitado)"
  else
    info "LOCAL_JWT_SECRET: não definida (backdoor /sys DESABILITADO)"
  fi

  # ALLOWED_ORIGINS
  ALLOWED=$(docker compose exec -T backend env 2>/dev/null | grep "^ALLOWED_ORIGINS=" | cut -d= -f2- || echo "")
  if [ -z "$ALLOWED" ]; then
    warn "ALLOWED_ORIGINS: não definida (usando padrão localhost — pode rejeitar tokens de produção)"
    info "Adicione em backend/.env: ALLOWED_ORIGINS=https://seudominio.com.br"
  else
    ok "ALLOWED_ORIGINS: $ALLOWED"
    # Verificar se inclui domínio de produção
    if echo "$ALLOWED" | grep -q "localhost"; then
      if ! echo "$ALLOWED" | grep -qE "https?://[a-z]"; then
        warn "ALLOWED_ORIGINS só tem localhost — adicione o domínio de produção"
      fi
    fi
  fi

  # CLERK_ISSUER formato
  CLERK_ISSUER_VAL=$(docker compose exec -T backend env 2>/dev/null | grep "^CLERK_ISSUER=" | cut -d= -f2- || echo "")
  if [ -n "$CLERK_ISSUER_VAL" ]; then
    if echo "$CLERK_ISSUER_VAL" | grep -q "clerk.accounts.dev"; then
      warn "CLERK_ISSUER aponta para instância de DESENVOLVIMENTO Clerk (.dev)"
      warn "  → Para produção, crie uma instância Production no Clerk Dashboard"
    elif echo "$CLERK_ISSUER_VAL" | grep -q "clerk.com"; then
      ok "CLERK_ISSUER parece ser instância de produção"
    fi
    info "CLERK_ISSUER = $CLERK_ISSUER_VAL"
  fi
fi

# =============================================================================
# 4. Banco de Dados — Usuário Admin
# =============================================================================
section "4. Banco de Dados — Verificação do Usuário"

DB_AVAILABLE=false
if docker compose exec -T db pg_isready -U clipbuilder &>/dev/null 2>&1; then
  ok "PostgreSQL: acessível"
  DB_AVAILABLE=true
else
  fail "PostgreSQL: não acessível via docker compose exec"
fi

if $DB_AVAILABLE; then
  # Listar todos os admins
  echo ""
  info "Usuários com role=admin no banco:"
  ADMINS=$(docker compose exec -T db psql -U clipbuilder -d clipbuilder -t -A -c \
    "SELECT email, role, is_active, deleted_at IS NOT NULL as deleted, clerk_id IS NOT NULL as has_clerk_id, clerk_id FROM users WHERE role='admin' ORDER BY created_at;" \
    2>/dev/null || echo "ERRO")

  if [ "$ADMINS" = "ERRO" ] || [ -z "$ADMINS" ]; then
    fail "Nenhum usuário admin encontrado no banco (ou tabela não existe)"
    info "Crie um admin: python3 promote_admin.py seu@email.com"
  else
    echo "$ADMINS" | while IFS='|' read -r email role active deleted has_clerk clerk_id; do
      [ -z "$email" ] && continue
      STATUS_ICON="✅"
      NOTES=""
      [ "$active" = "f" ] && STATUS_ICON="❌" && NOTES=" [DESATIVADO]"
      [ "$deleted" = "t" ] && STATUS_ICON="❌" && NOTES=" [DELETADO]"
      [ "$has_clerk" = "f" ] && NOTES="$NOTES [SEM clerk_id — não conseguirá logar via Clerk]"
      [ "$has_clerk" = "t" ] && NOTES="$NOTES [clerk_id: ${clerk_id:0:20}...]"
      echo -e "    $STATUS_ICON  ${BOLD}$email${RESET}  role=$role$NOTES"
    done
  fi

  # Verificar o email específico se fornecido
  if [ -n "$EMAIL" ]; then
    echo ""
    info "Detalhes do usuário: $EMAIL"
    USER_DETAIL=$(docker compose exec -T db psql -U clipbuilder -d clipbuilder -t -A -c \
      "SELECT id, email, role, is_active, deleted_at, clerk_id, full_name, created_at
       FROM users WHERE email = lower('$EMAIL');" \
      2>/dev/null || echo "ERRO")

    if [ -z "$USER_DETAIL" ] || [ "$USER_DETAIL" = "ERRO" ]; then
      fail "Usuário '$EMAIL' NÃO encontrado no banco"
      echo ""
      echo -e "  ${YELLOW}Para criar/promover este usuário como admin, execute:${RESET}"
      echo -e "  ${BOLD}  python3 $SCRIPT_DIR/promote_admin.py $EMAIL${RESET}"
    else
      echo "$USER_DETAIL" | while IFS='|' read -r id email role active deleted_at clerk_id full_name created_at; do
        [ -z "$id" ] && continue
        echo -e "    ID:         $id"
        echo -e "    Email:      $email"
        echo -e "    Role:       ${BOLD}$role${RESET}"
        echo -e "    Ativo:      $active"
        echo -e "    Deletado:   ${deleted_at:-não}"
        echo -e "    clerk_id:   ${clerk_id:-${RED}NÃO DEFINIDO${RESET}}"
        echo -e "    Nome:       ${full_name:-vazio}"
        echo -e "    Criado em:  $created_at"

        if [ "$role" != "admin" ]; then
          fail "Usuário '$email' tem role='$role' — NÃO É ADMIN"
          echo -e "  ${YELLOW}Para promover:${RESET} python3 $SCRIPT_DIR/promote_admin.py $EMAIL"
        else
          ok "Role = admin ✓"
        fi

        if [ "$active" = "f" ]; then
          fail "Usuário está DESATIVADO"
        else
          ok "Usuário ativo ✓"
        fi

        if [ -z "$clerk_id" ]; then
          fail "clerk_id está VAZIO — o usuário não está vinculado ao Clerk"
          info "Isso significa que ao logar via Clerk, um NOVO usuário será criado"
          info "Solução: O webhook user.created/updated precisa ter sido processado"
          info "  Ou vincule manualmente com:"
          info "  UPDATE users SET clerk_id='user_xxx' WHERE email='$EMAIL';"
        else
          ok "clerk_id definido ✓ ($clerk_id)"
        fi
      done
    fi

    # Verificar permissões
    echo ""
    info "Permissões do usuário '$EMAIL':"
    PERMS=$(docker compose exec -T db psql -U clipbuilder -d clipbuilder -t -A -c \
      "SELECT up.can_use_gemini, up.can_use_whisper, up.max_video_size_gb
       FROM user_permissions up
       JOIN users u ON u.id = up.user_id
       WHERE u.email = lower('$EMAIL');" \
      2>/dev/null || echo "")

    if [ -z "$PERMS" ]; then
      fail "Nenhuma permissão encontrada para '$EMAIL' — pode causar erros de acesso"
      info "Para criar permissões: python3 $SCRIPT_DIR/promote_admin.py $EMAIL"
    else
      echo "$PERMS" | while IFS='|' read -r gemini groq whisper max_gb; do
        [ -z "$gemini" ] && continue
        echo -e "    can_use_gemini:  $gemini"
        echo -e "    can_use_groq:    $groq"
        echo -e "    can_use_whisper: $whisper"
        echo -e "    max_video_gb:    $max_gb"
      done
    fi
  fi
fi

# =============================================================================
# 5. Clerk JWKS / Issuer Acessibilidade
# =============================================================================
section "5. Clerk JWKS — Acessibilidade do Endpoint"

CLERK_ISSUER_VAL=""
if [ -f "$SCRIPT_DIR/backend/.env" ]; then
  CLERK_ISSUER_VAL=$(grep "^CLERK_ISSUER=" "$SCRIPT_DIR/backend/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ' || echo "")
fi

# Tentar também pelo container
if [ -z "$CLERK_ISSUER_VAL" ] && docker compose ps 2>/dev/null | grep -qi "backend.*\(up\|running\)"; then
  CLERK_ISSUER_VAL=$(docker compose exec -T backend env 2>/dev/null | grep "^CLERK_ISSUER=" | cut -d= -f2- || echo "")
fi

if [ -z "$CLERK_ISSUER_VAL" ]; then
  fail "CLERK_ISSUER não encontrado — backend não conseguirá verificar tokens Clerk"
  info "Adicione em backend/.env: CLERK_ISSUER=https://xxx.clerk.accounts.dev"
else
  info "CLERK_ISSUER = $CLERK_ISSUER_VAL"

  # Testar JWKS endpoint
  JWKS_URL="${CLERK_ISSUER_VAL%/}/.well-known/jwks.json"
  info "Testando JWKS: $JWKS_URL"
  JWKS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "$JWKS_URL" 2>/dev/null || echo "000")
  if [ "$JWKS_CODE" = "200" ]; then
    ok "JWKS acessível: HTTP 200"
    # Verificar se tem chaves
    JWKS_BODY=$(curl -s --connect-timeout 10 "$JWKS_URL" 2>/dev/null || echo "")
    KEY_COUNT=$(echo "$JWKS_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('keys',[])))" 2>/dev/null || echo "?")
    if [ "$KEY_COUNT" = "0" ]; then
      fail "JWKS retornou 0 chaves — instância Clerk pode estar inativa ou mal configurada"
    else
      ok "JWKS contém $KEY_COUNT chave(s)"
    fi
  elif [ "$JWKS_CODE" = "000" ]; then
    fail "JWKS inacessível (timeout/sem conexão) — verifique conectividade com Clerk"
  else
    fail "JWKS retornou HTTP $JWKS_CODE — CLERK_ISSUER pode estar incorreto"
    info "JWKS URL testada: $JWKS_URL"
  fi
fi

# =============================================================================
# 6. Nginx — Rotas Proxy
# =============================================================================
section "6. Nginx — Verificação das Rotas Proxy"

NGINX_CONF="$SCRIPT_DIR/frontend/nginx.conf"
if [ ! -f "$NGINX_CONF" ]; then
  fail "nginx.conf não encontrado em $NGINX_CONF"
else
  ok "nginx.conf encontrado"

  # /api/
  if grep -q "location /api/" "$NGINX_CONF"; then
    ok "Proxy /api/ → backend: configurado"
  else
    fail "Proxy /api/ não encontrado no nginx.conf — backend inacessível pelo frontend"
  fi

  # /webhooks/
  if grep -q "location /webhooks/" "$NGINX_CONF"; then
    ok "Proxy /webhooks/ → backend: configurado"
  else
    fail "Proxy /webhooks/ não encontrado — webhooks Clerk não chegarão ao backend"
    info "Adicione em nginx.conf:"
    info '  location /webhooks/ {'
    info '    proxy_pass http://backend:8000;'
    info '  }'
  fi

  # Teste real via HTTP
  WEBHOOK_TEST=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost/webhooks/clerk \
    -H "Content-Type: application/json" \
    -d '{}' \
    --connect-timeout 5 2>/dev/null || echo "000")

  if [ "$WEBHOOK_TEST" = "400" ]; then
    ok "Rota /webhooks/clerk acessível via nginx (400 = chegou ao backend, assinatura inválida esperada)"
  elif [ "$WEBHOOK_TEST" = "000" ]; then
    warn "Nginx não respondeu (container frontend pode estar parado)"
  elif [ "$WEBHOOK_TEST" = "404" ]; then
    fail "Nginx retornou 404 para /webhooks/clerk — rota não está sendo proxied"
  else
    info "Nginx retornou HTTP $WEBHOOK_TEST para /webhooks/clerk"
  fi
fi

# =============================================================================
# 7. Teste do endpoint /auth/me via backdoor local (se disponível)
# =============================================================================
section "7. Teste do Endpoint /auth/me"

AUTH_ME_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/auth/me \
  --connect-timeout 5 2>/dev/null || echo "000")

if [ "$AUTH_ME_CODE" = "401" ] || [ "$AUTH_ME_CODE" = "422" ]; then
  ok "/auth/me acessível (HTTP $AUTH_ME_CODE — sem token, comportamento correto)"
elif [ "$AUTH_ME_CODE" = "200" ]; then
  warn "/auth/me retornou 200 sem token — endpoint pode estar sem proteção"
elif [ "$AUTH_ME_CODE" = "000" ]; then
  fail "/auth/me inacessível (backend pode estar parado)"
else
  info "/auth/me retornou HTTP $AUTH_ME_CODE"
fi

# Teste /admin/users (deve exigir admin)
ADMIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/admin/users \
  --connect-timeout 5 2>/dev/null || echo "000")

if [ "$ADMIN_CODE" = "401" ] || [ "$ADMIN_CODE" = "403" ] || [ "$ADMIN_CODE" = "422" ]; then
  ok "/admin/users protegido (HTTP $ADMIN_CODE — correto)"
elif [ "$ADMIN_CODE" = "200" ]; then
  fail "/admin/users retornou 200 sem token — ENDPOINT DESPROTEGIDO!"
elif [ "$ADMIN_CODE" = "000" ]; then
  warn "/admin/users inacessível (backend pode estar parado)"
else
  info "/admin/users retornou HTTP $ADMIN_CODE"
fi

# =============================================================================
# 8. Logs Recentes do Backend (últimas linhas relevantes)
# =============================================================================
section "8. Logs Recentes do Backend"

echo ""
info "Últimas 30 linhas do backend (filtradas por auth/clerk/admin/error):"
echo ""
docker compose logs --tail=80 backend 2>/dev/null | \
  grep -iE "(clerk|auth|admin|error|warning|jwt|webhook|401|403|500|issuer|azp)" | \
  tail -30 | \
  sed 's/^/    /' || echo "    (não foi possível obter logs)"

# =============================================================================
# Resumo Final
# =============================================================================
echo ""
echo -e "$SEP"
echo -e "  ${BOLD}Resumo do Diagnóstico${RESET}"
echo -e "$SEP"
echo ""
echo -e "  ${GREEN}Passou:  $pass${RESET}"
echo -e "  ${YELLOW}Avisos:  $warn${RESET}"
echo -e "  ${RED}Falhas:  $fail${RESET}"
echo ""

if [ $fail -eq 0 ] && [ $warn -eq 0 ]; then
  echo -e "  ${GREEN}${BOLD}✅ Tudo parece correto! Se ainda não consegue entrar:${RESET}"
  echo -e "     1. Limpe cookies/cache do browser e tente novamente"
  echo -e "     2. Abra o DevTools (F12) → Console e verifique erros"
  echo -e "     3. Verifique se o usuário no Clerk tem o mesmo email do banco"
elif [ $fail -gt 0 ]; then
  echo -e "  ${RED}${BOLD}❌ Encontrados $fail problema(s) crítico(s) — veja acima${RESET}"
  echo ""
  echo -e "  ${YELLOW}Ações mais comuns para resolver:${RESET}"
  echo -e "  • Promover admin:  ${BOLD}python3 promote_admin.py SEU@EMAIL.COM${RESET}"
  echo -e "  • Reiniciar:       ${BOLD}bash start.sh${RESET}"
  echo -e "  • Ver logs:        ${BOLD}docker compose logs --tail=100 backend${RESET}"
  echo -e "  • Rebuild:         ${BOLD}docker compose up -d --build${RESET}"
else
  echo -e "  ${YELLOW}${BOLD}⚠️  Encontrados $warn aviso(s) — revise os itens marcados com [WARN]${RESET}"
fi

echo ""
echo -e "  ${CYAN}Para mais diagnóstico com email específico:${RESET}"
echo -e "  ${BOLD}  bash diagnose_admin.sh SEU@EMAIL.COM${RESET}"
echo ""
