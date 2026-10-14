"""Static source/payload privacy gate; never reads app-data, runs the app or publishes."""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py",
    ".rs",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".conf",
    ".cfg",
    ".ps1",
    ".bat",
    ".cmd",
    ".png",
}
PRIVATE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".lwcontent",
    ".lworld",
    ".dpapi",
    ".pfx",
    ".p12",
    ".key",
    ".voicecard",
}
DATA_ROOTS = {"data", "runtime", "config", "saves", "exports", "user-data", "app-data"}
CREDENTIAL = re.compile(
    rb"(?<![A-Za-z0-9])(?:sk-(?:ant-)?[A-Za-z0-9_-]{25,}|AIza[0-9A-Za-z_-]{30,}|"
    rb"ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{25,})"
)
PRIVATE_KEY = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{16,}"
)
PROFILE_PATH = re.compile(rb"[A-Za-z]:(?:\\+|/)Users(?:\\+|/)[A-Za-z0-9_.-]+(?:\\+|/)", re.I)


def findings(name: str, data: bytes, *, source: bool) -> list[str]:
    """Return machine labels only; never print matched private bytes."""
    path = PurePosixPath(name)
    parts = [part.casefold() for part in path.parts]
    suffix = path.suffix.casefold()
    problems = []
    if (
        suffix in PRIVATE_SUFFIXES
        or re.search(r"\.(?:db|sqlite|sqlite3)-(?:wal|shm|journal)$", name, re.I)
        or path.name.casefold()
        in {"llm.json", "desktop-background.json", "speech-credentials.json"}
        or path.name.casefold().startswith(".env")
        and path.name.casefold() not in {".env.example", ".env.template"}
        or parts
        and parts[0] in DATA_ROOTS
        or any(part in {"user-data", "app-data", "saves"} for part in parts)
    ):
        problems.append("private_data_path")
    if data.startswith(b"SQLite format 3\x00"):
        problems.append("sqlite_database")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        cursor = 8
        while cursor + 12 <= len(data):
            size = struct.unpack_from(">I", data, cursor)[0]
            end = cursor + 12 + size
            if end > len(data):
                break
            kind, payload = data[cursor + 4 : cursor + 8], data[cursor + 8 : end - 4]
            if kind in {b"tEXt", b"zTXt", b"iTXt"} and payload.split(b"\x00", 1)[0] in {
                b"chara",
                b"ccv3",
            }:
                problems.append("character_card_png")
                break
            cursor = end
    if PRIVATE_KEY.search(data):
        problems.append("private_signing_key")
    for value in CREDENTIAL.findall(data):
        # Explicitly fictional canaries are permitted only in source tests.
        fictional = (b"SYNTHETIC" in value and b"NOT_REAL" in value) or b"test-secret" in value
        if not (source and name.startswith("tests/") and fictional):
            problems.append("credential_literal")
            break
    if suffix in {".md", ".txt", ".json"} and PROFILE_PATH.search(data):
        problems.append("personal_profile_path")
    if suffix == ".json":
        try:
            document = json.loads(data)
        except (ValueError, UnicodeError):
            document = None
        if isinstance(document, dict):
            if document.get("format") == "dreamtalk.chat":
                problems.append("chat_export")
            controlled = source and name.startswith(
                ("tests/fixtures/character_cards/", "tests/fixtures/lorebooks/")
            )
            entries = document.get("entries", [])
            if isinstance(entries, dict):
                entries = list(entries.values())
            lorebook = isinstance(entries, list) and any(
                isinstance(entry, dict) and "content" in entry for entry in entries
            )
            if not controlled and (
                document.get("spec") in ("chara_card_v2", "chara_card_v3") or lorebook
            ):
                problems.append("authored_content_export")
    return problems


def source_files(ref: str | None):
    if ref is not None:
        revision = (
            subprocess.check_output(
                ["git", "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"], cwd=ROOT
            )
            .decode()
            .strip()
        )
        entries = subprocess.check_output(
            ["git", "ls-tree", "-rz", "--full-tree", revision], cwd=ROOT
        ).split(b"\0")
        for entry in entries:
            if not entry:
                continue
            metadata, encoded_name = entry.split(b"\t", 1)
            file_mode, kind, identity = metadata.split()
            if kind != b"blob" or file_mode not in {b"100644", b"100755"}:
                raise ValueError("source_external_path")
            name = encoded_name.decode("utf-8")
            yield name, subprocess.check_output(["git", "cat-file", "blob", identity], cwd=ROOT)
        return
    entries = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT
    ).split(b"\0")
    for encoded_name in sorted(set(entries) - {b""}):
        name = encoded_name.decode("utf-8")
        path = ROOT / name
        if not path.exists():
            continue  # A tracked deletion is absent from the next source snapshot.
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("source_external_path")
        yield name, path.read_bytes()


def package_files(package: Path):
    artifacts = ROOT / "artifacts"
    if artifacts.is_symlink() or not artifacts.resolve().is_relative_to(ROOT):
        raise ValueError("package_external_path")
    package = package.resolve()
    if not package.is_relative_to(artifacts.resolve()) or not package.is_dir():
        raise ValueError("package_must_be_inside_artifacts")
    for path in sorted(package.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(package):
            raise ValueError("package_external_path")
        if not path.is_file():
            continue
        name = path.relative_to(package).as_posix()
        # Inspect headers of binaries, full text/configuration of readable resources.
        with path.open("rb") as stream:
            data = stream.read() if path.suffix.casefold() in TEXT_SUFFIXES else stream.read(8192)
        yield name, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ref", help="Inspect the exact committed source before publishing")
    mode.add_argument(
        "--package", type=Path, help="Inspect a staged/extracted package inside artifacts"
    )
    args = parser.parse_args()
    try:
        files = package_files(args.package) if args.package else source_files(args.ref)
        count, problems = 0, []
        for name, data in files:
            count += 1
            problems.extend(
                f"{name}: {code}" for code in findings(name, data, source=not args.package)
            )
    except (OSError, ValueError, subprocess.CalledProcessError):
        raise SystemExit("privacy_inspection_incomplete") from None
    if problems:
        raise SystemExit("Release privacy blocked:\n" + "\n".join(problems))
    print(f"Release privacy: {count} files inspected, 0 findings; no app-data or model access")


if __name__ == "__main__":
    main()
