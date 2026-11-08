# dreamtalk Android personal test source

This independent Android branch preserves the Python Core, versioned HTTP/SSE, SQLite WAL/FTS5 and Alembic architecture with a simple React/TypeScript frontend and a Tauri/Chaquopy host. It uses configured online APIs, without local chat, speech or vision deployment UI.

The Android source CI checks the exact commit with synthetic temporary storage, blocked external provider traffic, Core and old-revision upgrade tests, frontend tests, generated contracts and static checks. It does not claim device acceptance or run a production APK. CI reuses the pinned checkout, Node 24 and uv 0.11.32 actions used by the main project; action source licenses remain MIT/Apache-2.0 as applicable. Python CI versions are recorded in `ci/requirements.txt` and do not replace the separately built Android wheels.

Run the source checks after installing Node 24, Python 3.13, the requirements and npm dependencies: `python scripts/check-android-source.py`. Packaging additionally requires the Android SDK/NDK, JDK 21, the reviewed ARM64 Python wheels, original signing identity, and successful exact-commit Android CI; signing keys and local tool caches are intentionally excluded from source.

Source entry points: `apps/web/src/mobile`, `apps/mobile/src-tauri`, `plugins/android`, and `services/core/src/livingworld/bootstrap/mobile_host.py`. See `LICENSE` and `docs/licenses` for licensing. Releases are personal prereleases in the repository, separate from the Windows update channel. Installation, real API behavior and vendor background restrictions require device testing. This branch does not change main or the Windows release assets.
