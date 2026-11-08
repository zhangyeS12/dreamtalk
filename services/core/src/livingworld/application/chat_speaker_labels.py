"""Separate group source labels from dialogue, without rewriting stored messages."""

import re
from dataclasses import dataclass

from livingworld.domain.identifiers import CharacterId


def _body_after_header(value: str) -> str:
    value = value.lstrip(" \t")
    if value.startswith("\r\n"):
        return value[2:]
    return value[1:] if value.startswith("\n") else value


def without_legacy_speaker_header(
    text: str, speaker: CharacterId, *, name: str | None = None
) -> str:
    """Only an anchored, complete legacy header naming this exact sender is transport."""
    # Unknown historical names cannot consume prose, quotation or Markdown markers.
    candidate = text.lstrip("\ufeff \t\r\n")
    name_pattern = (
        re.escape(name) + r"[ \t]*"
        if name is not None
        else r"""[^\r\n（）()：:"'“”‘’「」『』。！？!?*`]+"""
    )
    header = re.match(
        r"\A"
        + name_pattern
        + r"[（(][ \t]*发言者标识[ \t]*[：:]"
        + r"[ \t]*(?i:"
        + re.escape(str(speaker.value))
        + r")[ \t]*[）)][ \t]*[：:]",
        candidate,
    )
    return _body_after_header(candidate[header.end() :]) if header else text


@dataclass(frozen=True, slots=True)
class SpeakerReplyText:
    name: str
    speaker: CharacterId

    def preview(self, text: str) -> str | None:
        """Withhold only a possible known header, including UUIDs split across deltas."""
        remaining = text.lstrip("\ufeff \t\r\n")
        tokens = (
            (self.name,),
            ("（", "("),
            ("发言者标识",),
            ("：", ":"),
            (str(self.speaker.value), str(self.speaker.value).upper()),
            ("）", ")"),
            ("：", ":"),
        )
        for alternatives in tokens:
            remaining = remaining.lstrip(" \t")
            matched = next((token for token in alternatives if remaining.startswith(token)), None)
            if matched is None:
                return None if any(token.startswith(remaining) for token in alternatives) else text
            remaining = remaining[len(matched) :]
        # A CR/LF separator can itself be split into two provider deltas.
        return None if remaining.lstrip(" \t") == "\r" else _body_after_header(remaining)

    def complete(self, text: str) -> str:
        if "发言者标识" in text and self.preview(text) is None:
            return ""  # A stopped, unfinished transport prefix is not character dialogue.
        return without_legacy_speaker_header(text, self.speaker, name=self.name)
