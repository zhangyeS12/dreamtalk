"""Check local Markdown destinations. External URLs are counted, not probed online."""

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
root = parser.parse_args().root.resolve()
sources = [*sorted(root.glob("*.md")), *sorted((root / "docs").rglob("*.md"))]
broken = []
checked = 0
external = 0
for source in sources:
    body = source.read_text(encoding="utf-8")
    targets = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", body)
    targets.extend(re.findall(r"(?m)^\s*\[[^\]]+\]:\s*(\S+)", body))
    for target in targets:
        target = target.strip("<>")
        parts = urlsplit(target)
        if parts.scheme or target.startswith("#"):
            external += bool(parts.scheme)
            continue
        checked += 1
        if not (source.parent / unquote(parts.path)).exists():
            broken.append(f"{source.relative_to(root)} -> {target}")
if broken:
    raise SystemExit("\n".join(broken))
print(f"Document links: {checked} local destinations, 0 broken; {external} external URLs counted")
