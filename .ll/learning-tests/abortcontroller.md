---
target: AbortController
date: '2026-09-19'
status: proven
assertions:
- claim: a new controller's signal.aborted is false
  result: pass
- claim: abort() sets signal.aborted to true
  result: pass
- claim: abort() with no argument sets signal.reason to a DOMException named AbortError
  result: pass
- claim: the abort event fires once and a second abort() call is a no-op
  result: pass
- claim: abort(reason) stores the reason by identity on signal.reason
  result: pass
- claim: signal.throwIfAborted() throws signal.reason when aborted
  result: pass
- claim: AbortSignal.timeout(ms) aborts with a DOMException named TimeoutError
  result: pass
- claim: fetch with a pre-aborted signal rejects with signal.reason
  result: pass
raw_output_path: .ll/learning-tests/raw/abortcontroller.txt
---
