#!/usr/bin/env bash
#
# Codex CLI adapter for the PostToolUse hook intent (FEAT-1489).
#
# Reads the host's stdin payload (set by Codex) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.post_tool_use.handle``. Today the handler is a no-op
# returning exit_code=0 — wired as a stable registration point for future
# consumers (audit logging, token budgeting, rate-limit enforcement).
#
# Fire-and-forget semantics: the matching ``hooks.json`` entry uses a short
# (≤5s) timeout. The no-op handler returns in <200ms p95, so the timeout is
# never hit in practice — backgrounding (`&`/`disown`) is intentionally
# avoided so this script stays a 4-line blocking shim, matching its
# siblings (`prompt-submit.sh`, `session-start.sh`, `pre-compact.sh`).
#
# Keep this script minimal (env-set + exec) — any edit flips Codex's trust
# status to ``Modified`` and re-prompts the user to re-trust.
#
export LL_HOOK_HOST=codex
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks post_tool_use
exit $?
