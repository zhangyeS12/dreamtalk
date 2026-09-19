"""Bounded one-way Rust-host to Python-Core control framing."""

from __future__ import annotations

import json
import struct
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from livingworld.application.llm_config import SecretRef
from livingworld.infrastructure.llm.credentials import SessionCredentialProvider
from livingworld.infrastructure.logging import StructuredLogger

_CONTRACT_PATH = Path(__file__).with_name("host_control_contract.json")
HOST_CONTROL_CONTRACT = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
PROTOCOL_VERSION = HOST_CONTROL_CONTRACT["protocol_version"]
MAX_FRAME_BYTES = HOST_CONTROL_CONTRACT["max_frame_bytes"]
MAX_SECRET_REF_BYTES = HOST_CONTROL_CONTRACT["max_secret_ref_bytes"]
MAX_SECRET_BYTES = HOST_CONTROL_CONTRACT["max_secret_bytes"]
MESSAGE_TYPES = frozenset(HOST_CONTROL_CONTRACT["message_types"])


class ControlProtocolError(ValueError):
    """A bounded safe label; malformed frame contents are never retained."""

    def __init__(self, code: str = "host_control_protocol_rejected"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ControlMessage:
    message_type: str
    secret_ref: SecretRef | None = None
    secret: str | None = field(default=None, repr=False)
    secure_store_available: bool | None = None


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = stream.read(length - len(chunks))
        if not chunk:
            raise ControlProtocolError("host_control_frame_truncated")
        chunks.extend(chunk)
    return bytes(chunks)


def decode_frame(stream: BinaryIO) -> ControlMessage | None:
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ControlProtocolError("host_control_header_truncated")
    length = struct.unpack(">I", header)[0]
    if not 1 <= length <= MAX_FRAME_BYTES:
        raise ControlProtocolError("host_control_frame_size_invalid")
    body = _read_exact(stream, length)
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise ControlProtocolError() from None
    if type(data) is not dict or data.get("version") != PROTOCOL_VERSION:
        raise ControlProtocolError()
    message_type = data.get("type")
    if message_type not in MESSAGE_TYPES:
        raise ControlProtocolError()
    if message_type == "credential_sync_complete":
        if (
            set(data) != {"version", "type", "secure_store_available"}
            or type(data["secure_store_available"]) is not bool
        ):
            raise ControlProtocolError()
        return ControlMessage(message_type, secure_store_available=data["secure_store_available"])
    required = {"version", "type", "secret_ref"}
    if message_type == "credential_upsert":
        required.add("secret")
    if set(data) != required:
        raise ControlProtocolError()
    reference = data["secret_ref"]
    if type(reference) is not str or len(reference.encode("utf-8")) > MAX_SECRET_REF_BYTES:
        raise ControlProtocolError()
    try:
        secret_ref = SecretRef(UUID(reference))
    except (ValueError, TypeError):
        raise ControlProtocolError() from None
    if message_type == "credential_remove":
        return ControlMessage(message_type, secret_ref=secret_ref)
    secret = data["secret"]
    if type(secret) is not str or not secret or len(secret.encode("utf-8")) > MAX_SECRET_BYTES:
        raise ControlProtocolError()
    return ControlMessage(message_type, secret_ref=secret_ref, secret=secret)


def apply_message(message: ControlMessage, credentials: SessionCredentialProvider) -> None:
    if message.message_type == "credential_upsert":
        credentials.upsert(message.secret_ref, message.secret)
    elif message.message_type == "credential_remove":
        credentials.remove(message.secret_ref)
    elif message.message_type == "credential_sync_complete":
        credentials.complete_sync(secure_store_available=message.secure_store_available)
    else:
        raise ControlProtocolError()


class HostControlListener:
    """A bounded reader whose host-owned pipe defines its lifecycle."""

    def __init__(
        self,
        stream: BinaryIO,
        credentials: SessionCredentialProvider,
        logger: StructuredLogger,
    ):
        self._stream = stream
        self._credentials = credentials
        self._logger = logger
        self._thread = threading.Thread(
            target=self._run,
            name="livingworld-host-control",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float) -> bool:
        """Wait for host pipe closure without allowing shutdown to block forever."""
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        try:
            while (message := decode_frame(self._stream)) is not None:
                apply_message(message, self._credentials)
                self._logger.emit("host_control", f"{message.message_type}_accepted")
        except (ControlProtocolError, OSError, ValueError):
            self._credentials.mark_degraded()
            self._logger.emit("host_control", "host_control_protocol_failed", level="ERROR")
