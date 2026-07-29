#!/usr/bin/env bash
#
# Kimi Code adapter for the PreCompact hook intent.
#
# Reads the host's stdin payload (set by Kimi Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.pre_compact.handle``. Kimi ignores PreCompact return
# values, so the dispatcher's exit code and stderr are advisory only.
#
# Keep this script minimal (env-set + exec) — hooks.toml references the
# command string, so logic belongs behind the stable
# ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=kimi-code
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks pre_compact
exit $?
