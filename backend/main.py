import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg

# ── Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── DATABASE CONFIGURATION

_DB_USER = os.getenv("DB_USER")
_DB_PASS = os.getenv("DB_PASSWORD")
_DB_HOST = os.getenv("DB_HOST", "hydrus-postgres")
_DB_NAME = os.getenv("DB_NAME", "hydrusdb")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:5432/{_DB_NAME}"
)


_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")]


# ── Connection Pool

db_pool: asyncpg.Pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    
    global db_pool
    logger.info("Connecting to database...")
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)

    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id        SERIAL PRIMARY KEY,
                title     TEXT    NOT NULL,
                completed BOOLEAN DEFAULT FALSE
            )
        """)
    logger.info("Database ready.")
    yield
    # Shutdown
    await db_pool.close()
    logger.info("Database pool closed.")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Schema
class Task(BaseModel):
    title: str

# ── Health Endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ── Readiness Endpoint — k8s readinessProbe
@app.get("/ready")
async def readiness_check():
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail=f"DB not reachable: {e}")

# ── API Endpoint
@app.get("/api/v1/tasks")
async def get_tasks():
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM tasks")

        if not rows:
            return [{"id": 0, "title": "No tasks found in DB", "completed": False}]

        return [dict(r) for r in rows]

    except Exception as e:
        logger.error(f"Failed to fetch tasks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
