---
target: localStorage
date: '2026-09-17'
status: proven
assertions:
- claim: globalThis.localStorage exists in Node 26 with no flag/import
  result: fail
- claim: setItem coerces non-string values via String() (object -> "[object Object]") unless pre-serialized
  result: pass
- claim: getItem on a missing key returns null, not undefined
  result: pass
- claim: data persists across separate Node process invocations when pointed at the same backing file (--localstorage-file)
  result: pass
- claim: removeItem on a nonexistent key is a silent no-op
  result: pass
- claim: without --localstorage-file, localStorage either works in-memory-only or throws a catchable error when accessed
  result: pass
- claim: JSON.stringify/JSON.parse round-trips a nested object through setItem/getItem intact
  result: pass
raw_output_path: .ll/learning-tests/raw/localstorage.txt
---
