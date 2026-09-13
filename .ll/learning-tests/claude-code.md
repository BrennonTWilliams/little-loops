---
target: claude-code
date: '2026-09-12'
status: proven
assertions:
- claim: 'headless `claude --permission-mode acceptEdits --add-dir <dir> -p "<prompt>"`
    (no --dangerously-skip-permissions, clean env) auto-approves a Write tool call
    to a file inside <dir> with no permission prompt'
  result: pass
- claim: 'the same invocation does NOT create a file for a Write tool call to a path
    outside <dir> and outside the process cwd (i.e. --add-dir + acceptEdits forms
    a filesystem jail)'
  result: fail
- claim: 'a stray DANGEROUSLY_SKIP_PERMISSIONS=1 env var (no --dangerously-skip-permissions
    CLI flag) alone causes the outside-directory Write to succeed where it would
    otherwise be denied'
  result: untested
- claim: 'the final {"type":"result"} envelope''s subtype is "success" even when
    the outside-directory write was denied'
  result: untested
- claim: 'a denied outside-directory write surfaces as an error-flagged tool_result
    in the stream-json output'
  result: untested
- claim: claude --version prints a string containing a semantic version number and exits 0
  result: pass
- claim: claude --output-format json -p "<prompt>" prints a single JSON object (not JSONL) to stdout
  result: pass
- claim: that JSON object contains a result key holding the final text response
  result: pass
- claim: claude --output-format stream-json --verbose -p "<prompt>" prints multiple JSON objects, one per line (JSONL), not one blob
  result: pass
- claim: each stream-json line is a dict with a type key
  result: pass
- claim: claude --dangerously-skip-permissions -p "<prompt>" --output-format json exits 0 for a trivial prompt with no side effects
  result: pass
- claim: --json-schema '<schema>' alongside --output-format json constrains the result field to match the given JSON Schema
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-code.txt
---
