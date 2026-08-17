#!/usr/bin/env bash
# little-loops CI — persist `.ll/history.db` across jobs (two-tier retention).
#
# Why this exists: `.ll/history.db` is gitignored and mutated in place by the
# ll_history pytest plugin, and actions/checkout runs `git clean -ffdx` (which
# removes ignored files) before every job — so without this script every run
# would start from an empty history and cross-run trend / regression detection
# would be impossible.
#
# Subcommands:
#   restore   — copy the newest snapshot back into .ll/history.db (no-op if a
#               history.db already exists, or if no snapshot has been taken yet).
#   snapshot  — copy .ll/history.db into the snapshot root with two-tier retention:
#               * rotated: last N snapshots (default 50)
#               * daily:   one calendar-anchored snapshot per day, kept M days
#                          (default 180)
#
# Retention policy (locked with QA/Watcher, Buzz #ci-cd 2026-08-17):
#   - last-N rotated (50) supports "did this break in the last N runs?"
#   - calendar-anchored daily (180d) supports "did this break in the last 6 months?"
#   Disk math: ~480 KB/run, ~110 MB/repo worst case, ~550 MB across the 5-repo
#   watchlist (~1% of Thinky free space).
set -euo pipefail

# Snapshot root sits OUTSIDE the checkout (one level above $GITHUB_WORKSPACE),
# so checkout's `git clean -ffdx` can never reach it. On Thinky's self-hosted
# runner this resolves inside the persistent runner_work Docker volume.
: "${SNAPSHOT_ROOT:="${GITHUB_WORKSPACE:-.}/../ll-snapshots"}"
: "${ROTATE_KEEP:=50}"
: "${DAILY_KEEP_DAYS:=180}"

DB=".ll/history.db"
ROTATED="$SNAPSHOT_ROOT/rotated"
DAILY="$SNAPSHOT_ROOT/daily"
# Unique rotated id — GitHub's run id in CI (monotonic, unique per run), else a
# nanosecond timestamp. Avoids same-second filename collisions (e.g. back-to-back
# local re-triggers) that would silently collapse two snapshots into one file.
TS="${GITHUB_RUN_ID:-$(date -u +%Y%m%dT%H%M%S.%N)}"
TODAY="$(date -u +%Y-%m-%d)"

restore() {
  if [ -f "$DB" ]; then
    echo "restore: $DB already present, leaving as-is"
    return 0
  fi
  local newest
  newest="$(ls -1t "$ROTATED"/history-*.db 2>/dev/null | head -1 || true)"
  [ -n "$newest" ] || newest="$(ls -1t "$DAILY"/history-*.db 2>/dev/null | head -1 || true)"
  if [ -n "$newest" ]; then
    mkdir -p "$(dirname "$DB")"
    cp "$newest" "$DB"
    echo "restore: $newest -> $DB"
  else
    echo "restore: no prior snapshot (first run)"
  fi
}

snapshot() {
  [ -f "$DB" ] || { echo "snapshot: no $DB to persist"; return 0; }
  mkdir -p "$ROTATED" "$DAILY"
  cp "$DB" "$ROTATED/history-$TS.db"
  cp "$DB" "$DAILY/history-$TODAY.db"   # idempotent: one anchor per calendar day
  # Prune rotated: keep newest ROTATE_KEEP.
  ( ls -1t "$ROTATED"/history-*.db 2>/dev/null \
      | tail -n +"$((ROTATE_KEEP + 1))" \
      | xargs -r rm -f ) || true
  # Prune daily: drop anchors older than DAILY_KEEP_DAYS.
  find "$DAILY" -name 'history-*.db' -mtime +"$DAILY_KEEP_DAYS" -delete 2>/dev/null || true
  echo "snapshot: $DB -> $SNAPSHOT_ROOT (rotated keep=$ROTATE_KEEP, daily keep=${DAILY_KEEP_DAYS}d)"
}

case "${1:-}" in
  restore)  restore ;;
  snapshot) snapshot ;;
  *) echo "usage: $0 {restore|snapshot}" >&2; exit 2 ;;
esac
