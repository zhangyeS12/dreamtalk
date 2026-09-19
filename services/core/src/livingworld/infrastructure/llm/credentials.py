"""Process-local credential state provisioned by the privileged desktop host."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock

from livingworld.application.llm import LLMContractError
from livingworld.application.llm_config import (
    CredentialUnavailableError,
    LLMRuntimeHealth,
    SecretRef,
    SecretValue,
)


class SessionCredentialProvider:
    """In-memory SecretRef map with no persistence or enumerable plaintext API."""

    def __init__(self, expected: Iterable[SecretRef] = ()):
        expected = tuple(expected)
        if any(not isinstance(reference, SecretRef) for reference in expected):
            raise LLMContractError("invalid_expected_credentials")
        self._expected = frozenset(expected)
        self._values: dict[SecretRef, SecretValue] = {}
        self._lock = RLock()
        self._sync_complete = False
        self._degraded = False

    async def resolve(self, reference: SecretRef) -> SecretValue:
        if not isinstance(reference, SecretRef):
            raise CredentialUnavailableError()
        with self._lock:
            value = self._values.get(reference)
            if value is None:
                raise CredentialUnavailableError()
            return value

    def contains(self, reference: SecretRef) -> bool:
        with self._lock:
            return reference in self._values

    def upsert(self, reference: SecretRef, secret: str) -> None:
        if not isinstance(reference, SecretRef):
            raise LLMContractError("invalid_secret_reference")
        value = SecretValue(secret)
        with self._lock:
            # A structurally invalid runtime config is fail-closed. The host may
            # still finish its startup sync, but the degraded Core retains no key.
            if self._degraded:
                return
            self._values[reference] = value

    def remove(self, reference: SecretRef) -> None:
        if not isinstance(reference, SecretRef):
            raise LLMContractError("invalid_secret_reference")
        with self._lock:
            self._values.pop(reference, None)

    def complete_sync(self, *, secure_store_available: bool) -> None:
        if type(secure_store_available) is not bool:
            raise LLMContractError("invalid_credential_sync_status")
        with self._lock:
            self._sync_complete = True
            self._degraded = self._degraded or not secure_store_available

    def mark_degraded(self) -> None:
        with self._lock:
            self._degraded = True
            self._values.clear()

    @property
    def health(self) -> LLMRuntimeHealth:
        with self._lock:
            if self._degraded:
                return LLMRuntimeHealth.DEGRADED
            configured = len(self._expected.intersection(self._values))
            if not self._expected or configured == 0:
                return LLMRuntimeHealth.UNCONFIGURED
            if configured < len(self._expected):
                return LLMRuntimeHealth.PARTIALLY_CONFIGURED
            return LLMRuntimeHealth.READY

    @property
    def sync_complete(self) -> bool:
        with self._lock:
            return self._sync_complete
