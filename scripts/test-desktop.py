"""Run desktop checks with separate saves, backups and caches; never inherit user backups."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    cargo = shutil.which("cargo")
    if not cargo:
        raise SystemExit("cargo_not_found")
    with tempfile.TemporaryDirectory(prefix="dreamtalk-desktop-checks-") as directory:
        isolated = Path(directory)
        if isolated.resolve().is_relative_to(root):
            raise SystemExit("isolated_checks_require_external_temp_directory")
        paths = {
            name: str(isolated / folder)
            for name, folder in {
                "LOCALAPPDATA": "local",
                "APPDATA": "roaming",
                "HF_HOME": "hf",
                "XDG_CACHE_HOME": "cache",
                "TEMP": "temp",
                "TMP": "temp",
            }.items()
        }
        for path in paths.values():
            Path(path).mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, **paths, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        result = subprocess.run(
            [
                cargo,
                "test",
                "--locked",
                "--manifest-path",
                str(root / "apps/desktop/src-tauri/Cargo.toml"),
                *sys.argv[1:],
            ],
            cwd=root,
            env=environment,
        )
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
