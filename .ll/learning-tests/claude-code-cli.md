---
target: Claude Code CLI
date: '2026-09-23'
status: proven
assertions:
- claim: '`claude --version` prints `<semver> (Claude Code)`'
  result: pass
- claim: '`claude -p <prompt> --output-format json` emits a single JSON object with
    type "result", subtype "success", and a string `result` field'
  result: pass
- claim: the json result envelope includes session_id, total_cost_usd, and usage
  result: pass
- claim: '`--output-format stream-json` with `-p` fails (non-zero exit) unless `--verbose`
    is also passed'
  result: pass
- claim: with `--verbose`, `-p --output-format stream-json` emits one JSON object per
    line and the final event is type "result", subtype "success"
  result: pass
- claim: the first stream-json event is type "system" subtype "init"
  result: fail
- claim: an unrecognized `--model` value exits non-zero
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-code-cli.txt
---
