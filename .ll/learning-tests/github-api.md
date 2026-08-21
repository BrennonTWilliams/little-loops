---
target: GitHub API
date: '2026-08-21'
status: proven
assertions:
- claim: gh repo view --json nameWithOwner -q .nameWithOwner returns a bare plain-text
    string (owner/repo), not JSON-quoted
  result: pass
- claim: gh issue list --json number,title,state returns a JSON array of objects
    containing exactly the requested keys
  result: untested
- claim: gh pr view <ref> --json state,mergedAt returns "state" as an uppercase
    enum string (OPEN/CLOSED/MERGED)
  result: pass
- claim: for an unmerged PR, gh pr view --json mergedAt returns JSON null for mergedAt,
    not an empty string
  result: pass
- claim: gh issue list --json number on a query with zero matches returns [] (empty
    array), not null or empty stdout
  result: pass
- claim: gh auth status exits 0 when authenticated, and its status text goes to
    stderr, not stdout
  result: fail
- claim: gh --version stdout begins with the literal string "gh version"
  result: pass
raw_output_path: .ll/learning-tests/raw/github-api.txt
---
