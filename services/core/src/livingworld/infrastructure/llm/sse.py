"""Bounded, pull-driven data-only SSE framing. No HTTP or application semantics."""

from collections.abc import Iterator
from dataclasses import dataclass


class SSEProtocolError(ValueError):
    """Only a fixed structural label; never rejected wire bytes."""


@dataclass(frozen=True, slots=True)
class StreamLimits:
    max_event_bytes: int = 1024 * 1024
    max_line_bytes: int = 256 * 1024
    max_error_body_bytes: int = 64 * 1024
    max_model_bytes: int = 1024

    def __post_init__(self):
        if any(
            type(value) is not int or value < 1
            for value in (
                self.max_event_bytes,
                self.max_line_bytes,
                self.max_error_body_bytes,
                self.max_model_bytes,
            )
        ):
            raise ValueError("invalid_stream_limits")


class SSEDecoder:
    """Holds at most one bounded line and event, never an event queue.

    UTF-8 is decoded only after assembling a whole line. Incomplete multibyte
    sequences stay in the bounded byte buffer across arbitrary network fragments.
    feed is lazy even when one transport fragment contains many events.
    """

    def __init__(self, limits: StreamLimits):
        self._limits = limits
        self._line = bytearray()
        self._data: list[str] = []
        self._event_bytes = 0
        self._first_line = True

    def feed(self, fragment: bytes) -> Iterator[str]:
        offset = 0
        while offset < len(fragment):
            newline = fragment.find(b"\n", offset)
            end = len(fragment) if newline < 0 else newline
            if len(self._line) + end - offset > self._limits.max_line_bytes:
                raise SSEProtocolError("sse_line_limit")
            self._line.extend(fragment[offset:end])
            offset = end + 1
            if newline < 0:
                return
            raw = bytes(self._line)
            self._line.clear()
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            invalid = False
            try:
                line = raw.decode("utf-8", errors="strict")
            except UnicodeError:
                invalid = True
            if invalid:
                raise SSEProtocolError("sse_invalid_utf8")
            if self._first_line:
                line = line.removeprefix("\ufeff")
                self._first_line = False
            if not line:
                if self._data:
                    data = "\n".join(self._data)
                    self._data.clear()
                    self._event_bytes = 0
                    yield data
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            if field != "data":
                continue  # event/id/retry fields have no Chat Completions semantics.
            if value.startswith(" "):
                value = value[1:]  # SSE removes one field separator space only.
            self._event_bytes += len(value.encode("utf-8")) + 1
            if self._event_bytes > self._limits.max_event_bytes:
                raise SSEProtocolError("sse_event_limit")
            self._data.append(value)
