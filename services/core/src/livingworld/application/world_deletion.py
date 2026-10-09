"""Short exclusive maintenance window; never abort or replay a paid generation."""

from livingworld.application.content_packages import PackageError


class WorldDeletionService:
    def __init__(self, store, runtime, maintenance, imports, assets, recall):
        self.store, self.runtime, self.maintenance = store, runtime, maintenance
        self.imports, self.assets, self.recall = imports, assets, recall

    async def delete(self, world_id, expected_name):
        # Admission is synchronous with HTTP/background operation accounting.
        # This authenticated DELETE itself owns exactly one admitted operation.
        if self.maintenance.preparing or self.maintenance.active != 1 or self.recall.working:
            raise ValueError("world_delete_busy")
        self.maintenance.begin_deletion()
        deleted = False
        try:
            await self.runtime.suspend_for_deletion(world_id)
            # A timed-out semantic worker may outlive its request. Reject above;
            # evict its derived cache while admission is fenced, before the purge.
            await self.recall.clear_derived_cache()
            digests = await self.store.purge(world_id, expected_name)
            deleted = True
            self.imports.forget_world(world_id)
            removed = []
            for digest in digests:
                try:
                    await self.assets.remove_unreferenced(digest)
                    removed.append(digest)
                except (OSError, PackageError):
                    pass  # Receipt retains the hashes for explicit retry after restart.
            await self.store.assets_removed(world_id, removed)
            return {"deleted": True, "asset_cleanup_pending": len(removed) != len(digests)}
        finally:
            self.runtime.deletion_finished(world_id, deleted=deleted)
            self.maintenance.end_deletion()
