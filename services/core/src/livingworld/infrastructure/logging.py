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

    def emit_llm_reply_facts(
        self,
        *,
        trace_id: str,
        transport: str,
        reason: str | None = None,
        event: str = "chat_structured_failure_facts",
        finish_reason: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reasoning_output_tokens: int | None = None,
        max_output_tokens: int | None = None,
        http_status: int | None = None,
        validator_keyword: str | None = None,
        instance_path: tuple[str | int, ...] = (),
        schema_path: tuple[str | int, ...] = (),
    ) -> None:
        """Fixed enums and counters only; no model, prompt, answer or private IDs."""
        from livingworld.application.llm import (
            FinishReason,
            StructuredFailureDetail,
            StructuredFailureReason,
        )
        from livingworld.domain.contracts import RequestId

        if event not in {"chat_structured_failure_facts", "chat_annotation_response_facts"}:
            raise ValueError("invalid_llm_fact_event")
        if reason is not None and reason not in {item.value for item in StructuredFailureReason}:
            raise ValueError("invalid_structured_failure_reason")
        if event == "chat_structured_failure_facts" and reason is None:
            raise ValueError("structured_failure_reason_required")
        if finish_reason is not None and finish_reason not in {item.value for item in FinishReason}:
            raise ValueError("invalid_finish_reason")
        if transport not in {"prompt_json", "native_json"}:
            raise ValueError("invalid_structured_transport")
        record: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": "WARNING" if reason is not None else "INFO",
            "component": "llm",
            "event": event,
            "trace_id": str(RequestId.parse(trace_id)),
            "transport": transport,
        }
        if reason is not None:
            record["reason"] = reason
        if reason is not None and (validator_keyword is not None or instance_path or schema_path):
            detail = StructuredFailureDetail(
                StructuredFailureReason(reason), instance_path, schema_path, validator_keyword
            )
            if detail.validator_keyword is not None:
                record["validator_keyword"] = detail.validator_keyword
            if detail.instance_path:
                record["instance_path"] = list(detail.instance_path)
            if detail.schema_path:
                record["schema_path"] = list(detail.schema_path)
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

    def emit_chat_media_context_facts(
        self,
        *,
        placement: str,
        library_available: bool,
        library_complete: bool,
        library_sticker_count: int | None,
        candidate_count: int,
        timestamped_candidates: int,
        media_allowed: bool,
    ) -> None:
        """Packed snapshot counts only, never descriptions, assets or private IDs."""
        if placement not in {"current_question", "group_context"}:
            raise ValueError("invalid_media_context_placement")
        if any(
            type(value) is not bool
            for value in (library_available, library_complete, media_allowed)
        ):
            raise ValueError("invalid_media_context_flag")
        if (
            library_sticker_count is not None
            and (
                type(library_sticker_count) is not int
                or not 0 <= library_sticker_count <= 2**63 - 1
            )
        ) or (not library_available and library_sticker_count is not None):
            raise ValueError("invalid_media_library_count")
        if (
            type(candidate_count) is not int
            or type(timestamped_candidates) is not int
            or not 0 <= timestamped_candidates <= candidate_count <= 5
            or (library_sticker_count is not None and candidate_count > library_sticker_count)
        ):
            raise ValueError("invalid_media_candidate_count")
        self._write(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "INFO",
                "component": "chat_media",
                "event": "packed_context_facts",
                "placement": placement,
                "library_available": library_available,
                "library_complete": library_complete,
                "library_sticker_count": library_sticker_count,
                "candidate_count": candidate_count,
                "timestamped_candidates": timestamped_candidates,
                "media_allowed": media_allowed,
            }
        )

    def emit_group_reply_facts(
        self,
        *,
        outcome: str,
        elapsed_ms: int,
        selection_calls: int,
        reply_calls: int,
        selection_ms: int,
        reply_ms: int,
        admission_blocks: int,
        reserved_attempts: int,
    ) -> None:
        """Local counters only; logical calls differ from physical reservations."""
        if outcome not in {"completed", "failed", "cancelled"}:
            raise ValueError("invalid_group_reply_outcome")
        counters = {
            "elapsed_ms": elapsed_ms,
            "selection_calls": selection_calls,
            "reply_calls": reply_calls,
            "selection_ms": selection_ms,
            "reply_ms": reply_ms,
            "admission_blocks": admission_blocks,
            "reserved_attempts": reserved_attempts,
        }
        if any(
            type(value) is not int or not 0 <= value <= 2**63 - 1 for value in counters.values()
        ):
            raise ValueError("invalid_group_reply_counter")
        self._write(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "INFO",
                "component": "group_chat",
                "event": "turn_execution_facts",
                "outcome": outcome,
                **counters,
            }
        )

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

    def emit_speech_signal_facts(
        self,
        *,
        sample_rate: int,
        channels: int,
        duration_seconds: float,
        declared_duration_seconds: float,
        trailing_quiet_seconds: float,
        missing_frames: int,
        per_second_rms_dbfs: list[float],
        per_second_peak_dbfs: list[float],
    ) -> None:
        """Only fixed numerical audio levels; waveform, text and identifiers are absent."""
        import math

        if (
            not 8000 <= sample_rate <= 192000
            or channels not in {1, 2}
            or not 0 < duration_seconds <= 1800
            or not 0 < declared_duration_seconds <= 1800
            or not 0 <= trailing_quiet_seconds <= duration_seconds
            or not 0 <= missing_frames <= sample_rate * 1800
            or not 1 <= len(per_second_rms_dbfs) <= 1800
            or len(per_second_rms_dbfs) != len(per_second_peak_dbfs)
            or any(
                not math.isfinite(value) or not -120 <= value <= 0
                for value in (*per_second_rms_dbfs, *per_second_peak_dbfs)
            )
        ):
            raise ValueError("speech_signal_facts_invalid")
        self._write(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "INFO",
                "component": "speech",
                "event": "audio_signal_statistics",
                "sample_rate": sample_rate,
                "channels": channels,
                "duration_seconds": duration_seconds,
                "declared_duration_seconds": declared_duration_seconds,
                "trailing_quiet_seconds": trailing_quiet_seconds,
                "missing_frames": missing_frames,
                "per_second_rms_dbfs": per_second_rms_dbfs,
                "per_second_peak_dbfs": per_second_peak_dbfs,
            }
        )

    def _write(self, record: dict[str, object]) -> None:
        line = json.dumps(record) + "\n"
        self.stream.write(line)
        self.stream.flush()
        if self.logfile is not None:
            with self.logfile.open("a", encoding="utf-8") as destination:
                destination.write(line)
