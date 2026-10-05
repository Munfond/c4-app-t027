from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.experiments import router as experiment_router
from src.api.lab import router as lab_router
from src.api.routes import router
from src.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    yield
    print("Shutting down...")


app = FastAPI(
    title="P-027 Perception Lab",
    description="nuScenes-mini lab and optional CARLA experiment API",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(experiment_router, prefix="/api/v1")
app.include_router(lab_router, prefix="/api/v1")
app.include_router(lab_router, prefix="/api")  # alias for /api/lab/...


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "P-027 Perception Lab API",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "scenes": "/api/v1/lab/scenes",
            "models": "/api/v1/lab/models",
            "benchmarks": "/api/v1/lab/benchmarks",
            "capabilities": "/api/v1/lab/capabilities",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
