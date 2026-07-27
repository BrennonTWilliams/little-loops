---
target: asyncio
date: '2026-07-27'
status: proven
assertions:
- claim: asyncio.run() creates a new event loop, runs the coroutine, and closes the loop afterward
  result: pass
- claim: asyncio.gather() runs coroutines concurrently and returns results in the same order as input, not completion order
  result: pass
- claim: asyncio.gather() with default return_exceptions=False cancels sibling tasks and raises immediately on first exception
  result: fail
- claim: asyncio.wait_for() raises asyncio.TimeoutError (or TimeoutError in 3.11+) and cancels the wrapped coroutine when the timeout elapses
  result: pass
- claim: a asyncio.create_task() task starts running only when control yields to the event loop (not immediately at creation)
  result: pass
- claim: asyncio.CancelledError propagates out of a task that is cancelled mid-await, even if wrapped in a bare except Exception
  result: pass
raw_output_path: .ll/learning-tests/raw/asyncio.txt
---
