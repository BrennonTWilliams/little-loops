#!/usr/bin/env bash
#
# Kimi Code adapter for the PostToolUse hook intent.
#
# Reads the host's stdin payload (set by Kimi Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.post_tool_use.handle``. The handler persists a
# single ``tool_events`` row per tool call when ``analytics.enabled`` is
# set; latency stays well under the hooks.toml timeout.
#
# Keep this script minimal (env-set + exec) — hooks.toml references the
# command string, so logic belongs behind the stable
# ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=kimi-code
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks post_tool_use
exit $?
