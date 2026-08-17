---
target: tomllib
date: '2026-08-17'
status: proven
assertions:
- claim: tomllib.loads accepts a str and returns a dict
  result: pass
- claim: nested TOML tables parse into nested dicts
  result: pass
- claim: TOML datetime values parse into datetime.datetime objects
  result: pass
- claim: tomllib.load requires a binary-mode file object; a text-mode stream raises TypeError
  result: pass
- claim: tomllib.load succeeds when given a binary file object
  result: pass
- claim: invalid TOML syntax raises tomllib.TOMLDecodeError
  result: pass
- claim: tomllib has no dump/dumps - it is read-only
  result: pass
raw_output_path: .ll/learning-tests/raw/tomllib.txt
---
