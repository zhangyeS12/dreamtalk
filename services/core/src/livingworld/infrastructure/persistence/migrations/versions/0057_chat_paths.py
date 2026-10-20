"""Add chat paths without rewriting existing messages, turns or financial receipts."""

from alembic import op

revision = "0057_chat_paths"
down_revision = "0056_player_cards"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE chat_paths (
	world_id VARCHAR(32) NOT NULL,
	path_id VARCHAR(32) NOT NULL,
	conversation_id VARCHAR(32) NOT NULL,
	parent_id VARCHAR(32),
	fork_message_id VARCHAR(32),
	name VARCHAR(80) NOT NULL,
	kind VARCHAR(16) NOT NULL,
	created_at VARCHAR(32) NOT NULL,
	PRIMARY KEY (world_id, path_id),
        FOREIGN KEY(world_id, conversation_id) REFERENCES chat_conversations (world_id,
conversation_id),
	FOREIGN KEY(world_id, parent_id) REFERENCES chat_paths (world_id, path_id),
	FOREIGN KEY(world_id, fork_message_id) REFERENCES chat_messages (world_id, message_id),
        CONSTRAINT ck_chat_path_kind CHECK (kind IN
('main','branch','checkpoint','candidate','edit')),
	CONSTRAINT ck_chat_path_name CHECK (length(trim(name)) > 0 AND length(name) <= 80)
)""")
    op.execute(
        """CREATE INDEX ix_chat_path_conversation
ON chat_paths (world_id, conversation_id, created_at,
path_id)"""
    )
    op.execute("""CREATE TABLE chat_path_states (
	world_id VARCHAR(32) NOT NULL,
	conversation_id VARCHAR(32) NOT NULL,
	active_path_id VARCHAR(32) NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (world_id, conversation_id),
        FOREIGN KEY(world_id, conversation_id) REFERENCES chat_conversations (world_id,
conversation_id),
	FOREIGN KEY(world_id, active_path_id) REFERENCES chat_paths (world_id, path_id),
	CONSTRAINT ck_chat_path_revision CHECK (revision >= 0)
)""")
    op.execute("""CREATE TABLE chat_path_messages (
	world_id VARCHAR(32) NOT NULL,
	path_id VARCHAR(32) NOT NULL,
	message_id VARCHAR(32) NOT NULL,
	PRIMARY KEY (world_id, path_id, message_id),
	FOREIGN KEY(world_id, path_id) REFERENCES chat_paths (world_id, path_id),
	FOREIGN KEY(world_id, message_id) REFERENCES chat_messages (world_id, message_id)
)""")
    op.execute(
        """CREATE INDEX ix_chat_path_message_source
ON chat_path_messages (world_id, message_id, path_id)"""
    )
    op.execute("""CREATE TABLE chat_path_turns (
	world_id VARCHAR(32) NOT NULL,
	turn_id VARCHAR(32) NOT NULL,
	path_id VARCHAR(32) NOT NULL,
	PRIMARY KEY (world_id, turn_id),
	FOREIGN KEY(world_id, turn_id) REFERENCES chat_turns (world_id, turn_id),
	FOREIGN KEY(world_id, path_id) REFERENCES chat_paths (world_id, path_id)
)""")
    op.execute("""CREATE TABLE chat_path_operations (
	request_id VARCHAR(32) NOT NULL,
	world_id VARCHAR(32) NOT NULL,
	conversation_id VARCHAR(32) NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	result_json TEXT NOT NULL,
	PRIMARY KEY (request_id),
        FOREIGN KEY(world_id, conversation_id) REFERENCES chat_conversations (world_id,
conversation_id),
	CONSTRAINT ck_chat_path_operation CHECK (length(fingerprint) = 64 AND json_valid(result_json))
)""")
    op.execute("""CREATE TABLE chat_memory_origins (
	world_id VARCHAR(32) NOT NULL,
	entry_id VARCHAR(32) NOT NULL,
	message_id VARCHAR(32) NOT NULL,
	PRIMARY KEY (world_id, entry_id),
	FOREIGN KEY(world_id, entry_id) REFERENCES long_chat_memories (world_id, entry_id),
	FOREIGN KEY(world_id, message_id) REFERENCES chat_messages (world_id, message_id)
)""")
    op.execute("""CREATE TABLE chat_lore_activations (
	world_id VARCHAR(32) NOT NULL,
	conversation_id VARCHAR(32) NOT NULL,
	anchor_id VARCHAR(32) NOT NULL,
	entry_key VARCHAR(64) NOT NULL,
	started BOOLEAN NOT NULL,
	PRIMARY KEY (world_id, conversation_id, anchor_id, entry_key),
        FOREIGN KEY(world_id, conversation_id) REFERENCES chat_conversations (world_id,
conversation_id),
	FOREIGN KEY(world_id, anchor_id) REFERENCES chat_messages (world_id, message_id),
	CONSTRAINT ck_chat_lore_entry_key CHECK (length(entry_key) = 64)
)""")
    # Prior memory extraction used the reply's exact creation timestamp. Ambiguous
    # legacy origins stay unassigned and are not inherited by a new chat path.
    op.execute("""INSERT INTO chat_memory_origins (world_id, entry_id, message_id)
        SELECT m.world_id, m.entry_id, MIN(r.message_id)
        FROM long_chat_memories m JOIN chat_messages r
          ON r.world_id=m.world_id AND r.conversation_id=m.conversation_id
         AND r.created_at_utc=m.created_at AND r.sender_character_id IS NOT NULL
        GROUP BY m.world_id, m.entry_id HAVING COUNT(*)=1""")


def downgrade():
    raise RuntimeError("chat_path_downgrade_not_supported")
