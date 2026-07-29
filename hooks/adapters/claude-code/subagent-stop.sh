#!/usr/bin/env bash
#
# Claude Code adapter for the SubagentStop hook intent.
#
# Reads the host's stdin payload (set by Claude Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.subagent_stop.handle``. The dispatcher's exit code and
# stderr feedback satisfy the Claude Code shell-hook contract directly.
#
INPUT=$(cat)
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks subagent_stop
exit $?
