---
target: pi
date: '2026-09-12'
status: proven
assertions:
- claim: pi --version prints a string containing a semantic version number and exits
    0
  result: pass
- claim: pi --mode json -p "<prompt>" prints at least one line parseable as JSON,
    each with a "type" key
  result: pass
- claim: the first JSON line printed by pi --mode json -p has type "session"
  result: pass
- claim: without a configured API key, pi --mode json -p exits non-zero and writes
    the "No API key found" error to stderr as plain text, separate from the JSON
    stdout stream
  result: pass
- claim: pi --help does not document an --output-format flag (only --mode text|json|rpc)
  result: pass
- claim: pi --help does not document a bare --agent flag
  result: pass
- claim: the pi binary on PATH resolves to the @earendil-works/pi-coding-agent npm
    package (pi-mono, FEAT-992), not oh-my-pi
  result: pass
raw_output_path: .ll/learning-tests/raw/pi.txt
---
