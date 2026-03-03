"""SQLite persistence layer for web demo sessions and datasets."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB = Path(__file__).parent / "vis_demo.db"


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or _DEFAULT_DB)
        self._init_db()

    # ------------------------------------------------------------------ schema

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id   TEXT PRIMARY KEY,
                    filename     TEXT NOT NULL,
                    csv_path     TEXT NOT NULL,
                    column_info  TEXT NOT NULL,
                    row_count    INTEGER NOT NULL,
                    preview      TEXT NOT NULL,
                    created_at   REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id           TEXT PRIMARY KEY,
                    dataset_id           TEXT,
                    created_at           REAL NOT NULL,
                    last_activity        REAL NOT NULL,
                    chart_type           TEXT,
                    current_spec         TEXT,
                    spec_history         TEXT,
                    conversation_history TEXT,
                    iteration_records    TEXT,
                    final_report         TEXT
                );
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------------------------------------------------------------- datasets

    def save_dataset(
        self,
        dataset_id: str,
        filename: str,
        csv_path: str,
        column_info: Dict,
        row_count: int,
        preview: List,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO datasets
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    dataset_id,
                    filename,
                    csv_path,
                    json.dumps(column_info, ensure_ascii=False),
                    row_count,
                    json.dumps(preview, ensure_ascii=False),
                    time.time(),
                ),
            )

    def get_dataset(self, dataset_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "dataset_id": row["dataset_id"],
            "filename": row["filename"],
            "csv_path": row["csv_path"],
            "column_info": json.loads(row["column_info"]),
            "row_count": row["row_count"],
            "preview": json.loads(row["preview"]),
            "created_at": row["created_at"],
        }

    # ---------------------------------------------------------------- sessions

    def save_session(self, session_id: str, data: Dict) -> None:
        """Persist a clean (no base64) session snapshot."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    data.get("dataset_id"),
                    data.get("created_at", time.time()),
                    data.get("last_activity", time.time()),
                    data.get("chart_type", ""),
                    _json_safe(data.get("current_spec")),
                    _json_safe(data.get("spec_history", [])),
                    _json_safe(data.get("conversation_history", [])),
                    _json_safe(data.get("iteration_records", [])),
                    _json_safe(data.get("final_report")),
                ),
            )

    def update_session(self, session_id: str, **fields: Any) -> None:
        """Partial update of a session row."""
        allowed = {
            "last_activity",
            "chart_type",
            "current_spec",
            "spec_history",
            "conversation_history",
            "iteration_records",
            "final_report",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = [_json_safe(v) if isinstance(v, (dict, list)) else v for v in updates.values()]
        values.append(session_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE sessions SET {set_clause} WHERE session_id = ?", values
            )

    def get_session(self, session_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return _deserialize_session(row)

    def list_sessions(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT session_id, dataset_id, created_at, last_activity, chart_type
                   FROM sessions ORDER BY last_activity DESC"""
            ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "dataset_id": r["dataset_id"],
                "created_at": r["created_at"],
                "last_activity": r["last_activity"],
                "chart_type": r["chart_type"],
            }
            for r in rows
        ]

    def delete_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


# -------------------------------------------------------------------- helpers

def _json_safe(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(str(obj))


def _deserialize_session(row: sqlite3.Row) -> Dict:
    def _load(val):
        if val is None:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    return {
        "session_id": row["session_id"],
        "dataset_id": row["dataset_id"],
        "created_at": row["created_at"],
        "last_activity": row["last_activity"],
        "chart_type": row["chart_type"],
        "current_spec": _load(row["current_spec"]),
        "spec_history": _load(row["spec_history"]) or [],
        "conversation_history": _load(row["conversation_history"]) or [],
        "iteration_records": _load(row["iteration_records"]) or [],
        "final_report": _load(row["final_report"]),
    }


_db_instance: Optional[Database] = None


def get_db(db_path: str | None = None) -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance
