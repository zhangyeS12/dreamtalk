"""Bounded, deterministic destination choice; never creates a physical move."""

import hashlib
import math

DAY_US = 24 * 60 * 60 * 1_000_000
RETURN_COOLDOWN_US = 7 * DAY_US
WINDOW_US = 6 * 60 * 60 * 1_000_000
RESIDENCY_WEIGHTS = {
    "normal": (0.50, 0.40, 0.10),
    "strong": (0.70, 0.25, 0.05),
    "very_strong": (0.85, 0.14, 0.01),
}


def unit_draw(seed, purpose):
    digest = hashlib.sha256(f"mobility:v1:{seed}:{purpose}".encode()).digest()
    return (int.from_bytes(digest[:8], "big") >> 11) / 2**53


def _destination(choices, initial, current, distance, seed):
    choices = sorted(choices, key=str)
    weights = [
        math.exp(-0.8 * distance(initial, node) - 0.3 * distance(current, node)) for node in choices
    ]
    threshold = unit_draw(seed, "destination") * sum(weights)
    for node, weight in zip(choices, weights, strict=True):
        threshold -= weight
        if threshold < 0:
            return node
    return choices[-1]


def movement_route(
    *,
    initial,
    current,
    allowed,
    region,
    distance,
    residency,
    now,
    away_since,
    far_opportunity,
    seed,
):
    """Choose a category before destinations so location count cannot dilute home."""
    home_region = region(initial)
    foreign = [node for node in allowed if region(node) != home_region]
    if region(current) != home_region:
        return (initial,), "return"
    if far_opportunity and foreign:
        target = _destination(foreign, initial, current, distance, seed)
        return (target, initial), "far_trip"
    local = [node for node in allowed if node != initial and region(node) == home_region]
    near = [node for node in local if distance(initial, node) <= 2]
    farther = [node for node in local if node not in near]
    home_weight, near_weight, _ = RESIDENCY_WEIGHTS[residency]
    # A confirmed absence increasingly favors home; this never redraws the rare gate.
    boost = (
        min(0.20, 1 - home_weight, max(0, now - away_since) / DAY_US * 0.20)
        if away_since is not None
        else 0
    )
    draw = unit_draw(seed, "category")
    if draw < home_weight + boost:
        return (initial,), "home"
    choices = (
        near
        if draw < home_weight + boost + near_weight * (1 - boost / (1 - home_weight))
        else farther
    )
    if not choices:
        return (initial,), "home"
    target = _destination(choices, initial, current, distance, seed)
    return (target, initial), "local_trip"
