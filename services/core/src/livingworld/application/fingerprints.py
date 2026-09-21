"""Versioned canonical semantic inputs, excluding request identity and wall time."""

import json
from collections.abc import Mapping
from decimal import Decimal
from hashlib import sha256

from livingworld.application.commands import (
    AcquireKnowledge,
    AssertWorldTruth,
    ChangeRelationship,
    CreateCharacter,
    CreateLocation,
    CreatePlayer,
    CreateWorld,
    FormCharacterBelief,
    MovePlayer,
    PlaceCharacter,
    WorldCommand,
)
from livingworld.domain.identifiers import (
    ActivationId,
    CharacterId,
    EventId,
    KnowledgeAssertionId,
    LocationId,
    MemoryId,
    ObservationId,
    PlayerId,
    SceneId,
    SceneParticipantId,
    TriggerId,
    WorldId,
)


def id_input(
    identity: WorldId
    | LocationId
    | PlayerId
    | CharacterId
    | KnowledgeAssertionId
    | ObservationId
    | MemoryId
    | EventId
    | TriggerId
    | ActivationId
    | SceneId
    | SceneParticipantId,
) -> dict[str, str]:
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
                "expected_presence_revision": command.expected_presence_revision.value,
            }
        case CreateCharacter():
            details = {"character_id": id_input(command.character_id), "name": command.name}
        case PlaceCharacter():
            details = {
                "character_id": id_input(command.character_id),
                "location_id": id_input(command.location_id),
                "expected_state_revision": command.expected_state_revision.value
                if command.expected_state_revision is not None
                else None,
            }
        case ChangeRelationship():
            details = {
                "source_id": id_input(command.source_id),
                "target_id": id_input(command.target_id),
                "affinity_delta": command.affinity_delta,
                "trust_delta": command.trust_delta,
                "familiarity_delta": command.familiarity_delta,
                "expected_relationship_revision": command.expected_relationship_revision.value
                if command.expected_relationship_revision is not None
                else None,
            }
        case AssertWorldTruth() | FormCharacterBelief():
            details = {
                "assertion_id": id_input(command.assertion_id),
                "subject": command.subject,
                "predicate": command.predicate,
                "value": command.value,
                "epistemic_status": command.epistemic_status,
                "confidence": decimal_input(command.confidence),
                "valid_from": command.valid_from.microseconds
                if command.valid_from is not None
                else None,
                "valid_to": command.valid_to.microseconds if command.valid_to is not None else None,
            }
            if isinstance(command, FormCharacterBelief):
                details |= {
                    "character_id": id_input(command.character_id),
                    "source_assertion_id": id_input(command.source_assertion_id)
                    if command.source_assertion_id is not None
                    else None,
                    "provenance_event_id": id_input(command.provenance_event_id)
                    if command.provenance_event_id is not None
                    else None,
                }
        case AcquireKnowledge():
            details = {
                "assertion_id": id_input(command.assertion_id),
                "receiver_id": id_input(command.receiver_id),
                "source_assertion_id": id_input(command.source_assertion_id),
                "channel": command.channel.value,
                "epistemic_status": command.epistemic_status,
                "confidence": decimal_input(command.confidence),
            }
        case _:
            raise TypeError("Unsupported command type")
    return common | details


def decimal_input(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if value == 0 else text


def _json_data(value):
    if isinstance(value, Mapping):
        return {key: _json_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_data(item) for item in value]
    return value


def canonical_json(value: dict) -> str:
    return json.dumps(
        _json_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def command_fingerprint(command: WorldCommand) -> str:
    return sha256(canonical_json(semantic_input(command)).encode("utf-8")).hexdigest()
