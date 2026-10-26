"""Durable, reversible overlays for authored character-card fields."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update

from livingworld.application.errors import EntityNotFoundError
from livingworld.domain.identifiers import WorldId
from livingworld.infrastructure.persistence.models import (
    CharacterCardEvolutionRecord,
    WorldContentImportRecord,
    WorldRecord,
)


class CharacterEvolutionStore:
    def __init__(self, sessions):
        self._sessions = sessions

    @staticmethod
    async def _root_import_id(session, world: WorldId, import_id: UUID) -> UUID:
        rows = list(
            await session.scalars(
                select(WorldContentImportRecord).where(
                    WorldContentImportRecord.world_id == world.value,
                    WorldContentImportRecord.kind == "character",
                )
            )
        )
        by_id = {row.import_id: row for row in rows}
        current = import_id
        seen: set[UUID] = set()
        while True:
            if current in seen or current not in by_id:
                raise EntityNotFoundError("character_card_not_found")
            seen.add(current)
            predecessor = by_id[current].replaces_import_id
            if predecessor is None:
                return current
            current = predecessor

    async def list(
        self,
        world: WorldId,
        root_import_id: UUID,
        scopes: tuple[str, ...] | None = None,
    ) -> list[dict]:
        async with self._sessions() as session:
            if await session.get(WorldRecord, world.value) is None:
                raise EntityNotFoundError("world_not_found")
            root_import_id = await self._root_import_id(session, world, root_import_id)
            statement = select(CharacterCardEvolutionRecord).where(
                CharacterCardEvolutionRecord.world_id == world.value,
                CharacterCardEvolutionRecord.root_import_id == root_import_id,
            )
            if scopes is not None:
                statement = statement.where(
                    CharacterCardEvolutionRecord.scope.in_(scopes),
                    CharacterCardEvolutionRecord.selected.is_(True),
                    CharacterCardEvolutionRecord.state == "active",
                )
            rows = await session.scalars(
                statement.order_by(
                    CharacterCardEvolutionRecord.field,
                    CharacterCardEvolutionRecord.scope,
                    CharacterCardEvolutionRecord.created_at_utc,
                    CharacterCardEvolutionRecord.entry_id,
                )
            )
            return [self._view(row) for row in rows]

    async def change(
        self,
        world: WorldId,
        root_import_id: UUID,
        *,
        field: str,
        scope: str,
        text: str,
        operation: str,
        entry_id: UUID | None,
        locked: bool,
        source: str,
    ) -> dict:
        fields = {"description", "personality", "background", "scenario", "speech_guidance"}
        scope = scope.strip()
        if field not in fields or not scope or len(scope) > 120:
            raise ValueError("character_evolution_field_invalid")
        if len(text) > 4000:
            raise ValueError("character_evolution_capacity")
        if operation not in {"add", "select", "deactivate", "restore", "lock", "unlock"}:
            raise ValueError("character_evolution_operation_invalid")
        if operation == "add" and not text.strip():
            raise ValueError("character_evolution_text_empty")
        if source not in {"user", "model", "import"}:
            raise ValueError("character_evolution_source_invalid")
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if await session.get(WorldRecord, world.value) is None:
                raise EntityNotFoundError("world_not_found")
            root_import_id = await self._root_import_id(session, world, root_import_id)
            imported = await session.get(WorldContentImportRecord, root_import_id)
            if imported is None or imported.world_id != world.value or imported.kind != "character":
                raise EntityNotFoundError("character_card_not_found")
            rows = list(
                await session.scalars(
                    select(CharacterCardEvolutionRecord).where(
                        CharacterCardEvolutionRecord.world_id == world.value,
                        CharacterCardEvolutionRecord.root_import_id == root_import_id,
                        CharacterCardEvolutionRecord.field == field,
                        CharacterCardEvolutionRecord.scope == scope,
                    )
                )
            )
            selected = next((row for row in rows if row.selected), None)
            if (
                selected is not None
                and selected.locked
                and operation
                in {
                    "add",
                    "select",
                    "deactivate",
                    "restore",
                }
            ):
                raise ValueError("character_evolution_locked")
            target = next(
                (row for row in rows if entry_id is not None and row.entry_id == entry_id), None
            )
            if operation == "add":
                await session.execute(
                    update(CharacterCardEvolutionRecord)
                    .where(
                        CharacterCardEvolutionRecord.world_id == world.value,
                        CharacterCardEvolutionRecord.root_import_id == root_import_id,
                        CharacterCardEvolutionRecord.field == field,
                        CharacterCardEvolutionRecord.scope == scope,
                    )
                    .values(selected=False)
                )
                target = CharacterCardEvolutionRecord(
                    entry_id=uuid4(),
                    world_id=world.value,
                    root_import_id=root_import_id,
                    field=field,
                    scope=scope,
                    text=text.strip(),
                    state="active",
                    selected=True,
                    locked=locked,
                    source=source,
                    created_at_utc=datetime.now(UTC),
                )
                session.add(target)
            else:
                if target is None:
                    raise EntityNotFoundError("character_evolution_entry_not_found")
                if operation == "select" or operation == "restore":
                    await session.execute(
                        update(CharacterCardEvolutionRecord)
                        .where(
                            CharacterCardEvolutionRecord.world_id == world.value,
                            CharacterCardEvolutionRecord.root_import_id == root_import_id,
                            CharacterCardEvolutionRecord.field == field,
                            CharacterCardEvolutionRecord.scope == scope,
                        )
                        .values(selected=False)
                    )
                    target.selected = True
                    target.state = "active"
                elif operation == "deactivate":
                    target.selected = False
                    target.state = "inactive"
                elif operation == "lock":
                    target.locked = True
                elif operation == "unlock":
                    target.locked = False
            await session.flush()
            return self._view(target)

    async def propose(
        self,
        world: WorldId,
        root_import_id: UUID,
        *,
        field: str,
        scope: str,
        text: str,
        quote: str,
        confidence: float,
    ) -> dict:
        """Stage a model suggestion without selecting it for prompt use."""
        fields = {"description", "personality", "background", "scenario", "speech_guidance"}
        scope = scope.strip()
        if field not in fields or not scope or len(scope) > 120:
            raise ValueError("character_evolution_field_invalid")
        text = text.strip()
        if not text:
            raise ValueError("character_evolution_text_empty")
        if len(text) > 4000:
            raise ValueError("character_evolution_capacity")
        quote = quote.strip()
        if len(quote) < 3 or len(quote) > 1000:
            raise ValueError("character_evolution_quote_invalid")
        if type(confidence) is not float or not 0.6 <= confidence <= 1:
            raise ValueError("character_evolution_confidence_invalid")
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if await session.get(WorldRecord, world.value) is None:
                raise EntityNotFoundError("world_not_found")
            root_import_id = await self._root_import_id(session, world, root_import_id)
            imported = await session.get(WorldContentImportRecord, root_import_id)
            if imported is None or imported.world_id != world.value or imported.kind != "character":
                raise EntityNotFoundError("character_card_not_found")
            existing = await session.scalar(
                select(CharacterCardEvolutionRecord).where(
                    CharacterCardEvolutionRecord.world_id == world.value,
                    CharacterCardEvolutionRecord.root_import_id == root_import_id,
                    CharacterCardEvolutionRecord.field == field,
                    CharacterCardEvolutionRecord.scope == scope,
                    CharacterCardEvolutionRecord.text == text,
                    CharacterCardEvolutionRecord.source == "model",
                )
            )
            if existing is not None:
                return self._view(existing)
            target = CharacterCardEvolutionRecord(
                entry_id=uuid4(),
                world_id=world.value,
                root_import_id=root_import_id,
                field=field,
                scope=scope,
                text=text,
                quote=quote,
                confidence=confidence,
                state="inactive",
                selected=False,
                locked=False,
                source="model",
                created_at_utc=datetime.now(UTC),
            )
            session.add(target)
            await session.flush()
            return self._view(target)

    @staticmethod
    def _view(row) -> dict:
        return {
            "entry_id": str(row.entry_id),
            "field": row.field,
            "scope": row.scope,
            "text": row.text,
            "quote": row.quote,
            "confidence": row.confidence,
            "state": row.state,
            "selected": row.selected,
            "locked": row.locked,
            "source": row.source,
            "created_at_utc": row.created_at_utc.isoformat(),
        }
