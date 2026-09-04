---
target: gh
date: '2026-09-04'
status: proven
assertions:
- claim: gh issue list --json number,title,state outputs a valid JSON array (even
    when empty)
  result: pass
- claim: gh issue create does not accept a --json flag; success output is a plain
    URL string
  result: pass
- claim: gh api repos/{owner}/{repo} returns a JSON object containing a default_branch
    key
  result: pass
- claim: gh auth status exits 0 when authenticated
  result: pass
- claim: gh issue edit supports an --add-label flag
  result: pass
- claim: gh pr view --json accepts a state field, which appears in the documented
    JSON FIELDS list
  result: pass
- claim: with GH_CONFIG_DIR pointed at an empty directory and GH_TOKEN/GITHUB_TOKEN
    unset, gh does not see a keyring-backed ambient login (gh auth status reports
    not logged in; gh api fails asking for gh auth login or GH_TOKEN)
  result: pass
- claim: gh auth token prints the ambient session's token (exit 0) even when no
    GH_TOKEN/GITHUB_TOKEN env var is set (keyring-backed login)
  result: pass
raw_output_path: .ll/learning-tests/raw/gh.txt
---
