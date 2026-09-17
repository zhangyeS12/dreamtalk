"""Invariant violations at the domain boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livingworld.domain.values import Revision


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

    def __init__(
        self,
        message: str,
        *,
        resource_kind: str | None = None,
        resource_identity: object = None,
        expected_revision: Revision | None = None,
        actual_revision: Revision | None = None,
    ) -> None:
        super().__init__(message)
        self.resource_kind = resource_kind
        self.resource_identity = resource_identity
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
