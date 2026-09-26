"""PyInstaller onedir Core; keep Alembic revisions available as real files."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "services" / "core" / "src"

analysis = Analysis(
    [str(ROOT / "scripts" / "core-entry.py")],
    pathex=[str(PACKAGE)],
    binaries=[],
    datas=collect_data_files("livingworld", include_py_files=True)
    + copy_metadata("dreamtalk-core"),
    hiddenimports=["aiosqlite"]
    + collect_submodules("livingworld.infrastructure.persistence.migrations.versions"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
