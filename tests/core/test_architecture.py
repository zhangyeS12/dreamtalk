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


def test_command_wall_clock_is_injected_and_raw_store_is_read_only():
    root = Path(__file__).resolve().parents[2] / "services/core/src/livingworld"
    for source in (root / "application").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"now", "utcnow", "execute", "merge"}, (
                    source,
                    node.lineno,
                )
    from livingworld.infrastructure.persistence.store import PersistenceStore

    assert not hasattr(PersistenceStore, "add")


def test_replay_has_no_external_effects_or_command_dispatch():
    root = Path(__file__).resolve().parents[2] / "services/core/src/livingworld"
    source = root / "application/replay.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden_modules = {"os", "pathlib", "socket", "httpx", "requests", "sqlite3", "random"}
    forbidden_calls = {
        "now",
        "utcnow",
        "now_utc",
        "uuid1",
        "uuid4",
        "uuid5",
        "open",
        "execute",
        "append",
        "send",
        "write_text",
        "write_bytes",
        "unlink",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] not in forbidden_modules for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] not in forbidden_modules
            assert "command_handler" not in node.module
        elif isinstance(node, ast.Call):
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            assert name not in forbidden_calls, (source, node.lineno, name)


def test_replay_ports_do_not_grant_canonical_mutation_capabilities():
    from livingworld.application.ports import CanonicalEventReader, ProjectionRebuildUnitOfWork

    assert not hasattr(CanonicalEventReader, "append")
    assert "events" not in ProjectionRebuildUnitOfWork.__annotations__
    assert "receipts" not in ProjectionRebuildUnitOfWork.__annotations__


def test_cas_contracts_use_existing_revision_and_focused_ports():
    from inspect import Parameter, signature
    from typing import get_type_hints

    from livingworld.application.commands import (
        ChangeRelationship,
        FormCharacterBelief,
        MovePlayer,
        PlaceCharacter,
    )
    from livingworld.application.ports import (
        CharacterRepository,
        PlayerRepository,
        RelationshipRepository,
    )
    from livingworld.domain.values import Revision

    for command, field, kind in (
        (MovePlayer, "expected_presence_revision", Revision),
        (PlaceCharacter, "expected_state_revision", Revision | None),
        (ChangeRelationship, "expected_relationship_revision", Revision | None),
    ):
        assert get_type_hints(command)[field] == kind
        assert signature(command).parameters[field].default is Parameter.empty
    for method, kind in (
        (PlayerRepository.replace_presence, Revision),
        (CharacterRepository.put_state, Revision | None),
        (RelationshipRepository.put, Revision | None),
    ):
        assert get_type_hints(method)["expected_revision"] == kind
        assert signature(method).parameters["expected_revision"].default is Parameter.empty
    assert not any("expected" in field for field in get_type_hints(FormCharacterBelief))


def test_content_flow_has_no_runtime_mutation_or_knowledge_capability():
    from livingworld.application.content import ContentRepository

    assert not {"events", "receipts", "worlds", "knowledge", "execute"} & set(
        vars(ContentRepository)
    )
    root = Path(__file__).resolve().parents[2] / "services/core/src/livingworld"
    forbidden = {"command_handler", "unit_of_work", "knowledge", "events", "participants", "world"}
    for relative in ("application/content.py", "infrastructure/persistence/content_repository.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module.startswith("livingworld."):
                assert node.module.split(".")[-1] not in forbidden, (relative, node.module)


def test_external_importers_have_only_content_and_import_capabilities():
    root = Path(__file__).resolve().parents[2] / "services/core/src/livingworld"
    allowed = (
        "livingworld.domain.content",
        "livingworld.domain.errors",
        "livingworld.application.content",
        "livingworld.application.imports",
        "livingworld.infrastructure.imports",
    )
    sources = [root / "application/imports.py", *(root / "infrastructure/imports").glob("*.py")]
    forbidden = {"socket", "subprocess", "urllib", "httpx", "requests", "os", "pathlib"}
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module]
            else:
                continue
            for module in modules:
                assert module.split(".")[0] not in forbidden, (source, module)
                if module.startswith("livingworld."):
                    assert any(
                        module == prefix or module.startswith(prefix + ".") for prefix in allowed
                    ), (source, module)


def test_external_exporters_have_no_runtime_or_external_effect_capabilities():
    root = Path(__file__).resolve().parents[2] / "services/core/src/livingworld"
    allowed = (
        "livingworld.domain.content",
        "livingworld.domain.errors",
        "livingworld.application.content",
        "livingworld.application.exports",
        "livingworld.application.imports",
        "livingworld.infrastructure.imports",
        "livingworld.infrastructure.exports",
    )
    forbidden = {
        "socket",
        "subprocess",
        "urllib",
        "httpx",
        "requests",
        "os",
        "pathlib",
        "sqlite3",
        "sqlalchemy",
    }
    sources = [root / "application/exports.py", *(root / "infrastructure/exports").glob("*.py")]
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text("utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module]
            else:
                modules = []
            for module in modules:
                assert module.split(".")[0] not in forbidden, (source, module)
                if module.startswith("livingworld."):
                    assert any(
                        module == prefix or module.startswith(prefix + ".") for prefix in allowed
                    ), (source, module)
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", "")
                )
                assert name not in {
                    "open",
                    "write_text",
                    "write_bytes",
                    "execute",
                    "eval",
                    "exec",
                    "uuid4",
                    "now",
                    "utcnow",
                }, (source, name)


def test_native_packages_are_content_only_and_container_io_stays_outside_application():
    root = Path(__file__).resolve().parents[2] / "services/core/src/livingworld"
    sources = [
        root / "application/content_packages.py",
        root / "application/package_service.py",
        root / "infrastructure/packages/lwcontent.py",
    ]
    allowed = (
        "livingworld.domain.content",
        "livingworld.domain.errors",
        "livingworld.domain.values",
        "livingworld.application.content",
        "livingworld.application.imports",
        "livingworld.application.content_packages",
        "livingworld.infrastructure.imports.json_input",
    )
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text("utf-8"))):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for module in modules:
                assert module.split(".")[0] not in {
                    "socket",
                    "subprocess",
                    "urllib",
                    "os",
                    "pathlib",
                    "sqlite3",
                    "sqlalchemy",
                    "httpx",
                    "requests",
                }, (source, module)
                if source.parent.name == "application":
                    assert module.split(".")[0] not in {"zipfile", "io"}
                if module.startswith("livingworld."):
                    assert any(
                        module == prefix or module.startswith(prefix + ".") for prefix in allowed
                    ), (source, module)
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", "")
                )
                assert name not in {
                    "extract",
                    "extractall",
                    "write_text",
                    "write_bytes",
                    "execute",
                    "eval",
                    "exec",
                    "now",
                    "utcnow",
                }, (source, name)
                assert not isinstance(node.func, ast.Name) or node.func.id != "open"
    for source in (root / "domain").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text("utf-8"))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                assert all(
                    module.split(".")[0] not in {"zipfile", "pathlib", "os"} for module in modules
                ), source
