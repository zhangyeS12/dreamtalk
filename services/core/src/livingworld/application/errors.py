"""Explicit application failures; no persistence exception details escape."""


class IdempotencyConflictError(ValueError):
    """A request identity is occupied by different or unverifiable semantics."""


class EntityNotFoundError(ValueError):
    """A referenced current-state entity does not exist."""


class EntityAlreadyExistsError(ValueError):
    """An explicit creation target already exists."""
