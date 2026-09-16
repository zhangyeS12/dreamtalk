import hashlib
import hmac
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from livingworld.domain.contracts import API_PROTOCOL, SESSION_DERIVATION


class BootstrapInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    bootstrap_secret: SecretStr = Field(min_length=32)
    instance_nonce: str = Field(pattern=r"^[a-zA-Z0-9-]{16,128}$")
    protocol_min: int = Field(ge=0)
    protocol_max: int = Field(ge=0)
    data_dir: Path
    log_dir: Path
    allowed_origins: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("data_dir", "log_dir")
    @classmethod
    def absolute_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("absolute_path_required")
        resolved = value.resolve()
        package_root = Path(__file__).resolve().parents[1]
        source_root = next(
            (parent for parent in package_root.parents if (parent / "pyproject.toml").is_file()),
            package_root.parent,
        )
        if resolved.is_relative_to(source_root) or resolved.is_relative_to(package_root):
            raise ValueError("source_directory_forbidden")
        return resolved


class BootstrapFileAccess(Protocol):
    """Extension seam for owner/ACL validation; replace before production packaging."""

    def validate(self, path: Path) -> None: ...
    def consume(self, path: Path) -> bytes: ...


class BasicBootstrapFileAccess:
    def validate(self, path: Path) -> None:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
            raise ValueError("bootstrap_file_invalid")

    def consume(self, path: Path) -> bytes:
        try:
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)


def read_bootstrap(path: Path, access: BootstrapFileAccess | None = None) -> BootstrapInput:
    access = access or BasicBootstrapFileAccess()
    try:
        access.validate(path)
        config = BootstrapInput.model_validate(json.loads(access.consume(path)))
        if not config.protocol_min <= API_PROTOCOL <= config.protocol_max:
            raise ValueError("protocol_incompatible")
        return config
    except (OSError, ValueError, ValidationError):
        raise ValueError("bootstrap_rejected") from None


def derive_session(secret: str, nonce: str, generation: str) -> str:
    message = f"{SESSION_DERIVATION}:{nonce}:{generation}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
