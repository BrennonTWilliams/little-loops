#!/usr/bin/env bash
#
# Claude Code adapter for the PostToolUse hook intent (BUG-1881).
#
# Mirrors hooks/adapters/codex/post-tool-use.sh. LL_HOOK_HOST is not set
# because the Python dispatcher defaults to "claude-code".
# Backgrounding (&/disown) is intentionally avoided — a single-row INSERT
# keeps p95 well below the 5 s timeout when analytics is enabled.
#
INPUT=$(cat)
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks post_tool_use
exit $?
