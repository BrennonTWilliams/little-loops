---
target: codex-rollout
date: '2026-09-08'
status: proven
assertions:
- claim: '~/.codex/projects/ does not exist'
  result: pass
- claim: rollout files live at ~/.codex/sessions/YYYY/MM/DD/rollout-<ISO-timestamp>-<uuid>.jsonl
  result: pass
- claim: every non-empty line in a rollout file parses as JSON with top-level keys timestamp, type, payload
  result: pass
- claim: the first line's type is session_meta
  result: pass
- claim: session_meta.payload contains id, cwd, originator, cli_version, source, model_provider
  result: pass
- claim: type values across a file are limited to {session_meta, turn_context, response_item, event_msg}
  result: pass
- claim: '~/.codex/state_<N>.sqlite exists with a threads table containing a rollout_path column'
  result: pass
raw_output_path: .ll/learning-tests/raw/codex-rollout.txt
---
