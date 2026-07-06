#!/usr/bin/env bash
#
# Claude Code adapter for the edit_batch_nudge PostToolUse hook intent (FEAT-2470).
#
# Fires on the Edit|Write|MultiEdit matcher in hooks.json. LL_HOOK_HOST is not
# set because the Python dispatcher defaults to "claude-code". The handler
# returns exit 2 for edit tools so its feedback is injected into the model's
# context; the adapter forwards that exit code unchanged.
#
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks edit_batch_nudge
exit $?
