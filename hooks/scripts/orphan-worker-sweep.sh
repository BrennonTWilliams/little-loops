#!/bin/bash
#
# orphan-worker-sweep.sh
# SessionEnd hook for little-loops plugin
#
# Reaps orphaned pytest-xdist workers left behind by killed pytest runs.
# xdist's setproctitle rewrites worker command lines to "[pytest-xdist running]",
# so `pkill -f "pytest scripts/tests"` misses them; each orphan spins at ~100%
# CPU (observed cumulative load=20). See audit run
# .loops/runs/general-task-20260707T133447/audit-report.md (S6).
#
# Safety: only kill workers that have reparented to init (PPID 1) — a live
# pytest controller in this or another concurrent session keeps its workers
# parented to itself, and those must not be touched.
#
# Note: `pgrep -af "pytest-xdist running"` self-matches the invoking shell
# (the literal appears in the command line), so we use ps + awk with a
# split literal so this pipeline never matches itself.
#
# This is a cleanup script — it must NEVER fail.

ps -axo pid=,ppid=,command= 2>/dev/null | \
    awk 'BEGIN { needle = "pytest-xdist" " running" }
         $2 == 1 && index($0, needle) { print $1 }' | \
    while read -r pid; do
        kill -9 "$pid" 2>/dev/null || true
    done

exit 0
