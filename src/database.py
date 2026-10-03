"""Database engine and session management for ADAS Lab."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import get_settings


def _normalize_db_url(url: str) -> str:
    """Normalize legacy postgres:// prefix to postgresql+psycopg2:// for SQLAlchemy 2.0+."""
    if not url:
        return "sqlite:///./data/app.db"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _normalize_db_url(get_settings().database_url)

# SQLite requires check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_db_available() -> bool:
    """Check whether database connection can be established."""
    try:
        with engine.connect() as conn:
            conn.execute(
                Base.metadata.tables and next(iter(Base.metadata.tables.values())).select().limit(1) or "SELECT 1"
            )
        return True
    except Exception:
        return False
