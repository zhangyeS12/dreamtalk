"""Versioned canonical semantic inputs, excluding request identity and wall time."""

import json
from hashlib import sha256

from livingworld.application.commands import (
    ChangeRelationship,
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    MovePlayer,
    PlaceCharacter,
    WorldCommand,
)
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId


def id_input(identity: WorldId | LocationId | PlayerId | CharacterId) -> dict[str, str]:
    result = {"kind": type(identity).__name__, "id": str(identity.value)}
    if not isinstance(identity, WorldId):
        result["world_id"] = str(identity.world_id.value)
    return result


def semantic_input(command: WorldCommand) -> dict:
    common = {
        "fingerprint_version": 1,
        "command_type": type(command).__name__,
        "world_id": id_input(command.world_id),
    }
    match command:
        case CreateWorld():
            scale = format(command.time_scale, "f")
            if "." in scale:
                scale = scale.rstrip("0").rstrip(".")
            if command.time_scale == 0:
                scale = "0"
            details = {
                "name": command.name,
                "initial_time": command.initial_time.microseconds,
                "time_scale": scale,
                "clock_state": command.clock_state.value,
            }
        case CreateLocation():
            details = {"location_id": id_input(command.location_id), "name": command.name}
        case CreatePlayer():
            details = {
                "player_id": id_input(command.player_id),
                "name": command.name,
                "initial_location_id": id_input(command.initial_location_id),
                "activity_state": command.activity_state.value,
                "availability_state": command.availability_state.value,
            }
        case MovePlayer():
            details = {
                "player_id": id_input(command.player_id),
                "destination_id": id_input(command.destination_id),
            }
        case CreateCharacter():
            details = {"character_id": id_input(command.character_id), "name": command.name}
        case PlaceCharacter():
            details = {
                "character_id": id_input(command.character_id),
                "location_id": id_input(command.location_id),
            }
        case ChangeRelationship():
            details = {
                "source_id": id_input(command.source_id),
                "target_id": id_input(command.target_id),
                "affinity_delta": command.affinity_delta,
                "trust_delta": command.trust_delta,
                "familiarity_delta": command.familiarity_delta,
            }
        case _:
            raise TypeError("Unsupported command type")
    return common | details


def canonical_json(value: dict) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def command_fingerprint(command: WorldCommand) -> str:
    return sha256(canonical_json(semantic_input(command)).encode("utf-8")).hexdigest()
