"""Convert the unmodified user-supplied DreamTalk artwork with Tauri's icon CLI."""

import base64
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "apps/web/public/brand/dreamtalk-logo.png"
    image = source.read_bytes()
    if image[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("brand_source_must_be_png")
    width, height = struct.unpack(">II", image[16:24])
    side = max(width, height)
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm_not_found")
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="brand-icons-", dir=artifacts) as temporary:
        work = Path(temporary)
        data = base64.b64encode(image).decode("ascii")
        svg = work / "app-icon.svg"
        svg.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{side}" height="{side}" viewBox="0 0 {side} {side}">'
            f'<image x="{(side - width) / 2}" y="{(side - height) / 2}" width="{width}" '
            f'height="{height}" xlink:href="data:image/png;base64,{data}"/></svg>',
            encoding="utf-8",
        )
        output = work / "generated"
        subprocess.run(
            [
                npm,
                "exec",
                "--workspace",
                "@dreamtalk/desktop",
                "--",
                "tauri",
                "icon",
                str(svg),
                "--output",
                str(output),
            ],
            check=True,
            cwd=root,
        )
        for name in ("icon.ico", "icon.png"):
            shutil.copy2(output / name, root / "apps/desktop/src-tauri/icons" / name)
        shutil.copy2(output / "32x32.png", source.parent / "icon-32.png")
    print("Native icons and browser favicon generated; source artwork is unchanged.")


if __name__ == "__main__":
    main()
