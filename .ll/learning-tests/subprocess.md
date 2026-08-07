---
target: subprocess
date: '2026-08-06'
status: proven
assertions:
- claim: Popen replaces the child environment entirely when env= is passed (no auto-merge)
  result: pass
- claim: an env dict built as {**os.environ, **override} passes an empty-string override to the child
  result: pass
- claim: a key set to '' in env is present-but-empty in the child and reads falsy via os.environ.get()
  result: pass
- claim: Popen(env=...) requires str values; None raises TypeError
  result: pass
raw_output_path: .ll/learning-tests/raw/subprocess.txt
---
