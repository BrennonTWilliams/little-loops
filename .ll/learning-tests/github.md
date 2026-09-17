---
target: github
date: '2026-09-17'
status: proven
assertions:
- claim: gh pr view <ref> --json state,mergedAt returns JSON with exactly the keys
    state and mergedAt
  result: pass
- claim: mergedAt is JSON null for an open (unmerged) PR
  result: pass
- claim: mergedAt is an ISO-8601 timestamp string for a merged PR
  result: pass
- claim: state is an uppercase enum string (OPEN, MERGED, CLOSED)
  result: pass
- claim: gh pr view on a nonexistent PR number exits non-zero with the error on
    stderr and empty stdout
  result: pass
- claim: gh auth status writes its human-readable status to stderr, not stdout
  result: fail
raw_output_path: .ll/learning-tests/raw/github.txt
---
