---
target: signal
date: '2026-08-24'
status: proven
assertions:
- claim: signal.signal(signal.SIGINT, handler) returns the previously-installed handler
  result: pass
- claim: restoring with signal.signal(signal.SIGINT, previous_handler) reinstates the prior handler
  result: pass
- claim: a custom SIGINT handler installed in a parent process is not automatically inherited by a subprocess.Popen-spawned child unless it re-execs or explicitly re-registers
  result: untested
- claim: os.killpg(os.getpgid(pid), signal.SIGTERM) sends the signal to every process in the group, not just the leader
  result: untested
- claim: a subprocess started with start_new_session=True (its own process group) does not receive SIGINT sent to the parent's foreground process group
  result: pass
- claim: signal.signal() can only be called from the main thread of the main interpreter — calling it from a non-main thread raises ValueError
  result: pass
raw_output_path: .ll/learning-tests/raw/signal.txt
---
