---
id: ENH-2356
priority: P4
type: ENH
status: open
discovered_date: 2026-06-27
discovered_by: audit-loop-run
confidence_score: 80
decision_needed: false
---

# ENH-2356: brainstorm saturation/novelty early-stop gate is inert in practice

## Summary

In the `brainstorm` built-in loop, the saturation-based early-stop convergence
path is effectively dead: the difflib novelty dedup never flags duplicates, so
the saturation counter never increments, so `saturation_gate` always routes
"continue." Termination comes solely from exhausting the finite lens queue. The
`max_saturation` contract is a safety net that never engages.

## Current Behavior

The `brainstorm` built-in loop's saturation-based early-stop path never engages.
`difflib.SequenceMatcher.ratio()` at threshold `0.80` rarely flags differently-worded
one-sentence brainstorm ideas as duplicates, so `saturation.txt` stays at `0`
throughout every run. The `saturation_gate` evaluator (`output_numeric`,
`lt ${context.max_saturation}`) always reads `0 < 2 → yes → pop_lens`. The loop
terminates only when the lens queue is exhausted, not when the saturation ceiling
is reached. The `novelty_threshold` and `max_saturation` config knobs have no
observable effect on run behavior.

## Expected Behavior

Either:
- **(a) Knobs engage:** `novelty_threshold` and `max_saturation` actively influence
  convergence — paraphrase-level duplicates register as non-novel, the saturation
  counter increments, and the early-stop fires before the lens queue drains, OR
- **(b) Contract is honest:** The documented contract explicitly states that
  lens-exhaustion is the sole convergence mechanism and `novelty_threshold` /
  `max_saturation` are labeled as safety-net-only parameters (or removed from the
  advertised config surface to avoid implying they tune output).

## Motivation

Audited via `/ll:audit-loop-run brainstorm` on run `2026-06-27T214631` (verdict:
`met` — the run was otherwise healthy). Evidence from that run:

- 9 lenses × `ideas_per_round=5` = **45 ideas**, and difflib dedup
  (`novelty_threshold=0.80`) removed **0 of 45**.
- `saturation.txt` stayed at `0` for the entire run (`count = 0 if novel else
  count + 1`, and every round had ≥1 "novel" idea).
- `saturation_gate` (`output_numeric`, `lt ${context.max_saturation}`) therefore
  evaluated `0 < 2 → yes → pop_lens` on every iteration. The loop only stopped
  because `pop_lens` drained the lens queue (`on_no → cluster`).

Root cause: a `0.80` difflib `SequenceMatcher.ratio()` on differently-worded
one-sentence ideas almost never reaches threshold, so the dedup pass admits
nearly everything as "novel." This makes the saturation early-stop and the
configured `max_saturation` contract decorative — convergence relies entirely on
the finite lens list.

This is not a correctness bug (finite lenses guarantee termination), but it means
two configured knobs (`novelty_threshold`, `max_saturation`) do not influence
behavior, which is misleading to anyone tuning the loop.

Distinct from ENH-2251 (done), which added `saturation_gate → on_error: cluster`
resilience routing — that fixed the error path, not the inert-gate behavior.

## Proposed Solution

One or more of:

1. Lower the default `novelty_threshold` (e.g. to ~0.55) so paraphrase-level
   duplicates actually register and saturation can build.

> **Selected:** Option 1 — lower `novelty_threshold` to 0.55 — activates the inert gate with a single constant change; Option 3 docs update should be bundled during implementation.

2. Wire the configured `novelty_backend` to a semantic comparator (embeddings)
   so dedup measures meaning rather than string overlap, letting the
   `max_saturation` early-stop engage on genuinely repeated ideas.
3. If lens-exhaustion is intended as the sole convergence mechanism, document
   `max_saturation` as a pure safety net and consider removing the
   `novelty_threshold`/`max_saturation` knobs from the advertised contract to
   avoid implying they tune output.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-27.

**Selected**: Option 1 — Lower `novelty_threshold` to 0.55

**Reasoning**: Option 1 directly resolves the behavioral inertness by making the configured knobs functional — a single constant change (`"0.80"` → `"0.55"`) with existing test infrastructure (`TestBrainstormDedup`, line 271) to validate it. Option 3 (docs-only) would document the inertness as acceptable rather than fixing it, which is the wrong choice for an ENH issue at minimal effort cost. Options 1 and 3 tied at 11/12; judgment favors behavioral fix over honest-but-inert documentation.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (lower threshold) | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option 2 (embeddings) | 1/3 | 0/3 | 1/3 | 1/3 | 3/12 |
| Option 3 (docs only) | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |

**Key evidence**:
- Option 1: `brainstorm.yaml` line 27 is a single constant in the `context:` block; `TestBrainstormDedup` (line 271) already exercises dedup logic; issue rates risk "Low" with no API surface change
- Option 2: No existing embedding infrastructure; out of scope per Scope Boundaries
- Option 3: Docs-only; does not fix the behavioral inertness; appropriate as a complementary step during Option 1 implementation

## Success Metrics

- [ ] A brainstorm run over a brief with overlapping idea space records ≥1
      duplicate removed in `ideas.jsonl` (dedup demonstrably fires), OR
- [ ] The loop's documented contract accurately reflects which knobs affect
      convergence.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

**Option 1 (lower threshold):**
- `scripts/little_loops/loops/brainstorm.yaml` — change `novelty_threshold: "0.80"` → `"0.55"` in the `context:` block (line 27)

**Option 3 (document knobs as safety-net-only):**
- `docs/guides/LOOPS_REFERENCE.md` — update line 191 brainstorm table entry to clarify that `novelty_threshold`/`max_saturation` are safety-net parameters, not convergence tuners

### Test Files

- `scripts/tests/test_brainstorm.py` — test class `TestBrainstormDedup` (line 271) exercises the dedup logic in isolation; class `TestBrainstormYaml` (line 22) asserts defaults
  - If Option 1: update `test_context_defaults` at line 96: `assert ctx.get("novelty_threshold") == "0.80"` → `"0.55"`
  - Consider adding a test in `TestBrainstormDedup` that verifies paraphrase-level dedup fires at 0.55 (currently no test covers that threshold range)

### Key Anchors

- `dedup_novelty` state — `scripts/little_loops/loops/brainstorm.yaml` lines 113–188: inline Python heredoc using `difflib.SequenceMatcher(None, text.lower(), ex.lower()).ratio() >= threshold` at line 159
- `saturation_gate` state — lines 190–202: `output_numeric` / `lt` / `${context.max_saturation}` evaluator; always reads `0 < 2 → yes` in practice
- `test_context_defaults` — `scripts/tests/test_brainstorm.py:96` asserts the current `"0.80"` default

### No New Files Needed

Both in-scope options are single-file edits with optional test update.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option 1 — Lower the default threshold to 0.55:**

1. Edit `scripts/little_loops/loops/brainstorm.yaml` line 27: `novelty_threshold: "0.80"` → `novelty_threshold: "0.55"`
2. Edit `scripts/tests/test_brainstorm.py:96`: `assert ctx.get("novelty_threshold") == "0.80"` → `== "0.55"`
3. (Optional) Add a `TestBrainstormDedup` test asserting that paraphrase-level near-duplicates (ratio ~0.60) are filtered at 0.55 but pass at 0.80, documenting the rationale for the new value
4. Run `python -m pytest scripts/tests/test_brainstorm.py -v` to verify all dedup tests pass
5. Run `ll-loop validate brainstorm` to confirm no new FSM validation errors

**Option 3 — Document knobs as safety-net-only:**

1. Edit `docs/guides/LOOPS_REFERENCE.md` line 191 brainstorm table entry — append a note after the `difflib.SequenceMatcher` mention, e.g.: `(novelty_threshold/max_saturation are safety-net parameters; lens-exhaustion is the primary convergence mechanism)`
2. Optionally update the `context:` block comments in `scripts/little_loops/loops/brainstorm.yaml` lines 26–28 to state explicitly that `novelty_threshold` and `max_saturation` are safety nets, not active tuners
3. No test changes required
4. Run `ll-loop validate brainstorm` to confirm clean validation

## Scope Boundaries

- **In scope**: Adjusting `novelty_threshold` default in the `brainstorm` built-in loop (option 1)
- **In scope**: Documenting `max_saturation` as safety-net-only and clarifying knob behavior (option 3)
- **Out of scope**: Implementing a full embeddings-based semantic deduplication backend (option 2 is a larger follow-on if option 1/3 is insufficient)
- **Out of scope**: Redesigning the brainstorm FSM architecture or lens-rotation mechanism
- **Out of scope**: Fixing saturation/novelty behavior in any other loop — only the `brainstorm` built-in

## Impact

- **Priority**: P4 — Behavioral deception only; finite lens queue guarantees safe termination; no user-visible correctness failure
- **Effort**: Small — Option 3 is docs-only; Option 1 is a single threshold constant change in the loop YAML
- **Risk**: Low — threshold or documentation change; no API surface change for options 1 or 3
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `brainstorm`

## Status

**Open** | Created: 2026-06-27 | Priority: P4


## Session Log
- `/ll:decide-issue` - 2026-06-28T02:17:26 - `fcd085ed-5850-4ae2-ad7a-bf6eb0fdc293.jsonl`
- `/ll:refine-issue` - 2026-06-28T01:39:53 - `30e32b40-781b-41e9-aeb1-ff1283baedee.jsonl`
- `/ll:format-issue` - 2026-06-28T01:31:49 - `56b196bb-d510-4444-8615-30ddeded49b6.jsonl`
