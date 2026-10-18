"""Keep JSON route schemas authoritative without opening a database or listening socket."""

import ast
from pathlib import Path

from livingworld.adapters.http import contracts
from pydantic import TypeAdapter

HTTP = Path(__file__).resolve().parents[2] / "services/core/src/livingworld/adapters/http"


def test_business_json_routes_cannot_silently_lose_their_response_schema():
    binary_or_stream = {
        "chat_media.py:image",
        "chat_messages.py:stream_direct_reply",
        "chat_messages.py:stream_group_reply",
        "file_exports.py:content_download",
        "file_exports.py:chat_download",
        "speech.py:reference",
        "speech.py:export",
        "speech.py:audio",
        "world_covers.py:image",
    }
    # The host control protocol remains separate from business DTOs.
    host = {"offline_contact.py:visibility", "worlds.py:deletion_status"}
    missing = []
    for path in HTTP.glob("*.py"):
        if path.name == "app.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                    and not any(keyword.arg == "response_model" for keyword in decorator.keywords)
                    and (node.returns is None or ast.unparse(node.returns) in {"dict", "object"})
                    and f"{path.name}:{node.name}" not in binary_or_stream | host
                ):
                    missing.append(f"{path.name}:{node.name}")
    assert missing == []


def test_response_schema_preserves_extension_fields_and_json_integer_representation():
    message = {
        "message_id": "message",
        "turn_id": "turn",
        "conversation_id": "conversation",
        "position": 1,
        "sender_kind": "character",
        "sender_id": "character",
        "text": "hello",
        "created_at_utc": "2026-10-18T00:00:00Z",
        "future_optional_annotation": {"safe": True},
    }
    adapter = TypeAdapter(contracts.ChatMessage)
    assert adapter.dump_json(adapter.validate_python(message)) == adapter.dump_json(message)
    assert type(adapter.validate_python(message)["position"]) is int
