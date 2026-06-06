---
id: FEAT-1925
title: 'll-logs-telemetry-digest: FSM loop wrapping EPIC-1918 subcommands'
type: FEAT
priority: P3
status: done
captured_at: '2026-06-04T03:04:39Z'
completed_at: '2026-06-06T05:42:20Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1918
relates_to:
- EPIC-1918
- ENH-1919
- ENH-1921
- ENH-1922
- ENH-1923
labels:
- captured
- ll-logs
- telemetry
- loop
- fsm
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1925: ll-logs-telemetry-digest — FSM loop wrapping EPIC-1918 subcommands

## Summary

Add a project-level FSM loop at `.loops/ll-logs-telemetry-digest.yaml` that
orchestrates all EPIC-1918 telemetry subcommands into a single periodic digest
run. The loop refreshes the log corpus, conditionally invokes each new
`ll-logs` subcommand as it becomes available (capability-detected via
`--help` guard), triages findings into issues, writes a structured digest, and
commits only when new issues were filed.

## Current Behavior

The EPIC-1918 telemetry subcommands (`ll-logs stats`, `ll-logs scan-failures`, `ll-logs sequences`, `ll-logs dead-skills`) must be run manually, individually, and in the correct order. There is no automated harness to compose them, correlate findings across subcommands, or produce a consolidated digest. No loop exists at `.loops/ll-logs-telemetry-digest.yaml`.

## Expected Behavior

Running `ll-loop run ll-logs-telemetry-digest` refreshes the log corpus, then sequentially invokes each EPIC-1918 subcommand using capability detection (`--help` guard) to skip those not yet implemented. Findings from `scan-failures` and `dead-skills` are triaged into issues (capped at 3 and 2 per run respectively). A structured digest is written to `${run_dir}/digest.md` and new issue files are committed only when created — all without manual intervention.

## Motivation

EPIC-1918 produces six independent subcommands that each surface a different
kind of telemetry signal. Without a harness that composes them, each must be
run manually and in the right order, and findings from one (e.g. `scan-failures`)
are never correlated with findings from another (e.g. dead-skill detection).
The loop acts as the single entrypoint: run it periodically and it surfaces
everything the corpus currently supports — growing deeper as each child issue
lands, with no loop edits required.

## Use Case

A developer runs `ll-loop run ll-logs-telemetry-digest` after a week of
interactive Claude Code sessions. The loop refreshes the log corpus, runs
`ll-logs stats` and `ll-logs scan-failures` (both shipped), skips
`ll-logs sequences` (ENH-1919 not yet done), finds 2 unreported tool failures,
triages them into bug issues, writes `.loops/runs/<run-id>/digest.md` with a
summary, and commits the new issue files — all without manual intervention.

## Implementation Steps

1. Create `.loops/ll-logs-telemetry-digest.yaml` with the FSM described below.
2. The loop is project-level (resolved by `ll-loop run` before checking builtins).
3. No Python changes required — loop YAML only.

### FSM States

```
refresh_corpus
  → run_stats          (ll-logs stats — ENH-1921; skip if unavailable)
  → scan_failures      (ll-logs scan-failures — ENH-1922; skip if unavailable)
    ├─[failures found]─► triage_failures ──┐
    └─[none/skip]──────────────────────────┤
                                           ▼
                                     run_sequences  (ENH-1919; skip if unavailable)
                                           ▼
                                   check_dead_skills (ENH-1923; skip if unavailable)
                                     ├─[dead found]─► file_dead_skill_issues ──┐
                                     └─[none/skip]────────────────────────────┤
                                                                               ▼
                                                                     synthesize_digest
                                                                           ▼
                                                                   commit_if_needed
                                                                     ├─► commit
                                                                     └─► done
```

### Key Design Decisions

- **Capability detection**: each subcommand gate runs `ll-logs <sub> --help >/dev/null 2>&1`; if the subcommand doesn't exist yet, the state emits a `*_UNAVAILABLE` sentinel and passes through.
- **Non-LLM routing only**: all FSM branching uses `output_contains` sentinels (`NO_FAILURES`, `NO_DEAD_SKILLS`, `REFRESHED`, `DIGEST_WRITTEN`, `NO_NEW_ISSUES`) — no LLM self-grading for routing decisions.
- **LLM states are triage-only**: `triage_failures` and `file_dead_skill_issues` cap new issues at 3 and 2 per run respectively to prevent backlog flooding.
- **Run-dir isolation (MR-3)**: all intermediate artifacts (`stats.txt`, `failures.json`, `sequences.txt`, `dead-skills.json`, `digest.md`) are written under `${context.run_dir}/`.
- **Commit gate**: `commit_if_needed` uses `git status --porcelain .issues/` — commits only when the filesystem confirms new files exist.
- **Not a meta-loop**: creates `.issues/` files, not harness artifacts; MR-1/MR-2 rules do not apply.

### Full YAML

```yaml
name: ll-logs-telemetry-digest
category: telemetry
description: |
  One-pass telemetry digest: refresh the ll-logs corpus, run all available
  EPIC-1918 analysis subcommands (stats, sequences, scan-failures,
  dead-skill detection), triage findings into issues, and write a digest.
  Subcommands not yet implemented are skipped gracefully via capability
  detection — the loop gains depth as EPIC-1918 children land.
initial: refresh_corpus
on_handoff: spawn

states:
  refresh_corpus:
    action: |
      ll-logs discover --quiet 2>/dev/null || true
      ll-logs extract --quiet 2>/dev/null && echo "REFRESHED" || echo "REFRESH_FAILED"
    action_type: shell
    evaluate:
      type: output_contains
      pattern: "REFRESHED"
    on_yes: run_stats
    on_no: done
    on_error: done

  run_stats:
    action: |
      OUT="${context.run_dir}/stats.txt"
      if ll-logs stats --help >/dev/null 2>&1; then
        ll-logs stats > "$OUT" 2>&1 && echo "STATS_OK" || echo "STATS_ERR"
      else
        echo "STATS_UNAVAILABLE"
      fi
    action_type: shell
    capture: stats_check
    next: scan_failures

  scan_failures:
    action: |
      OUT="${context.run_dir}/failures.json"
      if ll-logs scan-failures --help >/dev/null 2>&1; then
        ll-logs scan-failures --json > "$OUT" 2>&1
        COUNT=$(python3 -c "
      import json
      try:
          d = json.load(open('$OUT'))
          items = d.get('failures', d) if isinstance(d, dict) else d
          print(len(items) if isinstance(items, list) else 0)
      except Exception:
          print(0)
      " 2>/dev/null || echo 0)
        [ "$COUNT" -eq 0 ] && echo "NO_FAILURES" || echo "FAILURES_FOUND:$COUNT"
      else
        echo "NO_FAILURES"
      fi
    action_type: shell
    capture: failures_check
    evaluate:
      type: output_contains
      source: "${captured.failures_check.output}"
      pattern: "NO_FAILURES"
    on_yes: run_sequences
    on_no: triage_failures
    on_error: run_sequences

  triage_failures:
    action_type: prompt
    timeout: 600
    action: |
      ll-logs scan-failures found failed ll-* tool invocations in interactive
      sessions. The JSON report is at ${context.run_dir}/failures.json.

      For each distinct failure pattern:
      1. Run `ll-issues list --filter=open --json` to check for existing coverage
      2. If not already tracked, run `/ll:capture-issue` with the failure context
      3. Skip one-off environment failures (missing auth, absent env vars, typos)
      4. Capture at most 3 net-new issues to avoid backlog flooding

      Print "TRIAGE_DONE" when finished.
    capture: triage_status
    next: run_sequences

  run_sequences:
    action: |
      OUT="${context.run_dir}/sequences.txt"
      if ll-logs sequences --help >/dev/null 2>&1; then
        ll-logs sequences --top 20 --min-count 3 > "$OUT" 2>&1 \
          && echo "SEQUENCES_OK" || echo "SEQUENCES_ERR"
      else
        echo "SEQUENCES_UNAVAILABLE"
      fi
    action_type: shell
    capture: sequences_check
    next: check_dead_skills

  check_dead_skills:
    action: |
      OUT="${context.run_dir}/dead-skills.json"
      if ll-logs dead-skills --help >/dev/null 2>&1; then
        ll-logs dead-skills --json > "$OUT" 2>&1
        COUNT=$(python3 -c "
      import json
      try:
          d = json.load(open('$OUT'))
          items = d.get('dead', d) if isinstance(d, dict) else d
          print(len(items) if isinstance(items, list) else 0)
      except Exception:
          print(0)
      " 2>/dev/null || echo 0)
        [ "$COUNT" -eq 0 ] && echo "NO_DEAD_SKILLS" || echo "DEAD_SKILLS_FOUND:$COUNT"
      else
        echo "NO_DEAD_SKILLS"
      fi
    action_type: shell
    capture: dead_check
    evaluate:
      type: output_contains
      source: "${captured.dead_check.output}"
      pattern: "NO_DEAD_SKILLS"
    on_yes: synthesize_digest
    on_no: file_dead_skill_issues
    on_error: synthesize_digest

  file_dead_skill_issues:
    action_type: prompt
    timeout: 300
    action: |
      Dead-skill detection found skills with zero invocations in the log corpus.
      The list is at ${context.run_dir}/dead-skills.json.

      For each never-invoked skill:
      1. Check if it is an intentional one-shot (migration, bootstrap) — skip those
      2. If it appears genuinely undiscoverable or obsolete, run `/ll:capture-issue`
         to propose improving its trigger documentation or deprecating it
      3. Capture at most 2 issues per run

      Print "DEAD_TRIAGE_DONE" when finished.
    capture: dead_triage_status
    next: synthesize_digest

  synthesize_digest:
    action_type: prompt
    timeout: 300
    action: |
      Synthesize a telemetry digest from this run. Read whichever of these
      artifacts exist under ${context.run_dir}/:
        stats.txt        → skill frequency / quality summary (ENH-1921)
        sequences.txt    → top tool-chain n-grams (ENH-1919)
        failures.json    → failed ll-* calls found (ENH-1922)
        dead-skills.json → never-invoked skills (ENH-1923)

      Write a concise Markdown file to ${context.run_dir}/digest.md with:

      ## Run Summary
      - Which subcommands ran vs. were skipped (not yet implemented)
      - Key numbers: failure count, dead-skill count, top sequence if available

      ## Issues Created This Run
      - List any /ll:capture-issue calls made during triage steps

      ## Remaining EPIC-1918 Coverage
      - Which child issues (ENH-1919/1920/1921/1922/1923/1924) are still open,
        limiting what this loop can observe on subsequent runs

      Print "DIGEST_WRITTEN" when the file is saved.
    capture: digest_status
    evaluate:
      type: output_contains
      source: "${captured.digest_status.output}"
      pattern: "DIGEST_WRITTEN"
    on_yes: commit_if_needed
    on_no: done
    on_error: done

  commit_if_needed:
    action: |
      NEW=$(git status --porcelain .issues/ 2>/dev/null | grep -c '^?' || echo 0)
      [ "$NEW" -eq 0 ] && echo "NO_NEW_ISSUES" || echo "NEW_ISSUES:$NEW"
    action_type: shell
    evaluate:
      type: output_contains
      pattern: "NO_NEW_ISSUES"
    on_yes: done
    on_no: commit
    on_error: done

  commit:
    action_type: prompt
    timeout: 120
    action: |
      New issue files were created during this telemetry digest run.
      Run `/ll:commit` with a message like:
      "chore(telemetry): ll-logs digest — auto-filed bugs and dead-skill issues"
    next: done

  done:
    terminal: true

max_iterations: 2
timeout: 3600
```

## Impact

- **Priority**: P3 — automation convenience; depends on EPIC-1918 children shipping before the loop gains full depth
- **Effort**: Small — pure YAML loop, no Python changes required
- **Risk**: Low — isolated YAML artifact; touches no existing code or data paths
- **Breaking Change**: No

## API / Interface

- **Invocation**: `ll-loop run ll-logs-telemetry-digest`
- **Location**: `.loops/ll-logs-telemetry-digest.yaml` (project-level; takes precedence over builtins)
- **Outputs**: `${run_dir}/digest.md`, optionally new `.issues/` files staged + committed
- **No new Python required**: pure YAML loop definition

## Acceptance Criteria

- [x] `.loops/ll-logs-telemetry-digest.yaml` exists and passes `ll-loop validate`
- [x] Loop runs to `done` terminal state with only `discover` + `extract` available (all capability gates NOOP gracefully)
- [x] When ENH-1922 (`scan-failures`) ships: `scan_failures` state runs and findings route to `triage_failures`
- [x] When ENH-1923 (`dead-skills`) ships: `check_dead_skills` state runs and non-empty results route to `file_dead_skill_issues`
- [x] `commit_if_needed` never commits when no new `.issues/` files were created
- [x] All artifacts written under `${context.run_dir}/`, not `.loops/tmp/`



---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-1920 (eval-export) and ENH-1924 (diff) are intentionally excluded from this loop's orchestration. They are on-demand developer tools triggered by specific workflows (replay testing of prompt changes, session behavioral regression comparison) — not periodic batch-telemetry signals. The loop covers the four batch-telemetry subcommands: `stats` (ENH-1921), `scan-failures` (ENH-1922), `sequences` (ENH-1919), and dead-skill detection (ENH-1923).


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Resolution

Created `.loops/ll-logs-telemetry-digest.yaml` — pure YAML FSM loop with 11 states, non-LLM routing throughout, run-dir isolation for all artifacts, and capability-detection gates for all four EPIC-1918 subcommands. Passes `ll-loop validate` cleanly.

## Session Log
- `/ll:ready-issue` - 2026-06-06T05:40:32 - `ab6f39bb-9672-4dfb-b684-97d4771b34ef.jsonl`
- `/ll:confidence-check` - 2026-06-06T00:36:00Z - `8107f14f-4f99-41ee-b217-9335aae5bdbb.jsonl`
- `/ll:format-issue` - 2026-06-06T05:22:27 - `06e1fd7f-9e9e-4f4e-85e5-c6c182434078.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T05:19:22 - `8b34820d-ae67-4c39-b57a-ea2b07021501.jsonl`
- `/ll:capture-issue` - 2026-06-04T03:04:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/551af427-6235-4491-aaed-0867dd5fc912.jsonl`
