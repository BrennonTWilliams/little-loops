#!/usr/bin/env bash
# Dispatch a completed Codex turn to the detached stored-usage refresh.
export LL_HOOK_HOST=codex
INPUT=$(cat)
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks usage_stop
exit $?
