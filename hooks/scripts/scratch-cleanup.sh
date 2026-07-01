#!/bin/bash
#
# scratch-cleanup.sh
# SessionEnd hook for little-loops plugin (BUG-2420)
#
# Removes the scratch-pad directory (.loops/tmp/scratch) at session termination.
#
# This cleanup previously ran on the `Stop` event (in session-cleanup.sh), but
# `Stop` fires at the end of EVERY assistant turn — so it raced auto-backgrounded
# allowlisted commands that intentionally outlive the turn, deleting the scratch
# dir out from under a command that was still writing to it (zero output
# captured). `SessionEnd` fires only once, when the whole session terminates,
# after which no background work remains — the correct lifetime for this delete.
#
# IMPORTANT: This is a cleanup script - it must NEVER fail. All operations are
# wrapped to succeed even if the underlying command fails.

# Runs relative to CWD, which should be the project root.
rm -rf ".loops/tmp/scratch" 2>/dev/null || true

exit 0
