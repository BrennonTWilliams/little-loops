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
echo "$INPUT" | python -m little_loops.hooks session_end
exit $?
