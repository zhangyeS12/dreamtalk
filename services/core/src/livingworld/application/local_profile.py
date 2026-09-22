"""Local authored self-description; never an assertion of world truth or knowledge."""

from dataclasses import dataclass, field
from typing import Protocol

from livingworld.domain.identifiers import WorldId
from livingworld.domain.values import Revision, require_type


@dataclass(frozen=True, slots=True)
class LocalProfile:
    name: str = ""
    description: str = field(default="", repr=False)
    revision: Revision = Revision()

    def __post_init__(self) -> None:
        require_type(self.name, str, "profile name")
        require_type(self.description, str, "profile description")
        require_type(self.revision, Revision, "profile revision")
        if len(self.name) > 120 or len(self.description) > 8000:
            raise ValueError("profile_text_limit_exceeded")


class LocalProfileStore(Protocol):
    async def load(self, world_id: WorldId | None = None) -> LocalProfile: ...

    async def save(self, profile: LocalProfile, world_id: WorldId | None = None) -> LocalProfile:
        """Compare profile.revision and atomically return the next revision."""
        ...
