---
target: TextEncoder
date: '2026-09-19'
status: proven
assertions:
- claim: new TextEncoder().encoding is "utf-8"
  result: pass
- claim: encode() returns a Uint8Array
  result: pass
- claim: encode("") returns a zero-length array
  result: pass
- claim: multi-byte characters encode to UTF-8 byte sequences ("€" -> e2 82 ac)
  result: pass
- claim: a lone surrogate is replaced with U+FFFD (ef bf bd) and does not throw
  result: pass
- claim: encodeInto returns {read, written} and does not write partial characters
  result: pass
- claim: encode() with no argument encodes the empty string
  result: pass
raw_output_path: .ll/learning-tests/raw/textencoder.txt
---
