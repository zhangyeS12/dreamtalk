"""Alembic ownership and the one-time C-002 compatibility takeover."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, Connection, MetaData, UniqueConstraint, inspect, text

from livingworld.infrastructure.persistence.content_models import ContentBase
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.models import Base

LEGACY_REVISION = "0001_legacy_runtime_foundation"
DOMAIN_BASELINE_REVISION = "0002_world_domain_persistence"
COMMAND_REVISION = "0003_command_pipeline"
OBSERVATION_REVISION = "0004_observation_identity"
LEDGER_REVISION = "0005_canonical_ledger"
CONTENT_REVISION = "0006_canonical_content"
LORE_REVISION = "0007_lore_collections"
HEAD_REVISION = "0008_native_content_packages"
PACKAGE_TABLES = {"content_import_baselines", "content_asset_blob_bindings"}
LEGACY_CHECKSUM = "0345ec9d50fd45b01ba0f97ff6f14a25f683fb8d01f08f04ff9dc4892ad1cac5"
LEGACY_TABLES = {"schema_version", "migration_history"}
DOMAIN_TABLES = set(Base.metadata.tables)
CONTENT_TABLES = set(ContentBase.metadata.tables)

_LEGACY_COLUMNS = {
    "schema_version": [
        ("singleton", "INTEGER", False, 1),
        ("version", "INTEGER", True, 0),
    ],
    "migration_history": [
        ("version", "INTEGER", False, 1),
        ("name", "TEXT", True, 0),
        ("checksum", "TEXT", True, 0),
        ("applied_at", "TEXT", True, 0),
    ],
}
_LEGACY_SQL = {
    "schema_version": (
        "CREATE TABLE schema_version (singleton INTEGER PRIMARY KEY CHECK(singleton = 1), "
        "version INTEGER NOT NULL)"
    ),
    "migration_history": (
        "CREATE TABLE migration_history (version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
    ),
}
_EVENT_TRIGGERS = {
    f"world_events_no_{action}": (
        f"CREATE TRIGGER world_events_no_{action} BEFORE {action.upper()} ON world_events "
        "BEGIN SELECT RAISE(ABORT, 'world_event_immutable'); END"
    )
    for action in ("update", "delete")
}


def _normalized_sql(sql: str) -> str:
    # SQL keywords are case-insensitive; quoted values retain their exact meaning.
    parts = re.split(r"('(?:''|[^'])*')", sql)
    return "".join(
        part if index % 2 else re.sub(r"\s+", "", part).casefold()
        for index, part in enumerate(parts)
    )


def _fail(code: str) -> None:
    raise MigrationCompatibilityError(code)


def _index_predicate(value: object) -> str:
    return _normalized_sql(str(value)) if value is not None else ""


def _table_names(connection: Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT GLOB 'sqlite_*'")
        )
    }


def _validate_legacy_shape(connection: Connection) -> None:
    inspector = inspect(connection)
    for table_name, expected in _LEGACY_COLUMNS.items():
        if table_name not in inspector.get_table_names():
            _fail("legacy_schema_shape_mismatch")
        actual = [
            (
                column["name"],
                str(column["type"]).upper(),
                not column["nullable"],
                column["primary_key"],
            )
            for column in inspector.get_columns(table_name)
        ]
        if actual != expected:
            _fail("legacy_schema_shape_mismatch")
        ddl = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table_name},
        ).scalar_one()
        if _normalized_sql(ddl) != _normalized_sql(_LEGACY_SQL[table_name]):
            _fail("legacy_schema_shape_mismatch")
        if inspector.get_indexes(table_name) or inspector.get_foreign_keys(table_name):
            _fail("legacy_schema_shape_mismatch")


def _validate_legacy_metadata(connection: Connection) -> None:
    _validate_legacy_shape(connection)
    try:
        versions = connection.execute(text("SELECT singleton, version FROM schema_version")).all()
        history = connection.execute(
            text(
                "SELECT version, name, checksum, applied_at FROM migration_history ORDER BY version"
            )
        ).all()
    except Exception:
        _fail("legacy_metadata_corrupt")
    if versions != [(1, 1)]:
        if len(versions) == 1 and versions[0][0] == 1:
            _fail("legacy_schema_version_unsupported")
        _fail("legacy_metadata_corrupt")
    if len(history) != 1 or history[0][0:2] != (1, "runtime_metadata"):
        _fail("legacy_migration_history_mismatch")
    if history[0][2] != LEGACY_CHECKSUM:
        _fail("legacy_checksum_mismatch")
    try:
        applied_at = datetime.fromisoformat(history[0][3])
    except (TypeError, ValueError):
        _fail("legacy_migration_history_corrupt")
    if applied_at.tzinfo is None or applied_at.utcoffset() != timedelta(0):
        _fail("legacy_migration_history_corrupt")


def _alembic_config(connection: Connection) -> Config:
    config = Config()
    location = files("livingworld.infrastructure.persistence.migrations")
    config.set_main_option("script_location", str(location))
    config.attributes["connection"] = connection
    return config


def _current_revision(connection: Connection) -> str:
    columns = inspect(connection).get_columns("alembic_version")
    if len(columns) != 1 or (
        columns[0]["name"],
        str(columns[0]["type"]).upper(),
        columns[0]["nullable"],
        bool(columns[0]["primary_key"]),
    ) != ("version_num", "VARCHAR(32)", False, True):
        _fail("alembic_cursor_corrupt")
    rows = connection.execute(text("SELECT version_num FROM alembic_version")).all()
    if len(rows) != 1 or not isinstance(rows[0][0], str):
        _fail("alembic_cursor_corrupt")
    return rows[0][0]


def _validate_managed_state(connection: Connection, revision: str) -> None:
    if revision not in {
        LEGACY_REVISION,
        DOMAIN_BASELINE_REVISION,
        COMMAND_REVISION,
        OBSERVATION_REVISION,
        LEDGER_REVISION,
        CONTENT_REVISION,
        LORE_REVISION,
        HEAD_REVISION,
    }:
        _fail("alembic_revision_unsupported")
    _validate_legacy_metadata(connection)
    tables = _table_names(connection)
    expected = LEGACY_TABLES | {"alembic_version"}
    domain_present = revision != LEGACY_REVISION
    if domain_present:
        expected |= DOMAIN_TABLES
        if revision not in {LEDGER_REVISION, CONTENT_REVISION, LORE_REVISION, HEAD_REVISION}:
            expected -= {"world_ledger_cursors"}
    if revision in {CONTENT_REVISION, LORE_REVISION, HEAD_REVISION}:
        expected |= CONTENT_TABLES
        if revision != HEAD_REVISION:
            expected -= PACKAGE_TABLES
        if revision == CONTENT_REVISION:
            expected -= {"content_lore_collections"}
    if tables != expected:
        _fail("alembic_schema_state_mismatch")
    _validate_auxiliary_objects(connection, domain_present)
    if domain_present:
        _validate_domain_shape(connection, revision)
    if revision in {CONTENT_REVISION, LORE_REVISION, HEAD_REVISION}:
        _validate_domain_shape(connection, revision, ContentBase.metadata)


def _validate_auxiliary_objects(connection: Connection, domain_present: bool) -> None:
    objects = connection.execute(
        text("SELECT name, type, sql FROM sqlite_master WHERE type IN ('trigger', 'view')")
    ).all()
    expected = _EVENT_TRIGGERS if domain_present else {}
    if {row[0] for row in objects} != set(expected):
        _fail("migration_schema_objects_mismatch")
    for name, type_, sql in objects:
        if type_ != "trigger" or _normalized_sql(sql) != _normalized_sql(expected[name]):
            _fail("migration_schema_objects_mismatch")


def _validate_domain_shape(
    connection: Connection, revision: str, metadata: MetaData = Base.metadata
) -> None:
    """Detect partial/mismatched schemas; never infer a revision from them."""

    inspector = inspect(connection)
    # Explicit reviewed deltas describe historical shapes for each Alembic cursor.
    # The Alembic cursor selects the expected shape; shape never selects migrations.
    baseline = revision == DOMAIN_BASELINE_REVISION
    legacy_observations = revision in {DOMAIN_BASELINE_REVISION, COMMAND_REVISION}
    added_columns = {
        "relationships": {"affinity", "trust", "familiarity"},
        "command_receipts": {"result_payload", "command_fingerprint"},
    }
    added_checks = {
        "ck_relationship_affinity",
        "ck_relationship_trust",
        "ck_relationship_familiarity",
        "ck_command_receipt_command_result",
    }
    for table in metadata.sorted_tables:
        if revision != HEAD_REVISION and table.name in PACKAGE_TABLES:
            continue
        if revision == CONTENT_REVISION and table.name == "content_lore_collections":
            continue
        if (
            revision not in {LEDGER_REVISION, CONTENT_REVISION, LORE_REVISION, HEAD_REVISION}
            and table.name == "world_ledger_cursors"
        ):
            continue
        actual = [
            (column["name"], str(column["type"]).upper(), column["nullable"])
            for column in inspector.get_columns(table.name)
        ]
        expected = [
            (column.name, column.type.compile(dialect=connection.dialect).upper(), column.nullable)
            for column in table.columns
            if not (baseline and column.name in added_columns.get(table.name, set()))
            and not (
                legacy_observations
                and table.name == "observations"
                and column.name == "observation_id"
            )
            and not (
                revision not in {LEDGER_REVISION, CONTENT_REVISION, LORE_REVISION, HEAD_REVISION}
                and table.name == "world_events"
                and column.name == "ledger_position"
            )
            and not (
                revision == CONTENT_REVISION
                and table.name == "content_lore_entries"
                and column.name == "collection_id"
            )
        ]
        if actual != expected:
            _fail("alembic_schema_shape_mismatch")
        expected_pk = [column.name for column in table.primary_key.columns]
        if legacy_observations and table.name == "observations":
            expected_pk = [
                "world_id",
                "principal_kind",
                "principal_id",
                "target_kind",
                "target_id",
                "channel",
                "observed_at",
            ]
        if inspector.get_pk_constraint(table.name)["constrained_columns"] != expected_pk:
            _fail("alembic_schema_shape_mismatch")
        expected_fks = {
            (
                tuple(element.parent.name for element in foreign_key.elements),
                foreign_key.referred_table.name,
                tuple(element.column.name for element in foreign_key.elements),
            )
            for foreign_key in table.foreign_key_constraints
            if not (
                revision == CONTENT_REVISION
                and table.name == "content_lore_entries"
                and foreign_key.referred_table.name == "content_lore_collections"
            )
        }
        actual_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
            for fk in inspector.get_foreign_keys(table.name)
        }
        if actual_fks != expected_fks:
            _fail("alembic_schema_shape_mismatch")
        expected_checks = {
            (constraint.name, _normalized_sql(str(constraint.sqltext)))
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
            and not (baseline and constraint.name in added_checks)
            and not (
                revision not in {LEDGER_REVISION, CONTENT_REVISION, LORE_REVISION, HEAD_REVISION}
                and constraint.name == "ck_world_event_ledger_position"
            )
        }
        actual_checks = {
            (constraint["name"], _normalized_sql(constraint["sqltext"]))
            for constraint in inspector.get_check_constraints(table.name)
        }
        if actual_checks != expected_checks:
            _fail("alembic_schema_shape_mismatch")
        expected_uniques = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        actual_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(table.name)
        }
        if actual_uniques != expected_uniques:
            _fail("alembic_schema_shape_mismatch")
        expected_indexes = {
            (
                index.name,
                tuple(column.name for column in index.columns),
                bool(index.unique),
                _index_predicate(index.dialect_options["sqlite"].get("where")),
            )
            for index in table.indexes
            if not (baseline and index.name == "uq_command_request_identity")
            and not (
                revision not in {LEDGER_REVISION, CONTENT_REVISION, LORE_REVISION, HEAD_REVISION}
                and index.name == "uq_world_event_ledger_position"
            )
        }
        actual_indexes = {
            (
                index["name"],
                tuple(index["column_names"]),
                bool(index["unique"]),
                _index_predicate(index.get("dialect_options", {}).get("sqlite_where")),
            )
            for index in inspector.get_indexes(table.name)
        }
        if actual_indexes != expected_indexes:
            _fail("alembic_schema_shape_mismatch")


def upgrade(connection: Connection) -> None:
    """Upgrade an empty, verified legacy, or already Alembic-managed database."""

    tables = _table_names(connection)
    config = _alembic_config(connection)
    if "alembic_version" in tables:
        _validate_managed_state(connection, _current_revision(connection))
    elif not tables:
        _validate_auxiliary_objects(connection, False)
    elif tables == LEGACY_TABLES:
        _validate_legacy_metadata(connection)
        _validate_auxiliary_objects(connection, False)
        command.stamp(config, LEGACY_REVISION)
    else:
        _fail("legacy_schema_ambiguous")

    command.upgrade(config, "head")
    if _current_revision(connection) != HEAD_REVISION:
        _fail("alembic_schema_state_mismatch")
    _validate_managed_state(connection, HEAD_REVISION)
