"""Append only audit log (SQLite). Stores redacted queries and outcomes, never raw text."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from vigilix.config import SETTINGS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    endpoint TEXT NOT NULL,
    query_sha256 TEXT,
    redacted_query TEXT,
    redactions TEXT,
    intents TEXT,
    drugs TEXT,
    reactions TEXT,
    engine TEXT,
    evidence INTEGER,
    supported REAL,
    confidence TEXT,
    notices TEXT,
    latency_ms REAL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append only'); END;
"""


class AuditLog:
    def __init__(self, path: str | None = None):
        self.path = Path(path or SETTINGS.audit_db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with sqlite3.connect(self.path) as con:
            con.executescript(_SCHEMA)

    def record(self, endpoint: str, raw_query: str | None = None, result: dict | None = None, latency_ms: float | None = None, **extra) -> None:
        result = result or {}
        guard = result.get("guard", {})
        query = result.get("query", {})
        sents = [s for s in result.get("answer", []) if s.get("verification", {}).get("status") not in (None, "not_applicable")]
        sup = sum(1 for s in sents if s["verification"]["status"] == "supported") / len(sents) if sents else None
        row = (
            time.time(),
            endpoint,
            hashlib.sha256(raw_query.encode()).hexdigest() if raw_query else None,
            guard.get("redacted_text") or extra.get("redacted"),
            json.dumps(guard.get("redactions", extra.get("redactions", {}))),
            json.dumps(query.get("intents", [])),
            json.dumps(query.get("drugs", extra.get("drugs", []))),
            json.dumps(query.get("reactions", extra.get("reactions", []))),
            result.get("engine", extra.get("engine")),
            len(result.get("evidence", [])) if result else extra.get("evidence"),
            sup,
            (result.get("confidence") or {}).get("level"),
            json.dumps(result.get("notices", [])),
            latency_ms,
        )
        with self._lock, sqlite3.connect(self.path) as con:
            con.execute(
                "INSERT INTO audit (ts, endpoint, query_sha256, redacted_query, redactions, intents, drugs, reactions, engine, evidence, supported, confidence, notices, latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

    def recent(self, limit: int = 100) -> list[dict]:
        with sqlite3.connect(self.path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("redactions", "intents", "drugs", "reactions", "notices"):
                d[k] = json.loads(d[k]) if d[k] else None
            out.append(d)
        return out

    def stats(self) -> dict:
        with sqlite3.connect(self.path) as con:
            n, = con.execute("SELECT COUNT(*) FROM audit").fetchone()
            by_ep = dict(con.execute("SELECT endpoint, COUNT(*) FROM audit GROUP BY endpoint").fetchall())
        return {"entries": n, "by_endpoint": by_ep}
