"""Shared provider-neutral HTTP transport facts; no provider wire schemas."""

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from sys import float_info

import httpx

from livingworld.application.llm import DispatchState, LLMErrorCode


def normalize_retry_after(value, *, now_utc=None):
    """Normalize a standard Retry-After once without retaining the raw header."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"-?[0-9]+", value):
        if value.startswith("-"):
            return 0.0
        seconds = float(value)
        return max(0.0, seconds) if isfinite(seconds) else float_info.max
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return max(0.0, (date - (now_utc or datetime.now(UTC))).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_transport_failure(error, *, response_received=False):
    """Use only concrete HTTPX phase facts; uncertain dispatch is never replay-safe."""
    if isinstance(error, httpx.InvalidURL):
        return LLMErrorCode.CONFIGURATION, DispatchState.NOT_DISPATCHED
    code = (
        LLMErrorCode.TIMEOUT
        if isinstance(error, httpx.TimeoutException)
        else LLMErrorCode.PROVIDER_UNAVAILABLE
    )
    not_dispatched = not response_received and isinstance(
        error, (httpx.PoolTimeout, httpx.ConnectTimeout, httpx.ConnectError)
    )
    return code, (
        DispatchState.NOT_DISPATCHED if not_dispatched else DispatchState.DISPATCHED_OR_UNKNOWN
    )


def is_event_stream(value):
    parts = [part.strip().lower() for part in value.split(";")]
    if not parts or parts[0] != "text/event-stream":
        return False
    for part in parts[1:]:
        name, _, parameter = part.partition("=")
        if name.strip() == "charset" and parameter.strip().strip('"') not in {"utf-8", "utf8"}:
            return False
    return True


async def bounded_body(response, limit):
    body = bytearray()
    try:
        async for fragment in response.aiter_bytes():
            if len(body) + len(fragment) > limit:
                return None
            body.extend(fragment)
    except httpx.HTTPError:
        return None
    return bytes(body)
