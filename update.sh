#!/bin/bash
# =============================================================
#  update.sh — Atualiza e reinicia o ClipBuilder na VPS
#  Uso: bash update.sh   (na primeira vez, ou sempre)
#       ./update.sh      (após a primeira vez)
#
#  Usa fetch + reset --hard para NUNCA ter conflitos de merge.
#  A VPS sempre fica idêntica ao GitHub — nunca edite arquivos
#  diretamente na VPS, use este script para atualizar.
# =============================================================

# Auto-corrige a própria permissão de execução
chmod +x "$0"

set -e

# Resolve o diretório onde este script está, independente de onde for chamado
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Branch que a VPS deve sempre seguir
BRANCH="auth/clerk"

echo ""
echo "=========================================="
echo "  ClipBuilder — Update & Restart"
echo "=========================================="
echo ""

# 1. Sincroniza com o GitHub (sem merge, sem conflito)
echo "[1/4] Sincronizando com o GitHub..."
git fetch origin
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

# Garante permissões após o reset (o reset --hard apaga o +x)
chmod +x "$SCRIPT_DIR/update.sh"
chmod +x "$SCRIPT_DIR/setup_youtube_cookies.sh" 2>/dev/null || true

echo "      OK — branch: $BRANCH"
echo ""

# 2. Docker down
echo "[2/4] Derrubando containers..."
docker compose down
echo "      OK"
echo ""

# 3. Docker up com rebuild
echo "[3/4] Reconstruindo e subindo containers..."
docker compose up -d --build
echo "      OK"
echo ""

# 4. Status final
echo "[4/4] Status dos containers:"
docker compose ps
echo ""

echo "=========================================="
echo "  Atualização concluída com sucesso!"
echo "=========================================="
echo ""

# ── YouTube cookies check ────────────────────────────────────
# Verifica se os cookies do YouTube já foram configurados.
# Se não, avisa o admin para executar o setup.
YT_COOKIES=$(docker compose exec -T backend sh -c \
    'test -f /app/data/cookies.txt && grep -c "youtube.com\|google.com" /app/data/cookies.txt 2>/dev/null || echo 0' \
    2>/dev/null || echo "0")

if [ "$YT_COOKIES" = "0" ] || [ -z "$YT_COOKIES" ]; then
    echo "  ⚠  YouTube cookies ainda não configurados!"
    echo "     Downloads do YouTube podem ser bloqueados na VPS."
    echo ""
    echo "     Para configurar (uma única vez):"
    echo "       ./setup_youtube_cookies.sh"
    echo ""
    echo "     Documentação completa: docs/YOUTUBE_SETUP.md"
    echo ""
fi

# ── Bootstrap permanente ──────────────────────────────────────
# Cria o alias 'update' no .bashrc para nunca mais precisar de chmod.
# Após rodar este script uma vez com "bash update.sh", basta digitar
# "update" em qualquer diretório para atualizar o ClipBuilder.
ALIAS_LINE="alias update='bash /home/ClipBuilder/update.sh'"
BASHRC="/root/.bashrc"
if ! grep -qF "$ALIAS_LINE" "$BASHRC" 2>/dev/null; then
    echo "" >> "$BASHRC"
    echo "# ClipBuilder update shortcut" >> "$BASHRC"
    echo "$ALIAS_LINE" >> "$BASHRC"
    echo "  ✔ Alias 'update' adicionado ao .bashrc"
    echo "    Execute 'source ~/.bashrc' ou abra um novo terminal"
    echo "    e use apenas 'update' para atualizar o ClipBuilder."
    echo ""
fi
