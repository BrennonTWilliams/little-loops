---
target: pytest-timeout
date: '2026-09-12'
status: proven
assertions:
- claim: with --timeout-method=thread, a per-test timeout calls os._exit(1) and
    terminates the whole pytest process, so subsequent tests in that process never
    run
  result: pass
- claim: with --timeout-method=signal, a per-test timeout raises via pytest.fail()
    inside the test only, so subsequent tests in the same process still run
  result: pass
- claim: a subprocess.Popen child spawned before a thread-method timeout fires survives
    the parent's os._exit(1) and is left running (orphaned)
  result: pass
- claim: '@pytest.mark.timeout(N) on a test overrides a shorter global --timeout
    value for that test'
  result: pass
- claim: '@pytest.mark.timeout(0) disables the timeout for a test even under a global
    --timeout'
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest-timeout.txt
---
