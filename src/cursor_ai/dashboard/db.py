from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def from_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY,
          goal TEXT NOT NULL,
          status TEXT NOT NULL,
          model TEXT,
          base_url TEXT,
          started_at TEXT,
          ended_at TEXT,
          duration_s REAL,
          error TEXT,
          tool_calls INTEGER DEFAULT 0,
          messages INTEGER DEFAULT 0,
          prompt_tokens INTEGER,
          completion_tokens INTEGER,
          total_tokens INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
          run_id TEXT NOT NULL,
          ts TEXT NOT NULL,
          kind TEXT NOT NULL,
          content TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS preferences (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS features (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          description TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
          chat_id TEXT NOT NULL,
          ts TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pref_snapshots (
          id TEXT PRIMARY KEY,
          label TEXT,
          created_at TEXT NOT NULL,
          data TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_suites (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_cases (
          id TEXT PRIMARY KEY,
          suite_id TEXT NOT NULL,
          title TEXT NOT NULL,
          goal TEXT NOT NULL,
          rubric TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_runs (
          id TEXT PRIMARY KEY,
          suite_id TEXT NOT NULL,
          snapshot_id TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          started_at TEXT,
          ended_at TEXT,
          cases_total INTEGER DEFAULT 0,
          cases_done INTEGER DEFAULT 0,
          avg_duration_s REAL,
          avg_total_tokens REAL,
          total_tool_calls INTEGER DEFAULT 0,
          error TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_case_results (
          eval_run_id TEXT NOT NULL,
          case_id TEXT NOT NULL,
          status TEXT NOT NULL,
          output TEXT,
          duration_s REAL,
          prompt_tokens INTEGER,
          completion_tokens INTEGER,
          total_tokens INTEGER,
          tool_calls INTEGER DEFAULT 0,
          error TEXT,
          reviewed_verdict TEXT,
          reviewed_notes TEXT,
          reviewed_at TEXT,
          PRIMARY KEY (eval_run_id, case_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS improvements (
          id TEXT PRIMARY KEY,
          eval_run_id TEXT NOT NULL,
          snapshot_id TEXT NOT NULL,
          verdict TEXT NOT NULL,
          notes TEXT,
          verified_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


@dataclass(frozen=True)
class RunRow:
    id: str
    goal: str
    status: str
    model: str | None
    base_url: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_s: float | None
    error: str | None
    tool_calls: int
    messages: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None

    @staticmethod
    def from_row(r: sqlite3.Row) -> RunRow:
        return RunRow(
            id=r["id"],
            goal=r["goal"],
            status=r["status"],
            model=r["model"],
            base_url=r["base_url"],
            started_at=from_iso(r["started_at"]),
            ended_at=from_iso(r["ended_at"]),
            duration_s=r["duration_s"],
            error=r["error"],
            tool_calls=int(r["tool_calls"] or 0),
            messages=int(r["messages"] or 0),
            prompt_tokens=r["prompt_tokens"],
            completion_tokens=r["completion_tokens"],
            total_tokens=r["total_tokens"],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "model": self.model,
            "base_url": self.base_url,
            "started_at": to_iso(self.started_at),
            "ended_at": to_iso(self.ended_at),
            "duration_s": self.duration_s,
            "error": self.error,
            "tool_calls": self.tool_calls,
            "messages": self.messages,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


def insert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    goal: str,
    status: str,
    model: str | None,
    base_url: str | None,
    started_at: datetime | None,
) -> None:
    conn.execute(
        """
        INSERT INTO runs (id, goal, status, model, base_url, started_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, goal, status, model, base_url, to_iso(started_at)),
    )
    conn.commit()


def update_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    status: str | None = None,
    ended_at: datetime | None = None,
    duration_s: float | None = None,
    error: str | None = None,
    tool_calls: int | None = None,
    messages: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    for k, v in [
        ("status", status),
        ("ended_at", to_iso(ended_at) if ended_at else None),
        ("duration_s", duration_s),
        ("error", error),
        ("tool_calls", tool_calls),
        ("messages", messages),
        ("prompt_tokens", prompt_tokens),
        ("completion_tokens", completion_tokens),
        ("total_tokens", total_tokens),
    ]:
        if v is not None:
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return
    values.append(run_id)
    conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()


def get_run(conn: sqlite3.Connection, run_id: str) -> RunRow | None:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return RunRow.from_row(row) if row else None


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[RunRow]:
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [RunRow.from_row(r) for r in rows]


def insert_event(
    conn: sqlite3.Connection, *, run_id: str, ts: datetime, kind: str, content: str
) -> None:
    conn.execute(
        "INSERT INTO events (run_id, ts, kind, content) VALUES (?, ?, ?, ?)",
        (run_id, to_iso(ts), kind, content),
    )
    conn.commit()


def list_events(conn: sqlite3.Connection, run_id: str, limit: int = 500) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT ts, kind, content FROM events WHERE run_id = ? ORDER BY ts ASC LIMIT ?",
        (run_id, limit),
    ).fetchall()
    return [{"ts": r["ts"], "kind": r["kind"], "content": r["content"]} for r in rows]


def set_preference(conn: sqlite3.Connection, *, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO preferences (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, json.dumps(value, ensure_ascii=False), to_iso(utcnow())),
    )
    conn.commit()


def get_preference(conn: sqlite3.Connection, *, key: str) -> Any | None:
    row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return json.loads(row["value"])


def list_preferences(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM preferences").fetchall()
    out: dict[str, Any] = {}
    for r in rows:
        out[r["key"]] = json.loads(r["value"])
    return out


def insert_feature(
    conn: sqlite3.Connection,
    *,
    feature_id: str,
    title: str,
    description: str,
    status: str,
    now: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO features (id, title, description, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (feature_id, title, description, status, to_iso(now), to_iso(now)),
    )
    conn.commit()


def update_feature_status(
    conn: sqlite3.Connection, *, feature_id: str, status: str, now: datetime
) -> None:
    conn.execute(
        "UPDATE features SET status = ?, updated_at = ? WHERE id = ?",
        (status, to_iso(now), feature_id),
    )
    conn.commit()


def list_features(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        (
            "SELECT id, title, description, status, created_at, updated_at "
            "FROM features ORDER BY updated_at DESC LIMIT ?"
        ),
        (limit,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "description": r["description"],
            "status": r["status"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def insert_chat(conn: sqlite3.Connection, *, chat_id: str, now: datetime) -> None:
    conn.execute(
        "INSERT INTO chats (id, created_at) VALUES (?, ?)",
        (chat_id, to_iso(now)),
    )
    conn.commit()


def insert_chat_message(
    conn: sqlite3.Connection, *, chat_id: str, ts: datetime, role: str, content: str
) -> None:
    conn.execute(
        "INSERT INTO chat_messages (chat_id, ts, role, content) VALUES (?, ?, ?, ?)",
        (chat_id, to_iso(ts), role, content),
    )
    conn.commit()


def list_chat_messages(
    conn: sqlite3.Connection, *, chat_id: str, limit: int = 500
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT ts, role, content FROM chat_messages WHERE chat_id = ? ORDER BY ts ASC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [{"ts": r["ts"], "role": r["role"], "content": r["content"]} for r in rows]


def insert_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_id: str,
    label: str | None,
    created_at: datetime,
    data: Any,
) -> None:
    conn.execute(
        "INSERT INTO pref_snapshots (id, label, created_at, data) VALUES (?, ?, ?, ?)",
        (snapshot_id, label, to_iso(created_at), json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()


def get_snapshot(conn: sqlite3.Connection, snapshot_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, label, created_at, data FROM pref_snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "label": row["label"],
        "created_at": row["created_at"],
        "data": json.loads(row["data"]),
    }


def list_snapshots(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, label, created_at FROM pref_snapshots ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [{"id": r["id"], "label": r["label"], "created_at": r["created_at"]} for r in rows]


def insert_eval_suite(
    conn: sqlite3.Connection, *, suite_id: str, name: str, created_at: datetime
) -> None:
    conn.execute(
        "INSERT INTO eval_suites (id, name, created_at) VALUES (?, ?, ?)",
        (suite_id, name, to_iso(created_at)),
    )
    conn.commit()


def list_eval_suites(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, created_at FROM eval_suites ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "created_at": r["created_at"]} for r in rows]


def insert_eval_case(
    conn: sqlite3.Connection,
    *,
    case_id: str,
    suite_id: str,
    title: str,
    goal: str,
    rubric: str | None,
    now: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO eval_cases (id, suite_id, title, goal, rubric, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (case_id, suite_id, title, goal, rubric, to_iso(now), to_iso(now)),
    )
    conn.commit()


def list_eval_cases(
    conn: sqlite3.Connection, suite_id: str, limit: int = 500
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, suite_id, title, goal, rubric, created_at, updated_at
        FROM eval_cases
        WHERE suite_id = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (suite_id, limit),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "suite_id": r["suite_id"],
            "title": r["title"],
            "goal": r["goal"],
            "rubric": r["rubric"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def insert_eval_run(
    conn: sqlite3.Connection,
    *,
    eval_run_id: str,
    suite_id: str,
    snapshot_id: str,
    status: str,
    created_at: datetime,
    cases_total: int,
) -> None:
    conn.execute(
        """
        INSERT INTO eval_runs (id, suite_id, snapshot_id, status, created_at, cases_total)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (eval_run_id, suite_id, snapshot_id, status, to_iso(created_at), cases_total),
    )
    conn.commit()


def update_eval_run(
    conn: sqlite3.Connection,
    *,
    eval_run_id: str,
    status: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    cases_done: int | None = None,
    avg_duration_s: float | None = None,
    avg_total_tokens: float | None = None,
    total_tool_calls: int | None = None,
    error: str | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    for k, v in [
        ("status", status),
        ("started_at", to_iso(started_at) if started_at else None),
        ("ended_at", to_iso(ended_at) if ended_at else None),
        ("cases_done", cases_done),
        ("avg_duration_s", avg_duration_s),
        ("avg_total_tokens", avg_total_tokens),
        ("total_tool_calls", total_tool_calls),
        ("error", error),
    ]:
        if v is not None:
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return
    values.append(eval_run_id)
    conn.execute(f"UPDATE eval_runs SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()


def list_eval_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, suite_id, snapshot_id, status, created_at, started_at, ended_at,
               cases_total, cases_done, avg_duration_s, avg_total_tokens, total_tool_calls, error
        FROM eval_runs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_eval_run(conn: sqlite3.Connection, eval_run_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, suite_id, snapshot_id, status, created_at, started_at, ended_at,
               cases_total, cases_done, avg_duration_s, avg_total_tokens, total_tool_calls, error
        FROM eval_runs
        WHERE id = ?
        """,
        (eval_run_id,),
    ).fetchone()
    return dict(row) if row else None


def upsert_eval_case_result(
    conn: sqlite3.Connection,
    *,
    eval_run_id: str,
    case_id: str,
    status: str,
    output: str | None = None,
    duration_s: float | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    tool_calls: int | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO eval_case_results (
          eval_run_id, case_id, status, output, duration_s,
          prompt_tokens, completion_tokens, total_tokens, tool_calls, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(eval_run_id, case_id) DO UPDATE SET
          status = excluded.status,
          output = excluded.output,
          duration_s = excluded.duration_s,
          prompt_tokens = excluded.prompt_tokens,
          completion_tokens = excluded.completion_tokens,
          total_tokens = excluded.total_tokens,
          tool_calls = excluded.tool_calls,
          error = excluded.error
        """,
        (
            eval_run_id,
            case_id,
            status,
            output,
            duration_s,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            tool_calls,
            error,
        ),
    )
    conn.commit()


def review_eval_case_result(
    conn: sqlite3.Connection,
    *,
    eval_run_id: str,
    case_id: str,
    verdict: str,
    notes: str | None,
    reviewed_at: datetime,
) -> None:
    conn.execute(
        """
        UPDATE eval_case_results
        SET reviewed_verdict = ?, reviewed_notes = ?, reviewed_at = ?
        WHERE eval_run_id = ? AND case_id = ?
        """,
        (verdict, notes, to_iso(reviewed_at), eval_run_id, case_id),
    )
    conn.commit()


def list_eval_case_results(conn: sqlite3.Connection, eval_run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.eval_run_id, r.case_id, c.title, c.goal, c.rubric,
               r.status, r.output, r.duration_s, r.total_tokens, r.tool_calls, r.error,
               r.reviewed_verdict, r.reviewed_notes, r.reviewed_at
        FROM eval_case_results r
        JOIN eval_cases c ON c.id = r.case_id
        WHERE r.eval_run_id = ?
        ORDER BY c.created_at ASC
        """,
        (eval_run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_improvement(
    conn: sqlite3.Connection,
    *,
    improvement_id: str,
    eval_run_id: str,
    snapshot_id: str,
    verdict: str,
    notes: str | None,
    verified_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO improvements (id, eval_run_id, snapshot_id, verdict, notes, verified_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (improvement_id, eval_run_id, snapshot_id, verdict, notes, to_iso(verified_at)),
    )
    conn.commit()


def list_improvements(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, eval_run_id, snapshot_id, verdict, notes, verified_at
        FROM improvements
        ORDER BY verified_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
