import os
import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, EmailStr
from prometheus_fastapi_instrumentator import Instrumentator

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hydrus-api")

# ── Settings (from environment variables) ────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://hydrus:hydrus_pass@localhost:5432/hydrus_db",
)
ALLOWED_ORIGINS: list[str] = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:80"
).split(",")
APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

# ── Database connection pool ──────────────────────────────────────────────────
db_pool: Optional[asyncpg.Pool] = None


async def get_db() -> asyncpg.Pool:
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return db_pool


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    logger.info("Starting up — connecting to PostgreSQL …")
    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        # Ensure tasks table exists
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id        SERIAL PRIMARY KEY,
                    title     TEXT        NOT NULL,
                    completed BOOLEAN     NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        logger.info("Database connected and schema ready.")
    except Exception as exc:
        logger.warning(f"DB connection failed: {exc}. Running without DB.")
        db_pool = None

    yield  # app runs here

    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed.")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Hydrus Digital BD API",
    description="Production API for Hydrus DevOps Assessment",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Pydantic models ──────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str

class TaskOut(BaseModel):
    id: int
    title: str
    completed: bool
    created_at: datetime

class TaskUpdate(BaseModel):
    completed: bool

# ── Health endpoints ──────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — always returns 200 if the process is alive."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness probe — returns 200 only when the DB is reachable.
    Kubernetes uses this to decide whether to send traffic.
    """
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not ready")
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        logger.error(f"Readiness check failed: {exc}")
        raise HTTPException(status_code=503, detail="Database check failed")


# ── API endpoints ─────────────────────────────────────────────────────────────
@app.get("/api/v1/info", tags=["Info"])
async def app_info():
    """Returns application metadata."""
    return {
        "app": "Hydrus Digital BD API",
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
        "docs": "/api/docs",
    }


@app.get("/api/v1/tasks", response_model=list[TaskOut], tags=["Tasks"])
async def list_tasks(pool: asyncpg.Pool = Depends(get_db)):
    """Return all tasks ordered by creation time."""
    rows = await pool.fetch("SELECT * FROM tasks ORDER BY created_at DESC")
    return [dict(r) for r in rows]


@app.post("/api/v1/tasks", response_model=TaskOut, status_code=201, tags=["Tasks"])
async def create_task(body: TaskCreate, pool: asyncpg.Pool = Depends(get_db)):
    """Create a new task."""
    row = await pool.fetchrow(
        "INSERT INTO tasks (title) VALUES ($1) RETURNING *", body.title
    )
    return dict(row)


@app.patch("/api/v1/tasks/{task_id}", response_model=TaskOut, tags=["Tasks"])
async def update_task(
    task_id: int, body: TaskUpdate, pool: asyncpg.Pool = Depends(get_db)
):
    """Toggle task completion status."""
    row = await pool.fetchrow(
        "UPDATE tasks SET completed=$1 WHERE id=$2 RETURNING *",
        body.completed,
        task_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)


@app.delete("/api/v1/tasks/{task_id}", status_code=204, tags=["Tasks"])
async def delete_task(task_id: int, pool: asyncpg.Pool = Depends(get_db)):
    """Delete a task."""
    result = await pool.execute("DELETE FROM tasks WHERE id=$1", task_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Task not found")