---
target: threading
date: '2026-09-03'
status: proven
assertions:
- claim: threading.Condition().wait() releases its underlying lock while waiting and reacquires it before returning
  result: pass
- claim: threading.Semaphore(n) allows exactly n concurrent acquires before a further acquire() blocks
  result: pass
- claim: threading.current_thread().ident matches threading.get_ident() when read from within that same thread
  result: pass
- claim: with lock releases the lock automatically even when an exception is raised inside the block
  result: pass
- claim: threading.Timer(interval, func).cancel() called before the delay elapses prevents func from running
  result: pass
- claim: threading.Barrier(n).wait() blocks each of n threads until all n have called wait()
  result: pass
raw_output_path: .ll/learning-tests/raw/threading.txt
---
