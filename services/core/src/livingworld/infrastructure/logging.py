"""Allowlisted structured records. Never accept arbitrary payloads or exception text."""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO


class StructuredLogger:
    def __init__(self, stream: TextIO | None = None, logfile: Path | None = None) -> None:
        self.stream = stream or sys.stdout
        self.logfile = logfile

    def emit(self, component: str, event: str, *, level: str = "INFO", trace_id: str | None = None):
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("invalid_log_level")
        if not all(re.fullmatch(r"[a-z][a-z0-9_.]*", value) for value in (component, event)):
            raise ValueError("invalid_log_label")
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "component": component,
            "event": event,
        }
        if trace_id is not None:
            from livingworld.domain.contracts import RequestId

            record["trace_id"] = str(RequestId.parse(trace_id))
        self._write(record)

    def emit_scheduler(
        self,
        event: str,
        *,
        world_id: str,
        scheduler_state: str,
        trigger_kind: str | None = None,
        due_world_time: int | None = None,
        queue_lag_world_time: int | None = None,
        batch_size: int | None = None,
        activation_count: int | None = None,
    ) -> None:
        """Write only the fixed scheduler metadata allowlist; payload is impossible here."""
        if not re.fullmatch(r"[a-z][a-z0-9_.]*", event):
            raise ValueError("invalid_log_label")
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "INFO",
            "component": "simulation_scheduler",
            "event": event,
            "world_id": world_id,
            "scheduler_state": scheduler_state,
        }
        optional = {
            "trigger_kind": trigger_kind,
            "due_world_time": due_world_time,
            "queue_lag_world_time": queue_lag_world_time,
            "batch_size": batch_size,
            "activation_count": activation_count,
        }
        record.update({key: value for key, value in optional.items() if value is not None})
        self._write(record)

    def _write(self, record: dict[str, object]) -> None:
        line = json.dumps(record) + "\n"
        self.stream.write(line)
        self.stream.flush()
        if self.logfile is not None:
            with self.logfile.open("a", encoding="utf-8") as destination:
                destination.write(line)
