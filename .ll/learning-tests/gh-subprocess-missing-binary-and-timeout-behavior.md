---
target: gh subprocess missing binary and timeout behavior
date: '2026-09-07'
status: proven
assertions:
- claim: subprocess.run([<nonexistent-binary>, ...], capture_output=True, text=True, check=False) raises FileNotFoundError (not a non-zero-exit CompletedProcess) when the binary isn't on PATH
  result: pass
- claim: FileNotFoundError is a subclass of OSError, not of RuntimeError
  result: pass
- claim: subprocess.run([...], timeout=<short>) raises subprocess.TimeoutExpired when the child exceeds timeout seconds
  result: pass
- claim: subprocess.TimeoutExpired is not a subclass of RuntimeError (it is SubprocessError/Exception) — same catch gap as FileNotFoundError
  result: pass
- claim: 'a try/except (FileNotFoundError, subprocess.TimeoutExpired, OSError): raise RuntimeError(...) from exc wrapper converts both failure modes into a single catchable RuntimeError'
  result: pass
- claim: when FileNotFoundError is raised, no child process is ever spawned (failure occurs before exec, inside Popen.__init__) — there is no process to reap, only external side effects (e.g. a temp dir) that the except branch must clean up explicitly
  result: pass
raw_output_path: .ll/learning-tests/raw/gh-subprocess-missing-binary-and-timeout-behavior.txt
---
