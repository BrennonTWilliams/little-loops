---
target: actions/checkout
date: '2026-09-10'
status: proven
assertions:
- claim: actions/checkout@v4's action.yml declares input "fetch-depth" with default 1
  result: pass
- claim: git rev-parse --is-shallow-repository prints true inside a depth-1 clone
  result: pass
- claim: git rev-parse --is-shallow-repository prints false inside a full clone
  result: pass
- claim: git rev-list --count --all prints 1 inside a depth-1 clone (log --all --raw sees only the tip)
  result: pass
- claim: a blob addressed as <parent-commit>:<file> is unresolvable in a depth-1 clone (git cat-file -e exits non-zero)
  result: pass
- claim: git fetch --unshallow flips is-shallow-repository to false
  result: pass
- claim: a full clone reports the true commit count via rev-list --count --all
  result: pass
raw_output_path: .ll/learning-tests/raw/actionscheckout.txt
---
