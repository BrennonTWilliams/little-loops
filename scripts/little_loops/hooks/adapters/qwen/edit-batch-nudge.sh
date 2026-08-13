#!/usr/bin/env bash
#
# Qwen Code adapter for the PostToolUse hook intent.
#
# Reads the host's stdin payload (set by Qwen Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.edit_batch_nudge.handle``. Advisory stderr nudge after
# write_file/edit tool calls; wired with the same runtime-id matcher as
# pre-tool-use.
#
# Keep this script minimal (env-set + exec) — the managed settings block
# references the command string, so logic belongs behind the stable
# ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=qwen
INPUT=$(cat)
# Re-locate to the payload's project directory in case hooks are spawned
# from an extension/plugin root rather than the project (BUG-2921 hardening,
# cheap to carry up front on Qwen).
PAYLOAD_CWD=$(printf '%s' "$INPUT" | sed -n 's/.*"cwd":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
if [ -n "$PAYLOAD_CWD" ] && [ -d "$PAYLOAD_CWD" ]; then cd "$PAYLOAD_CWD" || true; fi
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks edit_batch_nudge
exit $?
