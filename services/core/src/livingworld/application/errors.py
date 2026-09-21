"""Explicit application failures; no persistence exception details escape."""


class IdempotencyConflictError(ValueError):
    """A request identity is occupied by different or unverifiable semantics."""


class EntityNotFoundError(ValueError):
    """A referenced current-state entity does not exist."""


class EntityAlreadyExistsError(ValueError):
    """An explicit creation target already exists."""


class MemoryEvidenceAccessDeniedError(ValueError):
    """Memory evidence was missing, cross-world, or not owned by the Character."""


class UnsupportedTriggerError(ValueError):
    """The allowlisted scheduler registry does not support a kind/version."""


class TriggerAlreadyFiredError(ValueError):
    """Cancellation lost to materialization; the durable activation remains valid."""


class UnsupportedActivationError(ValueError):
    """The allowlisted activation registry rejects a kind/version/target combination."""


class ActivationFanoutTooLargeError(ValueError):
    """A direct Character activation fanout exceeded its deterministic hard bound."""


class ActivationAccessDeniedError(ValueError):
    """A Character activation tried to reference an event it could not observe."""


class WorldCatchingUpError(RuntimeError):
    """A time-sensitive external mutation cannot overtake overdue temporal work."""


class WorldRuntimeUnavailableError(RuntimeError):
    """A world runtime is degraded, stopping, or otherwise unavailable for mutation."""


class ReplayError(Exception):
    """Rebuild rejected; old projections remain usable."""


class UnsupportedEventError(ReplayError):
    pass


class InvalidEventPayloadError(ReplayError):
    pass
