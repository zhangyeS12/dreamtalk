"""PyInstaller onedir Core; keep Alembic revisions available as real files."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "services" / "core" / "src"
if not (ROOT / "artifacts/semantic-model/manifest.json").is_file():
    raise SystemExit("Run scripts/prepare-semantic-model.py before packaging.")

analysis = Analysis(
    [str(ROOT / "scripts" / "core-entry.py")],
    pathex=[str(PACKAGE)],
    binaries=[
        (
            str(
                ROOT
                / "tools"
                / "deepseek-request-bound"
                / "target"
                / "release"
                / "dreamtalk-deepseek-request-bound.exe"
            ),
            "request-bound",
        )
    ],
    datas=collect_data_files("livingworld", include_py_files=True)
    + copy_metadata("dreamtalk-core")
    + copy_metadata("pillow")
    + copy_metadata("jieba")
    + copy_metadata("ddgs")
    + copy_metadata("primp")
    + copy_metadata("lxml")
    + copy_metadata("fastembed", recursive=True)
    + copy_metadata("diskcache")
    + copy_metadata("onnxruntime")
    + copy_metadata("tokenizers")
    + collect_data_files("fastembed", include_py_files=True)
    + [(str(ROOT / "artifacts/semantic-model"), "semantic-model")]
    + collect_data_files("ddgs", include_py_files=True),
    hiddenimports=["aiosqlite", "ddgs.ddgs"]
    + collect_submodules("ddgs.engines")
    + collect_submodules("fastembed")
    + collect_submodules("livingworld.infrastructure.persistence.migrations.versions"),
    hookspath=[str(ROOT / "scripts" / "pyinstaller-hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["jieba.lac_small", "paddle"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="dreamtalk-core",
    console=True,
)
collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="dreamtalk-core",
)
