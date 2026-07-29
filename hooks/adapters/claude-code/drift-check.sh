#!/usr/bin/env bash
INPUT=$(cat)
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
echo "$INPUT" | "$PY" -m little_loops.hooks drift_check
exit $?
