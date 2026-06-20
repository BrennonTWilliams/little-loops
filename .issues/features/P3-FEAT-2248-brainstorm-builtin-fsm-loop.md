---
id: FEAT-2248
title: brainstorm built-in FSM loop
type: FEAT
priority: P3
status: done
captured_at: '2026-06-20T19:18:10Z'
completed_at: '2026-06-20T20:48:55Z'
discovered_date: 2026-06-20
discovered_by: capture-issue
labels:
- loops
- planning
- ideation
decision_needed: false
confidence_score: 99
outcome_confidence: 79
score_complexity: 15
score_test_coverage: 15
score_ambiguity: 24
score_change_surface: 25
---

# FEAT-2248: brainstorm built-in FSM loop

## Summary

Add a general-purpose, portable `brainstorm` built-in FSM loop that performs
deliberate **divergence first, convergence second** (the double-diamond) while
actively resisting premature mode collapse. Every existing "thinking" loop in
`scripts/little_loops/loops/` is *convergent* (mode-seeking toward a single
optimum: `rn-plan`, `adversarial-redesign`, `hitl-compare`, `deep-research`).
None performs the core brainstorming move. This loop fills that gap.

## Current Behavior

No loop in the catalog diverges before converging. Users wanting structured
ideation must hand-roll prompts; there is no harness that guarantees idea
spread, dedups near-duplicates, or exits on saturation.

## Expected Behavior

`ll-loop run brainstorm --input brief="..."` produces a self-contained
ideation report (`brainstorm.md` + `ideas.jsonl`) in `${context.run_dir}` with
genuine spread (not N rewordings of one idea), a clustered + relative-ranked
idea set, and a synthesized best-of hybrid. The loop is autonomous (no HITL in
the convergence path) and always completes regardless of sink configuration.

## Motivation

Brainstorming is a distinct cognitive mode the toolkit lacks. Two project-specific
constraints shape the design:

- **Portability:** Built-in loops ship as a plugin into arbitrary projects.
  Ideation output is broader than issues, so the core has **zero dependency on
  the little-loops Issue system** — modeled on `deep-research` (→ portable
  `report.md`) and `rn-plan` (→ portable `plan.md`), not the issue-mutating
  loops. (See [[feedback_general_purpose_loop_decoupling]].)
- **Anti-self-grading:** `CLAUDE.md`/SHOR establish LLM self-grades are 33–55%
  accurate and must be paired with measurable evidence. Two mechanisms give the
  loop teeth: (1) a deterministic `difflib`-based novelty/dedup gate — the
  *inverse* of `diff_stall_gate` — that rejects near-duplicate ideas and exits
  on saturation; (2) **relative ranking** of the full idea set instead of
  absolute self-scores. The only raw LLM judgment that decides anything is
  *relative* ordering.

## Use Case

A developer runs `ll-loop run brainstorm --input brief="ways to reduce flaky
tests"`. The loop generates ideas under forced lenses (contrarian,
first-principles, end-user, ops/cost, invert-the-goal, cross-domain analogy,
plus 2–3 brief-derived lenses), dedups via difflib, clusters survivors,
relative-ranks them, synthesizes a hybrid, and writes `brainstorm.md` — with no
`.issues/` writes unless a sink is explicitly enabled.

## Proposed Solution

A **data loop** (writes to `${context.run_dir}`, and only when a sink is
explicitly enabled, `.issues/` — both exempt under MR-3). It is **not** a
meta-loop: it edits no harness artifacts, so MR-1..MR-6 do not formally bind;
their spirit is honored via the novelty gate. No `meta_self_eval_ok` needed.

Output sinks (all opt-in, off by default, degrade gracefully):
- always: portable `brainstorm.md` report in `run_dir`
- `sink=file`: copy report to a generic `output_path`
- `sink=issue`: invoke `/ll:capture-issue` per winner (ll-ecosystem convenience)
- `sink=decision`: populate an issue's `decision_needed` options (contract for
  `/ll:decide-issue`)

### Top-level YAML keys

```yaml
name: brainstorm
category: planning
input_key: brief
required_inputs: ["brief"]
initial: init
max_steps: 60
timeout: 3600
import:
  - lib/common.yaml
context:
  brief: ""
  sink: "none"              # none | file | issue | decision
  output_path: ""           # destination for sink=file
  decision_target: ""       # issue ID, required when sink=decision
  ideas_per_round: "5"
  top_k: "3"
  novelty_threshold: "0.80" # difflib ratio at/above which an idea is a duplicate
  max_saturation: "2"       # consecutive zero-novel rounds before early convergence
  novelty_backend: "difflib"# future opt-in: "embeddings"
```

### State machine (core writes only under `${captured.run_dir.output}`)

| State | type | Purpose | Routing |
|---|---|---|---|
| `init` | shell (`shell_exit`) | mkdir run_dir; seed empty `ideas.jsonl`, `saturation.txt`=0; echo `$(pwd)/run_dir` | capture `run_dir` → `frame` |
| `frame` | prompt | derive 2–3 task-specific lenses; union with fixed universal catalog; write one lens per line to `lenses.txt` | next `pop_lens` |
| `pop_lens` | shell (`queue_pop`) | head-1/tail-n+2/mv pop from `lenses.txt`; capture as `current_lens` | on_yes `diverge`; on_no `cluster` (exhausted) |
| `diverge` | prompt | generate `ideas_per_round` ideas under `current_lens`; emit `IDEAS_JSON` | capture `round_ideas` → `dedup_novelty` |
| `dedup_novelty` | shell (`parse_tagged_json`) | Python+`difflib.SequenceMatcher`: drop ideas with ratio ≥ threshold vs `ideas.jsonl`, append novel; update `saturation.txt` (reset 0 if novel>0 else +1) | next `saturation_gate` |
| `saturation_gate` | shell (`numeric_gate`) | `output_numeric operator: lt target: ${context.max_saturation}` | on_yes `pop_lens`; on_no `cluster` (saturated) |
| `cluster` | prompt | group `ideas.jsonl` into themes, drop dominated; write `clusters.md` | next `rank` |
| `rank` | prompt | **relative** ordering best→worst (no absolute scores); flag top-`top_k`; write `ranked.md` | next `converge` |
| `converge` | prompt | synthesize best-of hybrid; write portable `brainstorm.md` + `winners.md` | next `route_sink` |
| `route_sink` | shell | echo `${context.sink}`; `route:` table | none→`done`; file→`sink_file`; issue→`sink_issue`; decision→`sink_decision` |
| `sink_file` | shell (`shell_exit`) | copy `brainstorm.md` → `output_path` (degrade to notice if unset) | on_yes/on_no `done` |
| `sink_issue` | prompt | opt-in: invoke `/ll:capture-issue` per winner; collect IDs | next `done` |
| `sink_decision` | prompt | opt-in: append winners as `### Option A/B/C` under `## Proposed Solution`, set `decision_needed: true` | next `done` |
| `done` | prompt, `terminal: true` | report `brainstorm.md` (+ `ranked.md`, `ideas.jsonl`) and sink outcome | — |
| `failed` | prompt, `terminal: true` | diagnose (likely cluster/rank LLM error); report divergence reached | — |

### Key reuse (verified)

- `lib/common.yaml` fragments: `shell_exit`, `queue_pop`, `numeric_gate`
  (`output_numeric`, `operator: lt`, `target:`), `parse_tagged_json` idiom.
- File-based queue pop mirrors `autodev.yaml:56` / `rn-implement.yaml:135`.
- Per-run isolation via runner-injected `${context.run_dir}`, captured absolute
  in `init` (`rn-plan.yaml:22` / `hitl-compare.yaml:27`). (See
  [[reference_fsm_bash_brace_escape]] — bash `${...}` must be escaped `$${...}`.)

### Design corrections folded in

- Core decoupled from the Issue system; `brainstorm.md` is the primary portable
  output. Issue/decision integration is opt-in only.
- Do **not** use `oracles/oracle-capture-issue` for the issue sink — that oracle
  *scores* capture pairs (0–100), it does not create issues. The issue sink
  invokes `/ll:capture-issue` directly.
- `rank` uses relative ordering of the full set (apo-contrastive idiom), not a
  head-to-head bracket — right call for 3–5 ideas.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`route_sink` must use `evaluate.type: classify`** (the state machine table only labels it "shell"). The `classify` evaluator (`evaluators.py:evaluate_classify`) reads the last non-empty line of stdout verbatim as the verdict token — this is what makes a `route:` table dispatch work. Pattern (from `rn-remediate.yaml:states.diagnose`):

```yaml
route_sink:
  action: echo "${context.sink}"
  action_type: shell
  evaluate:
    type: classify
  route:
    none: done
    file: sink_file
    issue: sink_issue
    decision: sink_decision
    _: done
```

**`dedup_novelty` Python heredoc pattern** — when embedding FSM-captured LLM output inside a Python script in a shell action, use FSM interpolation directly inside the heredoc string (resolved before the shell runs, so no bash expansion conflict). Pattern from `assumption-firewall.yaml:states.parse_assumptions`:

```python
python3 << 'PYEOF'
import json, sys, difflib
output = """${captured.round_ideas.output}"""
# extract IDEAS_JSON: tag, then difflib.SequenceMatcher compare against existing ideas.jsonl
PYEOF
```

Note the `capture: round_ideas` on the `diverge` state is required so `dedup_novelty` can reference `${captured.round_ideas.output}`. The `diverge` prompt must instruct the LLM to emit `IDEAS_JSON: [...]` as its last tagged line.

**`init` → absolute run_dir** — use `echo "$(pwd)/$DIR"` (not `echo "$DIR"`) to convert the runner-injected relative path to an absolute path; confirmed in `rn-plan.yaml:states.init`. The bash `$()` is a subshell (no FSM escape needed); only `${...}` variable references inside the action body need `$${...}` escaping (per `[[reference_fsm_bash_brace_escape]]`).

**`saturation_gate` target interpolation** — `evaluate.target: "${context.max_saturation}"` interpolates from context at eval time; confirmed valid by `rn-implement.yaml:states.check_depth` using `evaluate.target: "${context.max_depth}"` with `fragment: numeric_gate`.

**`evaluate_classify` empty-stdout robustness** — `evaluators.py:evaluate_classify` (lines 416–467) returns `verdict=""` when stdout has no non-empty lines. The empty string does not match any named token in the `route:` table, so it falls through to the `_` wildcard. For `route_sink`, this means any `echo "${context.sink}"` failure (e.g., unset sink, subprocess error) still routes to `done` via `_`. The `_error` key handles non-zero exit code short-circuit separately.

## Integration Map

- **CREATE** `scripts/little_loops/loops/brainstorm.yaml` (primary deliverable).
- **EDIT** `scripts/tests/test_builtin_loops.py` — add `"brainstorm"` to the
  hardcoded `expected` set in `test_expected_loops_exist()` (~line 76). Only
  hard test coupling; all other tests auto-discover via `rglob` +
  `is_runnable_loop()`.
- **EDIT** `scripts/little_loops/loops/README.md` — add a catalog row under the
  `## Planning` table (after the `rn-*` rows).
- **EDIT** `README.md` (root) — line 163 has `**91 FSM loops**`; bump to `**92 FSM loops**`. Wiring analysis found this hardcoded count; `doc_counts.py` scans README.md via `(\d+)\s+\w*\s*loops?` regex and `test_doc_counts.py` will surface a mismatch. (Supersedes the `refine-issue` note below that said "no matches" — that grep pattern missed the markdown bold markers.)
- **EDIT** `docs/guides/LOOPS_GUIDE.md` — `## Choose Your Loop` table: add `brainstorm` to the appropriate group (Research & Knowledge or a new Planning row). [Agent 2 finding]
- **EDIT** `docs/guides/LOOPS_REFERENCE.md` — add a `brainstorm` entry under the Research & Knowledge / Planning section with invocation example and context variable table. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_builtin_loops.py:74–163` — `test_expected_loops_exist()` is at lines 74–163; the `expected` set is defined there. Add `"brainstorm"` to that set.
- `scripts/little_loops/loops/README.md:55–64` — Planning section rows are at lines 55–64 (after the `rn-*` rows); insert new row there.
- `scripts/little_loops/loops/apo-contrastive.yaml` — canonical relative-ranking reference for the `rank` state's apo-contrastive idiom.
- `scripts/little_loops/loops/assumption-firewall.yaml:states.parse_assumptions` — working `parse_tagged_json` caller pattern: Python heredoc embedding FSM interpolation via `"""${captured.<name>.output}"""`.
- `scripts/little_loops/loops/rn-remediate.yaml:states.diagnose` — working `classify` + `route:` table pattern; use this shape for `route_sink`.
- `scripts/little_loops/fsm/evaluators.py:evaluate_classify` — `classify` evaluator reads the last non-empty stdout line verbatim as the verdict token; required for `route:` table dispatch in `route_sink`.
- `scripts/little_loops/loops/rn-plan.yaml:states.init` — canonical `init` pattern: `echo "$(pwd)/$DIR"` converts runner-injected relative `${context.run_dir}` to absolute path; captured as `${captured.run_dir.output}` throughout.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

These files auto-discover `brainstorm.yaml` via `is_runnable_loop()` — no edits needed, but they will exercise the new loop automatically once the file exists:

- `scripts/little_loops/doc_counts.py` — calls `is_runnable_loop()` to count runnable loops (`verify_documentation()`); auto-detects brainstorm.yaml, bumps the live count to 92. [Agent 1 finding]
- `scripts/tests/test_doc_counts.py` — verifies the live count matches docs; auto-passes once README.md count is updated. [Agent 1 finding]
- `scripts/tests/test_fsm_flow.py` — `TestBuiltinLoopRegression.test_all_builtin_loops_still_load()` iterates `loops_dir.glob("*.yaml")` and calls `load_and_validate()`; will auto-exercise brainstorm.yaml. [Agent 3 finding]
- `scripts/little_loops/loops/loop-router.yaml` — `discover_loops` state calls `ll-loop list --json --visibility public` at runtime; brainstorm auto-appears once YAML exists. [Agent 2 finding]
- `scripts/little_loops/loops/loop-composer.yaml` — `discover_loops` state also calls `ll-loop list --json` at runtime; brainstorm auto-appears once YAML exists. [Agent 1 finding, 2nd wire pass]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `README.md` (root) line 163 — `**91 FSM loops**` → `**92 FSM loops**`; hardcoded count scanned by `doc_counts.py`. [Agent 3 finding]
- `docs/guides/LOOPS_GUIDE.md` — `## Choose Your Loop` table: add `brainstorm` to the Research & Knowledge or Planning group; this is the user-facing "which loop do I pick?" entry point. [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — add `brainstorm` entry (invocation example, context variable table, state summary) under the Research & Knowledge / Planning section. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_builtin_loops.py` — already in scope: add `"brainstorm"` to `expected` set (plain `set` literal, **not** a frozenset) in `TestBuiltinLoopFiles.test_expected_loops_exist()` — the set spans lines 76–161, insert `"brainstorm",` before the closing `}`; also: `test_deterministic_warning_categories_do_not_regrow()` (class `TestValidatorWarningBudget` at line 7277, method at line 7351) auto-covers brainstorm.yaml — will fail if it introduces uncategorized warnings in the ratcheted categories. [Agent 3 finding]
- `scripts/tests/test_brainstorm.py` — **new test file needed** (no existing dedicated test); follow the `test_deep_research.py` pattern (`TestBrainstormYaml`, `TestBrainstormShellStates`, `TestBrainstormDryRun` classes). Critically, a `TestBrainstormDedup` class is needed: the `dedup_novelty` difflib novelty gate has **zero existing test coverage** — model after `TestDedup.test_dedup_shell_logic_removes_duplicates()` in `test_loops_sft_corpus.py:1054`, **but use `difflib.SequenceMatcher` ratio (not `calculate_word_overlap`/Jaccard)** — the test's Python heredoc must mirror the actual `dedup_novelty` shell action logic. [Agent 3 finding]
- **Warning-ratchet authoring constraint** (`TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow`, lines 7277–7377): `brainstorm.yaml` must not trigger warnings in any of the 7 ratcheted categories at author time — `shared-tmp`, `partial-route`, `required-inputs`, `unreachable`, `failure-terminal`, `artifact-versioning`, `capture-ordering`. Most likely risks: `partial-route` (LLM `prompt`/`slash_command` states with `on_yes` but no `on_no`/`on_partial`) and `required-inputs` (omitting `required_inputs: ["brief"]` declaration). Run `ll-loop validate brainstorm` and confirm zero ratcheted-category warnings before merging; add `ALLOWLIST` entries keyed `("brainstorm", "<category>")` only if a violation is intentional. Note: step 4 says "0 errors" — this constraint extends to 0 ratcheted-category warnings. [Agent 2/3 finding, 2nd wire pass]

## Implementation Steps

1. Author `brainstorm.yaml` per the state-machine table above, reusing
   `lib/common.yaml` fragments.
2. Add `"brainstorm"` to the `expected` set in `test_builtin_loops.py`.
3. Add the catalog row to `loops/README.md`.
4. `ll-loop validate brainstorm` → 0 errors.
5. `ll-loop simulate brainstorm --input brief="..."` — confirm no
   unreachable/dead-end states across all four sink branches.
6. Novelty-gate discrimination check: extract the `dedup_novelty` Python to a
   scratch script; feed near-identical idea sets to confirm difflib flags
   duplicates and saturation increments.
7. Live smoke run (default, no sink); inspect `brainstorm.md` for genuine
   spread and a coherent hybrid; confirm no `.issues/` writes.
8. File sink + issue sink smoke runs.
9. `pytest scripts/tests/test_builtin_loops.py -v`, then `ll-verify-docs`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Bump `README.md` (root) line 163: `**91 FSM loops**` → `**92 FSM loops**`.
11. Add `brainstorm` entry to `docs/guides/LOOPS_GUIDE.md` `## Choose Your Loop` table.
12. Add `brainstorm` section to `docs/guides/LOOPS_REFERENCE.md` (invocation example, context vars, state summary).
13. Create `scripts/tests/test_brainstorm.py` — `TestBrainstormYaml`, `TestBrainstormShellStates`, `TestBrainstormDryRun`, and `TestBrainstormDedup` classes; model after `test_deep_research.py` + `test_loops_sft_corpus.py:TestDedup`.

## Acceptance Criteria

- [ ] `brainstorm.yaml` exists and `ll-loop validate brainstorm` reports 0 errors.
- [ ] `ll-loop simulate` shows no unreachable/dead-end states across all four
      sink branches.
- [ ] Default run emits `brainstorm.md` + `ideas.jsonl` in `run_dir` with no
      `.issues/` writes.
- [ ] difflib novelty gate demonstrably flags near-duplicate ideas and
      increments the saturation counter to early-exit.
- [ ] `rank` produces relative ordering (no absolute self-scores).
- [ ] `sink=file` copies the report; `sink=issue` creates `.issues/` files;
      `sink=decision` sets `decision_needed: true` with option blocks.
- [ ] `test_builtin_loops.py` green (incl. updated expected set); `ll-verify-docs`
      passes.

## API/Interface

New context knobs (all defaulted): `brief`, `sink`, `output_path`,
`decision_target`, `ideas_per_round`, `top_k`, `novelty_threshold`,
`max_saturation`, `novelty_backend`. Required input: `brief`.

## Edge Cases

- `sink=file` with unset `output_path` → degrade to a notice, still reach `done`.
- `sink=decision` with unset/invalid `decision_target` → degrade gracefully.
- Saturation reached before lenses exhausted → route to `cluster` early.
- Lenses exhausted before saturation → route to `cluster` normally.
- LLM error in cluster/rank → `failed` reports how far divergence got.

## Impact

Adds a net-new ideation capability with no change to existing loops. Portable
across plugin installs. Risk is low (additive); main risk is the novelty gate
being toothless — mitigated by the explicit discrimination check.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | optimizer error taxonomy, evaluator health |
| `scripts/little_loops/loops/deep-research.yaml` | portable-report model |
| `scripts/little_loops/loops/rn-plan.yaml` | run_dir capture / portable plan model |
| `scripts/little_loops/loops/lib/common.yaml` | reused `shell_exit`/`queue_pop`/`numeric_gate` fragments |

## Out of Scope / Follow-ups

- `novelty_backend: embeddings` (sharper than difflib; needs embedding API) —
  knob wired now, implemented later.
- True head-to-head pairwise bracket for `rank` — only if relative ranking
  proves unstable.
- HITL convergence variant (hand `winners.md` to `hitl-compare`) — deferred;
  the autonomous novelty-gated path is the chosen direction.

## Session Log
- `/ll:ready-issue` - 2026-06-20T20:37:00 - `8ff9d10c-4d74-4b3e-b348-e5e901e3c770.jsonl`
- `/ll:confidence-check` - 2026-06-20T22:00:00Z - `ef0b21ae-5944-468a-84c2-45873580c703.jsonl`
- `/ll:confidence-check` - 2026-06-20T21:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:refine-issue` - 2026-06-20T20:05:50 - `fc1788a4-667f-4b39-a1e2-6445777c429b.jsonl`
- `/ll:confidence-check` - 2026-06-20T20:00:00Z - `9738b7dd-b6f3-4159-beb5-1d8c74a52054.jsonl`
- `/ll:wire-issue` - 2026-06-20T20:18:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:wire-issue` - 2026-06-20T19:49:07 - `92e835d8-2b2a-4167-b8b1-f90fd296e069.jsonl`
- `/ll:refine-issue` - 2026-06-20T19:32:36 - `432269a5-55a7-4866-af30-a20f0f8d9fe1.jsonl`
- `/ll:format-issue` - 2026-06-20T19:23:40 - `e482087b-c7bd-45b4-b819-5cad47860009.jsonl`
- `/ll:capture-issue` - 2026-06-20T19:18:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ad41fd5-48f1-4196-8400-4e221ccd53e8.jsonl`

---

## Status

- **Current**: open
- **Last Updated**: 2026-06-20
