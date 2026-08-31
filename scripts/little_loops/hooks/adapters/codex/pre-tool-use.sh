#!/usr/bin/env bash
#
# Codex CLI adapter for the PreToolUse hook intent (FEAT-1489, FEAT-1742, ENH-1718).
#
# Reads the host's stdin payload (set by Codex) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.pre_tool_use.handle``. That handler dispatches
# Write/Edit calls to the learning-test discoverability gate
# (FEAT-1742) and passes every other tool through unchanged. The
# matching ``hooks.json`` entry scopes this shim to the ``Edit|Write``
# matcher so it never fires on the hot path for other tool calls.
#
# Keep this script minimal (env-set + exec) — any edit flips Codex's trust
# status to ``Modified`` and re-prompts the user to re-trust.
#
export LL_HOOK_HOST=codex
INPUT=$(cat)
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks pre_tool_use
exit $?
