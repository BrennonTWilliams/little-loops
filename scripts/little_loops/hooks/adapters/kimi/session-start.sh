#!/usr/bin/env bash
#
# Kimi Code adapter for the SessionStart hook intent.
#
# Reads the host's stdin payload (set by Kimi Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.session_start.handle``. The dispatcher writes the
# merged config JSON to stdout (Kimi appends it to the session context)
# and feature-flag/info messages to stderr.
#
# Keep this script minimal (env-set + exec) — hooks.toml references the
# command string, so logic belongs behind the stable
# ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=kimi-code
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks session_start
exit $?
