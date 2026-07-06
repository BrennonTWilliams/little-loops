#!/usr/bin/env bash
#
# Codex CLI adapter for the edit_batch_nudge PostToolUse hook intent (FEAT-2470).
#
# Reads the host's stdin payload (set by Codex) and pipes it through the
# host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.edit_batch_nudge.handle``. On an Edit/Write/MultiEdit
# tool call the handler returns exit 2 so its edit-batching reminder is
# injected into the model's context; all other tools pass through (exit 0).
# The nudge carries no model-routing semantics, so mirroring it to Codex is
# safe (see FEAT-2470 Decision Rationale).
#
# Keep this script minimal (env-set + exec) — any edit flips Codex's trust
# status to ``Modified`` and re-prompts the user to re-trust.
#
export LL_HOOK_HOST=codex
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks edit_batch_nudge
exit $?
