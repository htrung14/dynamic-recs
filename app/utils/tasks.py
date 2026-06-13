"""
Background task helpers
Prevent garbage collection of fire-and-forget asyncio tasks.
"""
import asyncio
from typing import Coroutine, Any, Set

_background_tasks: Set[asyncio.Task] = set()


def fire_and_forget(coro: Coroutine[Any, Any, Any]) -> "asyncio.Task":
    """Schedule a background task and retain a strong reference until it
    completes, so it is not garbage-collected mid-flight (see CPython docs
    for asyncio.create_task)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
