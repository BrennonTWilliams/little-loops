#!/usr/bin/env bash
#
# user-prompt-check.sh
# UserPromptSubmit hook for little-loops plugin
#
# Delegates to the Python host-agnostic handler which applies:
# 1. Correction detection + analytics write (analytics.enabled gate)
# 2. Auto-prompt optimization (prompt_optimization.enabled gate)
#
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks user_prompt_submit
exit $?
