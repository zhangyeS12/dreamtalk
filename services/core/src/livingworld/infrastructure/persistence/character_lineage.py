"""Resolve metadata only, with cycle detection independent of revision count."""

from sqlalchemy import select

from livingworld.infrastructure.persistence.models import WorldContentImportRecord as Imported


async def latest_character_import(session, world, root):
    lineage = (
        select(Imported.import_id, Imported.replaces_import_id, Imported.kind)
        .where(Imported.world_id == world, Imported.import_id == root)
        .cte(recursive=True)
    )
    # UNION (distinct) terminates even a corrupt cycle; no full card is loaded.
    lineage = lineage.union(
        select(Imported.import_id, Imported.replaces_import_id, Imported.kind)
        .join(lineage, Imported.replaces_import_id == lineage.c.import_id)
        .where(Imported.world_id == world)
    )
    rows = (await session.execute(select(lineage))).all()
    if not rows or any(row.kind != "character" for row in rows):
        raise ValueError("character_lineage_invalid")
    successors = {row.replaces_import_id: row.import_id for row in rows if row.replaces_import_id}
    seen, current = set(), root
    while current in successors:
        if current in seen:
            raise ValueError("character_lineage_invalid")
        seen.add(current)
        current = successors[current]
    return current
