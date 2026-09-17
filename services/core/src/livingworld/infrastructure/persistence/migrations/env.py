"""Alembic environment used only through the application-owned connection."""

from alembic import context

from livingworld.infrastructure.persistence.content_models import ContentBase
from livingworld.infrastructure.persistence.models import Base

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("alembic_application_connection_required")


def include_object(
    object: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    del object, reflected, compare_to
    return not (
        type_ == "table" and name in {"schema_version", "migration_history", "alembic_version"}
    )


context.configure(
    connection=connection,
    target_metadata=[Base.metadata, ContentBase.metadata],
    transactional_ddl=True,
    include_object=include_object,
)
with context.begin_transaction():
    context.run_migrations()
