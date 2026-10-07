"""Copy help documents and replace source-only destinations with versioned GitHub links."""

import json
import posixpath
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

_REPOSITORY = "https://github.com/zhangyeS12/dreamtalk"


def _source_ref(root: Path) -> str:
    git = shutil.which("git")
    if git is not None:
        result = subprocess.run(
            [git, "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", result.stdout.strip()):
            return result.stdout.strip()
    configuration = json.loads(
        (root / "apps/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )
    return f"v{configuration['version']}"


def copy_portable_docs(root: Path, package: Path) -> None:
    shutil.copytree(root / "docs", package / "docs")
    for name in ("AGENTS.md", "HANDOFF.md", "PRODUCT.md"):
        shutil.copy2(root / name, package / name)
    source_ref = _source_ref(root)
    for destination in sorted(package.rglob("*.md")):
        relative = destination.relative_to(package)
        source = root / relative
        if relative == Path("README.md"):
            source = root / "docs/PORTABLE_WINDOWS.md"

        def replace_target(
            match: re.Match,
            *,
            destination: Path = destination,
            source: Path = source,
            relative: Path = relative,
        ) -> str:
            target = match[2].strip("<>")
            parts = urlsplit(target)
            if parts.scheme or target.startswith("#"):
                return match[0]
            local = destination.parent / unquote(parts.path)
            if local.exists():
                return match[0]
            original = (source.parent / unquote(parts.path)).resolve()
            if not original.exists() or not original.is_relative_to(root.resolve()):
                raise ValueError(f"portable_document_target_missing:{relative}:{target}")
            original_relative = original.relative_to(root.resolve())
            if (package / original_relative).exists():
                path = quote(
                    posixpath.relpath(original_relative.as_posix(), relative.parent.as_posix()),
                    safe="/",
                )
                if parts.query:
                    path += "?" + parts.query
                if parts.fragment:
                    path += "#" + parts.fragment
                return match[1] + path + match[3]
            path = quote(original_relative.as_posix(), safe="/")
            kind = "tree" if original.is_dir() else "blob"
            url = f"{_REPOSITORY}/{kind}/{quote(source_ref, safe='')}/{path}"
            if parts.fragment:
                url += "#" + quote(parts.fragment, safe="")
            return match[1] + url + match[3]

        body = destination.read_text(encoding="utf-8")
        body = re.sub(r"(!?\[[^\]]*\]\()([^)]+)(\))", replace_target, body)
        body = re.sub(r"(?m)^(\s*\[[^\]]+\]:\s*)(\S+)()", replace_target, body)
        destination.write_text(body, encoding="utf-8")
    (package / "SOURCE_REVISION.txt").write_text(
        f"source_link_ref={source_ref}\n"
        "Source-only links use this Git reference; bundled documents may include local edits.\n",
        encoding="utf-8",
    )
