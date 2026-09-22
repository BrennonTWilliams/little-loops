---
target: gh CLI
date: '2026-09-22'
status: proven
assertions:
- claim: gh --version first line matches "gh version X.Y.Z (YYYY-MM-DD)"
  result: pass
- claim: gh issue create has no --json flag
  result: pass
- claim: an unknown gh subcommand exits non-zero and writes an error to stderr
  result: pass
- claim: gh auth status writes its human-readable status to stderr, not stdout, even on success
  result: fail
- claim: gh api user --jq .login returns exactly the authenticated username with no extra formatting
  result: pass
- claim: gh repo view --json name -q .name prints the bare repo name as plain text
  result: pass
raw_output_path: .ll/learning-tests/raw/gh-cli.txt
---
