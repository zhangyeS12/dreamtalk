import ast
import sys
from importlib.util import resolve_name
from pathlib import Path


def test_inner_layers_have_no_outward_dependencies():
    root = Path(__file__).resolve().parents[2] / "services/core/src/livingworld"
    forbidden = {"fastapi", "sqlalchemy", "alembic", "tauri", "pydantic", "uvicorn", "starlette"}
    for layer in ["domain", "application"]:
        for source in (root / layer).rglob("*.py"):
            package = ".".join(source.relative_to(root.parent).parts[:-1])
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    name = "." * node.level + (node.module or "")
                    modules = [resolve_name(name, package) if node.level else name]
                for module in modules:
                    assert module.split(".")[0] not in forbidden, (source, module)
                    if layer == "domain":
                        assert module.split(".")[0] != "sqlite3", (source, module)
                        assert (
                            module.split(".")[0] in sys.stdlib_module_names
                            or module.startswith("livingworld.domain.")
                            or module == "livingworld.domain"
                        ), (source, module)
                    if module.startswith("livingworld."):
                        allowed = (
                            ("livingworld.domain",)
                            if layer == "domain"
                            else (
                                "livingworld.domain",
                                "livingworld.application",
                            )
                        )
                        assert any(
                            module == prefix or module.startswith(prefix + ".")
                            for prefix in allowed
                        ), (source, module)
