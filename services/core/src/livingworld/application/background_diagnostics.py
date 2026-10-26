"""Content-free diagnostics for bounded background work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from livingworld.domain.identifiers import WorldId

BackgroundComponent = Literal["director", "proactive_contact", "offline_contact"]
BackgroundOutcome = Literal["failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class BackgroundTaskDiagnostic:
    """A safe task receipt; it never carries prompts, replies, or exception text."""

    component: BackgroundComponent
    outcome: BackgroundOutcome
    phase: str
    code: str
    world_id: WorldId | None = None
    task_id: UUID | None = None
    generation: int | None = None


class BackgroundDiagnosticSink(Protocol):
    def emit(self, diagnostic: BackgroundTaskDiagnostic) -> None: ...


class NullBackgroundDiagnosticSink:
    def emit(self, diagnostic: BackgroundTaskDiagnostic) -> None:
        pass


def emit_background_diagnostic(
    sink: BackgroundDiagnosticSink, diagnostic: BackgroundTaskDiagnostic
) -> None:
    """Diagnostics are best effort and cannot change task settlement or retry policy."""

    try:
        sink.emit(diagnostic)
    except Exception:
        pass
