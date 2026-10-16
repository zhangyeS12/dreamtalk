"""Durable setup receipts; no model, credentials, or private content in the receipt."""

import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from livingworld.application.errors import IdempotencyConflictError
from livingworld.infrastructure.persistence.models import ExampleWorldSetupRecord


class SqlAlchemyExampleWorldStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def pending(self, template_id):
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ExampleWorldSetupRecord).where(
                    ExampleWorldSetupRecord.template_id == template_id,
                    ExampleWorldSetupRecord.state == "pending",
                )
            )
            return tuple(
                {
                    "request_id": str(row.request_id),
                    "reviewed_hash": row.reviewed_hash,
                    "public_entries": json.loads(row.public_entries_json),
                }
                for row in rows
            )

    async def begin(self, request_id, world_id, template_id, reviewed_hash, public_entries):
        encoded = json.dumps(sorted(public_entries))

        async def attempt():
            async with self._sessions() as session, session.begin():
                await session.connection(execution_options={"livingworld_write_intent": True})
                row = await session.get(ExampleWorldSetupRecord, request_id.value)
                if row is not None:
                    if (
                        row.world_id,
                        row.template_id,
                        row.reviewed_hash,
                        row.public_entries_json,
                    ) != (world_id.value, template_id, reviewed_hash, encoded):
                        raise IdempotencyConflictError("example_setup_conflict")
                    return row.state == "complete"
                session.add(
                    ExampleWorldSetupRecord(
                        request_id=request_id.value,
                        world_id=world_id.value,
                        template_id=template_id,
                        reviewed_hash=reviewed_hash,
                        public_entries_json=encoded,
                        state="pending",
                    )
                )
                return False

        try:
            return await attempt()
        except IntegrityError:
            # A concurrent identical click may have committed the intent first.
            return await attempt()

    async def complete(self, request_id):
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(ExampleWorldSetupRecord, request_id.value)
            if row is None:
                raise IdempotencyConflictError("example_setup_missing")
            row.state = "complete"
