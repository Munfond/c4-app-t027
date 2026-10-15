"""Versioned remote queue schema and the small SQL surface shared with local studies.

No Lab tables are modified. Initialize explicitly with scripts.init_remote_worker.
PostgreSQL serializes admission/claim with a transaction-scoped advisory lock.
"""

import re
from collections.abc import Mapping
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text, create_engine, text

from src.config import get_settings

metadata = MetaData()
Table("remote_schema", metadata, Column("version", Integer, primary_key=True))
Table("remote_experiments", metadata,
      Column("id", String(32), primary_key=True), Column("key", String(160), unique=True),
      Column("fingerprint", String(64), nullable=False), Column("spec", Text, nullable=False),
      Column("status", String(20), nullable=False), Column("stage", Text, nullable=False),
      Column("created", Float(53), nullable=False), Column("heartbeat", Float(53)),
      Column("owner", Text), Column("cancelled", Integer, nullable=False, server_default="0"),
      Column("result", Text), Column("error", Text), Column("progress", Text))
Table("remote_sensor_studies", metadata,
      Column("id", String(32), primary_key=True), Column("spec", Text, nullable=False),
      Column("created", Float(53), nullable=False), Column("checkpoint", String(64), nullable=False),
      Column("metadata", Text, nullable=False), Column("summary", Text),
      Column("cancelled", Integer, nullable=False, server_default="0"))
Table("remote_sensor_study_jobs", metadata,
      Column("study_id", String(32), primary_key=True), Column("ordinal", Integer, primary_key=True),
      Column("job_id", String(32), nullable=False, unique=True))
Table("remote_workers", metadata,
      Column("id", String(64), primary_key=True), Column("heartbeat", Float(53), nullable=False),
      Column("capabilities", Text, nullable=False), Column("active_job", String(32)))
Table("remote_artifacts", metadata,
      Column("job_id", String(32), primary_key=True), Column("path", String(160), primary_key=True),
      Column("owner", Text, nullable=False), Column("bytes", Integer, nullable=False),
      Column("sha256", String(64), nullable=False), Column("object_key", Text, nullable=False))
Table("remote_reviews", metadata,
      Column("id", String(32), primary_key=True), Column("study_id", String(100), nullable=False),
      Column("created", Float(53), nullable=False), Column("evidence_sha256", String(64), nullable=False),
      Column("payload", Text, nullable=False), Column("snapshot", Text, nullable=False))


@lru_cache(maxsize=4)
def engine(url):
    if not url:
        raise RuntimeError("REMOTE_DATABASE_URL is required")
    if get_settings().app_env == "production" and not url.startswith(("postgres://", "postgresql://", "postgresql+")):
        raise RuntimeError("Production remote queues require PostgreSQL, not an ephemeral local database")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return create_engine(url, pool_pre_ping=True,
                         connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})


def initialize(url=None):
    target = engine(url or get_settings().remote_database_url)
    metadata.create_all(target)
    with target.begin() as db:
        versions = list(db.execute(text("SELECT version FROM remote_schema")).scalars())
        if versions and versions != [1]:
            raise RuntimeError("Unsupported remote schema version")
        if not versions:
            db.execute(text("INSERT INTO remote_schema(version) VALUES(1)"))


class Row(Mapping):
    def __init__(self, value):
        self.value = value

    def __getitem__(self, key):
        return self.value[key] if isinstance(key, int) else self.value._mapping[key]

    def __iter__(self):
        return iter(self.value._mapping)

    def __len__(self):
        return len(self.value)


class Result:
    def __init__(self, result=None):
        self.result = result
        self.rowcount = result.rowcount if result is not None else 0

    def fetchone(self):
        row = self.result.fetchone() if self.result is not None else None
        return Row(row) if row is not None else None

    def __iter__(self):
        return (Row(row) for row in self.result) if self.result is not None else iter(())


class Connection:
    def __init__(self, db):
        self.db = db

    def execute(self, sql, params=()):
        if sql.lstrip().startswith("CREATE TABLE"):
            return Result()  # Tables are owned by the explicit versioned migration.
        if sql == "BEGIN IMMEDIATE":
            if self.db.dialect.name == "postgresql":
                self.db.execute(text("SELECT pg_advisory_xact_lock(2701501)"))
            elif self.db.dialect.name == "sqlite":
                self.db.exec_driver_sql("BEGIN IMMEDIATE")
            return Result()
        for source, target in (("experiments", "remote_experiments"),
                               ("sensor_studies", "remote_sensor_studies"),
                               ("sensor_study_jobs", "remote_sensor_study_jobs"),
                               ("agent_reviews", "remote_reviews")):
            sql = re.sub(r"\b" + source + r"\b", target, sql)
        if "INSERT OR IGNORE" in sql:
            sql = sql.replace("INSERT OR IGNORE", "INSERT") + " ON CONFLICT DO NOTHING"
        if self.db.dialect.name == "postgresql":
            sql = sql.replace("json_extract(spec, '$.purpose')", "(CAST(spec AS JSONB)->>'purpose')")
        values = {}
        for i, value in enumerate(params):
            sql = sql.replace("?", f":p{i}", 1)
            values[f"p{i}"] = value
        return Result(self.db.execute(text(sql), values))

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()


@contextmanager
def connection():
    target = engine(get_settings().remote_database_url)
    with target.connect() as db:
        version = db.execute(text("SELECT version FROM remote_schema")).scalar()
        if version != 1:
            raise RuntimeError("Run python -m scripts.init_remote_worker before enabling remote mode")
        try:
            yield Connection(db)
            db.commit()
        except BaseException:
            db.rollback()
            raise
