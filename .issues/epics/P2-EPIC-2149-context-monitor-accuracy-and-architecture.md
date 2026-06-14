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

## Suggested Implementation Order

1. **ENH-2148** first — adds the `Status` hook handler as a new code path
   without touching the existing PostToolUse logic; can be validated
   independently.
2. **BUG-2145 + BUG-2146** together — the stale-baseline fix (2145) and the
   double-count fix (2146) must ship together since 2146's overcounting
   currently partially compensates for 2145's undercounting.
3. Deprecate PostToolUse JSONL path for Claude Code host; keep as fallback
   for OpenCode/Codex (see ENH-2148 migration notes).

## Potential Follow-On Work (not yet filed)

- Model-specific heuristic weights: Opus 4.8 tokenizer produces ~1.5× more
  tokens than Sonnet 4.6; `TOOL_CALL_BASE` and `READ_PER_LINE` weights should
  scale with `detected_model`.
- Increase `tail -50` depth in `get_transcript_baseline()` to `tail -200` —
  with 2–3 JSONL entries per API call, `-50` only covers ~17 turns.
- Prometheus/OTel export bridge: research identified this as a greenfield gap
  (stdin JSON → gauge values → Prometheus HTTP endpoint → Grafana).

## Success Criteria

- On a 100-turn session, `context-monitor.sh` reports usage within ±5% of the
  `Status` hook's `used_percentage`.
- BUG-865, BUG-924, and BUG-869 resolved as a side-effect of ENH-2148.
- No regression in handoff trigger behavior on short sessions or non-Claude-Code
  hosts.
