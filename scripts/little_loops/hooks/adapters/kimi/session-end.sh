#!/usr/bin/env bash
#
# Kimi Code adapter for the SessionEnd hook intent.
#
# Reads the host's stdin payload (set by Kimi Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.sweep_stale_refs.handle`` (the ``session_end``
# intent). Kimi fires SessionEnd natively on session teardown — unlike
# Claude Code, where ``session_end`` is dispatched from SessionStart due
# to an upstream bug.
#
# Keep this script minimal (env-set + exec) — hooks.toml references the
# command string, so logic belongs behind the stable
# ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=kimi-code
INPUT=$(cat)
# Kimi spawns plugin hooks with cwd = plugin root; relocate to the payload's
# project directory so config and telemetry resolve against the project's
# .ll/ rather than the managed plugin copy (BUG-2921).
PAYLOAD_CWD=$(printf '%s' "$INPUT" | sed -n 's/.*"cwd":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
if [ -n "$PAYLOAD_CWD" ] && [ -d "$PAYLOAD_CWD" ]; then cd "$PAYLOAD_CWD" || true; fi
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks session_end
exit $?
