---
target: Node.js
date: '2026-09-16'
status: proven
assertions:
- claim: node --test <file> exits 0 when all tests in the file pass
  result: pass
- claim: node --test <file> exits non-zero when at least one test fails
  result: pass
- claim: default TAP output includes a "# pass N" summary line
  result: fail
- claim: default TAP output includes a "# fail N" summary line
  result: fail
- claim: node --input-type=module -e "<script>" executes top-level import statements
    successfully
  result: pass
- claim: process.version is "v" + process.versions.node
  result: pass
raw_output_path: .ll/learning-tests/raw/nodejs.txt
---
