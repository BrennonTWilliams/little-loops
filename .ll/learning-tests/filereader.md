---
target: FileReader
date: '2026-09-17'
status: proven
assertions:
- claim: FileReader is a global constructor in a browser context (not in Node)
  result: pass
- claim: readAsText(blob) fires a load event where reader.result equals the original text content
  result: pass
- claim: reader.result is null immediately after construction, before any read
  result: pass
- claim: reader.readyState progresses 0 (EMPTY) to 1 (LOADING) to 2 (DONE) during a read
  result: pass
- claim: reading a real File from <input type=file> yields the same text as reading the underlying Blob directly
  result: pass
- claim: calling readAsText with an invalid argument (null) throws synchronously rather than silently succeeding
  result: pass
raw_output_path: .ll/learning-tests/raw/filereader.txt
---
