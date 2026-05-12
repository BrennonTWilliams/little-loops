#!/usr/bin/env bash
#
# Claude Code adapter for the PreCompact hook intent.
#
# Reads the host's stdin payload (set by Claude Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.pre_compact.handle``. The dispatcher's exit code and
# stderr feedback satisfy the Claude Code shell-hook contract directly.
#
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks pre_compact
exit $?
