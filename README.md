# dreamtalk Android personal test source

This Android source branch preserves the Python Core, versioned HTTP/SSE, SQLite WAL/FTS5, Alembic and Tauri/Chaquopy host with a simple React frontend and online APIs.

The startup hotfix canonicalizes only the trusted Android application-directory parent, preserves rejection of links within managed storage, and records redacted failures before the Core thread starts.

CI is not manually run or awaited unless explicitly requested by the user. This release uses a recorded, explicit SkipCI build invocation; default gates and shared workflow configuration remain unchanged. Local regression, compilation, signing, package/source correspondence and anonymous-download verification remain required. Existing repository automatic workflows may still react to a tag.

Source entry points: apps/web/src/mobile, apps/mobile/src-tauri, plugins/android, services/core/src/livingworld/bootstrap/mobile_host.py. Packaging needs the SDK/NDK, JDK 21, reviewed ARM64 Python wheels and the original signing identity; keys and caches are excluded. See LICENSE and docs/licenses. This branch does not alter Windows main or its update channel.
