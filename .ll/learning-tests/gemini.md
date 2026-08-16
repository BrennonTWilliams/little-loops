---
target: gemini
date: '2026-08-16'
status: proven
assertions:
- claim: gemini --version prints a bare semver string (X.Y.Z, no v-prefix) on this
    machine
  result: pass
- claim: gemini --help documents --approval-mode with a "yolo" choice for auto-approving
    all tool calls
  result: pass
- claim: gemini --help documents -r/--resume accepting "latest" or a numeric index/session-id
    string
  result: pass
- claim: gemini hooks migrate subcommand exists to migrate hooks from Claude Code
    to Gemini CLI
  result: pass
- claim: '--approval-mode yolo is silently overridden to "default" when the current
    working directory is not a trusted workspace, even though yolo was explicitly
    requested'
  result: pass
- claim: headless -p execution exits with code 41 (not one of the previously documented
    0/1/42/53 codes) when no auth is configured (GEMINI_API_KEY/GOOGLE_API_KEY/Vertex
    project+location)
  result: pass
- claim: on an auth failure, the JSON error envelope is written to stderr, not stdout,
    even when --output-format json was requested
  result: pass
raw_output_path: .ll/learning-tests/raw/gemini.txt
---
