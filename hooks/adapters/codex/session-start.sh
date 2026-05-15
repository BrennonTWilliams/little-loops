#!/usr/bin/env bash
#
# Codex CLI adapter for the SessionStart hook intent.
#
# Reads the host's stdin payload (set by Codex) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.session_start.handle``. The dispatcher writes the
# merged config JSON to stdout (Codex injects this as ``additionalContext``)
# and feature-flag/info messages to stderr.
#
# Keep this script minimal (env-set + exec) — any edit flips Codex's trust
# status to ``Modified`` and re-prompts the user to re-trust.
#
export LL_HOOK_HOST=codex
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks session_start
exit $?
