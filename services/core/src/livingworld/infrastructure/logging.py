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
        line = json.dumps(record) + "\n"
        self.stream.write(line)
        self.stream.flush()
        if self.logfile is not None:
            with self.logfile.open("a", encoding="utf-8") as destination:
                destination.write(line)
