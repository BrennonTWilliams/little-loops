---
target: 'claude CLI plugin subsystem: headless \claude plugin marketplace add <source>'
date: '2026-09-01'
status: proven
assertions:
- claim: claude plugin marketplace add <source> succeeds non-interactively (no TTY
    prompt) for a local path
  result: pass
- claim: re-adding the same source is idempotent (exit 0, no duplicate entry)
  result: pass
- claim: add on a nonexistent path exits non-zero with a clear error, no prompt
  result: pass
- claim: add accepts a bare github owner/repo shorthand and clones headlessly
  result: pass
- claim: --scope project writes the marketplace declaration into ./.claude/settings.json
    instead of user config
  result: pass
- claim: after marketplace add, plugin install <name>@<marketplace> also runs non-interactively
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-cli-plugin-subsystem-headless-claude-plugin-marketplace-add-source.txt
---
