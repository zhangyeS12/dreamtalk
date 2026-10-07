"""Rebuildable search projections; source rows remain the permission authority."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.types import UUIDStorage


class RecallDocumentRecord(Base):
    __tablename__ = "recall_documents"
    document_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    source_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(96), nullable=False)
    tokens: Mapped[str] = mapped_column(Text, nullable=False)
    vector_model: Mapped[str | None] = mapped_column(String(96))
    vector: Mapped[bytes | None] = mapped_column(LargeBinary)
    __table_args__ = (
        UniqueConstraint("world_id", "source_kind", "source_id", name="uq_recall_source"),
        CheckConstraint("source_kind IN ('memory','message')", name="ck_recall_source_kind"),
        CheckConstraint("vector IS NULL OR length(vector) = 2080", name="ck_recall_vector"),
    )


FTS_SQL = (
    "CREATE VIRTUAL TABLE recall_fts USING fts5(tokens, "
    "content='recall_documents', content_rowid='document_id', tokenize='unicode61')"
)
FTS_TABLES = {
    "recall_fts",
    "recall_fts_data",
    "recall_fts_idx",
    "recall_fts_docsize",
    "recall_fts_config",
}
FTS_TRIGGERS = {
    "recall_index_insert": """CREATE TRIGGER recall_index_insert AFTER INSERT ON recall_documents
BEGIN
    INSERT INTO recall_fts(rowid, tokens) VALUES (new.document_id, new.tokens);
END""",
    "recall_index_delete": """CREATE TRIGGER recall_index_delete AFTER DELETE ON recall_documents
BEGIN
    INSERT INTO recall_fts(recall_fts, rowid, tokens)
        VALUES ('delete', old.document_id, old.tokens);
END""",
    "recall_index_update": """CREATE TRIGGER recall_index_update
AFTER UPDATE OF tokens ON recall_documents
BEGIN
    INSERT INTO recall_fts(recall_fts, rowid, tokens)
        VALUES ('delete', old.document_id, old.tokens);
    INSERT INTO recall_fts(rowid, tokens) VALUES (new.document_id, new.tokens);
END""",
}
