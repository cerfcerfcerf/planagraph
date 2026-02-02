from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Iterable, Optional

DB_DEFAULT_PATH = "plangraph.db"


def get_db_path() -> str:
    env_path = os.getenv("DB_PATH", DB_DEFAULT_PATH)
    if os.path.isabs(env_path):
        return env_path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, env_path)


def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def init_db() -> None:
    path = get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                today TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                date TEXT,
                start_time TEXT,
                end_time TEXT,
                duration_min INTEGER NOT NULL,
                priority INTEGER NOT NULL,
                location TEXT,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                task_state TEXT NOT NULL DEFAULT 'pending',
                placement_hint TEXT,
                time_pref TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(id)
            );
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                day_start TEXT NOT NULL,
                day_end TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS planned_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                item_id INTEGER,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                date TEXT,
                start_time TEXT,
                end_time TEXT,
                duration_min INTEGER NOT NULL,
                priority INTEGER NOT NULL,
                location TEXT,
                notes TEXT,
                planned_start TEXT,
                planned_end TEXT,
                status TEXT NOT NULL,
                reason TEXT,
                FOREIGN KEY(plan_id) REFERENCES plans(id),
                FOREIGN KEY(item_id) REFERENCES items(id)
            );
            CREATE TABLE IF NOT EXISTS reminder_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                lead_min INTEGER NOT NULL,
                enabled INTEGER NOT NULL,
                default_time TEXT,
                target_per_week INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminder_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                item_id INTEGER,
                plan_id INTEGER,
                due_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                status TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                snoozed_until TEXT,
                FOREIGN KEY(rule_id) REFERENCES reminder_rules(id),
                FOREIGN KEY(item_id) REFERENCES items(id),
                FOREIGN KEY(plan_id) REFERENCES plans(id)
            );
            CREATE TABLE IF NOT EXISTS reminder_suppressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suppression_key TEXT NOT NULL UNIQUE,
                rule_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(rule_id) REFERENCES reminder_rules(id)
            );
            CREATE TABLE IF NOT EXISTS completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                rule_id INTEGER,
                completed_at TEXT NOT NULL,
                meta_json TEXT,
                FOREIGN KEY(item_id) REFERENCES items(id),
                FOREIGN KEY(rule_id) REFERENCES reminder_rules(id)
            );
            """
        )
        ensure_column(conn, "items", "task_state", "TEXT NOT NULL DEFAULT 'pending'")
        ensure_column(conn, "items", "placement_hint", "TEXT")
        conn.execute("UPDATE items SET task_state = 'pending' WHERE task_state IS NULL")
        conn.commit()


def insert_entry(text: str, today: Optional[str]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO entries (text, today, created_at) VALUES (?, ?, ?)",
            (text, today, now_iso()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def insert_items(entry_id: int, items: Iterable[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    with get_connection() as conn:
        for item in items:
            cursor = conn.execute(
                """
                INSERT INTO items
                (entry_id, title, type, date, start_time, end_time, duration_min, priority, location, notes, status,
                 task_state, placement_hint, time_pref, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    item.get("title"),
                    item.get("type"),
                    item.get("date"),
                    item.get("start_time"),
                    item.get("end_time"),
                    item.get("duration_min"),
                    item.get("priority"),
                    item.get("location"),
                    item.get("notes"),
                    item.get("status", "pending"),
                    item.get("task_state", "pending"),
                    item.get("placement_hint"),
                    item.get("time_pref"),
                    item.get("created_at") or now_iso(),
                ),
            )
            ids.append(int(cursor.lastrowid))
        conn.commit()
    return ids


def insert_task(task: dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO items
            (entry_id, title, type, date, start_time, end_time, duration_min, priority, location, notes, status,
             task_state, placement_hint, time_pref, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                task.get("title"),
                task.get("type"),
                task.get("date"),
                task.get("start_time"),
                task.get("end_time"),
                task.get("duration_min"),
                task.get("priority"),
                task.get("location"),
                task.get("notes"),
                task.get("status", "pending"),
                task.get("task_state", "pending"),
                task.get("placement_hint"),
                task.get("time_pref"),
                now_iso(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_tasks(
    date_from: Optional[str],
    date_to: Optional[str],
    status: Optional[str],
    item_type: Optional[str],
    query: Optional[str],
) -> list[sqlite3.Row]:
    sql = """
        SELECT items.*,
            (
                SELECT MIN(re.due_at)
                FROM reminder_events re
                WHERE re.item_id = items.id
                  AND re.status = 'pending'
            ) AS next_reminder_at
        FROM items
    """
    clauses = []
    params: list[Any] = []
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)
    if status:
        clauses.append("task_state = ?")
        params.append(status)
    if item_type:
        clauses.append("type = ?")
        params.append(item_type)
    if query:
        clauses.append("(title LIKE ? OR notes LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date ASC, start_time ASC, created_at DESC"
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_task(task_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM items WHERE id = ?", (task_id,)).fetchone()


def update_task(task_id: int, fields: dict[str, Any]) -> None:
    if not fields:
        return
    assignments = []
    params: list[Any] = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        params.append(value)
    params.append(task_id)
    sql = f"UPDATE items SET {', '.join(assignments)} WHERE id = ?"
    with get_connection() as conn:
        conn.execute(sql, params)
        conn.commit()


def delete_task(task_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM planned_items WHERE item_id = ?", (task_id,))
        conn.execute("DELETE FROM reminder_events WHERE item_id = ?", (task_id,))
        conn.execute("DELETE FROM items WHERE id = ?", (task_id,))
        conn.commit()


def complete_task(task_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE items SET task_state = 'completed' WHERE id = ?", (task_id,))
        conn.commit()


def update_item_status(item_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
        conn.commit()


def update_item_state(item_id: int, state: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE items SET task_state = ? WHERE id = ?", (state, item_id))
        conn.commit()


def insert_plan(day: str, day_start: str, day_end: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO plans (day, day_start, day_end, created_at) VALUES (?, ?, ?, ?)",
            (day, day_start, day_end, now_iso()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def insert_planned_items(plan_id: int, planned_items: Iterable[dict[str, Any]]) -> None:
    with get_connection() as conn:
        for item in planned_items:
            conn.execute(
                """
                INSERT INTO planned_items
                (plan_id, item_id, title, type, date, start_time, end_time, duration_min, priority, location, notes,
                 planned_start, planned_end, status, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    item.get("id"),
                    item.get("title"),
                    item.get("type"),
                    item.get("date"),
                    item.get("start_time"),
                    item.get("end_time"),
                    item.get("duration_min"),
                    item.get("priority"),
                    item.get("location"),
                    item.get("notes"),
                    item.get("planned_start"),
                    item.get("planned_end"),
                    item.get("status"),
                    item.get("reason"),
                ),
            )
        conn.commit()


def insert_reminder_event(event: dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reminder_events
            (rule_id, item_id, plan_id, due_at, kind, title, body, status, reason, created_at, delivered_at, snoozed_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("rule_id"),
                event.get("item_id"),
                event.get("plan_id"),
                event.get("due_at"),
                event.get("kind"),
                event.get("title"),
                event.get("body"),
                event.get("status"),
                event.get("reason"),
                event.get("created_at"),
                event.get("delivered_at"),
                event.get("snoozed_until"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_due_reminders(now_iso_value: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT re.*, items.title AS related_item_title
            FROM reminder_events re
            LEFT JOIN items ON items.id = re.item_id
            WHERE re.status = 'pending'
              AND re.due_at <= ?
            ORDER BY re.due_at ASC
            """,
            (now_iso_value,),
        ).fetchall()


def update_reminder_status(reminder_id: int, status: str, delivered_at: Optional[str], snoozed_until: Optional[str]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminder_events
            SET status = ?, delivered_at = ?, snoozed_until = ?
            WHERE id = ?
            """,
            (status, delivered_at, snoozed_until, reminder_id),
        )
        conn.commit()


def update_reminder_schedule(reminder_id: int, due_at: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminder_events
            SET due_at = ?, status = ?, snoozed_until = NULL
            WHERE id = ?
            """,
            (due_at, status, reminder_id),
        )
        conn.commit()


def insert_completion(item_id: Optional[int], rule_id: Optional[int], meta: Optional[dict[str, Any]]) -> None:
    meta_json = json.dumps(meta) if meta else None
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO completions (item_id, rule_id, completed_at, meta_json) VALUES (?, ?, ?, ?)",
            (item_id, rule_id, now_iso(), meta_json),
        )
        conn.commit()


def upsert_reminder_rule(rule: dict[str, Any]) -> int:
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM reminder_rules WHERE key = ?",
            (rule.get("key"),),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE reminder_rules
                SET title = ?, lead_min = ?, enabled = ?, default_time = ?, target_per_week = ?
                WHERE id = ?
                """,
                (
                    rule.get("title"),
                    rule.get("lead_min"),
                    1 if rule.get("enabled") else 0,
                    rule.get("default_time"),
                    rule.get("target_per_week"),
                    existing["id"],
                ),
            )
            conn.commit()
            return int(existing["id"])
        cursor = conn.execute(
            """
            INSERT INTO reminder_rules
            (key, title, lead_min, enabled, default_time, target_per_week, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rule.get("key"),
                rule.get("title"),
                rule.get("lead_min"),
                1 if rule.get("enabled") else 0,
                rule.get("default_time"),
                rule.get("target_per_week"),
                now_iso(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_reminder_rules() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM reminder_rules ORDER BY created_at DESC").fetchall()


def list_recent_completions(rule_id: int, limit: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT completed_at
            FROM completions
            WHERE rule_id = ?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (rule_id, limit),
        ).fetchall()


def count_week_completions(rule_id: int, week_start: str, week_end: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM completions
            WHERE rule_id = ?
              AND completed_at >= ?
              AND completed_at < ?
            """,
            (rule_id, week_start, week_end),
        ).fetchone()
        return int(row["count"])


def history_entries(limit: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT e.*, COUNT(i.id) AS item_count
            FROM entries e
            LEFT JOIN items i ON i.entry_id = e.id
            GROUP BY e.id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def history_plans(limit: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT p.*, 
                SUM(CASE WHEN pi.status = 'scheduled' THEN 1 ELSE 0 END) AS planned_count,
                SUM(CASE WHEN pi.status = 'unscheduled' THEN 1 ELSE 0 END) AS unscheduled_count
            FROM plans p
            LEFT JOIN planned_items pi ON pi.plan_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_reminder(reminder_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM reminder_events WHERE id = ?",
            (reminder_id,),
        ).fetchone()


def list_reminders_between(start_iso: str, end_iso: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT re.*, items.title AS related_item_title
            FROM reminder_events re
            LEFT JOIN items ON items.id = re.item_id
            WHERE re.status = 'pending'
              AND re.due_at > ?
              AND re.due_at <= ?
            ORDER BY re.due_at ASC
            """,
            (start_iso, end_iso),
        ).fetchall()


def has_plan_for_day(day: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM plans WHERE day = ? ORDER BY created_at DESC LIMIT 1",
            (day,),
        ).fetchone()
        return bool(row)


def insert_suppression(suppression_key: str, rule_id: Optional[int]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO reminder_suppressions (suppression_key, rule_id, created_at)
            VALUES (?, ?, ?)
            """,
            (suppression_key, rule_id, now_iso()),
        )
        conn.commit()


def is_suppressed(suppression_key: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM reminder_suppressions WHERE suppression_key = ?",
            (suppression_key,),
        ).fetchone()
        return bool(row)


def suppress_item_reminders(item_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE reminder_events SET status = 'cancelled_forever' WHERE item_id = ? AND status = 'pending'",
            (item_id,),
        )
        conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
