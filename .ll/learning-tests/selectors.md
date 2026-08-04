---
target: selectors
date: '2026-08-04'
status: proven
assertions:
- claim: selectors.DefaultSelector() resolves to KqueueSelector on this platform (macOS)
  result: pass
- claim: sel.select(timeout=1.0) returns an empty list when no registered fileobj has data ready within the timeout window, rather than blocking indefinitely
  result: pass
- claim: readline() on a ready pipe fileobj returns "" (empty string, falsy) exactly at EOF, distinguishing it from a blank line ("\n")
  result: pass
- claim: key.fileobj returned by sel.select() is identity-equal (is) to the object originally passed to sel.register()
  result: pass
- claim: sel.get_map() becomes empty (falsy) once all registered fileobjs have been unregister()-ed, so `while sel.get_map():` terminates the loop without an extra blocking select() call
  result: pass
raw_output_path: .ll/learning-tests/raw/selectors.txt
---
