#!/usr/bin/env bash
# Pass Claude Code's Stop payload directly to the detached usage-trigger intent.
PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"
export LL_HOOK_HOST=claude-code
exec "$PY" -m little_loops.hooks usage_stop
