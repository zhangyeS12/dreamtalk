"""Add immutable Character episodic memory and normalized Observation evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0014_episodic_memory"
down_revision = "0013_sparse_simulation_activation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_memories",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("memory_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("owner_character_id", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("kind_version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_format", sa.String(24), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("experienced_from", sa.BigInteger(), nullable=False),
        sa.Column("experienced_to", sa.BigInteger(), nullable=False),
        sa.Column("formed_at", sa.BigInteger(), nullable=False),
        sa.Column("created_at_utc", sa.String(32), nullable=False),
        sa.Column("salience", sa.Integer(), nullable=True),
        sa.Column("provenance_kind", sa.String(32), nullable=False),
        sa.Column("provenance_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        sa.ForeignKeyConstraint(
            ["world_id", "owner_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        sa.CheckConstraint("kind = 'episodic'", name="ck_character_memory_kind"),
        sa.CheckConstraint(
            "typeof(kind_version) = 'integer' AND kind_version = 1",
            name="ck_character_memory_kind_version",
        ),
        sa.CheckConstraint(
            "length(trim(content)) > 0 AND length(CAST(content AS BLOB)) <= 16384",
            name="ck_character_memory_content",
        ),
        sa.CheckConstraint(
            "content_format = 'plain_text' AND content_version = 1",
            name="ck_character_memory_content_format",
        ),
        sa.CheckConstraint(
            "experienced_to >= experienced_from AND formed_at >= experienced_to",
            name="ck_character_memory_chronology",
        ),
        sa.CheckConstraint(
            "salience IS NULL OR (typeof(salience) = 'integer' AND salience BETWEEN 0 AND 100)",
            name="ck_character_memory_salience",
        ),
        sa.CheckConstraint(
            "provenance_kind = 'observation_evidence' AND provenance_version = 1",
            name="ck_character_memory_provenance",
        ),
    )
    op.create_index(
        "ix_character_memories_world_owner",
        "character_memories",
        ["world_id", "owner_character_id", "memory_id"],
    )
    op.create_index(
        "ix_character_memories_owner_experienced",
        "character_memories",
        ["world_id", "owner_character_id", "experienced_to", "formed_at", "memory_id"],
    )
    op.create_index(
        "ix_character_memories_owner_formed",
        "character_memories",
        ["world_id", "owner_character_id", "formed_at", "memory_id"],
    )
    op.create_table(
        "episodic_memory_observation_sources",
        sa.Column("world_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("memory_id", sa.String(32), nullable=False, primary_key=True),
        sa.Column("position", sa.BigInteger(), nullable=False, primary_key=True),
        sa.Column("observation_id", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_id", "memory_id"],
            ["character_memories.world_id", "character_memories.memory_id"],
        ),
        sa.ForeignKeyConstraint(
            ["world_id", "observation_id"],
            ["observations.world_id", "observations.observation_id"],
        ),
        sa.UniqueConstraint(
            "world_id",
            "memory_id",
            "observation_id",
            name="uq_episodic_memory_observation_source",
        ),
        sa.CheckConstraint(
            "typeof(position) = 'integer' AND position >= 0",
            name="ck_episodic_memory_source_position",
        ),
    )
    op.create_index(
        "ix_episodic_memory_source_observation",
        "episodic_memory_observation_sources",
        ["world_id", "observation_id", "memory_id"],
    )


def downgrade():
    raise RuntimeError("episodic_memory_downgrade_requires_review")
