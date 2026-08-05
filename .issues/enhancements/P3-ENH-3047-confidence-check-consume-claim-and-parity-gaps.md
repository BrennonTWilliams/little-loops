---
id: ENH-3047
title: 'confidence-check: consume unverified-claim and missing-parity gaps as Criterion 4 deductions'
type: ENH
priority: P3
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: "2026-08-04T20:47:11Z"
blocked_by:
- FEAT-3048
relates_to:
- ENH-3045
- ENH-2946
- FEAT-2942
labels:
- skills
- issues
- gates
decision_needed: true
---

# ENH-3047: Feed claim/parity gaps into confidence-check scoring

## Summary

`/ll:confidence-check` scored FEAT-2942 at **93 readiness / 76 outcome** while the issue
contained a false claim about its own core write path, a silent behavior regression, two
internal contradictions, and three undefined terms. Wire the FEAT-3048 claim gaps and the
ENH-3045 parity gap into the existing Phase 1.6 pre-fetch as explicit Criterion 4 deductions, so
the score reflects what the new gates find.

## Current Behavior

Criterion 4 ("Issue Well-Specified") checks for the **presence** of sections — acceptance
criteria, specific files to modify, scope boundaries, actionable steps
(`skills/confidence-check/SKILL.md` Phase 2). FEAT-2942 has all four, so it scores well
regardless of whether those sections are *correct*, *consistent*, or *sufficient*.

Criterion 3's detection bullet 5 is the one instruction that reaches correctness — *"Verify
claims in the issue against actual code"* — but it is the last sub-bullet of a type-specific
criterion with no CLI behind it, and it is the only prose-only gate in a skill where every other
check has one. Phase 1.6 already pre-fetches the Program Design gate, so the mechanism and the
slot both exist; there is simply nothing to fetch for claims or parity yet.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- Phase 1.6's existing pre-fetch (`skills/confidence-check/SKILL.md`, `### Phase 1.6: Pre-Fetch Program Design Gate (ENH-2852)`, lines 132-150) is the concrete template this issue extends — it populates two shell variables from `ll-issues format-check {{issue_id}} --format json`: `PD_GAP` (raw reason string, `json.load(sys.stdin).get('program_design_nonspecific', [])` joined with `; `) and `PD_FAIL` (a separate pass/fail verdict from the dedicated `ll-issues check-design {{issue_id}}` exit code, not re-derived from JSON in the skill).
- The target keys this issue plans to consume — `stale_symbol_ref`, `stale_cli_flag` (FEAT-3048), `missing_behavior_parity` (ENH-3045) — do not exist anywhere in the current schema. `FormatGaps` (`scripts/little_loops/issue_parser.py:237`) currently has 15 `list[str]` fields (`missing`, `renamed`, `empty`, `boilerplate`, `malformed_id`, `prose_dep_drift`, `stale_prose_dep`, `program_design_nonspecific`, `deprecated_key`, `multi_frontmatter`, `testable`, `stale_file_ref`, `unmarked_superseded_directive`, `duplicate_findings_block`, `ambiguous_file_ref`) — none of the three target keys are present, confirmed by grepping the whole repo (hits only inside `.issues/*.md` proposing them). `docs/reference/CLI.md:1942`'s documented `format-check --format json` schema example likewise has no claim/parity keys.
- No precedent currently exists in the codebase for a pre-fetch step that defensively reads a JSON key its producing CLI does not yet emit at all — the one existing precedent (Program Design gate) is for a key that always exists in the schema but is empty/absent-content depending on project state (`program_design_gate_active()`, `scripts/little_loops/issues/program_design.py:415`), not a key that is schema-absent because its producing feature hasn't landed. This is a materially different degradation case than the "fails open when gate unarmed" pattern this issue's own text cites as precedent.

## Expected Behavior

Phase 1.6 additionally pre-fetches, via `ll-issues format-check --format json`:

- unverified-claim count (`stale_symbol_ref` + `stale_cli_flag` from FEAT-3048)
- missing behavior parity (`missing_behavior_parity` from ENH-3045, if that gap kind lands)

`skills/confidence-check/rubric.md` gains explicit Criterion 4 deductions keyed to those counts,
and the Phase 3 recommendation treats a nonzero unverified-claim count as a readiness blocker
rather than a soft signal — a false claim about the implementation surface is not a "well
specified" issue at any score.

## Motivation

Without this, FEAT-3048 and ENH-3045 improve the *gates* while the *score* stays uncalibrated —
and the score is what `/ll:go-no-go`, `ll-auto`, and sprint selection actually consume. An issue
that fails a claim check should not read as 93% ready.

## Proposed Solution

Follow the existing Phase 1.6 pattern: one `format-check --format json` call, parsed into
counts, referenced by the rubric tables. `ENH-2946` already established that confidence-check
reads `format-check` output, so this is an extension of a live integration rather than a new
coupling.

Keep the deduction table in `rubric.md` (the skill already delegates all scoring tables there),
not in `SKILL.md` — that file is 405 lines against the 500-line cap.

**Dependency:** hard-blocked on FEAT-3048, which produces the gap kinds this issue consumes;
without it there is nothing to read. Soft on ENH-3045 — the parity deduction is additive and
this can ship with claim deductions alone if parity detection lands later or not at all.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

**Option A**: Add deduction rows directly into the existing `### Criterion 4: Issue Well-Specified` `Finding | Score` table in `rubric.md` (absolute point value per row, same two-column shape as today). Mirrors the majority precedent — 5 of 6 rubric.md criterion tables use this shape.

**Option B**: Add a separate modifier table (`Target Status | Score Modifier | Action`) applied "on top of" Criterion 4, mirroring the one existing gate-driven-modifier precedent: the "Learning Test Status Scoring (Criterion 1 Modifier)" table (`rubric.md` lines 161-172).

**Recommended**: Option B — the two new gap kinds are count/presence-based hard signals (a claim either references current code or it doesn't; a parity gap either exists or it doesn't), structurally closer to the Learning Test target's `missing`/`refuted` states than to Criterion 4's existing qualitative "how well specified is this issue" prose conditions. Folding counts into the absolute Finding/Score table would require inventing prose bands ("mostly clean but 1 stale ref = 15") that don't reflect the actual signal shape, whereas a modifier table keeps the count-driven deduction explicit and composable with the Phase 3 hard-override paragraph pattern already established for Program Design and Learning Test gates.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 1.6 pre-fetch, Phase 3 recommendation
- `skills/confidence-check/rubric.md` — Criterion 4 deduction table
- `scripts/tests/` — scoring assertions for the deduction path

### Similar Patterns
- `ENH-2852` / `ENH-2967` — Program Design gate pre-fetch and its `check-design` CLI owner;
  the exact shape to copy
- `ENH-2946` — confidence-check already consuming `format-check` output

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Conventions in Force

- Rubric deduction tables are one `###`-level table per criterion/gate, `Finding | Score` (absolute point value), not a delta — evidence: 5 of 6 tables in `skills/confidence-check/rubric.md` "Phase 2 — Readiness Scoring Tables" (lines 176-252), including the existing `### Criterion 4: Issue Well-Specified` table this issue targets (lines 236-243).
- One documented exception exists: gate-driven modifiers use a different `Target Status | Score Modifier | Action` shape, signed delta applied "on top of" the base criterion rather than folded into its Finding/Score rows — evidence: "Learning Test Status Scoring (Criterion 1 Modifier)" table, `rubric.md` lines 161-172.
- Phase 3 hard overrides are named bolded paragraphs ("**X Hard Override**") placed before score summation, gated on a Phase-1.6-set variable being non-empty/non-zero, forcing `STOP — ADDRESS GAPS` "regardless of aggregate score" — evidence: Learning Test Hard Override and Program Design Hard Override, `skills/confidence-check/SKILL.md` "Phase 3: Score and Recommend" lines 300-306. This is the pattern the issue's Expected Behavior cites for "nonzero unverified-claim count as a readiness blocker."
- `format-check --format json` keys are referenced two ways in this codebase, both established: inline bash/python extraction into shell variables (confidence-check's Phase 1.6), and pure markdown prose naming the key plus its non-empty/nonzero condition with no code shown (`commands/refine-issue.md` Step 6.7, lines 781-831, for `prose_dep_drift`/`stale_prose_dep`/`program_design_nonspecific`/`superseded_marker_count`/`duplicate_findings_block`).
- `check_design.py`'s `cmd_check_design` is the CLI-owner precedent named in this issue's "Similar Patterns" — its docstring states it is the "single CLI owner of the `design_gate_failed()` predicate, replacing the three independent inline `python3 -c "..."` blocks in autodev.yaml that each re-derived the same boolean from raw `format-check --format json` output," and that it "fails open (exit 0) on projects that haven't armed the ... gate, mirroring `check_format_gaps()`'s existing fail-open behavior."

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Types

- `FormatGaps` (`scripts/little_loops/issue_parser.py:237`) — the dataclass all `format-check` JSON/text consumers key off; currently 15 `list[str]` gap-kind fields, each mirrored in `has_gaps` (lines 269-275) and `to_dict()` (lines 281-295). Adding claim/parity consumption here presupposes FEAT-3048/ENH-3045 add matching `list[str]` fields (`stale_symbol_ref`, `stale_cli_flag`, `missing_behavior_parity`) to this same dataclass — none exist today.
- `PD_GAP: str` / `PD_FAIL: str` — the two shell-variable shapes Phase 1.6 currently populates from `format-check`/`check-design` output (`skills/confidence-check/SKILL.md:132-150`): a joined reason-string (`PD_GAP`, from a `list[str]` JSON key) and a separate pass/fail verdict (`PD_FAIL`, `""` or `"yes"`, from a dedicated CLI's exit code rather than re-derived from JSON).

### Signatures

- `program_design_gate_active(issue_path: Path, content: str) -> bool`

  `scripts/little_loops/issues/program_design.py:415` — the activation-gating pattern (unstamped project / grandfathered / `*_not_applicable: true` frontmatter all return `False`) that the Program Design gate uses to fail open; a parity/claim equivalent, if the CLI layer needs one, would follow this same shape.
- `cmd_format_check() -> None`

  `scripts/little_loops/cli/issues/format_check.py:165` — the existing JSON-serialization entry point (`gaps.to_dict()` via `check_format_gaps()`) that would need the new `FormatGaps` fields threaded through before Phase 1.6 has anything new to parse.
- `cmd_check_design` — sole CLI owner of the `design_gate_failed()` boolean predicate (`scripts/little_loops/cli/issues/check_design.py`); the issue's own Expected Behavior only calls for parsing `format-check --format json` directly (no new CLI owner named), so whether a parallel `check-claims`-style CLI is warranted for the claim/parity boolean, versus deriving it inline the way `PD_FAIL` is today, is unresolved by research and is an implementation decision.

### Call Path

`skills/confidence-check/SKILL.md` Phase 1.6 bash block -> `ll-issues format-check --format json` -> `cmd_format_check()` (`format_check.py:165`) -> `check_format_gaps()` (`issue_parser.py`) -> `FormatGaps.to_dict()` (`issue_parser.py:281`) -> parsed via inline `python -c` in the SKILL.md bash block -> stored in a shell variable -> read by `rubric.md`'s Criterion 4 table and/or `SKILL.md` Phase 3's hard-override paragraph.

## Implementation Steps

1. Extend Phase 1.6 pre-fetch to parse the new gap kinds.
2. Add Criterion 4 deduction rows to `rubric.md`.
3. Make a nonzero unverified-claim count a Phase 3 readiness blocker.
4. Validate against FEAT-2942: score drops materially from 93.

## Impact

- **Priority**: P3 — depends on FEAT-3048; without it, no signal to consume
- **Effort**: Low — prompt/rubric wiring on an existing pre-fetch
- **Risk**: Low — scoring change only; may re-score existing issues downward (intended)

## Related Key Documentation

- `.claude/CLAUDE.md` — confidence gate thresholds in `.ll/ll-config.json`
  (`commands.confidence_gate`: readiness 85, outcome 65)
- `docs/reference/COMMANDS.md` — `/ll:confidence-check`

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-05T01:31:24 - `42ca0c4a-7282-4fbe-9b00-3b9e16ffcd31.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:09 - `b9710cb8-1d2b-4d04-8cf1-ad93d3cfccb7.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:28 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
