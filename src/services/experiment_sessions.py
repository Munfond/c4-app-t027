"""Leased browser sessions with isolated, temporary worker queues and artifacts."""

import re
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager

from src.services import experiment_store as store

TTL_SECONDS = 180
CLOSE_GRACE_SECONDS = 30


def directory():
    return store.get_settings().experiment_root.resolve() / "browser-sessions"


@contextmanager
def connection():
    directory().mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(directory() / "leases.sqlite3", timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, expires REAL NOT NULL, closed INTEGER NOT NULL DEFAULT 0, inflight INTEGER NOT NULL DEFAULT 0, busy_until REAL NOT NULL DEFAULT 0, suspended INTEGER NOT NULL DEFAULT 0)")
        columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
        for name, definition in (("inflight", "INTEGER NOT NULL DEFAULT 0"), ("busy_until", "REAL NOT NULL DEFAULT 0"),
                                 ("suspended", "INTEGER NOT NULL DEFAULT 0")):
            if name not in columns:
                db.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
        yield db


def path(ident):
    if not re.fullmatch(r"[a-f0-9]{32}", ident):
        raise KeyError("Invalid session")
    target = (directory() / ident).resolve()
    if target.parent != directory().resolve():
        raise ValueError("Session path outside temporary workspace")
    return target


def create():
    sweep()
    ident = uuid.uuid4().hex
    expires = time.time() + TTL_SECONDS
    with connection() as db:
        db.execute("INSERT INTO sessions(id,expires) VALUES(?,?)", (ident, expires))
    path(ident).mkdir(parents=True, exist_ok=True)
    return {"id": ident, "expires_at": expires, "close_grace_seconds": CLOSE_GRACE_SECONDS}


def touch(ident, resume=True):
    with connection() as db:
        cursor = db.execute("UPDATE sessions SET expires=CASE WHEN suspended=0 OR ? THEN ? ELSE expires END,"
                            "suspended=CASE WHEN ? THEN 0 ELSE suspended END WHERE id=? AND closed=0 AND expires>?",
                            (resume, time.time() + TTL_SECONDS, resume, ident, time.time()))
        if cursor.rowcount != 1:
            raise KeyError("Session expired or ended")
    return path(ident)


def suspend(ident):
    # Refresh/new document can renew during this grace period; closing the tab cannot.
    with connection() as db:
        db.execute("UPDATE sessions SET suspended=1,expires=MIN(expires,?) WHERE id=? AND closed=0",
                   (time.time() + CLOSE_GRACE_SECONDS, ident))


def acquire(ident, renew=True):
    """Keep files alive through an in-flight request, including an awaited LLM call."""
    target = touch(ident, resume=False) if renew else path(ident)
    with connection() as db:
        row = db.execute("UPDATE sessions SET inflight=inflight+1,busy_until=? WHERE id=? AND closed=0 AND expires>?",
                         (time.time() + 120, ident, time.time()))
        if row.rowcount != 1:
            raise KeyError("Session ended")
    return target


def release(ident):
    with connection() as db:
        db.execute("UPDATE sessions SET inflight=MAX(0,inflight-1) WHERE id=?", (ident,))
    sweep()


def end(ident):
    path(ident)
    with connection() as db:
        db.execute("UPDATE sessions SET closed=1,expires=? WHERE id=?", (time.time(), ident))
    sweep()


def active():
    with connection() as db:
        return [path(row["id"]) for row in db.execute("SELECT id FROM sessions WHERE closed=0 AND expires>?", (time.time(),))]


def sweep():
    """Cancel expired jobs, wait for a worker to release files, then remove the full session."""
    with connection() as db:
        expired = [dict(row) for row in db.execute("SELECT * FROM sessions WHERE closed=1 OR expires<=?", (time.time(),))]
    for lease in expired:
        ident = lease["id"]
        target = path(ident)
        if target.exists():
            with store.scope(target), store.connection() as db:
                db.execute("UPDATE experiments SET cancelled=1,status='cancelled' WHERE status='queued'")
                db.execute("UPDATE experiments SET cancelled=1 WHERE status='running'")
                if lease["inflight"] and lease["busy_until"] > time.time():
                    continue
                # A crashed worker no longer holds files after the normal lease expires.
                db.execute("UPDATE experiments SET status='cancelled' WHERE status='running' AND heartbeat<?",
                           (time.time() - store.get_settings().experiment_lease_seconds,))
                if db.execute("SELECT 1 FROM experiments WHERE status='running'").fetchone():
                    continue
            # No worker owns this session; remove only its verified, generated directory.
            try:
                shutil.rmtree(target)
            except OSError:
                continue  # Windows may still be streaming a preview. Retry next sweep.
        with connection() as db:
            db.execute("DELETE FROM sessions WHERE id=?", (ident,))
