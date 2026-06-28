---
id: EPIC-2149
type: EPIC
title: "Context monitor accuracy and architecture improvements"
priority: P2
status: open
discovered_date: 2026-06-13
discovered_by: research-review
labels:
  - context-monitor
  - accuracy
  - hooks
  - architecture
---

# EPIC-2149: Context monitor accuracy and architecture improvements

## Goal

Fix systematic inaccuracies in `context-monitor.sh` and migrate to Claude
Code's authoritative `Status` hook payload as the primary data source,
eliminating JSONL-parsing overhead and stale-baseline drift.

## Background

Reviewed `docs/research/claude-code-token-estimation-python.md` (deep-research
report, 3 iterations, 102 sources) against our actual JSONL transcripts.
Direct inspection of real session files confirmed two bugs and one architectural
opportunity the research flagged. The research's "hidden 45K-50K token gap"
warning does NOT apply to us (we already sum all four usage fields), and the
JSONL output token undercount bug (#22671) does NOT affect Claude Code's
transcript format (we see real values, not placeholder ~9s).

## Sub-Issues

| ID | Type | Title | Priority |
|---|---|---|---|
| BUG-2145 | BUG | Transcript baseline never refreshed across turns | P2 |
| BUG-2146 | BUG | SYSTEM_PROMPT_BASELINE double-counts when transcript available | P3 |
| ENH-2148 | ENH | Use Status hook `used_percentage` as zero-cost authoritative source | P2 |

## Implementation Status

1. ~~**BUG-2145** — Transcript baseline never refreshed across turns~~ **done**
2. ~~**BUG-2146** — SYSTEM_PROMPT_BASELINE double-counts when transcript available~~ **done**
3. **ENH-2148** — Use Status hook `used_percentage` as zero-cost authoritative source — **deferred**
4. Deprecate PostToolUse JSONL path for Claude Code host; keep as fallback
   for OpenCode/Codex (depends on ENH-2148 — blocked while deferred).

## Potential Follow-On Work (not yet filed)

- Model-specific heuristic weights: Opus 4.8 tokenizer produces ~1.5× more
  tokens than Sonnet 4.6; `TOOL_CALL_BASE` and `READ_PER_LINE` weights should
  scale with `detected_model`.
- Increase `tail -50` depth in `get_transcript_baseline()` to `tail -200` —
  with 2–3 JSONL entries per API call, `-50` only covers ~17 turns.
- Prometheus/OTel export bridge: research identified this as a greenfield gap
  (stdin JSON → gauge values → Prometheus HTTP endpoint → Grafana).

## Verification Notes (2026-06-17)

- BUG-2145 (mtime turn-boundary refresh) and BUG-2146 (double-count guard) are both `done` — fixes visible in `context-monitor.sh` lines 281-290 and 316-320. The epic body's Implementation Order section does not reflect this progress.
- ENH-2148 (Status hook `used_percentage`) is `deferred` — epic still references it as a pending deliverable.
- Update the Implementation Order section to mark BUG-2145/2146 complete and ENH-2148 deferred before resuming.

2026-06-19 (NEEDS_UPDATE): Implementation Status section is accurate (BUG-2145/2146 done, ENH-2148 deferred). Additionally, the Success Criteria section still reads "BUG-865, BUG-924, and BUG-869 resolved as a side-effect of ENH-2148" — those bugs are now done via independent resolutions, not via the still-deferred ENH-2148. Remove or update the side-effect claim in Success Criteria.

- **2026-06-26** (/ll:verify-issues): Decoupled the Success Criteria bullet —
  BUG-865/BUG-924/BUG-869 are all independently `done`, so the criterion no
  longer ties their resolution to the still-`deferred` ENH-2148. Implementation
  Status left unchanged (accurate).

## Session Log
- `/ll:verify-issues` - 2026-06-20T00:34:45 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`

## Children

- **ENH-2341** — Add Rubric-Gated Compaction Timing to pre_compact Hook

## Success Criteria

- On a 100-turn session, `context-monitor.sh` reports usage within ±5% of the
  `Status` hook's `used_percentage`.
- BUG-865, BUG-924, and BUG-869 resolved independently (all `done` via their own
  fixes — not as a side-effect of ENH-2148, which remains `deferred`).
- No regression in handoff trigger behavior on short sessions or non-Claude-Code
  hosts.
