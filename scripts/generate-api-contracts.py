"""Generate DTO types and guards from Python annotations, without importing the app."""

import argparse
import ast
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/core/src/livingworld/adapters/http/contracts.py"
TARGET = ROOT / "packages/api-client/src/contracts.generated.ts"


def generate() -> str:
    models: list[ast.ClassDef | ast.TypeAlias] = []
    source_dir = SOURCE.parent / "wire_contracts"
    for path in sorted(source_dir.glob("*.py")):
        models.extend(
            node
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, (ast.ClassDef, ast.TypeAlias))
        )
    # These production models also own the HTTP schema; do not mirror them in DTOs.
    persona = ast.parse(
        (SOURCE.parents[2] / "application/player_persona.py").read_text(encoding="utf-8")
    )
    persona_models = {
        "PersonaModel",
        "PersonaReference",
        "InitialRecognition",
        "PlayerPersonaDraft",
        "PersonaSourceChoice",
        "PersonaSourcePage",
        "PlayerPersonaSnapshot",
        "PlayerPersonaPreview",
    }
    models.extend(
        node
        for node in persona.body
        if isinstance(node, ast.ClassDef) and node.name in persona_models
    )
    paths = ast.parse((SOURCE.parents[2] / "application/chat_paths.py").read_text("utf-8"))
    models.extend(
        node
        for node in paths.body
        if isinstance(node, ast.ClassDef) and node.name in {"PathDraft", "PathConfirm"}
    )
    lore = ast.parse((SOURCE.parents[2] / "application/lore_controls.py").read_text("utf-8"))
    models.extend(
        node for node in lore.body if isinstance(node, ast.ClassDef) and node.name == "LoreControls"
    )
    runtime = ast.parse((SOURCE.parents[2] / "application/runtime.py").read_text(encoding="utf-8"))
    models.extend(
        node
        for node in runtime.body
        if isinstance(node, ast.TypeAlias) and node.name.id == "LLMRuntimeStatus"
    )
    enums: dict[str, list[str]] = {}
    for module, selected in (("participants", "PlayerAvailability"), ("world", "ClockState")):
        path = SOURCE.parents[2] / "domain" / (module + ".py")
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef) and node.name == selected:
                enums[node.name] = [
                    value.value.value
                    for value in node.body
                    if isinstance(value, ast.Assign)
                    and isinstance(value.value, ast.Constant)
                    and isinstance(value.value.value, str)
                ]
    # Request DTOs stay beside their HTTP handlers; their actual fields/defaults are authoritative.
    for path in sorted(SOURCE.parent.glob("*.py")):
        if path == SOURCE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        local = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and any(isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases)
        }
        changed = True
        while changed:
            previous = set(local)
            local.update(
                node.name
                for node in tree.body
                if isinstance(node, ast.ClassDef)
                and any(isinstance(base, ast.Name) and base.id in local for base in node.bases)
            )
            changed = previous != local
        prefix = "Http" + "".join(part.title() for part in path.stem.split("_"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name not in local:
                continue
            model = copy.deepcopy(node)

            class Rename(ast.NodeTransformer):
                def __init__(self, local_names: set[str], name_prefix: str) -> None:
                    self.local_names = local_names
                    self.name_prefix = name_prefix

                def visit_Name(self, node: ast.Name) -> ast.Name:
                    if node.id in self.local_names:
                        node.id = self.name_prefix + node.id
                    elif node.id in {"EditorDraft", "EditorEntry"}:
                        node.id = "Content" + node.id
                    elif node.id == "StrictBool":
                        node.id = "bool"
                    return node

            model = Rename(local, prefix).visit(model)
            model.name = prefix + node.name
            models.append(model)
    names = {node.name if isinstance(node, ast.ClassDef) else node.name.id for node in models}
    names.update(enums)

    def render(node: ast.expr, value: str | None = None) -> str:
        if isinstance(node, ast.Constant):
            literal = json.dumps(node.value, ensure_ascii=False)
            return literal if value is None else f"{value} === {literal}"
        if isinstance(node, ast.Name):
            simple = {
                "str": "string",
                "UUID": "string",
                "int": "number",
                "float": "number",
                "bool": "boolean",
            }
            if node.id in simple:
                kind = simple[node.id]
                return kind if value is None else f'typeof {value} === "{kind}"'
            if node.id == "Decimal":
                return (
                    "(string | number)"
                    if value is None
                    else f'(typeof {value} === "string" || typeof {value} === "number")'
                )
            if node.id == "object":
                return "unknown" if value is None else "true"
            if node.id in names:
                return node.id if value is None else f"is{node.id}({value})"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            sep = " | " if value is None else " || "
            parts = list(dict.fromkeys(render(part, value) for part in [node.left, node.right]))
            return "(" + sep.join(parts) + ")"
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == "Literal":
                parts = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
                return (
                    "("
                    + (" | " if value is None else " || ").join(
                        render(part, value) for part in parts
                    )
                    + ")"
                )
            if node.value.id == "list":
                return (
                    f"Array<{render(node.slice)}>"
                    if value is None
                    else (
                        f"(Array.isArray({value}) && "
                        f"{value}.every(item => {render(node.slice, 'item')}))"
                    )
                )
            if node.value.id == "dict" and isinstance(node.slice, ast.Tuple):
                key, item_type = node.slice.elts
                if isinstance(key, ast.Name) and key.id == "str":
                    if isinstance(item_type, ast.Name) and item_type.id == "object":
                        return "Record<string, unknown>" if value is None else f"isObject({value})"
                    return (
                        f"Record<string, {render(item_type)}>"
                        if value is None
                        else (
                            f"(isObject({value}) && Object.values({value}).every("
                            f"item => {render(item_type, 'item')}))"
                        )
                    )
                return (
                    f"Partial<Record<{render(key)}, {render(item_type)}>>"
                    if value is None
                    else (
                        f"(isObject({value}) && Object.entries({value}).every("
                        f"([key, item]) => ({render(key, 'key')}) && "
                        f"({render(item_type, 'item')})))"
                    )
                )
        raise ValueError("Unsupported contract annotation: " + ast.unparse(node))

    output = [
        "// Generated by scripts/generate-api-contracts.py. Edit Python DTOs, then regenerate.",
        "function isObject(value: unknown): value is Record<string, unknown> {",
        '  return typeof value === "object" && value !== null && !Array.isArray(value);',
        "}",
    ]
    for name in enums:
        literals = " | ".join(json.dumps(value) for value in enums[name])
        checks = " || ".join("value === " + json.dumps(value) for value in enums[name])
        output += [
            f"export type {name} = {literals};",
            f"export function is{name}(value: unknown): value is {name} {{ return {checks}; }}",
        ]
    for node in models:
        if isinstance(node, ast.TypeAlias):
            name = node.name.id
            output += [
                f"export type {name} = {render(node.value)};",
                (
                    f"export function is{name}(value: unknown): value is {name} "
                    f"{{ return {render(node.value, 'value')}; }}"
                ),
            ]
        elif isinstance(node, ast.ClassDef):
            bases = [
                base.id
                for base in node.bases
                if isinstance(base, ast.Name) and base.id not in {"BaseModel", "TypedDict"}
            ]
            fields: list[tuple[str, ast.expr, bool]] = []
            for field in node.body:
                if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name):
                    continue
                annotation = field.annotation
                optional = False
                if (
                    isinstance(annotation, ast.Subscript)
                    and isinstance(annotation.value, ast.Name)
                    and annotation.value.id == "NotRequired"
                ):
                    optional = True
                    annotation = annotation.slice
                default = field.value
                if default is not None:
                    if (
                        isinstance(default, ast.Call)
                        and isinstance(default.func, ast.Name)
                        and default.func.id == "Field"
                    ):
                        optional = (
                            optional
                            or bool(default.args)
                            or any(
                                k.arg in {"default", "default_factory"} for k in default.keywords
                            )
                        )
                    else:
                        optional = True
                fields.append((field.target.id, annotation, optional))
            if not fields and not bases:
                output += [
                    f"export type {node.name} = object;",
                    (
                        f"export function is{node.name}(value: unknown): value is {node.name} "
                        "{ return isObject(value); }"
                    ),
                ]
                continue
            output += [
                f"export type {node.name} = " + "".join(base + " & " for base in bases) + "{"
            ]
            for name, annotation, optional in fields:
                output += [f"  {name}{'?' if optional else ''}: {render(annotation)};"]
            output += [
                "};",
                f"export function is{node.name}(value: unknown): value is {node.name} {{",
            ]
            checks = ["isObject(value)"]
            for name, annotation, optional in fields:
                check = render(annotation, "value." + name)
                checks += [f'(!("{name}" in value) || ({check}))' if optional else check]
            checks += [f"is{base}(value)" for base in bases]
            output += ["  return " + " && ".join("(" + check + ")" for check in checks) + ";", "}"]
    return "\n".join(output) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = generate()
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != generated:
            raise SystemExit(
                "API contracts are stale; run "
                "uv run --frozen python scripts/generate-api-contracts.py"
            )
        print("Generated API DTOs and guards match Python annotations.")
    else:
        TARGET.write_text(generated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
