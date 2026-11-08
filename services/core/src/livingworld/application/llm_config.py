"""Configuration references credentials; requests never receive credential objects."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from livingworld.application.llm import LLMContractError, ModelRef, ProviderId, _count, _text, _type


@dataclass(frozen=True, slots=True)
class SecretRef:
    """Opaque credential identity, not a key, environment value, or filesystem path."""

    value: UUID

    def __post_init__(self):
        _type(self.value, UUID, "secret_reference")


class SecretValue:
    """Ephemeral adapter-only value; no dataclass/asdict or automatic JSON representation."""

    __slots__ = ("__value",)

    def __init__(self, value: str):
        _text(value, "secret_value")
        self.__value = value

    def __repr__(self):
        return "SecretValue([REDACTED])"

    def __str__(self):
        return "[REDACTED]"

    def reveal_for_adapter(self) -> str:
        return self.__value


class CredentialUnavailableError(RuntimeError):
    """A local SecretRef lookup failure; never contains the reference or a secret."""

    def __init__(self):
        super().__init__("credential_unavailable")


class LLMRuntimeHealth(StrEnum):
    READY = "ready"
    PARTIALLY_CONFIGURED = "partially_configured"
    UNCONFIGURED = "unconfigured"
    DEGRADED = "degraded"


class CredentialProvider(Protocol):
    async def resolve(self, reference: SecretRef) -> SecretValue: ...


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """Optional HTTP endpoint descriptor, not an HTTP client or provider schema."""

    base_url: str = field(repr=False)

    def __post_init__(self):
        _text(self.base_url, "endpoint")
        try:
            parsed = urlsplit(self.base_url)
            port = parsed.port
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or any(char.isspace() or ord(char) < 32 for char in self.base_url)
                or "\\" in self.base_url
                or port is not None
                and port <= 0
            ):
                raise ValueError
        except ValueError:
            raise LLMContractError("invalid_endpoint") from None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderConfig:
    provider_id: ProviderId
    endpoint: EndpointConfig | None = None
    secret_ref: SecretRef | None = None
    default_model: ModelRef | None = None
    timeout_ms: int = 30_000
    verify_tls: bool = True

    def __post_init__(self):
        _type(self.provider_id, ProviderId, "provider_id")
        if self.endpoint is not None:
            _type(self.endpoint, EndpointConfig, "endpoint")
        if self.secret_ref is not None:
            _type(self.secret_ref, SecretRef, "secret_reference")
        if self.default_model is not None:
            _type(self.default_model, ModelRef, "model_ref")
            if self.default_model.provider_id != self.provider_id:
                raise LLMContractError("default_model_provider_mismatch")
        _count(self.timeout_ms, "timeout", minimum=1)
        if type(self.verify_tls) is not bool or not self.verify_tls:
            raise LLMContractError("tls_verification_required")
