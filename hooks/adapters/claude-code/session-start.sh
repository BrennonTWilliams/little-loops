#!/usr/bin/env bash
#
# Claude Code adapter for the SessionStart hook intent.
#
# Reads the host's stdin payload (set by Claude Code) and pipes it through
# the host-agnostic Python dispatcher, which routes to
# ``little_loops.hooks.session_start.handle``. The dispatcher writes the
# merged config JSON to stdout (consumed by Claude Code as session context)
# and feature-flag/info messages to stderr.
#
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks session_start
exit $?
