---
target: Gemini CLI
date: '2026-09-28'
status: proven
assertions:
- claim: '`gemini --version` prints a bare semver (0.46.0) and exits 0'
  result: pass
- claim: '`--output-format` accepts exactly text, json, and stream-json'
  result: pass
- claim: '`--approval-mode` accepts exactly default, auto_edit, yolo, and plan'
  result: pass
- claim: 'with `--output-format json`, an auth/config failure exits 41 with empty stdout and a JSON object {session_id, error: {type, message, code: 41}} on stderr'
  result: pass
- claim: 'with `--output-format stream-json`, an auth/config failure exits 41 with empty stdout and plain-text (non-JSON) stderr'
  result: pass
- claim: 'in an untrusted folder, `--approval-mode yolo` is silently downgraded to default (stderr notice), and `--skip-trust` suppresses the downgrade'
  result: pass
- claim: '`--list-sessions` exits 0 without valid live credentials'
  result: fail
- claim: 'with `--output-format json -p`, stdout is a single JSON object containing response and stats keys'
  result: untested
- claim: 'with `--output-format stream-json -p`, stdout is JSONL where every line is an object with a type key'
  result: untested
- claim: 'the first stream-json event has type init'
  result: untested
- claim: 'the last stream-json event has type result'
  result: untested
- claim: '`--approval-mode yolo` with `-p` completes a headless run and exits 0'
  result: untested
raw_output_path: .ll/learning-tests/raw/gemini-cli.txt
---
