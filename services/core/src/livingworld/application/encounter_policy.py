"""Approved pacing limits and stable encounter identities; no probabilistic claims."""

from uuid import UUID, uuid5

MAX_ENCOUNTERS_PER_BATCH = 2
NEW_CONTACT_WINDOW_US = 24 * 60 * 60 * 1_000_000
PAIR_COOLDOWN_US = 6 * 60 * 60 * 1_000_000


def encounter_request_uuid(candidate_id: UUID) -> UUID:
    return uuid5(candidate_id, "kernel-encounter")


def encounter_event_uuid(candidate_id: UUID) -> UUID:
    return uuid5(encounter_request_uuid(candidate_id), "characters-met")
