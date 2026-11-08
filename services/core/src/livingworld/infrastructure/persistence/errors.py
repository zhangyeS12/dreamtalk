"""Persistence boundary failures that do not leak storage concerns into domain."""

from enum import StrEnum


class MigrationErrorCode(StrEnum):
    LEGACY_SHAPE = "legacy_schema_shape_mismatch"
    LEGACY_METADATA = "legacy_metadata_corrupt"
    LEGACY_VERSION = "legacy_schema_version_unsupported"
    LEGACY_HISTORY = "legacy_migration_history_mismatch"
    LEGACY_CHECKSUM = "legacy_checksum_mismatch"
    LEGACY_HISTORY_CORRUPT = "legacy_migration_history_corrupt"
    ALEMBIC_CURSOR = "alembic_cursor_corrupt"
    ALEMBIC_REVISION = "alembic_revision_unsupported"
    ALEMBIC_STATE = "alembic_schema_state_mismatch"
    SCHEMA_OBJECTS = "migration_schema_objects_mismatch"
    ALEMBIC_SHAPE = "alembic_schema_shape_mismatch"
    LEGACY_AMBIGUOUS = "legacy_schema_ambiguous"


class MigrationCompatibilityError(RuntimeError):
    """The database cannot be safely adopted or upgraded without operator action."""

    def __init__(self, code: str) -> None:
        self.code = MigrationErrorCode(code)
        super().__init__(self.code.value)


class PersistenceDataError(RuntimeError):
    """Stored data cannot be converted to a valid domain value."""


class PersistenceConflictError(RuntimeError):
    """A database uniqueness, reference or check invariant rejected an insert."""
