---
target: libuv
date: '2026-09-22'
status: proven
assertions:
- claim: default UV_THREADPOOL_SIZE is 4, so 8 concurrent pbkdf2 jobs serialize into
    a fast batch and a slower batch rather than completing uniformly
  result: pass
- claim: crypto.pbkdf2 (Node async crypto) executes on the libuv threadpool, so its
    completions are delayed once the pool is saturated
  result: pass
- claim: crypto.subtle.digest (WebCrypto) completion is not measurably delayed by
    libuv threadpool saturation from concurrent pbkdf2 jobs
  result: fail
- claim: setImmediate callbacks keep firing every event-loop turn even while the
    libuv threadpool is fully saturated with long-running pbkdf2 work
  result: pass
- claim: raising UV_THREADPOOL_SIZE before any threadpool-consuming call increases
    concurrent pbkdf2 throughput (less serialization) versus the default-4 pool
  result: pass
raw_output_path: .ll/learning-tests/raw/libuv.txt
---
