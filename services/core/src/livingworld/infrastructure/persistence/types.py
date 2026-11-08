"""Exact SQLite encodings for domain values."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from livingworld.domain.values import WorldTime, utc_timestamp
from livingworld.infrastructure.persistence.errors import PersistenceDataError

SQLITE_INT64_MIN = -(2**63)
SQLITE_INT64_MAX = 2**63 - 1


class UUIDStorage(TypeDecorator[UUID]):
    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: UUID | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, UUID):
            raise PersistenceDataError("uuid_storage_requires_uuid")
        return value.hex

    def process_result_value(self, value: str | None, dialect: Dialect) -> UUID | None:
        if value is None:
            return None
        try:
            return UUID(value)
        except (TypeError, ValueError):
            raise PersistenceDataError("stored_uuid_invalid") from None


class WorldTimeStorage(TypeDecorator[WorldTime]):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: WorldTime | None, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if not isinstance(value, WorldTime):
            raise PersistenceDataError("world_time_storage_requires_world_time")
        if not SQLITE_INT64_MIN <= value.microseconds <= SQLITE_INT64_MAX:
            raise PersistenceDataError("world_time_outside_sqlite_integer_range")
        return value.microseconds

    def process_result_value(self, value: int | None, dialect: Dialect) -> WorldTime | None:
        if value is None:
            return None
        if type(value) is not int:
            raise PersistenceDataError("stored_world_time_not_integer")
        return WorldTime(value)


class UTCTimestampStorage(TypeDecorator[datetime]):
    """Store canonical ISO-8601 UTC text and never return naive datetime values."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return utc_timestamp(value, "persistence timestamp").isoformat(timespec="microseconds")

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise PersistenceDataError("stored_timestamp_invalid") from None
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise PersistenceDataError("stored_timestamp_not_utc_aware")
        return parsed.astimezone(UTC)


class DecimalTextStorage(TypeDecorator[Decimal]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, Decimal) or not value.is_finite():
            raise PersistenceDataError("decimal_storage_requires_finite_decimal")
        return str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        try:
            result = Decimal(value)
        except (InvalidOperation, TypeError):
            raise PersistenceDataError("stored_decimal_invalid") from None
        if not result.is_finite():
            raise PersistenceDataError("stored_decimal_not_finite")
        return result


def _json_mutable(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_mutable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_mutable(child) for child in value]
    return value


class JSONTextStorage(TypeDecorator[object]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: object | None, dialect: Dialect) -> str | None:
        if value is None:
            return "null"
        try:
            return json.dumps(
                _json_mutable(value),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            raise PersistenceDataError("json_storage_requires_finite_json") from None

    def process_result_value(self, value: str | None, dialect: Dialect) -> object:
        if value is None:
            raise PersistenceDataError("stored_json_is_null_column")
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            raise PersistenceDataError("stored_json_invalid") from None
