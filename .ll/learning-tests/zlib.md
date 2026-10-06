---
target: zlib
date: '2026-10-06'
status: proven
assertions:
- claim: compress(data, 6) followed by decompress round-trips bytes exactly
  result: pass
- claim: default-level compress output is byte-identical to level 6 output
  result: pass
- claim: level 6 output starts with header bytes 0x78 0x9c
  result: pass
- claim: level 9 output differs from level 1 output
  result: pass
- claim: decompress of non-zlib bytes raises zlib.error
  result: pass
- claim: decompress of a truncated stream raises zlib.error
  result: pass
- claim: decompress of a str raises TypeError
  result: pass
- claim: trailing garbage after a valid stream is silently ignored by decompress
  result: pass
- claim: compress of empty bytes round-trips to empty bytes
  result: pass
raw_output_path: .ll/learning-tests/raw/zlib.txt
---
