---
target: codex-cli
date: '2026-09-23'
status: proven
assertions:
- claim: '`codex exec resume` accepts `-c key=value`'
  result: pass
- claim: '`codex exec resume` rejects `--sandbox <mode>` (unexpected argument, exit 2)'
  result: pass
- claim: '`codex exec resume` rejects the short flag `-s <mode>` (unexpected argument, exit 2)'
  result: pass
- claim: '`codex exec resume` accepts `--dangerously-bypass-approvals-and-sandbox`'
  result: pass
- claim: '`codex exec --sandbox <mode> resume --last` (flag placed before `resume`) is accepted'
  result: pass
- claim: '`codex exec -c key=value resume --last` (flag placed before `resume`) is accepted'
  result: pass
- claim: '`codex exec resume` accepts `--json`'
  result: pass
raw_output_path: .ll/learning-tests/raw/codex-cli.txt
---
