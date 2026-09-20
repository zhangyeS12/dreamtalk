"""Safe scheduler diagnostics composition."""

from livingworld.application.scheduler import SchedulerDiagnostic
from livingworld.infrastructure.logging import StructuredLogger


class StructuredSchedulerDiagnosticSink:
    def __init__(self, logger: StructuredLogger) -> None:
        self._logger = logger

    def emit(self, diagnostic: SchedulerDiagnostic) -> None:
        self._logger.emit_scheduler(
            diagnostic.event,
            world_id=str(diagnostic.world_id.value),
            scheduler_state=diagnostic.scheduler_state,
            trigger_kind=diagnostic.trigger_kind,
            due_world_time=(
                diagnostic.due_at.microseconds if diagnostic.due_at is not None else None
            ),
            queue_lag_world_time=diagnostic.queue_lag_microseconds,
            batch_size=diagnostic.batch_size,
            activation_count=diagnostic.activation_count,
        )
