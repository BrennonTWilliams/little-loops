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
- claim: 'ENH-3205 gap (2026-09-07) — unlike gh auth status/gh api, gh auth token
    still prints the operator''s token (exit 0) even when GH_CONFIG_DIR is
    redirected to a freshly-created empty directory and GH_TOKEN/GITHUB_TOKEN are
    unset. On macOS gh stores the OAuth token in the login Keychain under a fixed
    service name ("gh:github.com"), keyed by hostname only — not gated by
    GH_CONFIG_DIR/hosts.yml the way gh auth status/gh api are. Consequence: the
    GH_CONFIG_DIR-redirect-based non-escalation guarantee in ENH-3205''s Decision
    Rules ("an inner github state spawned under an outer non-github declaring
    state... gh auth token fails against the inherited empty config dir") does
    NOT hold on keychain-backed macOS gh — a nested github-scoped spawn can still
    mint a token via the probe regardless of an inherited empty GH_CONFIG_DIR.'
  result: fail
raw_output_path: .ll/learning-tests/raw/gh.txt
---
