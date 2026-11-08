"""World-local canonical positions; rowid is only legacy bootstrap evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0005_canonical_ledger"
down_revision = "0004_observation_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    ddl = connection.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name='world_events'")
    ).scalar_one()
    columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(world_events)"))}
    if "WITHOUT ROWID" in ddl.upper() or columns & {"rowid", "_rowid_", "oid"}:
        raise RuntimeError("legacy_event_insertion_order_unavailable")
    count, rowids = connection.execute(
        sa.text("SELECT count(*), count(DISTINCT _rowid_) FROM world_events")
    ).one()
    if count != rowids:
        raise RuntimeError("legacy_event_insertion_order_unavailable")
    triggers = {
        row[0]
        for row in connection.execute(
            sa.text(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='world_events'"
            )
        )
    }
    if triggers != {"world_events_no_update", "world_events_no_delete"}:
        raise RuntimeError("legacy_event_append_protection_mismatch")

    # Native ALTER preserves old rowids, payloads, FKs and DELETE protection.
    # UPDATE protection is replaced inside the same atomic migration transaction;
    # competing writers cannot observe the intermediate schema. Replay never does this.
    op.add_column(
        "world_events",
        sa.Column(
            "ledger_position",
            sa.BigInteger(),
            sa.CheckConstraint(
                "typeof(ledger_position) = 'integer' AND ledger_position > 0",
                name="ck_world_event_ledger_position",
            ),
            nullable=False,
            server_default="1",
        ),
    )
    op.execute("DROP TRIGGER world_events_no_update")
    connection.execute(
        sa.text(
            "WITH positions AS (SELECT _rowid_ AS legacy_rowid, "
            "row_number() OVER (PARTITION BY world_id ORDER BY _rowid_) "
            "AS position FROM world_events) "
            "UPDATE world_events SET ledger_position = "
            "(SELECT position FROM positions WHERE legacy_rowid = world_events._rowid_)"
        )
    )
    op.execute(
        "CREATE TRIGGER world_events_no_update BEFORE UPDATE ON world_events "
        "BEGIN SELECT RAISE(ABORT, 'world_event_immutable'); END"
    )
    op.create_index(
        "uq_world_event_ledger_position",
        "world_events",
        ["world_id", "ledger_position"],
        unique=True,
    )
    op.create_table(
        "world_ledger_cursors",
        sa.Column("world_id", sa.String(32), sa.ForeignKey("worlds.world_id"), primary_key=True),
        sa.Column("last_position", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "typeof(last_position) = 'integer' AND last_position >= 0",
            name="ck_world_ledger_cursor_position",
        ),
    )
    connection.execute(
        sa.text(
            "INSERT INTO world_ledger_cursors (world_id, last_position) "
            "SELECT worlds.world_id, coalesce(max(world_events.ledger_position), 0) FROM worlds "
            "LEFT JOIN world_events ON worlds.world_id = world_events.world_id "
            "GROUP BY worlds.world_id"
        )
    )


def downgrade() -> None:
    raise RuntimeError("canonical_ledger_downgrade_requires_review")
