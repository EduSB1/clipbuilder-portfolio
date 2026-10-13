#!/usr/bin/env python3
"""ClipBuilder — YouTube download diagnostic script.

Tests whether yt-dlp can fetch metadata from YouTube using each configured
auth strategy.  No video file is actually downloaded (--skip-download).

Usage:
    python backend/scripts/test_youtube_download.py [URL]

If no URL is provided, a default public video is used for testing.

Exit codes:
    0  — at least one strategy succeeded
    1  — all strategies failed

Environment variables are loaded from backend/.env automatically.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# ── Resolve paths ─────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DOTENV_PATH = BACKEND_DIR / ".env"

DEFAULT_TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo"

# ── Colors (ANSI) ────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _load_dotenv() -> None:
    """Load backend/.env into os.environ."""
    try:
        from dotenv import load_dotenv

        if DOTENV_PATH.exists():
            load_dotenv(dotenv_path=DOTENV_PATH)
        else:
            load_dotenv()
    except ImportError:
        # Manual fallback — parse KEY=VALUE lines
        if not DOTENV_PATH.exists():
            return
        for line in DOTENV_PATH.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _ytdlp_cmd() -> list[str]:
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def _get_ytdlp_version() -> str | None:
    try:
        proc = subprocess.run(
            _ytdlp_cmd() + ["--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception:
        pass
    return None


def _check_pot_plugin() -> bool:
    """Check if bgutil-ytdlp-pot-provider is installed."""
    try:
        import importlib

        importlib.import_module("yt_dlp_plugins")
        return True
    except ImportError:
        pass
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "show", "bgutil-ytdlp-pot-provider"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _cookie_args() -> list[str]:
    raw = _env("CLIPBUILDER_YTDLP_COOKIES_FILE")
    if not raw:
        return []
    try:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (BACKEND_DIR / p).resolve()
        if p.exists() and p.is_file():
            return ["--cookies", str(p)]
    except Exception:
        pass
    return []


def _browser_cookie_args() -> list[str]:
    raw = _env("CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER")
    if not raw:
        return []
    extra = _env("CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER_ARGS")
    selector = f"{raw}:{extra}" if extra else raw
    return ["--cookies-from-browser", selector]


def _po_token_args() -> list[str]:
    """PO Token strategy — use ONLY when cookies are NOT present.

    player_client=web + GetPOT plugin works on VPS without cookies.
    Do NOT combine with a cookies file: the two auth paths conflict in
    yt-dlp 2026.x and produce "No video formats found!".
    Use _tv_client_args() + cookies instead.
    """
    args = [
        "--extractor-args",
        "youtube:player_client=web",
        "--extractor-args",
        "youtube:po_token=web+MnS",
    ]
    extractor_url = _env("CLIPBUILDER_YTDLP_PO_TOKEN_EXTRACTOR_URL")
    if extractor_url:
        args += ["--extractor-args", f"youtube:pot_provider_base_url={extractor_url}"]
    return args


def _tv_client_args() -> list[str]:
    """TV embedded client — use WITH cookies to avoid GetPOT conflict.

    player_client=tv_embedded does NOT require a PO Token, so it sidesteps
    the GetPOT plugin entirely.  Combined with a valid cookies file it
    authenticates as a logged-in user on a TV app — YouTube accepts this
    even from VPS IPs that would otherwise trigger a bot check.
    """
    return [
        "--extractor-args",
        "youtube:player_client=tv_embedded",
    ]


def _proxy_args() -> list[str]:
    proxy = _env("CLIPBUILDER_YTDLP_PROXY")
    if not proxy:
        return []
    return ["--proxy", proxy]


def _mask_url(url: str) -> str:
    """Mask credentials in a proxy URL for safe display."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            return url.replace(parsed.password, "****")
    except Exception:
        pass
    return url


def _is_bot_check(output: str) -> bool:
    lowered = (output or "").lower()
    return (
        ("sign in to confirm" in lowered and "not a bot" in lowered)
        or "confirm you're not a bot" in lowered
        or "tryyoutube" in lowered
        or "please sign in" in lowered
    )


def _is_bad_cookies(output: str) -> bool:
    """Detect when cookies are expired/corrupt and poisoning the request.

    When cookies are bad (e.g. only 24 lines instead of 100+), YouTube returns
    an empty player response.  The GetPOT plugin then reports "No video formats
    found!" because the authenticated session is broken.  Retrying WITHOUT
    cookies (PO Token only) typically fixes this.
    """
    lowered = (output or "").lower()
    return (
        "no video formats found" in lowered
        or "requested format is not available" in lowered
        or ("unable to extract" in lowered and "initial player" in lowered)
        or "login required" in lowered
    )


def _run_strategy(
    label: str, extra_args: list[str], url: str
) -> tuple[bool, str, bool, bool]:
    """Run yt-dlp with --skip-download --print title.

    Returns (success, output_or_error, is_bot_block, is_bad_cookies).
    """
    cmd = (
        _ytdlp_cmd()
        + [
            "--no-playlist",
            "--no-warnings",
            "--skip-download",
            "--print",
            "title",
        ]
        + extra_args
        + [url]
    )

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False, "Timeout after 60s", False, False

    if proc.returncode == 0:
        title = (proc.stdout or "").strip()
        return True, title, False, False

    combined = "\n".join(
        filter(None, [(proc.stderr or "").strip(), (proc.stdout or "").strip()])
    )
    tail = "\n".join(combined.splitlines()[-10:])
    bot = _is_bot_check(combined)
    bad_cookies = _is_bad_cookies(combined)
    return False, tail, bot, bad_cookies


def main() -> int:
    _load_dotenv()

    url = DEFAULT_TEST_URL
    if len(sys.argv) > 1 and sys.argv[1] not in ("-h", "--help"):
        url = sys.argv[1]
    elif len(sys.argv) > 1:
        print(__doc__)
        return 0

    print()
    print(
        f"{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════╗{RESET}"
    )
    print(
        f"{CYAN}{BOLD}║       ClipBuilder — YouTube Download Diagnostic             ║{RESET}"
    )
    print(
        f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════════════╝{RESET}"
    )
    print()
    print(f"  Test URL: {BOLD}{url}{RESET}")
    print()

    # ── Environment summary ───────────────────────────────────────────
    print(f"{CYAN}── Environment ─────────────────────────────────────{RESET}")

    version = _get_ytdlp_version()
    if version:
        print(f"  {GREEN}✓{RESET} yt-dlp version: {BOLD}{version}{RESET}")
    else:
        print(f"  {RED}✗ yt-dlp is NOT installed!{RESET}")
        print("    Install with: pip install yt-dlp")
        return 1

    cookies_file = _env("CLIPBUILDER_YTDLP_COOKIES_FILE")
    cookie_a = _cookie_args()
    cookies_line_count = 0
    if cookies_file:
        if cookie_a:
            try:
                p = Path(cookies_file).expanduser()
                if not p.is_absolute():
                    p = (BACKEND_DIR / p).resolve()
                cookies_line_count = sum(
                    1 for _ in p.open(encoding="utf-8", errors="ignore")
                )
            except Exception:
                pass
            if cookies_line_count < 50:
                print(
                    f"  {YELLOW}⚠{RESET} Cookies file: {cookies_file} "
                    f"({cookies_line_count} lines — {BOLD}suspiciously small!{RESET} "
                    f"A valid cookies.txt usually has 100+ lines)"
                )
            else:
                print(
                    f"  {GREEN}✓{RESET} Cookies file: {cookies_file} ({cookies_line_count} lines)"
                )
        else:
            print(
                f"  {YELLOW}⚠{RESET} Cookies file configured but NOT found: {cookies_file}"
            )
    else:
        print(f"  {DIM}  Cookies file: not configured{RESET}")

    browser = _env("CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER")
    if browser:
        print(f"  {GREEN}✓{RESET} Browser cookies: {browser}")
    else:
        print(f"  {DIM}  Browser cookies: not configured{RESET}")

    pot_installed = _check_pot_plugin()
    if pot_installed:
        print(f"  {GREEN}✓{RESET} PO Token plugin: installed")
    else:
        print(f"  {YELLOW}⚠{RESET} PO Token plugin: NOT installed")

    extractor_url = _env("CLIPBUILDER_YTDLP_PO_TOKEN_EXTRACTOR_URL")
    if extractor_url:
        print(f"  {GREEN}✓{RESET} PO Token extractor URL: {extractor_url}")

    proxy = _env("CLIPBUILDER_YTDLP_PROXY")
    if proxy:
        print(f"  {GREEN}✓{RESET} Proxy: {_mask_url(proxy)}")
    else:
        print(f"  {DIM}  Proxy: not configured{RESET}")

    print()

    # ── Build strategies ──────────────────────────────────────────────
    # ROOT CAUSE: GetPOT plugin intercepts ALL yt-dlp YouTube requests
    # (visible as [youtube+GetPOT] in error output). Combining
    # player_client=web + cookies in yt-dlp 2026.x causes "No video
    # formats found!" because the two auth paths conflict.
    #
    # SOLUTION: When cookies are present → use player_client=tv_embedded
    # (no PO Token needed, no GetPOT conflict, works with cookies).
    # When no cookies → use player_client=web + GetPOT (PO Token).
    #
    # Order:
    #   1. cookies + tv_embedded + proxy  ← correct combo for cookies
    #   2. cookies + tv_embedded          ← same without proxy
    #   3. pot + proxy                    ← no cookies, GetPOT handles it
    #   4. pot-only                       ← no cookies, no proxy
    #   5. cookies + web + proxy (legacy) ← old behaviour, last resort
    #   6. cookies + web (legacy)         ← same without proxy
    #   7. bare                           ← absolute last resort
    proxy_a = _proxy_args()
    browser_a = _browser_cookie_args()
    all_cookie_a = cookie_a or browser_a
    po_a = _po_token_args()
    tv_a = _tv_client_args()

    # (label, extra_args, uses_cookies)
    strategies: list[tuple[str, list[str], bool]] = []

    # Cookie strategies — tv_embedded avoids GetPOT conflict
    if all_cookie_a:
        if proxy_a:
            strategies.append(
                ("cookies+tv_embedded+proxy", all_cookie_a + tv_a + proxy_a, True)
            )
        strategies.append(("cookies+tv_embedded", all_cookie_a + tv_a, True))

    # PO Token strategies — no cookies, GetPOT generates the token
    strategies.append(("pot+proxy", po_a + proxy_a, False))
    strategies.append(("pot-only", po_a, False))

    # Legacy fallbacks: cookies with web client (may conflict with GetPOT)
    if all_cookie_a and proxy_a:
        strategies.append(("cookies+web+proxy (legacy)", all_cookie_a + proxy_a, True))
    if all_cookie_a:
        strategies.append(("cookies+web (legacy)", all_cookie_a, True))

    strategies.append(("bare (no auth)", [], False))

    # De-duplicate consecutive identical arg lists
    seen: list[list[str]] = []
    deduped: list[tuple[str, list[str], bool]] = []
    for label, extra, uses_cookies in strategies:
        if extra not in seen:
            seen.append(extra)
            deduped.append((label, extra, uses_cookies))

    # ── Run strategies ────────────────────────────────────────────────
    print(f"{CYAN}── Testing strategies ──────────────────────────────{RESET}")
    print()

    any_success = False
    any_bot_block = False
    any_bad_cookies = False
    cookies_are_bad = False  # once True, skip remaining cookie strategies
    winning_strategy: str | None = None

    for i, (label, extra_args, uses_cookies) in enumerate(deduped, 1):
        # Skip cookie-based strategies once we know cookies are poisoned
        if uses_cookies and cookies_are_bad:
            print(
                f"  [{i}/{len(deduped)}] {BOLD}{label}{RESET} ... "
                f"{DIM}SKIPPED (cookies are bad){RESET}"
            )
            continue

        print(
            f"  [{i}/{len(deduped)}] {BOLD}{label}{RESET} ... ",
            end="",
            flush=True,
        )
        success, output, bot, bad_cookies = _run_strategy(label, extra_args, url)

        if success:
            print(f"{GREEN}✓ SUCCESS{RESET}")
            print(f"         Video title: {BOLD}{output}{RESET}")
            any_success = True
            winning_strategy = label
            break
        else:
            if bad_cookies and uses_cookies:
                any_bad_cookies = True
                cookies_are_bad = True
                print(f"{YELLOW}✗ BAD COOKIES{RESET}")
                print(
                    f"         {DIM}Cookies appear expired/corrupt — poisoning the request{RESET}"
                )
            elif bot:
                any_bot_block = True
                print(f"{RED}✗ BOT BLOCK{RESET}")
                print(
                    f"         {DIM}YouTube: 'Sign in to confirm you're not a bot'{RESET}"
                )
            else:
                print(f"{RED}✗ FAILED{RESET}")
                for line in output.splitlines()[:3]:
                    print(f"         {DIM}{line}{RESET}")

    print()

    # ── Results ───────────────────────────────────────────────────────
    print(f"{CYAN}── Result ─────────────────────────────────────────{RESET}")
    print()

    if any_success:
        print(f"  {GREEN}{BOLD}✓ YouTube download is working!{RESET}")
        print(f"  Winning strategy: {BOLD}{winning_strategy}{RESET}")
        if any_bad_cookies:
            print()
            print(
                f"  {YELLOW}{BOLD}⚠ Warning:{RESET} Your cookies file is expired/corrupt "
                f"({cookies_line_count} lines — a valid one has 100+)."
            )
            print("  Downloads work via PO Token, but re-exporting fresh cookies")
            print("  would make more strategies available and improve reliability.")
            print(f"  Run: {BOLD}./setup_youtube_cookies.sh{RESET}")
        print()
        return 0

    print(f"  {RED}{BOLD}✗ All strategies failed.{RESET}")
    print()

    if any_bad_cookies:
        print(f"  {YELLOW}{BOLD}⚠ Your cookies file is expired/corrupt!{RESET}")
        print(
            f"    Only {cookies_line_count} lines (a valid cookies.txt has 100+ lines)."
        )
        print("    Bad cookies POISON strategies that use them — YouTube returns")
        print("    empty responses instead of actual video data.")
        print()
        print(f"  {BOLD}Fix:{RESET} Re-export cookies or remove the bad file:")
        print(f"    {CYAN}Option A:{RESET} ./setup_youtube_cookies.sh")
        print(f"    {CYAN}Option B:{RESET} ./setup_youtube_cookies.sh --remove")
        print()

    if any_bot_block:
        print(f"  {YELLOW}{BOLD}YouTube is blocking downloads from this server.{RESET}")
        print()
        print(f"  {BOLD}Recommended solutions (in order of reliability):{RESET}")
        print()
        print(f"  {CYAN}1. Residential proxy (STRONGEST){RESET}")
        print("     Set CLIPBUILDER_YTDLP_PROXY in backend/.env:")
        print("       CLIPBUILDER_YTDLP_PROXY=http://user:pass@host:port")
        print("       CLIPBUILDER_YTDLP_PROXY=socks5://user:pass@host:port")
        print("     Providers: Bright Data, Oxylabs, Smartproxy")
        print()
        print(f"  {CYAN}2. YouTube cookies{RESET}")
        if any_bad_cookies:
            print("     ↑ Your current cookies are BAD — re-export them first!")
        print("     Run: ./setup_youtube_cookies.sh")
        print("     Or set CLIPBUILDER_YTDLP_COOKIES_FILE in backend/.env")
        print("     pointing to a Netscape-format cookies.txt exported from")
        print("     a browser logged into YouTube.")
        print()
        print(f"  {CYAN}3. Manual upload{RESET}")
        print("     Download the video on your local machine and upload the")
        print("     .mp4 or .mkv file directly via the ClipBuilder UI.")
        print()
    elif not any_bad_cookies:
        print("  The failure does not appear to be a YouTube bot block.")
        print("  Check your network connectivity and yt-dlp version.")
        print("  Update yt-dlp: pip install --upgrade yt-dlp")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
