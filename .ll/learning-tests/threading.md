---
target: threading
date: '2026-07-30'
status: proven
assertions:
- claim: threading.Thread created with daemon=True does not block process exit even if still running
  result: pass
- claim: threading.Lock.acquire() blocks the calling thread if another thread holds the lock, until released
  result: pass
- claim: threading.Lock().acquire() called twice by the same thread deadlocks (non-reentrant)
  result: pass
- claim: threading.RLock() allows the same thread to acquire it multiple times without deadlocking
  result: pass
- claim: threading.Event.wait(timeout) returns False if the timeout elapses before set() is called, True if set
  result: pass
- claim: threading.local() gives each thread its own independent attribute namespace
  result: pass
- claim: an unhandled exception inside a Thread target does not propagate to the main thread or crash the process
  result: pass
raw_output_path: .ll/learning-tests/raw/threading.txt
---
