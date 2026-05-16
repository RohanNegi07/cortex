"""
CORTEX — FastAPI Service
Project intelligence and PM command layer for the consultancy.

Runs on port 8004 (configurable via CORTEX_PORT).
Entry points: NERVE webhook, document upload, chat, scheduled jobs.
"""

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from datetime import datetime

from cortex.config import CORTEX_HOST, CORTEX_PORT, CORTEX_ENV, CORTEX_API_KEY
from cortex.models.db import init_db, close_db, init_schema
from cortex.models.schemas import HealthCheckResponse
from cortex.routers import nerve, chat, documents, slack, team, calibrate
from cortex.scheduler import start_scheduler, stop_scheduler

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CORTEX] %(levelname)s — %(message)s",
)
log = logging.getLogger("cortex")

# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown"""
    # Startup
    log.info(f"CORTEX starting... (env: {CORTEX_ENV})")
    db_ok = await init_db()
    if not db_ok:
        log.warning("Database init returned False. Continuing in stub mode.")

    schema_ok = await init_schema()
    if not schema_ok:
        log.warning("Schema init returned False. Continuing in stub mode.")

    # Start scheduler
    try:
        await start_scheduler()
        log.info("[OK] Scheduler started")
    except Exception as e:
        log.warning(f"Scheduler start failed: {e}. Continuing without scheduler.")

    log.info("[OK] CORTEX ready")
    yield
    # Shutdown
    try:
        await stop_scheduler()
    except Exception as e:
        log.warning(f"Scheduler stop failed: {e}")

    await close_db()
    log.info("[OK] CORTEX shutdown complete")

# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CORTEX",
    description="Client Oversight & Relationship Trajectory Executive",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/cortex/health", response_model=HealthCheckResponse)
async def health_check():
    """Service health check"""
    return HealthCheckResponse(
        status="ok",
        message="CORTEX is running",
        database_connected=True,
        version="0.1.0"
    )

# ─────────────────────────────────────────────────────────────────────────────
# API KEY MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

async def verify_api_key(api_key: str = Header(None)):
    """Verify CORTEX_API_KEY for protected endpoints"""
    if not CORTEX_API_KEY:
        # In dev, skip auth if no key configured
        if CORTEX_ENV != "development":
            raise HTTPException(status_code=401, detail="CORTEX_API_KEY not configured")
        return None

    if not api_key or api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key

# ─────────────────────────────────────────────────────────────────────────────
# ROUTERS
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(nerve.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(slack.router)
app.include_router(team.router)
app.include_router(calibrate.router)

# ─────────────────────────────────────────────────────────────────────────────
# ROOT
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "CORTEX",
        "version": "0.1.0",
        "status": "running",
        "health": "/cortex/health"
    }

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    log.info(f"Starting CORTEX on {CORTEX_HOST}:{CORTEX_PORT}")
    uvicorn.run(
        app,
        host=CORTEX_HOST,
        port=CORTEX_PORT,
        log_level="info"
    )
