"""social wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import TypedDict

from pydantic import ConfigDict, with_config


@with_config(ConfigDict(extra="allow"))
class SocialSnapshotFactionsItem(TypedDict):
    faction_id: str
    parent_id: str | None
    name: str


@with_config(ConfigDict(extra="allow"))
class SocialSnapshotCharactersItem(TypedDict):
    root_import_id: str
    current_import_id: str
    character_id: str
    name: str
    avatar_digest: str | None


@with_config(ConfigDict(extra="allow"))
class SocialSnapshotMembershipsItem(TypedDict):
    faction_id: str
    root_import_id: str


@with_config(ConfigDict(extra="allow"))
class SocialSnapshotConnectionsItem(TypedDict):
    first_root_import_id: str
    second_root_import_id: str
    faction_ids: list[str]


@with_config(ConfigDict(extra="allow"))
class SocialSnapshot(TypedDict):
    factions: list[SocialSnapshotFactionsItem]
    characters: list[SocialSnapshotCharactersItem]
    memberships: list[SocialSnapshotMembershipsItem]
    connections: list[SocialSnapshotConnectionsItem]


@with_config(ConfigDict(extra="allow"))
class AvatarDigest(TypedDict):
    root_import_id: str
    digest: str
