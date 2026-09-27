# BUG-2908: check_passed/recheck_*/regate_* only ever recorded that an
# issue STAGED past the readiness/outcome thresholds — that happens
# before implement_current runs, so a no-op or crashed implementation
# left the same ID in autodev-passed.txt as a genuinely closed one, with
# nothing to ever revoke the entry. Promote staged IDs to
# autodev-passed.txt here, ONLY once verified closed; anything staged
# but not closed lands in autodev-unverified.txt instead so it can be
# reported and gate the verdict below rather than laundered as a pass.
STAGED_IDS=$(cat ${context.run_dir}/autodev-staged.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
# ENH-3613: cancelled closures are tallied in memory (CANCELLED_IDS) so the
# summary can split them from implemented ones; they still land in
# autodev-passed.txt as bare IDs.
CANCELLED_IDS=""
# FEAT-3573: with the quality gate on, an implemented (done/completed) ID is
# promoted only if quality/<ID>.json records GATE_PASS or GATE_SKIP. A
# GATE_FAILED / GATE_INFRA record was already ledgered by
# record_quality_evidence (`quality_gate_failed` / `quality_gate_infra`); a
# done ID with no record at all is `quality_evidence_missing`. Cancelled
# closures are promoted on status alone.
QUALITY_GATE=$(printf '%s' ${context.quality_gate:shell:default=true} | tr '[:upper:]' '[:lower:]')
QUALITY_DIR=${context.run_dir}/quality
for ID in $STAGED_IDS; do
  STATUS=$(ll-issues show "$ID" --json 2>/dev/null \
    | python3 -c "import json,sys; print((json.load(sys.stdin).get('status') or '').lower())" \
    2>/dev/null || echo "")
  case "$STATUS" in
    done|completed)
      case "$QUALITY_GATE" in
        false|0|no|off)
          echo "$ID" >> ${context.run_dir}/autodev-passed.txt ;;
        *)
          QUALITY_VERDICT=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('verdict') or '')" \
            "$QUALITY_DIR/$ID.json" 2>/dev/null || echo "")
          case "$QUALITY_VERDICT" in
            GATE_PASS|GATE_SKIP)
              echo "$ID" >> ${context.run_dir}/autodev-passed.txt ;;
            GATE_FAILED) QUALITY_REASON=quality_gate_failed ;;
            GATE_INFRA) QUALITY_REASON=quality_gate_infra ;;
            *) QUALITY_REASON=quality_evidence_missing ;;
          esac
          case "$QUALITY_VERDICT" in
            GATE_PASS|GATE_SKIP) ;;
            *)
              if ! grep -qE "^$ID([[:space:]]|$)" ${context.run_dir}/autodev-unverified.txt 2>/dev/null; then
                echo "$ID  $QUALITY_REASON" >> ${context.run_dir}/autodev-unverified.txt
              fi ;;
          esac ;;
      esac ;;
    cancelled)
      echo "$ID" >> ${context.run_dir}/autodev-passed.txt
      CANCELLED_IDS="$CANCELLED_IDS $ID"
      ;;
    *)
      # BUG-3390: verify_impl_closed may already hold "ID  reason"; sort -u
      # cannot merge that with a bare "ID", so guard like the ABANDONED
      # branch below.
      if ! grep -qE "^$ID([[:space:]]|$)" ${context.run_dir}/autodev-unverified.txt 2>/dev/null; then
        echo "$ID" >> ${context.run_dir}/autodev-unverified.txt
      fi ;;
  esac
done

PASSED_IDS=$(cat ${context.run_dir}/autodev-passed.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
UNVERIFIED_IDS=$(cat ${context.run_dir}/autodev-unverified.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
# ENH-2727: exclude infra-class skips from the generic Skipped bucket so
# they are surfaced separately (re-runnable) below and not double-counted.
# ENH-2868: likewise exclude pre-flight status skips (already_done /
# already_cancelled / already_deferred) — these never entered refinement
# at all and are not a failure signal.
# ENH-2909: exclude blocked_by_unmet pre-flight skips from the generic
# Skipped bucket too — these never entered refinement (see the already_*
# exclusion below for the identical ENH-2868 precedent).
# ENH-2989: exclude notstarted_* skips — a Phase 1 rejection never
# reached implementation, so it belongs in the not_started bucket, not
# double-counted here too (decision #2a).
SKIPPED_IDS=$(cat ${context.run_dir}/autodev-skipped.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | grep -v 'refine_failed_infra' \
  | grep -v '[[:space:]]already_' | grep -v '[[:space:]]blocked_by_unmet' \
  | grep -v '[[:space:]]notstarted_' \
  | sort -u || true)
INFRA_SKIPPED_IDS=$(grep 'refine_failed_infra' ${context.run_dir}/autodev-skipped.txt 2>/dev/null \
  | awk '{print $1}' | grep -v '^[[:space:]]*$' | sort -u || true)
ALREADY_RESOLVED_IDS=$(grep '[[:space:]]already_' ${context.run_dir}/autodev-skipped.txt 2>/dev/null \
  | awk '{print $1" ("$2")"}' | sed 's/already_//' \
  | grep -v '^[[:space:]]*$' | sort -u || true)
BLOCKED_BY_UNMET_IDS=$(grep '[[:space:]]blocked_by_unmet' ${context.run_dir}/autodev-skipped.txt 2>/dev/null \
  | awk '{print $1}' | grep -v '^[[:space:]]*$' | sort -u || true)
GATE_BLOCKED_IDS=$(cat ${context.run_dir}/autodev-gate-blocked.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
DECISION_UNRESOLVED_IDS=$(cat ${context.run_dir}/autodev-decision-unresolved.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
# ENH-2989: "ID  reason" ledger lines formatted "ID (reason)" so the
# operator sees why without opening the ledger — the Already-resolved
# line's exact idiom.
NOT_STARTED_IDS=$(cat ${context.run_dir}/autodev-not-started.txt 2>/dev/null \
  | awk '{print $1" ("$2")"}' | grep -v '^[[:space:]]*$' | sort -u || true)

PASSED_COUNT=$(echo "$PASSED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$PASSED_COUNT" ] && PASSED_COUNT=0
# ENH-3613: closed_implemented + closed_cancelled == closed by construction.
CLOSED_CANCELLED=$(echo "$CANCELLED_IDS" | tr ' ' '\n' | grep -c '[^[:space:]]' || true)
[ -z "$CLOSED_CANCELLED" ] && CLOSED_CANCELLED=0
CLOSED_IMPLEMENTED=$((PASSED_COUNT - CLOSED_CANCELLED))
CANCELLED_LIST=$(echo "$CANCELLED_IDS" | tr ' ' '\n' | grep -v '^[[:space:]]*$' | tr '\n' ',' | sed 's/,$//')
SKIPPED_COUNT=$(echo "$SKIPPED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$SKIPPED_COUNT" ] && SKIPPED_COUNT=0
INFRA_SKIPPED_COUNT=$(echo "$INFRA_SKIPPED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$INFRA_SKIPPED_COUNT" ] && INFRA_SKIPPED_COUNT=0
ALREADY_RESOLVED_COUNT=$(echo "$ALREADY_RESOLVED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$ALREADY_RESOLVED_COUNT" ] && ALREADY_RESOLVED_COUNT=0
BLOCKED_BY_UNMET_COUNT=$(echo "$BLOCKED_BY_UNMET_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$BLOCKED_BY_UNMET_COUNT" ] && BLOCKED_BY_UNMET_COUNT=0
GATE_BLOCKED_COUNT=$(echo "$GATE_BLOCKED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$GATE_BLOCKED_COUNT" ] && GATE_BLOCKED_COUNT=0
DECISION_UNRESOLVED_COUNT=$(echo "$DECISION_UNRESOLVED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$DECISION_UNRESOLVED_COUNT" ] && DECISION_UNRESOLVED_COUNT=0
NOT_STARTED_COUNT=$(echo "$NOT_STARTED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$NOT_STARTED_COUNT" ] && NOT_STARTED_COUNT=0
# BUG-3603: pre-implement proof-gate helper failures get their own bucket,
# sourced from the mark_proof_gate_infra ledger.
PROOF_GATE_INFRA_COUNT=$(grep -c '[^[:space:]]' ${context.run_dir}/autodev-proof-gate-infra.txt 2>/dev/null || true)
[ -z "$PROOF_GATE_INFRA_COUNT" ] && PROOF_GATE_INFRA_COUNT=0

INFLIGHT=$(cat ${context.run_dir}/autodev-inflight 2>/dev/null | tr -d '[:space:]' || true)
# BUG-2908 Step 4: a residual autodev-inflight sentinel at finalize means
# dequeue_next dispatched an issue that never reached passed/skipped —
# fold it into the unverified bucket (with a distinct reason) instead of
# a standalone advisory line so it feeds the verdict below rather than
# being invisible to it.
ABANDONED=0
if [ -n "$INFLIGHT" ] && ! grep -qxF "$INFLIGHT" ${context.run_dir}/autodev-passed.txt 2>/dev/null; then
  ABANDONED=1
  # BUG-2981 D2: only skip the append if this ID is already recorded in
  # the unverified bucket (bare or otherwise) — the guard previously
  # asked "was this already passed?" when the correct question is "was
  # this already recorded at all?" ABANDONED stays set either way; it is
  # a verdict input independent of whether the line gets appended.
  if ! grep -qE "^$INFLIGHT([[:space:]]|$)" ${context.run_dir}/autodev-unverified.txt 2>/dev/null; then
    echo "$INFLIGHT  inflight_at_finalize" >> ${context.run_dir}/autodev-unverified.txt
  fi
fi
UNVERIFIED_IDS=$(cat ${context.run_dir}/autodev-unverified.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' | sort -u || true)
UNVERIFIED_COUNT=$(echo "$UNVERIFIED_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$UNVERIFIED_COUNT" ] && UNVERIFIED_COUNT=0
# FEAT-3573: quality-gate outcomes are ledgered in the unverified bucket (so they
# count in not_closed and feed the verdict ladder) but get their own summary
# keys and lines; the generic Unverified "re-queue to retry" hint is wrong for
# them — the issue is already `done`, so a rerun skips it as already_done and
# will not re-gate it.
QUALITY_FAILED_COUNT=$(grep -cE '[[:space:]]quality_gate_failed([[:space:]]|$)' ${context.run_dir}/autodev-unverified.txt 2>/dev/null || true)
[ -z "$QUALITY_FAILED_COUNT" ] && QUALITY_FAILED_COUNT=0
QUALITY_INFRA_COUNT=$(grep -cE '[[:space:]]quality_gate_infra([[:space:]]|$)' ${context.run_dir}/autodev-unverified.txt 2>/dev/null || true)
[ -z "$QUALITY_INFRA_COUNT" ] && QUALITY_INFRA_COUNT=0
UNVERIFIED_DISPLAY_IDS=$(echo "$UNVERIFIED_IDS" | grep -vE '[[:space:]]quality_gate_(failed|infra)([[:space:]]|$)' || true)
UNVERIFIED_DISPLAY_COUNT=$(echo "$UNVERIFIED_DISPLAY_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$UNVERIFIED_DISPLAY_COUNT" ] && UNVERIFIED_DISPLAY_COUNT=0
# "ID@<short head_sha>[ (dirty)]" per ID, read from the evidence record.
quality_list() {
  for QID in $(grep -E "[[:space:]]$1([[:space:]]|\$)" ${context.run_dir}/autodev-unverified.txt 2>/dev/null | awk '{print $1}' | sort -u); do
    python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = {}
sha = (d.get('head_sha') or '')[:8]
print(sys.argv[2] + ('@' + sha if sha else '') + (' (dirty)' if d.get('dirty') else ''))
" "$QUALITY_DIR/$QID.json" "$QID"
  done | paste -sd, -
}
QUALITY_FAILED_LIST=$(quality_list quality_gate_failed)
QUALITY_INFRA_LIST=$(quality_list quality_gate_infra)
QUALITY_GATED_COUNT=$(find "$QUALITY_DIR" -maxdepth 1 -name '*.json' 2>/dev/null | grep -c . || true)
[ -z "$QUALITY_GATED_COUNT" ] && QUALITY_GATED_COUNT=0

PASSED_LIST=$(echo "$PASSED_IDS" | tr '\n' ',' | sed 's/,$//')
SKIPPED_LIST=$(echo "$SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
INFRA_SKIPPED_LIST=$(echo "$INFRA_SKIPPED_IDS" | tr '\n' ',' | sed 's/,$//')
ALREADY_RESOLVED_LIST=$(echo "$ALREADY_RESOLVED_IDS" | tr '\n' ',' | sed 's/,$//')
BLOCKED_BY_UNMET_LIST=$(echo "$BLOCKED_BY_UNMET_IDS" | tr '\n' ',' | sed 's/,$//')
GATE_BLOCKED_LIST=$(echo "$GATE_BLOCKED_IDS" | tr '\n' ',' | sed 's/,$//')
DECISION_UNRESOLVED_LIST=$(echo "$DECISION_UNRESOLVED_IDS" | tr '\n' ',' | sed 's/,$//')
NOT_STARTED_LIST=$(echo "$NOT_STARTED_IDS" | tr '\n' ',' | sed 's/,$//')
UNVERIFIED_LIST=$(echo "$UNVERIFIED_DISPLAY_IDS" | grep -v '^[[:space:]]*$' | tr '\n' ',' | sed 's/,$//')

printf '\n=== Autodev Summary ===\n\n'
if [ "$CLOSED_CANCELLED" -gt 0 ]; then
  printf 'Passed       (%d): %s  (%d implemented, %d cancelled: %s)\n' "$PASSED_COUNT" "$${PASSED_LIST:-none}" "$CLOSED_IMPLEMENTED" "$CLOSED_CANCELLED" "$CANCELLED_LIST"
else
  printf 'Passed       (%d): %s\n' "$PASSED_COUNT" "$${PASSED_LIST:-none}"
fi
printf 'Skipped      (%d): %s\n' "$SKIPPED_COUNT" "$${SKIPPED_LIST:-none}"
if [ "$INFRA_SKIPPED_COUNT" -gt 0 ]; then
  printf 'Infra-skipped (%d): %s  (transient kill — just re-run)\n' "$INFRA_SKIPPED_COUNT" "$INFRA_SKIPPED_LIST"
fi
if [ "$ALREADY_RESOLVED_COUNT" -gt 0 ]; then
  printf 'Already-resolved (%d): %s  (pre-flight skip — no refinement attempted)\n' "$ALREADY_RESOLVED_COUNT" "$ALREADY_RESOLVED_LIST"
fi
if [ "$BLOCKED_BY_UNMET_COUNT" -gt 0 ]; then
  printf 'Blocked-by-unmet (%d): %s  (unmet blocked_by deps — resolve them, then re-run)\n' "$BLOCKED_BY_UNMET_COUNT" "$BLOCKED_BY_UNMET_LIST"
fi
if [ "$GATE_BLOCKED_COUNT" -gt 0 ]; then
  printf 'Gate-blocked (%d): %s  (prove deps with /ll:explore-api, then re-run)\n' "$GATE_BLOCKED_COUNT" "$GATE_BLOCKED_LIST"
fi
if [ "$DECISION_UNRESOLVED_COUNT" -gt 0 ]; then
  printf 'Decision-unresolved (%d): %s  (resolve with /ll:decide-issue, then re-run)\n' "$DECISION_UNRESOLVED_COUNT" "$DECISION_UNRESOLVED_LIST"
fi
SPIKE_INCONCLUSIVE_LIST=$(grep -v '^[[:space:]]*$' ${context.run_dir}/autodev-spike-inconclusive.txt 2>/dev/null | sort -u | tr '\n' ',' | sed 's/,$//' || true)
if [ -n "$SPIKE_INCONCLUSIVE_LIST" ]; then
  printf 'Spike-inconclusive (%d): %s  (fix the cause, run /ll:spike <ID> --force, then re-run)\n' "$(echo "$SPIKE_INCONCLUSIVE_LIST" | tr ',' '\n' | wc -l | tr -d ' ')" "$SPIKE_INCONCLUSIVE_LIST"
fi
PROPOSAL_UNSOUND_LIST=$(grep -v '^[[:space:]]*$' ${context.run_dir}/autodev-proposal-unsound.txt 2>/dev/null | sort -u | tr '\n' ',' | sed 's/,$//' || true)
if [ -n "$PROPOSAL_UNSOUND_LIST" ]; then
  printf 'Proposal-unsound (%d): %s  (selected proposal refuted, no alternative; revise ## Proposed Solution, then re-run)\n' "$(echo "$PROPOSAL_UNSOUND_LIST" | tr ',' '\n' | wc -l | tr -d ' ')" "$PROPOSAL_UNSOUND_LIST"
fi
PROOF_GATE_INFRA_LIST=$(grep -v '^[[:space:]]*$' ${context.run_dir}/autodev-proof-gate-infra.txt 2>/dev/null | sort -u | tr '\n' ',' | sed 's/,$//' || true)
if [ -n "$PROOF_GATE_INFRA_LIST" ]; then
  printf 'Proof-gate-infra [infra] (%d): %s  (check-gate produced no verdict before implement; retry later)\n' "$PROOF_GATE_INFRA_COUNT" "$PROOF_GATE_INFRA_LIST"
fi
if [ "$NOT_STARTED_COUNT" -gt 0 ]; then
  printf 'Not-started  (%d): %s  (never reached implementation — Phase 1 rejected)\n' "$NOT_STARTED_COUNT" "$NOT_STARTED_LIST"
fi
if [ "$QUALITY_FAILED_COUNT" -gt 0 ]; then
  printf 'Quality-failed (%d): %s  (marked done but gate failed — review these commits; rerun will not re-gate)\n' "$QUALITY_FAILED_COUNT" "$QUALITY_FAILED_LIST"
fi
if [ "$QUALITY_INFRA_COUNT" -gt 0 ]; then
  printf 'Quality-gate-infra [infra] (%d): %s  (gate crashed — re-run the oracle manually)\n' "$QUALITY_INFRA_COUNT" "$QUALITY_INFRA_LIST"
fi
if [ "$QUALITY_GATED_COUNT" -gt 0 ] && [ $((QUALITY_FAILED_COUNT + QUALITY_INFRA_COUNT)) -eq "$QUALITY_GATED_COUNT" ]; then
  printf 'Hint: every gated issue failed the quality gate — if the base branch is already red, re-run with --context quality_gate=false (auto-refine-and-implement forwards quality_gate too)\n'
fi
if [ "$UNVERIFIED_DISPLAY_COUNT" -gt 0 ]; then
  printf 'Unverified   (%d): %s  (threshold passed; implementation did not close — re-queue to retry)\n' "$UNVERIFIED_DISPLAY_COUNT" "$UNVERIFIED_LIST"
fi
# finalize_rate_limited stamps the stop reason; the queue still holds
# every issue never dequeued, so surface it rather than dropping it.
STOP_REASON=$(cat ${context.run_dir}/autodev-stop-reason 2>/dev/null | tr -d '[:space:]' || true)
[ -z "$STOP_REASON" ] && STOP_REASON=completed
PENDING_IDS=$(cat ${context.run_dir}/autodev-queue.txt 2>/dev/null \
  | grep -v '^[[:space:]]*$' || true)
PENDING_COUNT=$(echo "$PENDING_IDS" | grep -c '[^[:space:]]' || true)
[ -z "$PENDING_COUNT" ] && PENDING_COUNT=0
if [ "$STOP_REASON" != completed ]; then
  PENDING_LIST=$(echo "$PENDING_IDS" | tr '\n' ',' | sed 's/,$//')
  printf 'Stopped early: %s — pending (%d): %s  (re-run to continue)\n' "$STOP_REASON" "$PENDING_COUNT" "$${PENDING_LIST:-none}"
fi
printf '\n'

# BUG-2908: verdict reflects verified closure, not threshold-pass. A run
# only reports success/partial when at least one issue is verifiably
# implemented (ENH-3613: cancelled closures do not count, matching
# BUG-3449 in auto-refine-and-implement); anything staged-but-unverified or abandoned mid-flight makes
# it phantom regardless of legitimate skips (decomposed/gate-blocked/
# decision-unresolved/low-readiness parking is not a failure signal).
if [ "$CLOSED_IMPLEMENTED" -gt 0 ] && [ "$UNVERIFIED_COUNT" -eq 0 ] && [ "$ABANDONED" -eq 0 ]; then
  VERDICT=success
elif [ "$CLOSED_IMPLEMENTED" -gt 0 ]; then
  VERDICT=partial
elif [ "$UNVERIFIED_COUNT" -gt 0 ] || [ "$ABANDONED" -gt 0 ]; then
  VERDICT=phantom
elif [ "$NOT_STARTED_COUNT" -gt 0 ]; then
  # ENH-2989: a Phase 1 rejection is a legitimate parking outcome, not
  # an infrastructure failure — distinct from both `phantom` (a real
  # implementation failure) and `no-op` (nothing implemented,
  # including an all-cancelled run; refine/wire/confidence-check ran here
  # before the rejection).
  VERDICT=not_started
else
  VERDICT=no-op
fi
# A rate-limit stop is an interrupted run, not a phantom implementation
# failure: the in-flight issue (if any) is already counted as abandoned
# above, and the verdict names the stop so callers can retry.
if [ "$STOP_REASON" = rate_limit ]; then
  VERDICT=rate_limited
fi

printf '{"verdict":"%s","closed":%s,"not_closed":%s,"skipped":%s,"gate_blocked":%s,"decision_unresolved":%s,"not_started":%s,"inflight_unresolved":%s,"abandoned":%s,"stop_reason":"%s","pending":%s,"proof_gate_infra":%s,"closed_implemented":%s,"closed_cancelled":%s,"quality_failed":%s,"quality_gate_infra":%s}\n' \
  "$VERDICT" "$PASSED_COUNT" "$UNVERIFIED_COUNT" "$SKIPPED_COUNT" "$GATE_BLOCKED_COUNT" "$DECISION_UNRESOLVED_COUNT" "$NOT_STARTED_COUNT" "$ABANDONED" "$ABANDONED" "$STOP_REASON" "$PENDING_COUNT" "$PROOF_GATE_INFRA_COUNT" "$CLOSED_IMPLEMENTED" "$CLOSED_CANCELLED" "$QUALITY_FAILED_COUNT" "$QUALITY_INFRA_COUNT" \
  > ${context.run_dir}/summary.json

# BUG-2908: route the FSM terminal on verified closure, not "reached the
# end" — mirrors BUG-2636's fix to auto-refine-and-implement.yaml's
# finalize. Only `phantom` diverts to `failed`; success/partial/no-op
# (a genuinely empty, fully-parked or all-cancelled backlog) still render `done`.
case "$VERDICT" in
  phantom) exit 1 ;;
  *) exit 0 ;;
esac
