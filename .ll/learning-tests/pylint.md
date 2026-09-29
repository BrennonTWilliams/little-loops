---
target: pylint
date: '2026-09-26'
status: proven
assertions:
- claim: exit code is 0 for a clean file and a bitmask otherwise (convention=16, warning=4, error=2)
  result: pass
- claim: --output-format=json prints a JSON list of objects with keys type, message-id, symbol, path, line, message
  result: pass
- claim: --disable=all --enable=E suppresses non-error messages so a convention-only file exits 0
  result: pass
- claim: the "rated at" score line is printed to stdout by default
  result: pass
- claim: --exit-zero returns exit 0 while still reporting messages
  result: pass
raw_output_path: .ll/learning-tests/raw/pylint.txt
---
