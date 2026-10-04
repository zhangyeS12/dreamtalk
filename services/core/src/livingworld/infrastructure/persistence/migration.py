"""Alembic ownership and the one-time C-002 compatibility takeover."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, Connection, MetaData, UniqueConstraint, inspect, text

from livingworld.infrastructure.persistence.content_builder import (
    ContentBuilderJobRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.content_models import ContentBase
from livingworld.infrastructure.persistence.conversation_memory import (
    ConversationMemoryDraftRecord,  # noqa: F401
    ConversationMemoryRevisionRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.director_models import (
    DirectorSettingsRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterSettingsRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.errors import MigrationCompatibilityError
from livingworld.infrastructure.persistence.faction_models import (
    AcquaintanceRecord,  # noqa: F401
    CharacterAvatarRecord,  # noqa: F401
    FactionMemberRecord,  # noqa: F401
    FactionRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.llm_models import AccountingBase
from livingworld.infrastructure.persistence.long_memory_models import (
    LongChatMemoryRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.models import Base
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactSettingsRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.proactive_models import (
    ProactiveSettingsRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivityRecord,  # noqa: F401
)
from livingworld.infrastructure.persistence.story_models import ChatStoryRecord  # noqa: F401
from livingworld.infrastructure.persistence.world_cover_models import WorldCoverRecord  # noqa: F401

LEGACY_REVISION = "0001_legacy_runtime_foundation"
DOMAIN_BASELINE_REVISION = "0002_world_domain_persistence"
COMMAND_REVISION = "0003_command_pipeline"
OBSERVATION_REVISION = "0004_observation_identity"
LEDGER_REVISION = "0005_canonical_ledger"
CONTENT_REVISION = "0006_canonical_content"
LORE_REVISION = "0007_lore_collections"
PACKAGE_REVISION = "0008_native_content_packages"
ACCOUNTING_REVISION = "0009_llm_accounting"
BUDGET_REVISION = "0010_llm_budget_guard"
SIMULATION_REVISION = "0011_simulation_scheduler"
ACTION_REVISION = "0012_action_scenes_perception"
SPARSE_REVISION = "0013_sparse_simulation_activation"
MEMORY_REVISION = "0014_episodic_memory"
BINDING_REVISION = "0015_local_player_binding"
PROFILE_REVISION = "0016_local_profiles"
WORLD_CONTENT_REVISION = "0017_world_content_imports"
CHAT_CONVERSATION_REVISION = "0018_chat_conversations"
CHAT_MESSAGE_REVISION = "0019_chat_messages"
CHAT_DISPATCH_REVISION = "0020_chat_turn_dispatch"
CHAT_COMPLETION_REVISION = "0021_group_turn_completion"
COMMON_LORE_REVISION = "0022_world_common_lore"
BUILDER_REVISION = "0023_content_builder_jobs"
CONVERSATION_MEMORY_REVISION = "0024_conversation_memory"
DIRECTOR_REVISION = "0025_director_runtime"
LOCAL_LOCATION_REVISION = "0026_local_location_catalog"
OFFLINE_CONTACT_REVISION = "0027_offline_contact"
STORY_REVISION = "0028_world_event_journal"
LONG_MEMORY_REVISION = "0029_long_chat_memory"
COVER_REVISION = "0030_world_covers"
REPLY_RECOVERY_REVISION = "0031_chat_reply_recovery"
CONTEXT_REPORT_REVISION = "0032_chat_context_reports"
ENCOUNTER_REVISION = "0033_character_encounters"
SHARED_REVISION = "0034_shared_activities"
PROACTIVE_REVISION = "0035_proactive_contact"
HEAD_REVISION = "0036_character_factions"
FACTION_TABLES = {
    "character_factions",
    "character_faction_members",
    "character_avatars",
    "character_acquaintances",
}
PROACTIVE_TABLES = {
    "proactive_contact_settings",
    "proactive_contact_episodes",
    "chat_read_positions",
}
SHARED_TABLES = {"director_shared_settings", "director_shared_activities"}
ENCOUNTER_TABLES = {"director_encounter_settings", "director_encounters"}
REPLY_RECOVERY_TABLES = {"chat_reply_executions", "chat_reply_recoveries"}
COVER_TABLES = {"world_covers", "world_cover_images"}
LONG_MEMORY_TABLES = {"long_chat_memories", "long_chat_memory_settings"}
STORY_TABLES = {
    "world_news_settings",
    "world_news_marks",
    "chat_story_entries",
    "world_news_candidates",
    "world_news_batches",
}
OFFLINE_CONTACT_TABLES = {
    "offline_contact_settings",
    "offline_contact_episodes",
    "local_session_visibility",
}
LOCAL_LOCATION_TABLES = {"local_location_catalog"}
DIRECTOR_TABLES = {"director_settings", "director_plans", "director_candidates"}
CONVERSATION_MEMORY_TABLES = {"conversation_memory_revisions", "conversation_memory_drafts"}
BUILDER_JOB_TABLES = {"content_builder_jobs"}
CHAT_IDENTITY_TABLES = {"chat_conversations", "chat_participants"}
CHAT_MESSAGE_TABLES = {"chat_turns", "chat_messages"}
CHAT_DISPATCH_TABLES = {"chat_turn_dispatches"}
CHAT_TABLES = CHAT_IDENTITY_TABLES | CHAT_MESSAGE_TABLES | CHAT_DISPATCH_TABLES
WORLD_COMMON_LORE_TABLES = {"world_common_lore"}
LOCAL_PROFILE_TABLES = {"local_user_profile", "local_world_profiles"}
BUDGET_TABLES = {"llm_budgets", "llm_budget_reservations"}
SIMULATION_TABLES = {
    "simulation_queue_cursors",
    "simulation_scheduled_triggers",
    "simulation_activations",
    "simulation_activation_causes",
    "simulation_schedule_receipts",
}
ACTION_TABLES = {"scenes", "scene_participants"}
SPARSE_TABLES = {"simulation_activation_causes"}
MEMORY_TABLES = {"character_memories", "episodic_memory_observation_sources"}
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
    # Additive authored/job tables do not change the older runtime shapes.
    pre_faction_revision = revision != HEAD_REVISION
    pre_proactive_revision = revision not in {PROACTIVE_REVISION, HEAD_REVISION}
    pre_shared_revision = revision not in {SHARED_REVISION, PROACTIVE_REVISION, HEAD_REVISION}
    pre_encounter_revision = revision not in {
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_context_report_revision = revision not in {
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_reply_recovery_revision = revision not in {
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_cover_revision = revision not in {
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_long_memory_revision = revision not in {
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_story_revision = revision not in {
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_offline_contact_revision = revision not in {
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_local_location_revision = revision not in {
        LOCAL_LOCATION_REVISION,
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_director_revision = revision not in {
        DIRECTOR_REVISION,
        LOCAL_LOCATION_REVISION,
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_conversation_memory_revision = revision not in {
        CONVERSATION_MEMORY_REVISION,
        DIRECTOR_REVISION,
        LOCAL_LOCATION_REVISION,
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_builder_revision = revision not in {
        BUILDER_REVISION,
        CONVERSATION_MEMORY_REVISION,
        DIRECTOR_REVISION,
        LOCAL_LOCATION_REVISION,
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_completion_revision = revision not in {
        CHAT_COMPLETION_REVISION,
        COMMON_LORE_REVISION,
        BUILDER_REVISION,
        CONVERSATION_MEMORY_REVISION,
        DIRECTOR_REVISION,
        LOCAL_LOCATION_REVISION,
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    pre_common_lore_revision = revision not in {
        COMMON_LORE_REVISION,
        BUILDER_REVISION,
        CONVERSATION_MEMORY_REVISION,
        DIRECTOR_REVISION,
        LOCAL_LOCATION_REVISION,
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }
    if revision in {
        CHAT_COMPLETION_REVISION,
        COMMON_LORE_REVISION,
        BUILDER_REVISION,
        CONVERSATION_MEMORY_REVISION,
        DIRECTOR_REVISION,
        LOCAL_LOCATION_REVISION,
        OFFLINE_CONTACT_REVISION,
        STORY_REVISION,
        LONG_MEMORY_REVISION,
        COVER_REVISION,
        REPLY_RECOVERY_REVISION,
        CONTEXT_REPORT_REVISION,
        ENCOUNTER_REVISION,
        SHARED_REVISION,
        PROACTIVE_REVISION,
        HEAD_REVISION,
    }:
        revision = CHAT_DISPATCH_REVISION
    if revision not in {
        LEGACY_REVISION,
        DOMAIN_BASELINE_REVISION,
        COMMAND_REVISION,
        OBSERVATION_REVISION,
        LEDGER_REVISION,
        CONTENT_REVISION,
        LORE_REVISION,
        PACKAGE_REVISION,
        ACCOUNTING_REVISION,
        BUDGET_REVISION,
        SIMULATION_REVISION,
        ACTION_REVISION,
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        WORLD_CONTENT_REVISION,
        CHAT_CONVERSATION_REVISION,
        CHAT_MESSAGE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        _fail("alembic_revision_unsupported")
    # Through 0020, chat revisions only add tables. Validate each historical
    # cursor against that reviewed shape minus its later tables; 0021 is the
    # separately checked nullable completion column.
    pre_chat_revision = revision not in {
        CHAT_CONVERSATION_REVISION,
        CHAT_MESSAGE_REVISION,
        CHAT_DISPATCH_REVISION,
    }
    pre_message_revision = revision not in {CHAT_MESSAGE_REVISION, CHAT_DISPATCH_REVISION}
    pre_dispatch_revision = revision != CHAT_DISPATCH_REVISION
    if revision in {WORLD_CONTENT_REVISION, CHAT_CONVERSATION_REVISION, CHAT_MESSAGE_REVISION}:
        revision = CHAT_DISPATCH_REVISION
    _validate_legacy_metadata(connection)
    tables = _table_names(connection)
    expected = LEGACY_TABLES | {"alembic_version"}
    domain_present = revision != LEGACY_REVISION
    if domain_present:
        expected |= DOMAIN_TABLES
        if pre_chat_revision:
            expected -= CHAT_IDENTITY_TABLES
        if pre_message_revision:
            expected -= CHAT_MESSAGE_TABLES
        if pre_dispatch_revision:
            expected -= CHAT_DISPATCH_TABLES
        if revision not in {
            LEDGER_REVISION,
            CONTENT_REVISION,
            LORE_REVISION,
            PACKAGE_REVISION,
            ACCOUNTING_REVISION,
            BUDGET_REVISION,
            SIMULATION_REVISION,
            ACTION_REVISION,
            SPARSE_REVISION,
            MEMORY_REVISION,
            BINDING_REVISION,
            PROFILE_REVISION,
            CHAT_DISPATCH_REVISION,
        }:
            expected -= {"world_ledger_cursors"}
    if revision in {
        CONTENT_REVISION,
        LORE_REVISION,
        PACKAGE_REVISION,
        ACCOUNTING_REVISION,
        BUDGET_REVISION,
        SIMULATION_REVISION,
        ACTION_REVISION,
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        expected |= CONTENT_TABLES
        if revision not in {
            PACKAGE_REVISION,
            ACCOUNTING_REVISION,
            BUDGET_REVISION,
            SIMULATION_REVISION,
            ACTION_REVISION,
            SPARSE_REVISION,
            MEMORY_REVISION,
            BINDING_REVISION,
            PROFILE_REVISION,
            CHAT_DISPATCH_REVISION,
        }:
            expected -= PACKAGE_TABLES
        if revision == CONTENT_REVISION:
            expected -= {"content_lore_collections"}
    if revision in {
        ACCOUNTING_REVISION,
        BUDGET_REVISION,
        SIMULATION_REVISION,
        ACTION_REVISION,
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        expected |= set(AccountingBase.metadata.tables)
        if revision == ACCOUNTING_REVISION:
            expected -= BUDGET_TABLES
    if revision not in {
        SIMULATION_REVISION,
        ACTION_REVISION,
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        expected -= SIMULATION_TABLES
    elif revision not in {
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        expected -= SPARSE_TABLES
    if revision not in {
        ACTION_REVISION,
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        expected -= ACTION_TABLES
    if revision not in {
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        expected -= MEMORY_TABLES
    if revision not in {BINDING_REVISION, PROFILE_REVISION, CHAT_DISPATCH_REVISION}:
        expected -= {"local_player_bindings"}
    if revision not in {PROFILE_REVISION, CHAT_DISPATCH_REVISION}:
        expected -= LOCAL_PROFILE_TABLES
    if revision != CHAT_DISPATCH_REVISION:
        expected -= {"world_content_imports"}
    if pre_faction_revision:
        expected -= FACTION_TABLES
    if pre_proactive_revision:
        expected -= PROACTIVE_TABLES
    if pre_shared_revision:
        expected -= SHARED_TABLES
    if pre_encounter_revision:
        expected -= ENCOUNTER_TABLES
    if pre_reply_recovery_revision:
        expected -= REPLY_RECOVERY_TABLES
    if pre_cover_revision:
        expected -= COVER_TABLES
    if pre_long_memory_revision:
        expected -= LONG_MEMORY_TABLES
    if pre_story_revision:
        expected -= STORY_TABLES
    if pre_offline_contact_revision:
        expected -= OFFLINE_CONTACT_TABLES
    if pre_local_location_revision:
        expected -= LOCAL_LOCATION_TABLES
    if pre_director_revision:
        expected -= DIRECTOR_TABLES
    if pre_conversation_memory_revision:
        expected -= CONVERSATION_MEMORY_TABLES
    if pre_builder_revision:
        expected -= BUILDER_JOB_TABLES
    if pre_common_lore_revision:
        expected -= WORLD_COMMON_LORE_TABLES
    if tables != expected:
        _fail("alembic_schema_state_mismatch")
    _validate_auxiliary_objects(connection, domain_present)
    if domain_present:
        _validate_domain_shape(
            connection,
            revision,
            pre_chat_revision=pre_chat_revision,
            pre_message_revision=pre_message_revision,
            pre_dispatch_revision=pre_dispatch_revision,
            pre_completion_revision=pre_completion_revision,
            pre_common_lore_revision=pre_common_lore_revision,
            pre_builder_revision=pre_builder_revision,
            pre_conversation_memory_revision=pre_conversation_memory_revision,
            pre_director_revision=pre_director_revision,
            pre_local_location_revision=pre_local_location_revision,
            pre_offline_contact_revision=pre_offline_contact_revision,
            pre_story_revision=pre_story_revision,
            pre_long_memory_revision=pre_long_memory_revision,
            pre_cover_revision=pre_cover_revision,
            pre_reply_recovery_revision=pre_reply_recovery_revision,
            pre_context_report_revision=pre_context_report_revision,
            pre_encounter_revision=pre_encounter_revision,
            pre_shared_revision=pre_shared_revision,
            pre_proactive_revision=pre_proactive_revision,
            pre_faction_revision=pre_faction_revision,
        )
    if revision in {
        CONTENT_REVISION,
        LORE_REVISION,
        PACKAGE_REVISION,
        ACCOUNTING_REVISION,
        BUDGET_REVISION,
        SIMULATION_REVISION,
        ACTION_REVISION,
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        _validate_domain_shape(connection, revision, ContentBase.metadata)

    if revision in {
        ACCOUNTING_REVISION,
        BUDGET_REVISION,
        SIMULATION_REVISION,
        ACTION_REVISION,
        SPARSE_REVISION,
        MEMORY_REVISION,
        BINDING_REVISION,
        PROFILE_REVISION,
        CHAT_DISPATCH_REVISION,
    }:
        _validate_domain_shape(connection, revision, AccountingBase.metadata)


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
    connection: Connection,
    revision: str,
    metadata: MetaData = Base.metadata,
    *,
    pre_chat_revision: bool | None = None,
    pre_message_revision: bool | None = None,
    pre_dispatch_revision: bool | None = None,
    pre_completion_revision: bool = True,
    pre_common_lore_revision: bool = True,
    pre_builder_revision: bool = True,
    pre_conversation_memory_revision: bool = True,
    pre_director_revision: bool = True,
    pre_local_location_revision: bool = True,
    pre_offline_contact_revision: bool = True,
    pre_story_revision: bool = True,
    pre_long_memory_revision: bool = True,
    pre_cover_revision: bool = True,
    pre_reply_recovery_revision: bool = True,
    pre_context_report_revision: bool = True,
    pre_encounter_revision: bool = True,
    pre_shared_revision: bool = True,
    pre_proactive_revision: bool = True,
    pre_faction_revision: bool = True,
) -> None:
    """Detect partial/mismatched schemas; never infer a revision from them."""

    inspector = inspect(connection)
    if pre_chat_revision is None:
        pre_chat_revision = revision != CHAT_DISPATCH_REVISION
    if pre_message_revision is None:
        pre_message_revision = revision != CHAT_DISPATCH_REVISION
    if pre_dispatch_revision is None:
        pre_dispatch_revision = revision != CHAT_DISPATCH_REVISION
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
        if pre_faction_revision and table.name in FACTION_TABLES:
            continue
        if pre_proactive_revision and table.name in PROACTIVE_TABLES:
            continue
        if pre_shared_revision and table.name in SHARED_TABLES:
            continue
        if pre_encounter_revision and table.name in ENCOUNTER_TABLES:
            continue
        if pre_reply_recovery_revision and table.name in REPLY_RECOVERY_TABLES:
            continue
        if pre_cover_revision and table.name in COVER_TABLES:
            continue
        if pre_long_memory_revision and table.name in LONG_MEMORY_TABLES:
            continue
        if pre_story_revision and table.name in STORY_TABLES:
            continue
        if pre_offline_contact_revision and table.name in OFFLINE_CONTACT_TABLES:
            continue
        if pre_local_location_revision and table.name in LOCAL_LOCATION_TABLES:
            continue
        if pre_director_revision and table.name in DIRECTOR_TABLES:
            continue
        if pre_conversation_memory_revision and table.name in CONVERSATION_MEMORY_TABLES:
            continue
        if pre_builder_revision and table.name in BUILDER_JOB_TABLES:
            continue
        if pre_common_lore_revision and table.name in WORLD_COMMON_LORE_TABLES:
            continue
        if pre_chat_revision and table.name in CHAT_IDENTITY_TABLES:
            continue
        if pre_message_revision and table.name in CHAT_MESSAGE_TABLES:
            continue
        if pre_dispatch_revision and table.name in CHAT_DISPATCH_TABLES:
            continue
        if (
            revision
            not in {
                SIMULATION_REVISION,
                ACTION_REVISION,
                SPARSE_REVISION,
                MEMORY_REVISION,
                BINDING_REVISION,
                PROFILE_REVISION,
                CHAT_DISPATCH_REVISION,
            }
            and table.name in SIMULATION_TABLES
        ):
            continue
        if (
            revision
            not in {
                SPARSE_REVISION,
                MEMORY_REVISION,
                BINDING_REVISION,
                PROFILE_REVISION,
                CHAT_DISPATCH_REVISION,
            }
            and table.name in SPARSE_TABLES
        ):
            continue
        if (
            revision
            not in {
                ACTION_REVISION,
                SPARSE_REVISION,
                MEMORY_REVISION,
                BINDING_REVISION,
                PROFILE_REVISION,
                CHAT_DISPATCH_REVISION,
            }
            and table.name in ACTION_TABLES
        ):
            continue
        if (
            revision
            not in {MEMORY_REVISION, BINDING_REVISION, PROFILE_REVISION, CHAT_DISPATCH_REVISION}
            and table.name in MEMORY_TABLES
        ):
            continue
        if revision != CHAT_DISPATCH_REVISION and table.name == "world_content_imports":
            continue
        if (
            revision not in {PROFILE_REVISION, CHAT_DISPATCH_REVISION}
            and table.name in LOCAL_PROFILE_TABLES
        ):
            continue
        if (
            revision not in {BINDING_REVISION, PROFILE_REVISION, CHAT_DISPATCH_REVISION}
            and table.name == "local_player_bindings"
        ):
            continue
        if revision == ACCOUNTING_REVISION and table.name in BUDGET_TABLES:
            continue
        if (
            revision
            not in {
                PACKAGE_REVISION,
                ACCOUNTING_REVISION,
                BUDGET_REVISION,
                SIMULATION_REVISION,
                ACTION_REVISION,
                SPARSE_REVISION,
                MEMORY_REVISION,
                BINDING_REVISION,
                PROFILE_REVISION,
                CHAT_DISPATCH_REVISION,
            }
            and table.name in PACKAGE_TABLES
        ):
            continue
        if revision == CONTENT_REVISION and table.name == "content_lore_collections":
            continue
        if (
            revision
            not in {
                LEDGER_REVISION,
                CONTENT_REVISION,
                LORE_REVISION,
                PACKAGE_REVISION,
                ACCOUNTING_REVISION,
                BUDGET_REVISION,
                SIMULATION_REVISION,
                ACTION_REVISION,
                SPARSE_REVISION,
                MEMORY_REVISION,
                BINDING_REVISION,
                PROFILE_REVISION,
                CHAT_DISPATCH_REVISION,
            }
            and table.name == "world_ledger_cursors"
        ):
            continue
        actual = [
            (column["name"], str(column["type"]).upper(), column["nullable"])
            for column in inspector.get_columns(table.name)
        ]
        expected = [
            (
                column.name,
                column.type.compile(dialect=connection.dialect).upper(),
                False
                if (
                    revision
                    not in {
                        SPARSE_REVISION,
                        MEMORY_REVISION,
                        BINDING_REVISION,
                        PROFILE_REVISION,
                        CHAT_DISPATCH_REVISION,
                    }
                    and table.name == "simulation_activations"
                    and column.name == "source_trigger_id"
                )
                else column.nullable,
            )
            for column in table.columns
            if not (
                pre_context_report_revision
                and table.name == "chat_reply_executions"
                and column.name == "context_reports"
            )
            if not (
                pre_offline_contact_revision
                and (
                    table.name == "chat_turns"
                    and column.name == "kind"
                    or table.name == "chat_messages"
                    and column.name == "story_sent_at_utc"
                )
            )
            if not (
                pre_completion_revision
                and table.name == "chat_turn_dispatches"
                and column.name == "completed_at_utc"
            )
            if not (baseline and column.name in added_columns.get(table.name, set()))
            and not (
                legacy_observations
                and table.name == "observations"
                and column.name == "observation_id"
            )
            and not (
                revision
                not in {
                    ACTION_REVISION,
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and table.name == "observations"
                and column.name == "basis"
            )
            and not (
                revision
                not in {
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and table.name == "simulation_scheduled_triggers"
                and column.name
                in {
                    "activation_target_kind",
                    "activation_target_id",
                    "activation_target_character_id",
                    "activation_kind",
                    "activation_version",
                    "activation_coalescing_key",
                    "activation_attention",
                }
            )
            and not (
                revision
                not in {
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and table.name == "simulation_activations"
                and column.name
                in {
                    "target_kind",
                    "target_id",
                    "target_character_id",
                    "activation_kind",
                    "activation_version",
                    "priority",
                    "enqueue_position",
                    "coalescing_key",
                    "attention",
                }
            )
            and not (
                revision
                not in {
                    LEDGER_REVISION,
                    CONTENT_REVISION,
                    LORE_REVISION,
                    PACKAGE_REVISION,
                    ACCOUNTING_REVISION,
                    BUDGET_REVISION,
                    SIMULATION_REVISION,
                    ACTION_REVISION,
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
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
                revision
                not in {
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and table.name in {"simulation_scheduled_triggers", "simulation_activations"}
                and foreign_key.referred_table.name == "characters"
            )
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
                revision
                not in {
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and constraint.name
                in {
                    "ck_simulation_trigger_activation_target",
                    "ck_simulation_trigger_activation_version",
                    "ck_simulation_trigger_activation_attention",
                    "ck_simulation_activation_target",
                    "ck_simulation_activation_version",
                    "ck_simulation_activation_priority",
                    "ck_simulation_activation_enqueue_position",
                    "ck_simulation_activation_attention",
                }
            )
            and not (
                revision
                not in {
                    LEDGER_REVISION,
                    CONTENT_REVISION,
                    LORE_REVISION,
                    PACKAGE_REVISION,
                    ACCOUNTING_REVISION,
                    BUDGET_REVISION,
                    SIMULATION_REVISION,
                    ACTION_REVISION,
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and constraint.name == "ck_world_event_ledger_position"
            )
        }
        if (
            table.name == "command_receipts"
            and revision
            not in {
                ACTION_REVISION,
                SPARSE_REVISION,
                MEMORY_REVISION,
                BINDING_REVISION,
                PROFILE_REVISION,
                CHAT_DISPATCH_REVISION,
            }
            and not baseline
        ):
            expected_checks.discard(
                (
                    "ck_command_receipt_command_result",
                    _normalized_sql(
                        "(command_fingerprint IS NULL AND result_payload IS NULL) OR "
                        "(command_fingerprint IS NOT NULL AND length(command_fingerprint) = 64 "
                        "AND result_payload IS NOT NULL AND status IN ('committed', 'rejected') "
                        "AND completed_at IS NOT NULL)"
                    ),
                )
            )
            expected_checks.add(
                (
                    "ck_command_receipt_command_result",
                    _normalized_sql(
                        "(command_fingerprint IS NULL AND result_payload IS NULL) OR "
                        "(command_fingerprint IS NOT NULL AND length(command_fingerprint) = 64 "
                        "AND result_payload IS NOT NULL AND status = 'committed' "
                        "AND completed_at IS NOT NULL AND result_event_id IS NOT NULL)"
                    ),
                )
            )
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
            and not (
                revision
                not in {
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and constraint.name == "uq_simulation_activation_enqueue_position"
            )
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
                revision
                not in {
                    LEDGER_REVISION,
                    CONTENT_REVISION,
                    LORE_REVISION,
                    PACKAGE_REVISION,
                    ACCOUNTING_REVISION,
                    BUDGET_REVISION,
                    SIMULATION_REVISION,
                    ACTION_REVISION,
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and index.name == "uq_world_event_ledger_position"
            )
            and not (
                revision
                not in {
                    ACTION_REVISION,
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and index.name
                in {
                    "ix_character_state_location",
                    "ix_observation_principal_history",
                    "ix_player_presence_active_location",
                    "uq_observation_event_principal",
                }
            )
            and not (
                revision
                not in {
                    SPARSE_REVISION,
                    MEMORY_REVISION,
                    BINDING_REVISION,
                    PROFILE_REVISION,
                    CHAT_DISPATCH_REVISION,
                }
                and index.name
                in {
                    "ix_simulation_activation_due",
                    "ix_simulation_activation_target",
                    "uq_simulation_activation_pending_coalescing",
                    "ix_simulation_activation_cause_order",
                    "ix_simulation_activation_cause_identity",
                }
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
