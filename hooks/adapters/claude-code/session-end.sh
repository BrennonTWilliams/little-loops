#!/usr/bin/env bash
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks session_end
exit $?
