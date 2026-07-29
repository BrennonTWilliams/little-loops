#!/usr/bin/env bash
#
# Claude Code adapter for the PreCompact handoff hook intent.
#
# Reads the host's stdin payload and pipes it through the Python dispatcher,
# which routes to ``little_loops.hooks.pre_compact_handoff.handle``.
#
INPUT=$(cat)
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks pre_compact_handoff
exit $?
