"""Persistent candidate search, authorized vector pages and incremental local indexing."""

from sqlalchemy import String, and_, case, cast, column, func, literal, or_, table, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from livingworld.infrastructure.persistence.long_memory_models import LongChatMemoryRecord as Memory
from livingworld.infrastructure.persistence.recall_index_models import (
    RecallDocumentRecord as Document,
)
from livingworld.infrastructure.semantic_chat_retrieval import VECTOR_MODEL_VERSION

_FTS = table("recall_fts", column("rowid"), column("rank"))
BACKFILL_PAGE = 64
VECTOR_PAGE = 512


def source_revision(model):
    return (
        model.fingerprint + literal(":") + cast(model.revision, String)
        if model is Memory
        else literal("immutable-v1")
    )


def row_revision(row, model):
    return f"{row.fingerprint}:{row.revision}" if model is Memory else "immutable-v1"


def source_id(model):
    return model.entry_id if model is Memory else model.message_id


def document_join(model):
    return and_(
        Document.world_id == model.world_id,
        Document.source_kind == ("memory" if model is Memory else "message"),
        Document.source_id == source_id(model),
        Document.source_revision == source_revision(model),
    )


class PersistentRecallIndex:
    def __init__(self, sessions, ranker):
        self.sessions, self.ranker = sessions, ranker

    async def backfill(self, session, authorized, model):
        # Start at the oldest unfinished source, including missing/old-model vectors.
        # There is no newest-8192 cutoff. Source authorization includes state/revision.
        stamp = model.created_at if model is Memory else model.created_at_utc
        return (
            await session.scalars(
                authorized.outerjoin(Document, document_join(model))
                .where(
                    or_(
                        Document.document_id.is_(None),
                        Document.vector.is_(None),
                        Document.vector_model != VECTOR_MODEL_VERSION,
                    )
                )
                .order_by(None)
                .order_by(Document.document_id.is_not(None), stamp, source_id(model))
                .limit(BACKFILL_PAGE)
            )
        ).all()

    async def lexical(self, session, authorized, model, terms, limit):
        if not terms:
            return []
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        # No global hit limit precedes the owner/source conditions. Unauthorized
        # matches cannot crowd out this character's candidates or return bodies.
        statement = (
            authorized.join(Document, document_join(model))
            .join(_FTS, _FTS.c.rowid == Document.document_id)
            .where(text("recall_fts MATCH :recall_match").bindparams(recall_match=match))
            .order_by(None)
            .order_by(_FTS.c.rank, source_id(model))
            .limit(limit)
        )
        indexed = (await session.scalars(statement)).all()
        if len(indexed) >= limit:
            return indexed
        fields = (Memory.topic, Memory.content, Memory.quote) if model is Memory else (model.text,)
        # Preserve keyword access during cold backfill. CASE prevents checking
        # historical bodies whose current revision already has a usable index.
        cold_match = case(
            (
                Document.document_id.is_(None),
                or_(*(field.contains(term, autoescape=True) for field in fields for term in terms)),
            ),
            else_=False,
        )
        stamp = model.created_at if model is Memory else model.created_at_utc
        unindexed = (
            await session.scalars(
                authorized.outerjoin(Document, document_join(model))
                .where(cold_match)
                .order_by(None)
                .order_by(stamp.desc(), source_id(model))
                .limit(limit - len(indexed))
            )
        ).all()
        return [*indexed, *unindexed]

    async def payloads(self, session, authorized, model, identities):
        if not identities:
            return {}
        statement = (
            authorized.with_only_columns(source_id(model), Document.vector)
            .join(Document, document_join(model))
            .where(
                source_id(model).in_(identities),
                Document.vector_model == VECTOR_MODEL_VERSION,
                Document.vector.is_not(None),
            )
            .order_by(None)
        )
        return dict((await session.execute(statement)).all())

    async def vector_batches(self, session, authorized, model):
        statement = (
            authorized.with_only_columns(source_id(model), Document.vector)
            .join(Document, document_join(model))
            .where(Document.vector_model == VECTOR_MODEL_VERSION, Document.vector.is_not(None))
            .order_by(None)
            .order_by(Document.document_id)
            .execution_options(yield_per=VECTOR_PAGE)
        )
        result = await session.stream(statement)
        try:
            async for rows in result.partitions(VECTOR_PAGE):
                yield rows
        finally:
            await result.close()

    async def save(self, authorized, model, candidates, payloads):
        if not candidates:
            return True
        token_method = getattr(self.ranker, "tokenize_documents", None)
        if token_method is None:
            return False
        tokens = await token_method(tuple(item.text for item in candidates))
        payloads = dict(payloads)
        identity = source_id(model)
        expected = {
            (item.row.entry_id if model is Memory else item.row.message_id): (item, token)
            for item, token in zip(candidates, tokens, strict=True)
        }
        try:
            # A separate short write transaction revalidates every source. It
            # never changes chat, memory status, knowledge or the canonical ledger.
            async with self.sessions() as writer, writer.begin():
                await writer.connection(execution_options={"livingworld_write_intent": True})
                identities = tuple(expected)
                for offset in range(0, len(identities), 128):
                    rows = (
                        await writer.scalars(
                            authorized.where(identity.in_(identities[offset : offset + 128]))
                        )
                    ).all()
                    values = []
                    for row in rows:
                        item, token = expected[row.entry_id if model is Memory else row.message_id]
                        if row_revision(row, model) != row_revision(item.row, model):
                            continue
                        payload = payloads.get(item.index_key)
                        values.append(
                            {
                                "world_id": row.world_id,
                                "source_kind": "memory" if model is Memory else "message",
                                "source_id": row.entry_id if model is Memory else row.message_id,
                                "source_revision": row_revision(row, model),
                                "tokens": token,
                                "vector_model": VECTOR_MODEL_VERSION if payload else None,
                                "vector": payload,
                            }
                        )
                    if not values:
                        continue
                    statement = insert(Document).values(values)
                    incoming = statement.excluded
                    same = Document.source_revision == incoming.source_revision
                    await writer.execute(
                        statement.on_conflict_do_update(
                            index_elements=[
                                Document.world_id,
                                Document.source_kind,
                                Document.source_id,
                            ],
                            set_={
                                "source_revision": incoming.source_revision,
                                "tokens": incoming.tokens,
                                "vector_model": case(
                                    (
                                        same,
                                        func.coalesce(incoming.vector_model, Document.vector_model),
                                    ),
                                    else_=incoming.vector_model,
                                ),
                                "vector": case(
                                    (same, func.coalesce(incoming.vector, Document.vector)),
                                    else_=incoming.vector,
                                ),
                            },
                            where=or_(
                                ~same,
                                Document.tokens != incoming.tokens,
                                and_(
                                    incoming.vector.is_not(None),
                                    or_(
                                        Document.vector.is_(None),
                                        Document.vector_model != incoming.vector_model,
                                    ),
                                ),
                            ),
                        )
                    )
            return True
        except SQLAlchemyError:
            # This rebuildable projection cannot turn an otherwise valid reply
            # into a failed canonical operation. Coverage remains partial.
            return False
