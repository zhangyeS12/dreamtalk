from typing import Literal, TypedDict

ExpressionName = Literal[
    "neutral",
    "joy",
    "content",
    "sad",
    "angry",
    "surprised",
    "scared",
    "disgusted",
    "confused",
    "love",
    "embarrassed",
    "thinking",
]


class ChatVisualExpression(TypedDict):
    root_import_id: str
    expression: Literal[
        "neutral",
        "joy",
        "content",
        "sad",
        "angry",
        "surprised",
        "scared",
        "disgusted",
        "confused",
        "love",
        "embarrassed",
        "thinking",
    ]
    digest: str


class ChatVisuals(TypedDict):
    common_background_digest: str | None
    character_backgrounds: dict[str, str]
    expressions: list[ChatVisualExpression]


class ChatVisualBackgroundWrite(TypedDict):
    digest: str | None


class ChatVisualCharacterBackgroundWrite(TypedDict):
    root_import_id: str
    digest: str | None


class ChatVisualExpressionWrite(TypedDict):
    root_import_id: str
    expression: Literal[
        "neutral",
        "joy",
        "content",
        "sad",
        "angry",
        "surprised",
        "scared",
        "disgusted",
        "confused",
        "love",
        "embarrassed",
        "thinking",
    ]
    digest: str | None
