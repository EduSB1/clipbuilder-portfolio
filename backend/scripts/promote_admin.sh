#!/usr/bin/env bash
#
# promote_admin.sh — Promote / create an admin user via the DB container.
#
# This script talks directly to the PostgreSQL container using
# "docker compose exec db psql …", so it does NOT need pip, psycopg2,
# or any Python dependency on the host.
#
# Usage:
#   ./promote_admin.sh                                        # list all users
#   ./promote_admin.sh admin@example.com                # promote to admin (keep current password)
#   ./promote_admin.sh admin@example.com 123456         # promote + reset password
#   ./promote_admin.sh admin@clipbuilder.com   admin123       # create if missing + set password
#
# The script auto-detects whether to use "sudo docker" or plain "docker".

set -euo pipefail

# ── Docker detection ────────────────────────────────────────────────────────

DOCKER="docker"
if ! $DOCKER info &>/dev/null; then
  DOCKER="sudo docker"
  if ! $DOCKER info &>/dev/null; then
    echo "❌ Cannot connect to Docker daemon. Try running with sudo or add your user to the docker group."
    exit 1
  fi
fi

COMPOSE="$DOCKER compose"

# Ensure we're in the project root (where docker-compose.yml lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f docker-compose.yml ]]; then
  echo "❌ docker-compose.yml not found in $SCRIPT_DIR"
  exit 1
fi

# ── Input validation ────────────────────────────────────────────────────────

validate_email() {
    local email="$1"
    if [[ ! "$email" =~ ^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$ ]]; then
        echo "❌ E-mail inválido: '$email'"; exit 1
    fi
    if [[ ${#email} -gt 254 ]]; then
        echo "❌ E-mail muito longo (máx 254 caracteres)"; exit 1
    fi
}

# ── DB connection helper ────────────────────────────────────────────────────

DB_USER="clipbuilder"
DB_NAME="clipbuilder"
DB_CONTAINER="db"

run_sql() {
  $COMPOSE exec -T "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "$1" 2>/dev/null
}

run_sql_pretty() {
  $COMPOSE exec -T "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "$1" 2>/dev/null
}

# ── Check DB is up ──────────────────────────────────────────────────────────

if ! run_sql "SELECT 1;" &>/dev/null; then
  echo "❌ Cannot connect to the database container."
  echo "   Is it running?  $DOCKER compose ps"
  exit 1
fi

# ── List mode ───────────────────────────────────────────────────────────────

list_users() {
  echo ""
  echo "📋 All users in the database:"
  echo ""
  run_sql_pretty "
    SELECT
      email,
      role,
      CASE WHEN is_active THEN '✅ yes' ELSE '❌ no' END AS active,
      CASE WHEN deleted_at IS NOT NULL THEN '🗑 yes' ELSE 'no' END AS deleted,
      COALESCE(full_name, '') AS name
    FROM users
    ORDER BY created_at;
  "
  echo ""
}

# ── No arguments → list users ──────────────────────────────────────────────

if [[ $# -eq 0 ]]; then
  list_users
  echo "Usage:  $0 <email> [new_password]"
  exit 0
fi

# ── Promote / create user ──────────────────────────────────────────────────

EMAIL="$(echo "$1" | tr '[:upper:]' '[:lower:]' | xargs)"
NEW_PASSWORD="${2:-}"

# ── Validate inputs ────────────────────────────────────────────────────────

validate_email "$EMAIL"

if [[ -n "$NEW_PASSWORD" ]]; then
  if [[ ${#NEW_PASSWORD} -lt 8 ]]; then
    echo "❌ Senha muito curta (mínimo 8 caracteres)"; exit 1
  fi
  if [[ ${#NEW_PASSWORD} -gt 128 ]]; then
    echo "❌ Senha muito longa (máximo 128 caracteres)"; exit 1
  fi
fi

echo ""
echo "🔧 Promoting '$EMAIL' to admin..."

# Check if user exists (parameterized query)
USER_ROW=$(
  $COMPOSE exec -T "$DB_CONTAINER" \
    psql -U "$DB_USER" -d "$DB_NAME" -t -A \
    -v email="$EMAIL" \
    -c "SELECT id, role, is_active, (deleted_at IS NOT NULL) AS deleted FROM users WHERE email = :'email' LIMIT 1;" \
  2>/dev/null
)

if [[ -n "$USER_ROW" ]]; then
  # User exists — parse fields (psql -t -A uses | as separator)
  USER_ID=$(echo "$USER_ROW" | cut -d'|' -f1)
  CURRENT_ROLE=$(echo "$USER_ROW" | cut -d'|' -f2)
  IS_ACTIVE=$(echo "$USER_ROW" | cut -d'|' -f3)
  IS_DELETED=$(echo "$USER_ROW" | cut -d'|' -f4)

  CHANGES=""

  # Promote to admin (use $USER_ID which is a UUID, safe for interpolation)
  if [[ "$CURRENT_ROLE" != "admin" ]]; then
    run_sql "UPDATE users SET role = 'admin' WHERE id = '$USER_ID';" >/dev/null
    CHANGES="$CHANGES\n   • role: $CURRENT_ROLE → admin"
  fi

  # Reactivate
  if [[ "$IS_ACTIVE" == "f" ]]; then
    run_sql "UPDATE users SET is_active = true WHERE id = '$USER_ID';" >/dev/null
    CHANGES="$CHANGES\n   • is_active: false → true"
  fi

  # Clear soft-delete
  if [[ "$IS_DELETED" == "t" ]]; then
    run_sql "UPDATE users SET deleted_at = NULL WHERE id = '$USER_ID';" >/dev/null
    CHANGES="$CHANGES\n   • deleted_at: cleared"
  fi

  # Reset password (if provided) — password passed via environment variable, not CLI argument
  if [[ -n "$NEW_PASSWORD" ]]; then
    HASH=$(
      NEW_PASSWORD="$NEW_PASSWORD" \
      $COMPOSE exec -T backend python3 -c "
import bcrypt, os
pwd = os.environ.get('NEW_PASSWORD', '').encode()
print(bcrypt.hashpw(pwd, bcrypt.gensalt()).decode())
" 2>/dev/null | tr -d '\r'
    )
    if [[ -n "$HASH" ]]; then
      # Escape single quotes in hash for SQL
      HASH_ESCAPED="${HASH//\'/\'\'}"
      run_sql "UPDATE users SET password_hash = '$HASH_ESCAPED' WHERE id = '$USER_ID';" >/dev/null
      CHANGES="$CHANGES\n   • password: reset"
    else
      echo "   ⚠️  Could not generate password hash (backend container not running?)"
    fi
  fi

  # Update timestamp
  run_sql "UPDATE users SET updated_at = NOW() WHERE id = '$USER_ID';" >/dev/null

  # Ensure permissions exist
  HAS_PERMS=$(run_sql "SELECT COUNT(*) FROM user_permissions WHERE user_id = '$USER_ID';")
  if [[ "$HAS_PERMS" == "0" ]]; then
    run_sql "
      INSERT INTO user_permissions (user_id, can_use_gemini, can_use_whisper, max_video_size_gb, created_at)
      VALUES ('$USER_ID', true, true, 6.0, NOW());
    " >/dev/null
    CHANGES="$CHANGES\n   • permissions: created (all enabled)"
  fi

  if [[ -n "$CHANGES" ]]; then
    echo -e "✅ User '$EMAIL' updated:$CHANGES"
  else
    echo "✅ User '$EMAIL' is already an active admin. No changes needed."
  fi

else
  # User does not exist — create new admin
  NEW_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())" 2>/dev/null || echo "$(date +%s)-$(head -c 8 /dev/urandom | xxd -p)")
  ACTUAL_PASSWORD="${NEW_PASSWORD:-admin123}"

  # Validate password for new user too
  if [[ ${#ACTUAL_PASSWORD} -lt 8 ]]; then
    echo "❌ Senha muito curta (mínimo 8 caracteres)"; exit 1
  fi

  # Generate bcrypt hash inside the backend container — password via env var
  HASH=$(
    NEW_PASSWORD="$ACTUAL_PASSWORD" \
    $COMPOSE exec -T backend python3 -c "
import bcrypt, os
pwd = os.environ.get('NEW_PASSWORD', '').encode()
print(bcrypt.hashpw(pwd, bcrypt.gensalt()).decode())
" 2>/dev/null | tr -d '\r'
  )

  if [[ -z "$HASH" ]]; then
    echo "❌ Cannot generate password hash. Is the backend container running?"
    echo "   Run: $DOCKER compose ps"
    exit 1
  fi

  HASH_ESCAPED="${HASH//\'/\'\'}"

  # Use parameterized query for INSERT with email
  $COMPOSE exec -T "$DB_CONTAINER" \
    psql -U "$DB_USER" -d "$DB_NAME" -t -A \
    -v email="$EMAIL" \
    -v id="$NEW_ID" \
    -v hash="$HASH_ESCAPED" \
    -c "INSERT INTO users (id, email, password_hash, full_name, role, is_active, created_at, updated_at)
        VALUES (:'id', :'email', :'hash', 'Administrador', 'admin', true, NOW(), NOW());" \
  >/dev/null 2>/dev/null

  run_sql "
    INSERT INTO user_permissions (user_id, can_use_gemini, can_use_whisper, max_video_size_gb, created_at)
    VALUES ('$NEW_ID', true, true, 6.0, NOW());
  " >/dev/null

  echo "✅ User '$EMAIL' CREATED as admin."
  echo "   Password: $ACTUAL_PASSWORD"
fi

# Show final state (parameterized query)
echo ""
echo "📋 Final state:"
$COMPOSE exec -T "$DB_CONTAINER" \
  psql -U "$DB_USER" -d "$DB_NAME" \
  -v email="$EMAIL" \
  -c "SELECT email, role, is_active, full_name FROM users WHERE email = :'email';" \
2>/dev/null
echo ""
