#!/usr/bin/env bash
#
# Gemini CLI adapter for the AfterTool hook intent.
#
# Reads the host's stdin payload (set by Gemini) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.post_tool_use.handle`` (per-tool byte metrics into
# ``.ll/history.db`` when ``analytics.enabled``, FEAT-1623).
#
# Keep this script minimal (env-set + exec) — logic belongs behind the
# stable ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=gemini
INPUT=$(cat)
PAYLOAD_CWD=$(printf '%s' "$INPUT" | sed -n 's/.*"cwd":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
if [ -n "$PAYLOAD_CWD" ] && [ -d "$PAYLOAD_CWD" ]; then cd "$PAYLOAD_CWD" || true; fi
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks post_tool_use
exit $?
