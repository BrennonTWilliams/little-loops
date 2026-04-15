---
id: ENH-1114
type: ENH
priority: P4
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
related: [FEAT-1112, ENH-1111]
---

# ENH-1114: Intent Parameter for Large ll-* CLI Outputs

## Summary

Add an optional `--intent <query>` parameter to `ll-history`, `ll-deps`, `ll-scan-*`, `ll-workflows`, and similar CLIs so the full result is indexed but only the slice matching the intent is returned to the caller.

## Motivation

These CLIs today dump their entire result to stdout. A single `ll-deps` run on a mature issue set can be thousands of lines; `ll-history` analysis excerpts push the same. In loop contexts, the agent reads the full dump, even when it only needs "which issues touch FSM state machine rate limits."

Context-mode (github.com/mksglu/context-mode) calls this "intent-driven filtering": when tool output exceeds a threshold and an intent is supplied, the full result is indexed and only the relevant sections return. They report this as one of their highest-impact context reductions.

## Current Behavior

- `ll-history`, `ll-deps`, `ll-scan-*` all print full results
- No way to ask "dependency chain for FEAT-960 only" without piping through grep (which loses context)
- Output sizes routinely exceed 500 lines on real projects

## Expected Behavior

- Affected CLIs accept `--intent "<query>"` and `--intent-limit <N>` (default 50 lines)
- When `--intent` is supplied and full output >200 lines:
  - Full result written to `.ll/scratch/<cmd>-<timestamp>.txt` (or indexed into session DB once FEAT-1112 lands)
  - Ranked subset returned to stdout with a footer: `# Full output: <path> (N lines)`
- Ranking uses simple BM25 over the result lines (stdlib — no extra deps), or delegates to FTS5 once FEAT-1112 lands
- `--intent` without a threshold hit is a no-op

## Acceptance Criteria

- `--intent` flag wired into at least 3 CLIs (`ll-history`, `ll-deps`, `ll-scan-codebase`)
- Ranking module in `scripts/little_loops/ranking.py` with unit tests
- Integration test: `ll-history --intent "rate limit" | wc -l` returns < `ll-history | wc -l`
- CLAUDE.md / API reference updated

## References

- Inspiration: context-mode intent-driven filtering
- Natural upgrade once FEAT-1112 session SQLite+FTS5 store lands (switch ranking backend to FTS5)
- Pairs with ENH-1111 scratch-pad enforcement
