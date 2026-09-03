#!/usr/bin/env bash
#
# Gemini CLI adapter for the SessionStart hook intent.
#
# Reads the host's stdin payload (set by Gemini) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.session_start.handle``. SessionStart is advisory
# only on Gemini (cannot block); the dispatcher's stdout is injected as
# ``additionalContext``.
#
# Keep this script minimal (env-set + exec) — logic belongs behind the
# stable ``python -m little_loops.hooks <intent>`` interface.
#
export LL_HOOK_HOST=gemini
INPUT=$(cat)
# Re-locate to the payload's project directory in case hooks are spawned
# from an extension/plugin root rather than the project (BUG-2921 hardening,
# same treatment as the qwen adapter).
PAYLOAD_CWD=$(printf '%s' "$INPUT" | sed -n 's/.*"cwd":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
if [ -n "$PAYLOAD_CWD" ] && [ -d "$PAYLOAD_CWD" ]; then cd "$PAYLOAD_CWD" || true; fi
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks session_start
exit $?
