---
target: gh
date: '2026-09-08'
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
- claim: 'ENH-3205 gap, ambient-only (2026-09-07, reworded 2026-09-08 per
    BUG-3402) — unlike gh auth status/gh api, gh auth token still prints the
    operator''s token (exit 0) even when GH_CONFIG_DIR is redirected to a
    freshly-created empty directory and GH_TOKEN/GITHUB_TOKEN are left unset
    (i.e. no gh_scope_extra() sentinel is injected — a fully ambient
    invocation with no credential-scope declared at all). On macOS gh stores
    the OAuth token in the login Keychain under a fixed service name
    ("gh:github.com"), keyed by hostname only — not gated by
    GH_CONFIG_DIR/hosts.yml the way gh auth status/gh api are. This residual
    case is unchanged by the BUG-3402 sentinel fix below, which only applies
    where gh_scope_extra() itself is called (with_token=False) — re-verified
    2026-09-08 against gh 2.86.0 after the fix landed.'
  result: fail
- claim: 'BUG-3402 fix (2026-09-08) — setting GH_TOKEN to an obviously-invalid
    sentinel value (e.g. "ll-scoped-no-github-token") alongside a GH_CONFIG_DIR
    redirected to an empty directory causes gh auth status to report a login
    failure ("The token in GH_TOKEN is invalid.", exit 1) instead of falling back
    to the Keychain-backed ambient login.'
  result: pass
- claim: 'BUG-3402 fix (2026-09-08) — under the same GH_TOKEN sentinel +
    GH_CONFIG_DIR-redirect environment, gh auth token prints the sentinel value
    itself (exit 0) rather than the operator''s real Keychain-backed token,
    confirming GH_TOKEN precedence over Keychain closes the gh_scope_extra()
    isolation gap for the with_token=False case.'
  result: pass
- claim: 'BUG-3402 fix, nested case (2026-09-08) — with GH_TOKEN set to the
    GH_SCOPED_NO_TOKEN sentinel (simulating a nested github-declaring state
    inheriting an outer non-github declaring state''s injected sentinel via
    env), gh auth token prints only the sentinel value (exit 0), not the
    operator''s real Keychain-backed token — confirming a nested probe
    cannot reach Keychain even when the sentinel is inherited rather than
    freshly injected, closing the ENH-3205 non-escalation gap on
    keychain-backed macOS gh. Verified against gh 2.86.0.'
  result: pass
raw_output_path: .ll/learning-tests/raw/gh.txt
---
