---
target: tsc
date: '2026-09-26'
status: proven
assertions:
- claim: '`tsc --version` prints `Version X.Y.Z` and exits 0 (observed: Version 7.0.2)'
  result: pass
- claim: '`tsc --noEmit` exits 0 on type-correct code'
  result: pass
- claim: '`tsc --noEmit` exits non-zero on a type error (observed exit 1, not 2)'
  result: pass
- claim: '`tsc --pretty false` reports diagnostics as `file(line,col): error TSnnnn: message`'
  result: pass
- claim: '`tsc --noEmit` writes no output files'
  result: pass
- claim: 'without `--noEmit`, tsc emits a `.js` file next to the source'
  result: pass
raw_output_path: .ll/learning-tests/raw/tsc.txt
---
