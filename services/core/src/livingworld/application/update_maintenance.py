"""Generation-local update barrier; no persistence or provider replay."""

import asyncio
from contextlib import contextmanager
from time import monotonic


class UpdateMaintenance:
    def __init__(self):
        self._until = 0.0
        self.active = 0
        self.on_resume = lambda: None

    @property
    def preparing(self):
        if self._until and monotonic() >= self._until:
            self._until = 0.0
            self.on_resume()
        return bool(self._until)

    def prepare(self):
        # A lost host must not leave a surviving Core permanently fenced.
        self._until = monotonic() + 300
        return self.snapshot()

    def cancel(self):
        was_preparing = bool(self._until)
        self._until = 0.0
        if was_preparing:
            self.on_resume()
        return self.snapshot()

    def snapshot(self):
        return {"preparing": self.preparing, "active": self.active}

    @contextmanager
    def operation(self):
        # Admission and accounting are synchronous on the single event loop.
        admitted = not self.preparing
        if admitted:
            self.active += 1
        try:
            yield admitted
        finally:
            if admitted:
                self.active -= 1

    def spawn(self, coroutine):
        # A caller already holds an admitted operation while claiming the job.
        # Account before scheduling, including a task not yet given its first turn.
        self.active += 1
        task = asyncio.create_task(coroutine)
        task.add_done_callback(lambda _task: self._finished())
        return task

    def _finished(self):
        self.active -= 1
