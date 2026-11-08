"""Structured sink for bounded background-task diagnostics."""

from livingworld.application.background_diagnostics import BackgroundTaskDiagnostic
from livingworld.infrastructure.logging import StructuredLogger


class StructuredBackgroundDiagnosticSink:
    def __init__(self, logger: StructuredLogger) -> None:
        self._logger = logger

    def emit(self, diagnostic: BackgroundTaskDiagnostic) -> None:
        self._logger.emit_background_task(
            component=diagnostic.component,
            outcome=diagnostic.outcome,
            phase=diagnostic.phase,
            code=diagnostic.code,
            world_id=(str(diagnostic.world_id.value) if diagnostic.world_id is not None else None),
            task_id=(str(diagnostic.task_id) if diagnostic.task_id is not None else None),
            generation=diagnostic.generation,
        )
