"""
ClipBuilder System Constants
=============================

Centralizes all hardcoded values (magic numbers) for easy maintenance and configuration.
All values are organized by category with clear documentation.

Usage:
    from app.core.constants import MAX_VIDEO_SIZE_MB, DEFAULT_GEMINI_CLIP_SECONDS
"""

# ══════════════════════════════════════════════════════════════════════════════
# UPLOAD LIMITS
# ══════════════════════════════════════════════════════════════════════════════

# Video upload limits (in MB)
MAX_VIDEO_SIZE_MB = 700
DEFAULT_MAX_VIDEO_MB = 700

# Image upload limits (in MB)
MAX_TOTAL_IMAGE_BYTES_MB = 50
MAX_SINGLE_IMAGE_BYTES_MB = 15

# GIF upload limits (in MB)
MAX_GIF_BYTES_MB = 100

# Upload chunk size (in KB)
UPLOAD_CHUNK_SIZE_KB = 1024  # 1 MB


# ══════════════════════════════════════════════════════════════════════════════
# TIMEOUTS & INTERVALS (in seconds)
# ══════════════════════════════════════════════════════════════════════════════

# yt-dlp timeouts
YTDLP_DEFAULT_TIMEOUT_SECONDS = 600  # 10 minutes
YTDLP_DIAGNOSTIC_TIMEOUT_SECONDS = 10

# Gemini polling
GEMINI_POLL_TIMEOUT_SECONDS = 300  # 5 minutes
GEMINI_POLL_INTERVAL_SECONDS = 2

# SMTP timeouts
SMTP_SSL_CONNECTION_TIMEOUT_SECONDS = 15
SMTP_CONNECTION_TIMEOUT_SECONDS = 15

# Retry delays
MAX_RETRY_SLEEP_SECONDS = 15

# Background utility timeouts
BGUTIL_DIAGNOSTIC_TIMEOUT_SECONDS = 15


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

# Gemini video settings
DEFAULT_GEMINI_CLIP_SECONDS = 90
DEFAULT_GEMINI_PROXY_HEIGHT = 720  # pixels

# Video encoding
VIDEO_ENCODE_CRF = 28  # Constant Rate Factor (quality)
MIN_CLIP_DURATION_SECONDS = 10

# Video analysis windows (in seconds)
TIMESTAMP_ANALYSIS_WINDOW_SECONDS = 40
FRAME_EXTRACTION_WINDOW_SECONDS = 40

# Frame extraction
DEFAULT_FRAME_COUNT = 5
MIN_FRAME_SCALE_HEIGHT = 144  # pixels


# ══════════════════════════════════════════════════════════════════════════════
# AUDIO PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

AUDIO_BITRATE_KBPS = 96
WHISPER_SAMPLE_RATE_HZ = 16000
MIN_AUDIO_FILE_SIZE_BYTES = 1000
AUDIO_EXTRACTION_WINDOW_SECONDS = 40


# ══════════════════════════════════════════════════════════════════════════════
# GIF PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

GIF_FRAME_COUNT = 5


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI AI SETTINGS
# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
# PAGINATION & QUERY LIMITS
# ══════════════════════════════════════════════════════════════════════════════

# General pagination
DEFAULT_PAGE_SIZE = 20
DEFAULT_USER_PAGE_SIZE = 20

# Admin pagination
ADMIN_DEFAULT_PAGE_SIZE = 20
ADMIN_MAX_PAGE_SIZE = 500

# Usage and transaction logs
DEFAULT_USAGE_LOG_LIMIT = 50
DEFAULT_TRANSACTION_QUERY_LIMIT = 50
DEFAULT_CREDIT_TRANSACTION_LIMIT = 50
MAX_CREDIT_TRANSACTION_LIMIT = 200
CREDIT_ADJUSTMENT_TRANSACTION_LIMIT = 10

# Activity and metrics
RECENT_ACTIVITY_LOG_LIMIT = 20
DASHBOARD_CHART_DAYS = 30

# Clerk sync
CLERK_SYNC_USER_LIMIT = 100

# Data files
DEFAULT_MAX_DATA_FILES = 5


# ══════════════════════════════════════════════════════════════════════════════
# BILLING & CREDITS
# ══════════════════════════════════════════════════════════════════════════════

# Initial credits
INITIAL_FREE_CREDITS = 10

# Credit packages
# Starter package
STARTER_PACKAGE_CREDITS = 100
STARTER_PACKAGE_PRICE_BRL = 50.0
STARTER_PACKAGE_PRICE_CENTS = 5000

# Pro package
PRO_PACKAGE_CREDITS = 300
PRO_PACKAGE_PRICE_BRL = 130.0
PRO_PACKAGE_PRICE_CENTS = 13000

# Business package
BUSINESS_PACKAGE_CREDITS = 1000
BUSINESS_PACKAGE_PRICE_BRL = 380.0
BUSINESS_PACKAGE_PRICE_CENTS = 38000

# Payment settings
MAX_INSTALLMENTS = 12


# ══════════════════════════════════════════════════════════════════════════════
# PLAN LIMITS (Video Size in GB)
# ══════════════════════════════════════════════════════════════════════════════

FREE_PLAN_MAX_VIDEO_SIZE_GB = 2.0
STARTER_PLAN_MAX_VIDEO_SIZE_GB = 4.0
PRO_PLAN_MAX_VIDEO_SIZE_GB = 8.0
BUSINESS_PLAN_MAX_VIDEO_SIZE_GB = 20.0


# ══════════════════════════════════════════════════════════════════════════════
# GROUP SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_GROUP_MAX_STORAGE_GB = 100
DEFAULT_GROUP_MAX_MONTHLY_AI_REQUESTS = 1000


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY & RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════════

# Authentication
LOCAL_LOGIN_RATE_LIMIT_PER_MINUTE = 5
LOGIN_ANTI_ENUMERATION_DELAY_SECONDS = 0.5
MIN_TOKEN_EXPIRE_MINUTES = 5

# Token expiration (in minutes)
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
DEFAULT_LOCAL_JWT_EXPIRE_MINUTES = 480  # 8 hours

# JWKS cache
JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

# Log file rotation
LOG_FILE_MAX_BYTES = 2_000_000  # 2 MB
LOG_INFO_BACKUP_COUNT = 5
LOG_ERROR_FILE_MAX_BYTES = 2_000_000  # 2 MB
LOG_ERROR_BACKUP_COUNT = 10


# ══════════════════════════════════════════════════════════════════════════════
# NETWORK & COMMUNICATION
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_SMTP_PORT = 587


# ══════════════════════════════════════════════════════════════════════════════
# TIME CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# End of day time components (for date calculations)
END_OF_DAY_HOUR = 23
END_OF_DAY_MINUTE = 59
END_OF_DAY_SECOND = 59
