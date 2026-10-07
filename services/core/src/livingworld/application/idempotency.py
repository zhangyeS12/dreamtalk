"""Recover a committed receipt after rollback; never execute the operation twice."""

from collections.abc import Awaitable, Callable
from dataclasses import replace

from livingworld.application.ports import UnitOfWork
from livingworld.application.results import ActionResult, CommandResult, MemoryResult, SceneResult


async def run_with_receipt_recovery[T: CommandResult | ActionResult | MemoryResult | SceneResult](
    operation: Callable[[], Awaitable[T]],
    uow_factory: Callable[[], UnitOfWork],
    read_receipt: Callable[[UnitOfWork], Awaitable[T | None]],
    recoverable: tuple[type[Exception], ...],
) -> T:
    try:
        return await operation()
    except recoverable:
        # The operation's transaction has already exited/rolled back. Inspect
        # once in a fresh transaction, without repeating a mutation or API call.
        async with uow_factory() as uow:
            existing = await read_receipt(uow)
        if existing is None:
            raise
        return replace(existing, replayed=True)
