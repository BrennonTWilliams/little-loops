#!/usr/bin/env bash
#
# Kimi Code adapter for the PreToolUse hook intent.
#
# Reads the host's stdin payload (set by Kimi Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.pre_tool_use.handle``. Exit code and stderr pass
# back to Kimi verbatim (exit 2 blocks the tool call; stderr is the
# reason shown to the user).
#
# Keep this script minimal (env-set + exec) — hooks.toml references the
# command string, so logic belongs behind the stable
# ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=kimi-code
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks pre_tool_use
exit $?
