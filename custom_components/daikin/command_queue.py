"""Per-entity Daikin command queue: one device.set() at a time, newest value wins.

v2.45.0: Every climate service call used to start its own device.set(). Rapid
UI taps (six "+" presses in six seconds) queued on the unit's request
semaphore (BRP069/072C: one request at a time, ~6-8 requests per set), so the
later taps waited past the 60 s service wait and raised TimeoutError, although
every command eventually landed.

Overlapping set() calls also raced: pydaikin's BRP069 set() reads
get_control_info, merges the delta into the shared values and writes the whole
state back. A second set() whose read ran before the first one's write sent
the old state back with only its own delta, silently reverting the first
command (e.g. a fan change undoing a temperature change sent a moment before).

This queue fixes both. Commands for one entity merge into a pending batch
(the newest value per key wins, keys from different commands accumulate) and a
single worker sends one batch at a time. A burst of taps becomes at most one
command in flight plus one pending, and no two set() calls ever overlap.

Deliberately free of Home Assistant imports so it can be tested with plain
asyncio.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def _consume_outcome(fut: asyncio.Future) -> None:
    """Mark a waiter's exception as retrieved.

    A caller that gave up (its 60 s wait expired, or its automation run was
    cancelled) never reads the future; without this, asyncio logs
    'Future exception was never retrieved' when the batch fails.
    """
    if not fut.cancelled():
        fut.exception()


class CommandQueue:
    """Serialize and coalesce device.set() calls for one entity."""

    def __init__(
        self,
        send: Callable[[dict[str, Any]], Awaitable[Any]],
        *,
        create_task: Callable[[Coroutine[Any, Any, None]], asyncio.Task],
        on_dispatch: Callable[[dict[str, Any]], Any] | None = None,
        on_done: Callable[[dict[str, Any], Any, BaseException | None], None]
        | None = None,
    ) -> None:
        """Set up the queue.

        send: coroutine function that sends one merged batch to the device.
        create_task: schedules the worker (hass.async_create_task in HA).
        on_dispatch(values) -> token: called as a batch is taken for sending.
        on_done(values, token, exc): called once per batch BEFORE its waiters
            are resolved; exc is None on success.
        """
        self._send = send
        self._create_task = create_task
        self._on_dispatch = on_dispatch
        self._on_done = on_done
        self._pending: dict[str, Any] = {}
        self._waiters: list[asyncio.Future] = []
        self._worker: asyncio.Task | None = None

    def submit(self, values: dict[str, Any]) -> asyncio.Future:
        """Merge values into the pending batch and return this caller's waiter.

        Synchronous: the merge happens before the caller's first await, so the
        submission order is the call order. The waiter resolves with the
        result (or exception) of the batch that carried these values.
        """
        self._pending.update(values)
        fut = asyncio.get_running_loop().create_future()
        fut.add_done_callback(_consume_outcome)
        self._waiters.append(fut)
        # done() as well as None: HA starts tasks eagerly, so a batch that
        # fails before its first real suspension finishes _run() (and clears
        # _worker) INSIDE create_task, and the assignment below would then
        # store an already-finished task.
        if self._worker is None or self._worker.done():
            self._worker = self._create_task(self._run())
        return fut

    def pending_has(self, key: str) -> bool:
        """Return True if a not-yet-sent batch carries key."""
        return key in self._pending

    def _notify_done(
        self, values: dict[str, Any], token: Any, exc: BaseException | None
    ) -> None:
        """Run on_done; a fault in it must never strand the batch's waiters."""
        if self._on_done is None:
            return
        try:
            self._on_done(values, token, exc)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Daikin command queue: on_done failed for %s", values)

    async def _run(self) -> None:
        """Send pending batches one at a time until none are left."""
        try:
            while self._pending:
                values, waiters = self._pending, self._waiters
                self._pending, self._waiters = {}, []
                token = None
                try:
                    if self._on_dispatch:
                        token = self._on_dispatch(values)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Daikin command queue: on_dispatch failed for %s", values
                    )
                try:
                    result = await self._send(dict(values))
                except asyncio.CancelledError:
                    # HA shutdown cancelled the worker: nothing queued will be
                    # sent, so release every waiter.
                    for fut in waiters + self._waiters:
                        fut.cancel()
                    self._pending, self._waiters = {}, []
                    raise
                except Exception as exc:  # noqa: BLE001 - handed to callers
                    self._notify_done(values, token, exc)
                    for fut in waiters:
                        if not fut.done():
                            fut.set_exception(exc)
                else:
                    self._notify_done(values, token, None)
                    for fut in waiters:
                        if not fut.done():
                            fut.set_result(result)
        finally:
            # No await between the loop's last check and here, so a submit()
            # can never land in a window where it would be left unsent.
            self._worker = None
