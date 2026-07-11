---
target: claude-code-hooks
date: '2026-07-10'
status: proven
assertions:
- claim: claude --version reports Claude Code (CLI installed)
  result: pass
- claim: pre-tool-use.sh documents exit 0=allow and exit 2=block
  result: pass
- claim: sibling hook parses tool_name and tool_input.file_path from stdin via jq
  result: pass
- claim: sibling hook returns the documented allow JSON response shape
  result: pass
- claim: hooks.json registers check-duplicate-issue-id.sh under PreToolUse Write|Edit with timeout 5
  result: pass
- claim: sibling hook early-exits (allow_response) when tool_name is neither Write nor Edit
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-code-hooks.txt
---