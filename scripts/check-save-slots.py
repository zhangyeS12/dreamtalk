"""Run this specifically authorized save-slot check set using external synthetic storage."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="dreamtalk-save-checks-") as temporary:
        isolated = Path(temporary)
        if isolated.is_relative_to(root):
            raise SystemExit("isolated_checks_require_external_temp_directory")
        environment = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
        for key in ("LOCALAPPDATA", "APPDATA", "HF_HOME", "XDG_CACHE_HOME", "TEMP", "TMP"):
            path = isolated / key.lower()
            path.mkdir()
            environment[key] = str(path)
        environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--tb=short",
            "--basetemp",
            str(isolated / "pytest"),
            "tests/persistence/test_save_slots.py",
            "tests/persistence/test_save_safety.py",
        ]
        if "--web-only" not in sys.argv:
            result = subprocess.run(command, cwd=root, env=environment)
            if result.returncode:
                raise SystemExit(result.returncode)
        node = shutil.which("node")
        if not node:
            raise SystemExit("node_not_found")
        config = isolated / "vitest.config.mjs"
        config.write_text(
            "export default "
            + json.dumps(
                {
                    "root": str(root),
                    "cacheDir": str(isolated / "vite-cache"),
                    "test": {
                        "include": ["apps/web/src/SaveSlots.test.tsx"],
                        "environment": "jsdom",
                        "setupFiles": ["apps/web/src/testSetup.ts"],
                        "cache": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        raise SystemExit(
            subprocess.run(
                [
                    node,
                    "node_modules/vitest/vitest.mjs",
                    "run",
                    "apps/web/src/SaveSlots.test.tsx",
                    "--config",
                    str(config),
                ],
                cwd=root,
                env=environment,
            ).returncode
        )


if __name__ == "__main__":
    main()
