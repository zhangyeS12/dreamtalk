"""Library identities use typed UUIDs without a runtime WorldId."""

from dataclasses import dataclass
from uuid import UUID

from livingworld.domain.errors import DomainInvariantError


@dataclass(frozen=True, slots=True)
class _ContentIdentity:
    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise DomainInvariantError("Content identity requires a UUID")


@dataclass(frozen=True, slots=True)
class CharacterDefinitionId(_ContentIdentity):
    pass


@dataclass(frozen=True, slots=True)
class WorldContentId(_ContentIdentity):
    pass


@dataclass(frozen=True, slots=True)
class LoreEntryId(_ContentIdentity):
    pass


@dataclass(frozen=True, slots=True)
class LoreCollectionId(_ContentIdentity):
    pass


@dataclass(frozen=True, slots=True)
class ContentAssetId(_ContentIdentity):
    pass


@dataclass(frozen=True, slots=True)
class RawImportId(_ContentIdentity):
    pass


type ContentId = CharacterDefinitionId | WorldContentId | LoreEntryId | LoreCollectionId
