from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_N = 20
MAX_N = 500


def escape_like(pattern: str) -> str:
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_turn(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "ts": row["ts"],
        "turn_id": row["turn_id"],
        "user": row["user_text"],
        "assistant": row["assistant_text"],
        "interrupted": bool(row["interrupted"]),
    }


class TurnStore:
    def __init__(self, path: Path, jsonl_dir: Path | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()
        self.import_jsonl_if_empty(jsonl_dir or (self.path.parent / "transcripts"))

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS turns (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ts TEXT NOT NULL,
                  turn_id TEXT NOT NULL,
                  user_text TEXT NOT NULL,
                  assistant_text TEXT NOT NULL,
                  interrupted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);
                """
            )
            self._conn.commit()

    def count(self, since: str | None = None, *, exclusive: bool = False) -> int:
        with self._lock:
            if since:
                op = ">" if exclusive else ">="
                row = self._conn.execute(
                    f"SELECT COUNT(*) FROM turns WHERE ts {op} ?", (since,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()
        return int(row[0]) if row else 0

    def append(
        self,
        turn_id: str,
        user_text: str,
        assistant_text: str,
        interrupted: bool = False,
        ts: str | None = None,
    ) -> None:
        stamp = ts or datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns (ts, turn_id, user_text, assistant_text, interrupted) "
                "VALUES (?, ?, ?, ?, ?)",
                (stamp, turn_id, user_text, assistant_text, int(interrupted)),
            )
            self._conn.commit()

    def import_jsonl_if_empty(self, folder: Path) -> int:
        if self.count() > 0 or not folder.is_dir():
            return 0
        imported = 0
        for path in sorted(folder.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self.append(
                    turn_id=str(item.get("turn_id") or ""),
                    user_text=str(item.get("user") or item.get("text") or ""),
                    assistant_text=str(item.get("assistant") or ""),
                    interrupted=bool(item.get("interrupted")),
                    ts=str(item.get("ts") or datetime.now().isoformat(timespec="seconds")),
                )
                imported += 1
        return imported

    def all_turns(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM turns ORDER BY ts ASC, id ASC"
            ).fetchall()
        return [_row_to_turn(row) for row in rows]

    def search(
        self,
        *,
        pattern: str | None = None,
        since: str | None = None,
        until: str | None = None,
        day: str | None = None,
        field: str = "both",
        n: int | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        limit = DEFAULT_N if n is None else int(n)
        limit = max(1, min(limit, MAX_N))
        direction = "ASC" if str(order).lower() == "asc" else "DESC"
        who = (field or "both").lower()
        if who not in {"user", "assistant", "both"}:
            who = "both"
        since_ts = since or None
        until_ts = until or None
        if day:
            try:
                parsed = date.fromisoformat(day)
            except ValueError as exc:
                raise ValueError(f"invalid day {day}") from exc
            start = f"{parsed.isoformat()}T00:00:00"
            end = (parsed + timedelta(days=1)).isoformat() + "T00:00:00"
            since_ts = start if since_ts is None else max(since_ts, start)
            until_ts = end if until_ts is None else min(until_ts, end)
        clauses: list[str] = []
        params: list[Any] = []
        if since_ts:
            clauses.append("ts >= ?")
            params.append(since_ts)
        if until_ts:
            clauses.append("ts < ?")
            params.append(until_ts)
        needle = (pattern or "").strip()
        if needle:
            like = f"%{escape_like(needle)}%"
            if who == "user":
                clauses.append("user_text LIKE ? ESCAPE '\\'")
                params.append(like)
            elif who == "assistant":
                clauses.append("assistant_text LIKE ? ESCAPE '\\'")
                params.append(like)
            else:
                clauses.append(
                    "(user_text LIKE ? ESCAPE '\\' OR assistant_text LIKE ? ESCAPE '\\')"
                )
                params.extend([like, like])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM turns{where} ORDER BY ts {direction}, id {direction} LIMIT ?"
        )
        params.append(limit + 1)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        truncated = len(rows) > limit
        turns = [_row_to_turn(row) for row in rows[:limit]]
        return {"turns": turns, "truncated": truncated}
