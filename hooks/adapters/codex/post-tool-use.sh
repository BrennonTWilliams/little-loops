#!/usr/bin/env bash
#
# Codex CLI adapter for the PostToolUse hook intent (FEAT-1489, FEAT-1623).
#
# Reads the host's stdin payload (set by Codex) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.post_tool_use.handle``. Per FEAT-1623 the handler
# persists per-tool byte metrics (``bytes_in`` / ``bytes_out`` /
# ``cache_hit``) into ``.ll/session.db`` so ``/ll:ctx-stats`` (FEAT-1160)
# can surface which tools consumed the most context-window bytes. Writes
# are gated on the ``analytics.enabled`` config flag — when off, the
# handler returns exit 0 without touching SQLite.
#
# Latency: the matching ``hooks.json`` entry uses a short (≤5s) timeout.
# A single-row INSERT keeps p95 well below the timeout when analytics is
# enabled; the disabled-guard path is effectively free. Backgrounding
# (`&`/`disown`) is intentionally avoided so this script stays a 4-line
# blocking shim, matching its siblings (`prompt-submit.sh`,
# `session-start.sh`, `pre-compact.sh`).
#
# Keep this script minimal (env-set + exec) — any edit flips Codex's trust
# status to ``Modified`` and re-prompts the user to re-trust.
#
export LL_HOOK_HOST=codex
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks post_tool_use
exit $?
