"""The single real wall-clock implementation for application commands."""

from datetime import UTC, datetime


class SystemWallClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)
