#!/usr/bin/env bash
# ============================================================================
# ClipBuilder — YouTube Cookies Setup
# ============================================================================
#
# This script installs a cookies.txt file into the backend Docker volume
# so that yt-dlp can download YouTube videos without being blocked on VPS.
#
# Usage:
#   ./setup_youtube_cookies.sh                  # interactive guide
#   ./setup_youtube_cookies.sh /path/to/cookies.txt   # direct install
#   ./setup_youtube_cookies.sh --test           # test existing cookies
#   ./setup_youtube_cookies.sh --remove         # remove installed cookies
#
# The cookies.txt must be in Netscape format (the standard export format
# from browser extensions like "Get cookies.txt LOCALLY" for Chrome or
# "cookies.txt" for Firefox).
#
# Once installed, cookies are stored inside the persistent Docker volume
# at /app/data/cookies.txt and survive container rebuilds/restarts.
# You typically only need to do this once — cookies last 6-12 months.
# ============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Resolve project directory ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Docker Compose detection ─────────────────────────────────────────
if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo -e "${RED}ERROR: docker compose not found. Install Docker first.${NC}"
    exit 1
fi

# ── Helper: check backend is running ─────────────────────────────────
ensure_backend() {
    local running
    running=$($COMPOSE ps --status running --format '{{.Service}}' 2>/dev/null | grep -c backend || true)
    if [ "$running" -eq 0 ]; then
        echo -e "${YELLOW}Backend container is not running. Starting services...${NC}"
        $COMPOSE up -d
        echo -e "${GREEN}Waiting 5s for backend to initialize...${NC}"
        sleep 5
    fi
}

# ── Helper: test cookies inside the container ────────────────────────
test_cookies() {
    echo ""
    echo -e "${CYAN}Testing YouTube cookies...${NC}"
    echo ""

    local test_output
    test_output=$($COMPOSE exec -T backend sh -c '
        COOKIES_FILE="/app/data/cookies.txt"
        if [ ! -f "$COOKIES_FILE" ]; then
            echo "NO_FILE"
            exit 1
        fi

        # Count YouTube cookie lines (skip comments and blank lines)
        YT_LINES=$(grep -c "youtube.com\|google.com" "$COOKIES_FILE" 2>/dev/null || echo "0")
        echo "COOKIE_LINES=$YT_LINES"

        # Try a real download test with the first YouTube video ever
        RESULT=$(yt-dlp \
            --cookies "$COOKIES_FILE" \
            --extractor-args "youtube:player_client=tv_embedded" \
            --skip-download \
            --print title \
            --no-warnings \
            --no-playlist \
            "https://www.youtube.com/watch?v=jNQXAC9IVRw" 2>&1)
        EXIT=$?

        if [ $EXIT -eq 0 ] && echo "$RESULT" | grep -qi "me at the zoo"; then
            echo "TEST_OK"
            echo "TITLE=$RESULT"
        else
            echo "TEST_FAIL"
            # Show last 5 lines of output for debugging
            echo "$RESULT" | tail -5
        fi
    ' 2>&1) || true

    if echo "$test_output" | grep -q "NO_FILE"; then
        echo -e "${RED}  ✗ No cookies.txt found in the container.${NC}"
        echo -e "    Run this script without arguments to install cookies."
        return 1
    fi

    local cookie_lines
    cookie_lines=$(echo "$test_output" | grep "COOKIE_LINES=" | head -1 | cut -d= -f2)

    if echo "$test_output" | grep -q "TEST_OK"; then
        local title
        title=$(echo "$test_output" | grep "TITLE=" | head -1 | cut -d= -f2-)
        echo -e "${GREEN}${BOLD}  ✓ Cookies are working!${NC}"
        echo -e "${GREEN}    Cookie lines: ${cookie_lines}${NC}"
        echo -e "${GREEN}    Test video:   ${title}${NC}"
        echo ""
        echo -e "  YouTube downloads should work without blocks."
        return 0
    else
        echo -e "${RED}  ✗ Cookies test failed.${NC}"
        echo -e "${RED}    Cookie lines found: ${cookie_lines:-0}${NC}"
        echo ""
        echo -e "  ${DIM}Debug output:${NC}"
        echo "$test_output" | grep -v "COOKIE_LINES=\|TEST_\|NO_FILE\|TITLE=" | head -10
        echo ""
        echo -e "  ${YELLOW}The cookies may be expired or invalid.${NC}"
        echo -e "  ${YELLOW}Re-export them from your browser and try again.${NC}"
        return 1
    fi
}

# ── Helper: install cookies file ─────────────────────────────────────
install_cookies() {
    local src="$1"

    if [ ! -f "$src" ]; then
        echo -e "${RED}ERROR: File not found: ${src}${NC}"
        return 1
    fi

    # Basic validation
    local line_count
    line_count=$(wc -l < "$src")
    if [ "$line_count" -lt 3 ]; then
        echo -e "${RED}ERROR: File seems too small (${line_count} lines). Not a valid cookies.txt.${NC}"
        return 1
    fi

    # Check specifically for YouTube/Google cookies
    if ! grep -qiE "youtube\.com|google\.com|\.youtube\." "$src"; then
        echo -e "${RED}ERROR: File does not contain any YouTube or Google cookies.${NC}"
        echo -e "${YELLOW}       Make sure you are on ${BOLD}youtube.com${NC}${YELLOW} when you click export.${NC}"
        echo -e "${YELLOW}       Your current file seems to contain other cookies (e.g. Cloudflare).${NC}"
        return 1
    fi

    local yt_cookie_count
    yt_cookie_count=$(grep -c "youtube.com\|google.com\|\.youtube\.\|\.google\." "$src" 2>/dev/null || echo "0")

    echo -e "${CYAN}Installing cookies into backend container...${NC}"
    echo -e "  Source:  ${src}"
    echo -e "  Lines:   ${line_count}"
    echo -e "  YouTube/Google cookies: ${yt_cookie_count}"
    echo ""

    # Copy into the running container's data volume
    ensure_backend

    # Use docker cp to place file in the named volume via the container
    docker cp "$src" "$($COMPOSE ps -q backend)":/app/data/cookies.txt

    # Verify it landed
    local check
    check=$($COMPOSE exec -T backend sh -c '
        if [ -f /app/data/cookies.txt ]; then
            wc -l < /app/data/cookies.txt
        else
            echo "MISSING"
        fi
    ' 2>/dev/null) || true

    if [ "$check" = "MISSING" ] || [ -z "$check" ]; then
        echo -e "${RED}ERROR: Failed to copy cookies into the container.${NC}"
        return 1
    fi

    echo -e "${GREEN}${BOLD}  ✓ Cookies installed successfully! (${check} lines)${NC}"
    echo ""

    # Auto-test
    test_cookies
}

# ── Helper: remove cookies ───────────────────────────────────────────
remove_cookies() {
    ensure_backend
    echo -e "${CYAN}Removing cookies from backend container...${NC}"

    $COMPOSE exec -T backend sh -c 'rm -f /app/data/cookies.txt' 2>/dev/null || true

    echo -e "${GREEN}  ✓ Cookies removed.${NC}"
    echo -e "  yt-dlp will fall back to PO Token (may be blocked on some VPS IPs)."
}

# ── Interactive guide ────────────────────────────────────────────────
interactive_guide() {
    echo ""
    echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║       ClipBuilder — YouTube Cookies Setup                   ║${NC}"
    echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Check if cookies already exist
    ensure_backend

    local existing
    existing=$($COMPOSE exec -T backend sh -c '
        if [ -f /app/data/cookies.txt ]; then
            LINES=$(wc -l < /app/data/cookies.txt)
            echo "EXISTS:$LINES"
        else
            echo "NONE"
        fi
    ' 2>/dev/null) || existing="NONE"

    if echo "$existing" | grep -q "EXISTS:"; then
        local lines
        lines=$(echo "$existing" | cut -d: -f2)
        echo -e "${GREEN}  Existing cookies found (${lines} lines).${NC}"
        echo ""
        echo -e "  Options:"
        echo -e "    ${BOLD}1)${NC} Test existing cookies"
        echo -e "    ${BOLD}2)${NC} Replace with new cookies"
        echo -e "    ${BOLD}3)${NC} Remove cookies"
        echo -e "    ${BOLD}4)${NC} Exit"
        echo ""
        read -rp "  Choose [1-4]: " choice
        case "$choice" in
            1) test_cookies; return ;;
            2) ;; # continue to install flow below
            3) remove_cookies; return ;;
            *) echo "Exiting."; return ;;
        esac
        echo ""
    fi

    echo -e "${BOLD}  How to get your cookies.txt:${NC}"
    echo ""
    echo -e "  ${CYAN}Step 1:${NC} Install a cookies export extension in your browser"
    echo ""
    echo -e "    Chrome:  ${BOLD}Get cookies.txt LOCALLY${NC}"
    echo -e "             https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
    echo ""
    echo -e "    Firefox: ${BOLD}cookies.txt${NC}"
    echo -e "             https://addons.mozilla.org/addon/cookies-txt/"
    echo ""
    echo -e "  ${CYAN}Step 2:${NC} Open ${BOLD}https://www.youtube.com${NC} and make sure you're logged in"
    echo ""
    echo -e "  ${CYAN}Step 3:${NC} Click the extension icon → Export/Download → save as ${BOLD}cookies.txt${NC}"
    echo ""
    echo -e "  ${CYAN}Step 4:${NC} Copy the file to this server:"
    echo -e "           ${DIM}scp cookies.txt root@your-server:$(pwd)/cookies.txt${NC}"
    echo ""
    echo -e "  ${CYAN}Step 5:${NC} Enter the path below (or press Enter if it's at ${BOLD}$(pwd)/cookies.txt${NC})"
    echo ""

    local default_path="$(pwd)/cookies.txt"
    read -rp "  Path to cookies.txt [${default_path}]: " input_path
    local cookies_path="${input_path:-$default_path}"

    # Expand ~ if present
    cookies_path="${cookies_path/#\~/$HOME}"

    if [ ! -f "$cookies_path" ]; then
        echo ""
        echo -e "${RED}  File not found: ${cookies_path}${NC}"
        echo ""
        echo -e "  Make sure you've copied the cookies.txt to this server first."
        echo -e "  From your local machine:"
        echo -e "    ${DIM}scp ~/Downloads/cookies.txt root@$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'your-server'):$(pwd)/cookies.txt${NC}"
        echo ""
        return 1
    fi

    echo ""
    install_cookies "$cookies_path"
}

# ── Main ─────────────────────────────────────────────────────────────

case "${1:-}" in
    --test|-t)
        ensure_backend
        test_cookies
        ;;
    --remove|--delete|-r)
        ensure_backend
        remove_cookies
        ;;
    --help|-h)
        echo ""
        echo "Usage: $0 [OPTIONS] [path/to/cookies.txt]"
        echo ""
        echo "Options:"
        echo "  (no args)          Interactive setup guide"
        echo "  /path/cookies.txt  Install cookies from file"
        echo "  --test, -t         Test installed cookies"
        echo "  --remove, -r       Remove installed cookies"
        echo "  --help, -h         Show this help"
        echo ""
        echo "The cookies.txt must be in Netscape format, exported from a browser"
        echo "where you are logged into YouTube. Use extensions like:"
        echo "  Chrome:  'Get cookies.txt LOCALLY'"
        echo "  Firefox: 'cookies.txt'"
        echo ""
        ;;
    "")
        interactive_guide
        ;;
    *)
        # Treat as a file path
        if [ -f "$1" ]; then
            ensure_backend
            install_cookies "$1"
        else
            echo -e "${RED}ERROR: File not found: $1${NC}"
            echo "Run '$0 --help' for usage."
            exit 1
        fi
        ;;
esac

echo ""
