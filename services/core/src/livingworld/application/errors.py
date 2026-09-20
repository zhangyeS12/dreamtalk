"""Explicit application failures; no persistence exception details escape."""


class IdempotencyConflictError(ValueError):
    """A request identity is occupied by different or unverifiable semantics."""


class EntityNotFoundError(ValueError):
    """A referenced current-state entity does not exist."""


class EntityAlreadyExistsError(ValueError):
    """An explicit creation target already exists."""


class UnsupportedTriggerError(ValueError):
    """The allowlisted scheduler registry does not support a kind/version."""


class TriggerAlreadyFiredError(ValueError):
    """Cancellation lost to materialization; the durable activation remains valid."""


class ReplayError(Exception):
    """Rebuild rejected; old projections remain usable."""


class UnsupportedEventError(ReplayError):
    pass


class InvalidEventPayloadError(ReplayError):
    pass
