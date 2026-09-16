"""Invariant violations at the domain boundary."""


class DomainInvariantError(ValueError):
    """A value or combination of values has no valid domain meaning."""


class CrossWorldReferenceError(DomainInvariantError):
    """A reference crosses the World isolation boundary."""


class InvalidKnowledgeOwnershipError(DomainInvariantError):
    """Knowledge scope and its owner do not agree."""


class InvalidPresenceError(DomainInvariantError):
    """A player's physical presence is missing or invalid."""


class ConcurrencyConflictError(DomainInvariantError):
    """An update was based on a different revision."""
