"""Safe scheduler diagnostics composition."""

from livingworld.application.scheduler import SchedulerDiagnostic
from livingworld.application.simulation_runtime import CatchUpReport, WorldRuntimeState
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


class StructuredCatchUpDiagnosticSink:
    def __init__(self, logger: StructuredLogger) -> None:
        self._logger = logger

    def emit(self, report: CatchUpReport) -> None:
        level = "WARNING" if report.anomalies or not report.completed else "INFO"
        self._logger.emit_catch_up(
            "catch_up_completed" if report.completed else "catch_up_interrupted",
            world_id=str(report.world_id.value),
            from_world_time=report.from_world_time.microseconds,
            target_world_time=report.target_world_time.microseconds,
            offline_elapsed_microseconds=report.offline_elapsed_microseconds,
            batches=report.batches,
            triggers_materialized=report.triggers_materialized,
            distinct_activations=report.distinct_activations,
            anomalies=tuple(value.value for value in report.anomalies),
            more_due=report.more_due,
            completed=report.completed,
            runtime_nanoseconds=report.runtime_nanoseconds,
            level=level,
        )

    def failed(self, world_id, state: WorldRuntimeState) -> None:
        self._logger.emit_catch_up(
            "catch_up_failed",
            world_id=str(world_id.value),
            completed=False,
            level="ERROR",
        )
