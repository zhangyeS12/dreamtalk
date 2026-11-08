"""Read only committed outreach, with durable, idempotent Android notification IDs.

No transcript body, privacy spans, hidden lore, model inputs or secrets cross the
notification bridge. Row IDs are only local delivery cursors, not business IDs.
"""

import json
import sqlite3
from uuid import UUID

from livingworld.infrastructure.save_safety import atomic_json


def poll(root, host):
    database = root / "data/runtime.sqlite3"
    if not database.is_file():
        return 0
    marker = root / "notification-cursor.json"
    stat = database.stat()
    identity = f"{stat.st_dev}:{stat.st_ino}"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2) as connection:
        maximum = connection.execute("select coalesce(max(rowid),0) from chat_messages").fetchone()[
            0
        ]
        saved = json.loads(marker.read_text()) if marker.exists() else None
        if saved is None or saved.get("database") != identity:
            atomic_json(marker, {"database": identity, "rowid": maximum})
            return 0
        cursor = saved["rowid"]
        rows = connection.execute(
            """
            select m.rowid, m.world_id, m.message_id, m.conversation_id,
                   c.player_id, ch.name
            from chat_messages m
            join chat_turns t on t.world_id=m.world_id and t.turn_id=m.turn_id
            join chat_conversations c
              on c.world_id=m.world_id and c.conversation_id=m.conversation_id
            join local_player_bindings b
              on b.world_id=c.world_id and b.player_id=c.player_id
            join characters ch
              on ch.world_id=m.world_id and ch.character_id=m.sender_character_id
            where m.rowid > ? and t.kind='outreach' order by m.rowid limit 64
        """,
            (cursor,),
        ).fetchall()
    sent = 0
    for row, world, message, conversation, player, name in rows:
        payload = {
            "id": str(UUID(message)),
            "world_id": str(UUID(world)),
            "conversation_id": str(UUID(conversation)),
            "player_id": str(UUID(player)),
            "title": str(name)[:80],
            "body": "给你发来一条新消息",
        }
        if not host.isForeground():
            if not host.postContactNotification(json.dumps(payload, ensure_ascii=False)):
                break
            sent += 1
        cursor = row
        atomic_json(marker, {"database": identity, "rowid": cursor})
    else:
        if len(rows) < 64:
            atomic_json(marker, {"database": identity, "rowid": max(cursor, maximum)})
    return sent


def dispatch_notifications(operation, value, runtime):
    if operation == "notification_baseline":
        # Set a baseline while still in foreground, before enabling generation.
        poll(runtime._root, runtime._host)
        return True, None
    if operation == "background_tick":
        return True, poll(runtime._root, runtime._host)
    return False, None
