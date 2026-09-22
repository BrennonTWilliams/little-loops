---
target: actions/setup-node
date: '2026-09-22'
status: proven
assertions:
- claim: node-version input has no explicit default in action.yml
  result: pass
- claim: cache input's documented supported values are npm, yarn, pnpm
  result: pass
- claim: token input defaults to the github.token expression (falls back to empty
    off github.com)
  result: pass
- claim: action declares exactly four outputs cache-hit, cache-primary-key, cache-matched-key,
    node-version
  result: pass
- claim: runs.using is a JS runtime (node24), not a docker action
  result: pass
- claim: package-manager-cache input defaults to boolean true
  result: pass
raw_output_path: .ll/learning-tests/raw/actionssetup-node.txt
---
