---
target: concurrent.futures
date: '2026-08-04'
status: proven
assertions:
- claim: future.cancel() returns True only if the task hasn't started running yet;
    once running, it returns False and the task keeps executing.
  result: pass
- claim: as_completed() yields futures in completion order, not submission order.
  result: pass
- claim: A worker function that raises an exception does not propagate until .result()
    is called on its future -- as_completed() itself doesn't raise.
  result: pass
- claim: concurrent.futures.wait() with return_when=FIRST_COMPLETED returns as soon
    as one future finishes, leaving the rest in not_done.
  result: pass
- claim: ThreadPoolExecutor.map() returns results in submission order even if tasks
    finish out of order.
  result: pass
- claim: Calling .result(timeout=N) on an unfinished future raises concurrent.futures.TimeoutError
    (module-level), not builtins.TimeoutError, distinct from the one caught in link_checker.py.
  result: fail
- claim: Exiting a with ThreadPoolExecutor() as executor -- block blocks until all
    submitted tasks complete, even if .shutdown() was never called explicitly.
  result: pass
raw_output_path: .ll/learning-tests/raw/concurrentfutures.txt
---
