"""Database-only save protection; no directory replacement or snapshot catalog writes."""

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from livingworld.infrastructure.save_errors import SaveSafetyError


def identifier(value: object) -> str:
    """Only canonical SQLite identifiers may enter SQL; values always use parameters."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise SaveSafetyError("save_schema_invalid")
    return '"' + value + '"'


ACCOUNTING = (
    "llm_attempts",
    "llm_budgets",
    "llm_budget_reservations",
    "speech_call_receipts",
    "chat_media_caption_calls",
)

CONTENT_TABLES = {
    "chat_messages",
    "content_character_definitions",
    "content_worlds",
    "content_lore_entries",
    "content_lore_collections",
    "content_raw_imports",
    "voice_cards",
    "chat_media_assets",
    "world_covers",
}


def preserve_accounting(current: Path, restored: Path, *, replace_destination=False) -> None:
    """Story restoration must not roll back known costs, hard budgets or daily receipts."""
    if not current.is_file() and not replace_destination:
        return
    try:
        source = (
            sqlite3.connect(current.as_uri() + "?mode=ro", uri=True) if current.is_file() else None
        )
        destination = sqlite3.connect(restored)
        try:
            for table in ACCOUNTING:
                new_columns = destination.execute(
                    f"PRAGMA table_info({identifier(table)})"
                ).fetchall()
                if source is None:
                    if new_columns:
                        destination.execute(f"DELETE FROM {identifier(table)}")
                    continue
                old_columns = source.execute(f"PRAGMA table_info({identifier(table)})").fetchall()
                if not old_columns:
                    continue
                if not new_columns or [item[1] for item in old_columns] != [
                    item[1] for item in new_columns
                ]:
                    raise SaveSafetyError("save_financial_schema_incompatible")
                if replace_destination:
                    destination.execute(f"DELETE FROM {identifier(table)}")
                names = [item[1] for item in old_columns]
                keys = [item[1] for item in old_columns if item[5]]
                fields = ",".join(identifier(name) for name in names)
                conflict = ",".join(identifier(name) for name in keys)
                assignments = ",".join(
                    f"{identifier(name)}=excluded.{identifier(name)}"
                    for name in names
                    if name not in keys
                )
                placeholders = ",".join("?" for _ in names)
                statement = (
                    f"INSERT INTO {identifier(table)} ({fields}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({conflict}) DO UPDATE SET {assignments}"
                )
                destination.executemany(
                    statement, source.execute(f"SELECT {fields} FROM {identifier(table)}")
                )
            destination.commit()
        finally:
            if source is not None:
                source.close()
            destination.close()
    except sqlite3.DatabaseError:
        # Do not silently discard newer known spending or hard-budget reservations.
        raise SaveSafetyError("save_financial_metadata_unavailable") from None


def quarantine_restored_tasks(database: Path) -> None:
    """Only operational state changes; canonical history and message bodies stay intact."""
    connection = sqlite3.connect(database)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        if {"chat_turn_dispatches", "chat_reply_executions", "chat_turns"} <= tables:
            stamp = datetime.now(UTC).isoformat(timespec="microseconds")
            connection.execute(
                "INSERT OR IGNORE INTO chat_turn_dispatches(world_id,turn_id,claimed_at_utc) "
                "SELECT world_id,turn_id,? FROM chat_turns",
                (stamp,),
            )
            connection.execute(
                "INSERT OR IGNORE INTO chat_reply_executions(world_id,turn_id,state) "
                "SELECT world_id,turn_id,'unknown' FROM chat_turns"
            )
            connection.execute(
                "UPDATE chat_reply_executions SET state='unknown' WHERE state='running'"
            )
        for table in (
            "director_settings",
            "world_news_settings",
            "offline_contact_settings",
            "proactive_contact_settings",
        ):
            if table in tables:
                connection.execute(
                    f"UPDATE \"{table}\" SET enabled=0,state='off',revision=revision+1"
                )
        for table, states, has_error in (
            ("director_plans", ("planning",), True),
            ("world_news_batches", ("queued", "dispatched"), False),
            ("offline_contact_episodes", ("queued", "planning", "writing"), True),
            ("proactive_contact_episodes", ("writing",), True),
        ):
            if table in tables:
                placeholders = ",".join("?" for _ in states)
                error_assignment = ",error='save_restored'" if has_error else ""
                connection.execute(
                    f"UPDATE \"{table}\" SET state='interrupted'{error_assignment} "
                    f"WHERE state IN ({placeholders})",
                    states,
                )
        if "speech_jobs" in tables:
            connection.execute(
                "UPDATE speech_jobs SET state='interrupted',error='save_restored' "
                "WHERE state IN ('pending','queued','submitted','running','generating')"
            )
        if "chat_media_assets" in tables:
            connection.execute(
                "UPDATE chat_media_assets SET caption_state='failed' WHERE caption_state='running'"
            )
        if "chat_media_caption_calls" in tables:
            connection.execute(
                "UPDATE chat_media_caption_calls SET state='unknown' WHERE state='running'"
            )
        if "llm_budget_reservations" in tables:
            connection.execute(
                "UPDATE llm_budget_reservations SET status='held_uncertain' WHERE status='held'"
            )
        connection.commit()
    finally:
        connection.close()


def _verify_database_continuity(app_data: Path, saved_data: Path, *, frozen: bool) -> None:
    suffix = "?mode=ro&immutable=1" if frozen else "?mode=ro"
    source = sqlite3.connect((saved_data / "runtime.sqlite3").as_uri() + suffix, uri=True)
    current = sqlite3.connect((app_data / "data/runtime.sqlite3").as_uri() + "?mode=ro", uri=True)
    try:
        for schema, table, kind, *_ in source.execute("PRAGMA table_list"):
            if (
                schema != "main"
                or kind != "table"
                or table.startswith("sqlite_")
                or table == "alembic_version"
            ):
                continue
            if not re.fullmatch(r"[A-Za-z0-9_]+", table):
                raise SaveSafetyError("save_schema_invalid")
            primary = [
                item[1]
                for item in sorted(
                    source.execute(f"PRAGMA table_info({identifier(table)})"),
                    key=lambda item: item[5],
                )
                if item[5]
            ]
            if any(not re.fullmatch(r"[A-Za-z0-9_]+", field) for field in primary):
                raise SaveSafetyError("save_schema_invalid")
            if not primary:
                continue
            fields = ",".join(identifier(field) for field in primary)
            rows = source.execute(f"SELECT {fields} FROM {identifier(table)}")
            while batch := rows.fetchmany(256):
                placeholders = ",".join("(" + ",".join("?" for _ in primary) + ")" for _ in batch)
                found = set(
                    current.execute(
                        f"SELECT {fields} FROM {identifier(table)} "
                        f"WHERE ({fields}) IN ({placeholders})",
                        [part for row in batch for part in row],
                    )
                )
                if not set(batch) <= found:
                    raise SaveSafetyError("save_update_continuity_failed")
            if table in CONTENT_TABLES:
                # Stream one immutable-content row at a time, including BLOBs.
                # Nothing is logged or sent to a model; only equality is reported.
                columns = [
                    item[1]
                    for item in source.execute(f"PRAGMA table_info({identifier(table)})")
                    if not (table == "chat_media_assets" and item[1] == "caption_state")
                ]
                if any(not re.fullmatch(r"[A-Za-z0-9_]+", field) for field in columns):
                    raise SaveSafetyError("save_schema_invalid")
                names = ",".join(identifier(field) for field in columns)
                key_indices = [columns.index(field) for field in primary]
                predicate = " AND ".join(f"{identifier(field)}=?" for field in primary)
                for old in source.execute(f"SELECT {names} FROM {identifier(table)}"):
                    new = current.execute(
                        f"SELECT {names} FROM {identifier(table)} WHERE {predicate}",
                        [old[index] for index in key_indices],
                    ).fetchone()
                    if old != new:
                        raise SaveSafetyError("save_update_content_changed")
    finally:
        source.close()
        current.close()
