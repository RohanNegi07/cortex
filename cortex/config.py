"""
CORTEX Configuration
Environment variables and constants loaded from .env
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE)

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

# Convert SQLAlchemy format to asyncpg format if needed
_db_url = os.environ.get("DATABASE_URL", "postgresql://cortex_user:cortex_pass@localhost:5432/cortex_db")
DATABASE_URL = (_db_url
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("postgresql+psycopg://", "postgresql://")
    .replace("postgresql+psycopg2://", "postgresql://")
    .replace("postgres+asyncpg://", "postgresql://")
    .replace("postgres+psycopg://", "postgresql://")
    .replace("postgres+psycopg2://", "postgresql://")
)
DATABASE_POOL_SIZE = int(os.environ.get("DATABASE_POOL_SIZE", 10))
DATABASE_MAX_OVERFLOW = int(os.environ.get("DATABASE_MAX_OVERFLOW", 20))

# ─────────────────────────────────────────────────────────────────────────────
# R2 (Cloudflare)
# ─────────────────────────────────────────────────────────────────────────────

R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "erp-agents")

# ─────────────────────────────────────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL = "text-embedding-3-small"  # for pgvector

# ─────────────────────────────────────────────────────────────────────────────
# EXTERNAL SERVICES
# ─────────────────────────────────────────────────────────────────────────────

IRIS_API_BASE_URL = os.environ.get("IRIS_API_BASE_URL", "http://localhost:8000")
IRIS_API_KEY = os.environ.get("IRIS_API_KEY", "")

CELL_API_BASE_URL = os.environ.get("CELL_API_BASE_URL", "http://localhost:8002")
CELL_API_KEY = os.environ.get("CELL_API_KEY", "")

ERP_API_BASE_URL = os.environ.get("ERP_API_BASE_URL", "")
ERP_API_KEY = os.environ.get("ERP_API_KEY", "")

INTRANET_API_BASE_URL = os.environ.get("INTRANET_API_BASE_URL", "")
INTRANET_API_KEY = os.environ.get("INTRANET_API_KEY", "")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

# ─────────────────────────────────────────────────────────────────────────────
# CORTEX SERVICE
# ─────────────────────────────────────────────────────────────────────────────

CORTEX_HOST = os.environ.get("CORTEX_HOST", "0.0.0.0")
CORTEX_PORT = int(os.environ.get("CORTEX_PORT", 8004))
CORTEX_API_KEY = os.environ.get("CORTEX_API_KEY", "")
CORTEX_ENV = os.environ.get("CORTEX_ENV", "development")

# ─────────────────────────────────────────────────────────────────────────────
# TIMEZONE & SCHEDULING
# ─────────────────────────────────────────────────────────────────────────────

TIMEZONE = os.environ.get("TZ", "Asia/Kolkata")

# APScheduler job definitions
HEALTH_SCAN_TIME = os.environ.get("HEALTH_SCAN_TIME", "08:00")
HEALTH_SCAN_DAY = os.environ.get("HEALTH_SCAN_DAY", "monday")
WEEKLY_PLAN_TIME = os.environ.get("WEEKLY_PLAN_TIME", "07:30")
CADENCE_CHECK_TIME = os.environ.get("CADENCE_CHECK_TIME", "08:00")
RENEWAL_CHECK_TIME = os.environ.get("RENEWAL_CHECK_TIME", "08:00")

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH SCORE THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

HEALTH_SCORE_RED_THRESHOLD = int(os.environ.get("HEALTH_SCORE_RED_THRESHOLD", 60))
HEALTH_SCORE_AMBER_THRESHOLD = int(os.environ.get("HEALTH_SCORE_AMBER_THRESHOLD", 80))

BLOCKER_ALERT_DAYS = int(os.environ.get("BLOCKER_ALERT_DAYS", 2))
SENTIMENT_DECLINE_WINDOW = int(os.environ.get("SENTIMENT_DECLINE_WINDOW", 3))
CADENCE_GAP_DAYS_CLIENT = int(os.environ.get("CADENCE_GAP_DAYS_CLIENT", 14))
RENEWAL_SIGNAL_WEEKS = int(os.environ.get("RENEWAL_SIGNAL_WEEKS", 6))
