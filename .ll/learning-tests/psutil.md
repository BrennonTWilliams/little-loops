---
target: psutil
date: '2026-07-14'
status: proven
assertions:
- claim: psutil.Process(pid).cmdline() returns a list of strings for a live process
  result: pass
- claim: psutil.Process(pid).create_time() returns a float epoch timestamp
  result: pass
- claim: psutil.Process(pid) or its .cmdline() raises psutil.NoSuchProcess for a dead/recycled pid
  result: pass
- claim: psutil.Process(pid).is_running() reflects current liveness
  result: pass
raw_output_path: .ll/learning-tests/raw/psutil.txt
---
