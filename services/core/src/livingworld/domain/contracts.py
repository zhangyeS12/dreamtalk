"""One packaged contract is read by Python, TypeScript and Rust."""

import json
from dataclasses import dataclass
from importlib.resources import files
from uuid import UUID

_contract = json.loads(files(__package__).joinpath("api_contract.json").read_text(encoding="utf-8"))
API_PROTOCOL: int = _contract["api_protocol"]
LOOPBACK_HOST: str = _contract["loopback_host"]
SESSION_DERIVATION: str = _contract["session_derivation"]


@dataclass(frozen=True)
class RequestId:
    """Identity for infrastructure mutations; not a business-event deduplication policy."""

    value: UUID

    @classmethod
    def parse(cls, raw: str) -> "RequestId":
        return cls(UUID(raw))

    def __str__(self) -> str:
        return str(self.value)
