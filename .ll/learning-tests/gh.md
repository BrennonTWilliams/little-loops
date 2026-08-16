---
target: gh
date: '2026-08-16'
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
raw_output_path: .ll/learning-tests/raw/gh.txt
---
