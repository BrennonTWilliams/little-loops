#!/usr/bin/env bash
#
# Claude Code adapter for the edit_batch_nudge PostToolUse hook intent (FEAT-2470).
#
# Fires on the Edit|Write|MultiEdit matcher in hooks.json. LL_HOOK_HOST is not
# set because the Python dispatcher defaults to "claude-code". On a nudge fire
# the handler returns exit 0 with a hookSpecificOutput.additionalContext JSON
# payload on stdout (ENH-2994) — Claude Code renders PostToolUse exit 2 as a
# blocking-error banner, which is misleading for this purely advisory reminder.
# The adapter forwards stdout and the exit code unchanged.
#
INPUT=$(cat)
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks edit_batch_nudge
exit $?
