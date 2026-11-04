"""Common test fixtures and synchronous coroutine runner for Windows sandbox environment."""

import inspect
from typing import Any, Coroutine


def run_async(coro: Coroutine) -> Any:
    """Executes a coroutine and any nested coroutines synchronously to completion

    without opening OS network loopback sockets (preventing Windows sandbox stalls).
    """
    stack = [coro]
    val = None
    while stack:
        current = stack[-1]
        try:
            res = current.send(val)
            val = None
            if inspect.iscoroutine(res):
                stack.append(res)
        except StopIteration as e:
            stack.pop()
            val = e.value
    return val

