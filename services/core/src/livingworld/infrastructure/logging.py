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

    def emit_llm_structured_failure(
        self,
        *,
        trace_id: str,
        reason: str,
        transport: str,
        finish_reason: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reasoning_output_tokens: int | None = None,
        max_output_tokens: int | None = None,
        http_status: int | None = None,
    ) -> None:
        """Fixed enums and counters only; no model, prompt, answer or private IDs."""
        from livingworld.application.llm import FinishReason, StructuredFailureReason
        from livingworld.domain.contracts import RequestId

        if reason not in {item.value for item in StructuredFailureReason}:
            raise ValueError("invalid_structured_failure_reason")
        if finish_reason is not None and finish_reason not in {item.value for item in FinishReason}:
            raise ValueError("invalid_finish_reason")
        if transport not in {"prompt_json", "native_json"}:
            raise ValueError("invalid_structured_transport")
        record: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "WARNING",
            "component": "llm",
            "event": "chat_structured_failure_facts",
            "trace_id": str(RequestId.parse(trace_id)),
            "reason": reason,
            "transport": transport,
        }
        if finish_reason is not None:
            record["finish_reason"] = finish_reason
        for name, value in {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": reasoning_output_tokens,
            "max_output_tokens": max_output_tokens,
            "http_status": http_status,
        }.items():
            if value is not None:
                if type(value) is not int or not 0 <= value <= 2**63 - 1:
                    raise ValueError("invalid_llm_counter")
                if name == "http_status" and not 100 <= value <= 599:
                    raise ValueError("invalid_http_status")
                record[name] = value
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

    def emit_catch_up(
        self,
        event: str,
        *,
        world_id: str,
        from_world_time: int | None = None,
        target_world_time: int | None = None,
        offline_elapsed_microseconds: int | None = None,
        batches: int | None = None,
        triggers_materialized: int | None = None,
        distinct_activations: int | None = None,
        anomalies: tuple[str, ...] = (),
        more_due: bool | None = None,
        completed: bool | None = None,
        runtime_nanoseconds: int | None = None,
        level: str = "INFO",
    ) -> None:
        """Write only bounded clock/catch-up facts; trigger payloads are impossible."""
        if level not in {"INFO", "WARNING", "ERROR"}:
            raise ValueError("invalid_log_level")
        if not re.fullmatch(r"[a-z][a-z0-9_.]*", event):
            raise ValueError("invalid_log_label")
        record: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "component": "simulation_catch_up",
            "event": event,
            "world_id": world_id,
        }
        optional = {
            "from_world_time": from_world_time,
            "target_world_time": target_world_time,
            "offline_elapsed_microseconds": offline_elapsed_microseconds,
            "batches": batches,
            "triggers_materialized": triggers_materialized,
            "distinct_activations": distinct_activations,
            "more_due": more_due,
            "completed": completed,
            "runtime_nanoseconds": runtime_nanoseconds,
        }
        record.update({key: value for key, value in optional.items() if value is not None})
        if anomalies:
            record["anomalies"] = list(anomalies)
        self._write(record)

    def _write(self, record: dict[str, object]) -> None:
        line = json.dumps(record) + "\n"
        self.stream.write(line)
        self.stream.flush()
        if self.logfile is not None:
            with self.logfile.open("a", encoding="utf-8") as destination:
                destination.write(line)
