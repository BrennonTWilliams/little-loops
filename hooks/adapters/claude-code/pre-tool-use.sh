#!/usr/bin/env bash
#
# Claude Code adapter for the PreToolUse hook intent (FEAT-1742).
#
# Pipes the Claude Code PreToolUse JSON payload to the Python
# learning-tests discoverability gate via the shared intent dispatcher.
#
# Exit semantics (Claude Code PreToolUse contract):
#   0 = allow (stderr hint shown to user in warn mode)
#   2 = block (feedback injected into model context in block mode)
#
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks pre_tool_use
exit $?
