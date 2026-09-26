---
target: codex
date: '2026-09-25'
status: proven
assertions:
- claim: codex exec takes the prompt as a positional argument
  result: pass
- claim: codex exec has a --json flag
  result: pass
- claim: codex exec has an --output-schema flag
  result: pass
- claim: codex -p is --profile, not a prompt flag
  result: pass
- claim: codex exec resume supports --last
  result: pass
- claim: codex exec --sandbox accepts read-only, workspace-write, and danger-full-access
  result: pass
- claim: codex exec has no --agent flag
  result: pass
raw_output_path: .ll/learning-tests/raw/codex.txt
---
