---
id: FEAT-3328
type: FEAT
title: 'Gate-completeness lint: flag intermediate gates that restate a validator rule
  table instead of importing it'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T17:33:30Z'
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3328: Gate-completeness lint: flag intermediate gates that restate a validator rule table instead of importing it

## Summary

A meta-loop that gates each lowering pass with an inline `python3 -c` assertion can
restate a validator's rule table instead of importing it. When the restatement is a
proper *subset* of what the terminal gate checks, the intermediate gate does not
merely miss defects — it launders them, giving every downstream pass false
confidence and pushing detection to a point where the retry topology can no longer
reach the state that made the mistake.

This is exactly what happened in `workflow-generator` run `2026-08-26T171218`:
`validate_evaluators` checked `evaluate.type` membership but not required companion
fields, so four states carrying bare `type: output_json` passed the gate, propagated
through two more passes, and first surfaced 4 states downstream as 12 errors at
`validate_artifact` — where `count_emit_retry` routes back to `emit_artifact`, a
state structurally incapable of fixing an `attach_evaluators` defect.

The instance is fixed. This issue is about making the *class* detectable.

## Current Behavior

`fsm/validation` has no lint that inspects intermediate `shell` gate actions
for hardcoded rule restatement. A meta-loop author can write an inline
`python3 -c` gate that hand-lists a literal subset of values (e.g. `{"exit_code",
"regex_match"}`) instead of importing the validator's own exported table
(e.g. `NON_LLM_EVALUATOR_TYPES` in
`scripts/little_loops/fsm/validation/_base.py:66`), and nothing flags the
drift. This is exactly what `validate_evaluators` in
`workflow-generator.yaml` did before it was fixed: it checked
`evaluate.type` membership but not the companion fields
`EVALUATOR_REQUIRED_FIELDS` requires, so four states carrying bare
`type: output_json` passed the gate and the defect surfaced three states
downstream at `validate_artifact` instead.

## Expected Behavior

`fsm/validation` gains a meta-rule (alongside MR-1..MR-6 in
`scripts/little_loops/fsm/validation/meta_rules.py`) that, for a loop whose
terminal gate is a little-loops validator, flags any intermediate
`action_type: shell` state whose action contains `python3` and hardcodes a
literal set/frozenset of values that is a subset of a known exported table's
keys (e.g. a literal evaluator-type set instead of importing
`NON_LLM_EVALUATOR_TYPES`, literal required-field lists instead of
`EVALUATOR_REQUIRED_FIELDS`, or a literal operator set instead of
`VALID_OPERATORS` — the full linted-table list is in AC #1). Severity is
`warning` — a restatement can be a
deliberate, narrower curated vocabulary — suppressible via a
`gate_completeness_ok` top-level flag (see Escape hatch below).

### Escape hatch — resolved

Earlier drafts of this issue specified the suppression two incompatible ways:
an inline source comment (`# gate-completeness: intentional-subset`) in the
Acceptance Criteria and Proposed Solution, versus a top-level YAML flag in the
research findings and every Wiring Phase entry. **Resolved in favor of the
top-level flag**, `gate_completeness_ok`, matching the established convention
(`meta_self_eval_ok`, `shared_state_ok`, `generator_fix_ok`,
`partial_route_ok`, `abstention_route_ok`); no inline-comment suppression
mechanism exists anywhere in `fsm/validation` today, and introducing one for a
single rule would be a second, inconsistent convention.

Consequence to accept explicitly: the flag is **loop-wide**, whereas this
section previously promised suppression of "a specific state". Two options:

- **(a) Accept loop-wide granularity** (`gate_completeness_ok: true`) —
  simplest, and exactly matches every sibling flag.
- **(b) Accept a list** (`gate_completeness_ok: [state_a, state_b]`) —
  per-state, but no sibling flag is list-shaped, so it needs its own parsing
  and its own `KNOWN_TOP_LEVEL_KEYS`/`from_dict`/`to_dict` handling for a
  non-bool type.

Recommend **(a)**. At `warning` severity on a rule expected to ship with zero
violations, per-state precision is not worth a bespoke flag shape.

## Use Case

A loop author writing a new intermediate gate for `workflow-generator` (or
any other meta-loop with a terminal validator gate) hardcodes a literal
`{"exit_code", "regex_match"}` check instead of importing
`NON_LLM_EVALUATOR_TYPES`. `ll-loop validate` now emits a `warning` naming
the state and the exported table it should import instead, catching the drift
at authoring time instead of three states downstream at the terminal gate —
the same failure class this issue's Summary describes as already having
happened once.

## Acceptance Criteria

1. `ll-loop validate` flags an `action_type: shell` state whose `python3`
   action contains a **literal collection display** that is a subset of one of
   the **linted tables** (see the list below), at `warning` severity, naming the
   state and the exported table to import instead. To be flagged, the literal
   must satisfy **all** of:
   - **at least 3 members** — a bare `{"exit_code"}` or `{"exit_code",
     "output_contains"}` appears in plenty of unrelated shell and is not
     evidence of a restated table;
   - **no member outside the table** — a literal mixing table members with
     unrelated strings is not a copy of that table;
   - **the action does not already import the table** it is a subset of.

   State the floor in the rule's docstring; it is the difference between a
   useful guard and a noisy one.

1b. **Match set, frozenset, list, AND tuple displays — not sets alone.**
   Earlier drafts scoped detection to "a literal set/frozenset". That misses
   the likeliest restatement shape and would not have caught the defect in this
   issue's own Summary had the author written it as a list:
   - The literals that actually appear in these gates today are **tuples** —
     `('done', 'failed')` at `workflow-generator.yaml:206` and `:259`.
   - `EVALUATOR_REQUIRED_FIELDS`'s values are `list[str]` (`_base.py:45-63`),
     so a hand-restated required-field table is naturally written
     `["operator", "target"]`, never `{"operator", "target"}`.
   - A restated `NON_LLM_EVALUATOR_TYPES` is just as plausible as a
     `("exit_code", "output_contains", "output_numeric")` membership tuple.

   The regex must therefore match `{...}`, `[...]`, and `(...)` displays of
   string literals (single- or double-quoted, since gate bodies are embedded in
   double-quoted `python3 -c "…"` strings and use single quotes inside). The
   ≥3-member / no-outside-members floor from AC #1 still does all the
   noise suppression — widening the bracket class does not widen the false
   positive surface, it only stops the rule from being trivially evadable by
   choosing a different bracket. Note the existing 2-member `('done', 'failed')`
   tuples stay below the floor and remain unflagged.

   **Linted tables.** All are exported from
   `scripts/little_loops/fsm/validation/__init__.py`:
   - `EVALUATOR_REQUIRED_FIELDS` (keys) — `_base.py:45`
   - `NON_LLM_EVALUATOR_TYPES` — `_base.py:66`
   - `VALID_OPERATORS` — `_base.py:74`. **Do not omit this one.** BUG-3326 is
     landing a `VALID_OPERATORS` import into `validate_evaluators` for exactly
     the reason this rule exists; a hand-restated `{"eq", "ne", "lt", "le",
     "gt", "ge"}` is the same defect class as a restated evaluator-type set,
     and leaving it unlinted means the rule does not cover the very move its
     own Ordering section depends on. **Confirmed** it is declared as a bare
     `set` (`VALID_OPERATORS = {"eq", "ne", "lt", "le", "gt", "ge"}`,
     `_base.py:74`), not an annotated `frozenset` like `NON_LLM_EVALUATOR_TYPES`
     (`:66`) and `VALID_VISIBILITY` (`:78`). **Tighten it to
     `VALID_OPERATORS: frozenset[str] = frozenset({...})` in this pass** — a
     one-line change that removes the normalize-on-read special case from the
     new rule and makes the three linted tables uniform. Grep first: it is
     re-exported from `fsm/validation/__init__.py:51,168`, so confirm no caller
     mutates it (none should — it is a vocabulary constant).
   - `VALID_VISIBILITY` (`_base.py:78`) — optional; three members total, so any
     subset meeting the ≥3 floor is the *entire* table, which makes it a
     high-signal, zero-ambiguity case. Include unless it proves noisy.

1a. **Report each literal against the most specific matching table only.**
   `NON_LLM_EVALUATOR_TYPES` is *derived* from `EVALUATOR_REQUIRED_FIELDS`
   (`_base.py:66`: `frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {...}`), so
   every literal that is a subset of the former is necessarily also a subset of
   the latter. A naive per-table loop therefore emits **two warnings for one
   literal**, naming two different tables to import — actively confusing, since
   only one of them is the right answer. Resolve by checking tables in
   specificity order (smallest first) and emitting at most one warning per
   literal, or by preferring the table whose membership the literal matches
   most tightly. Assert single-emission in the tests: a positive-case fixture
   whose literal is a subset of both tables must produce exactly one
   `ValidationError`.
2. A loop declaring `gate_completeness_ok: true` does not raise the warning
   (see Escape hatch above — a top-level YAML flag, **not** an inline
   comment).
3. Running the rule against the current built-in loop set produces zero
   violations — this rule ships as a forward guard, not a fix for an existing
   loop. Note this depends on BUG-3326 having landed first; see Ordering.

   **Verified 2026-08-26, including under AC #1b's widened bracket class.**
   Swept `loops/**.yaml`: the only literal collection displays inside `python3`
   shell gates are the 2-member `('done', 'failed')` tuples
   (`workflow-generator.yaml:206`, `:259`), which sit below the ≥3 floor.
   `validate_evaluators` imports both `EVALUATOR_REQUIRED_FIELDS` and
   `NON_LLM_EVALUATOR_TYPES` directly. No built-in restates an operator
   vocabulary — the sole `"eq"` occurrence is `docs-sync.yaml:72`'s
   `operator: "eq"`, a scalar evaluator field, not a display. Zero violations
   holds both before and after BUG-3326.
4. The rule is documented in
   `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § The Design Rules alongside
   MR-1..MR-14, as an **unnumbered named rule** (`**gate-completeness**`,
   following the existing `policy-table` / `terminal-action-ok` precedent in
   the same table), with the retry-reachability item (below) captured as a
   related-but-unmechanized heuristic. Taking a numbered `MR-15` slot instead
   would force four renumbering touchpoints — including the section heading
   (which drives the GFM anchor) and `.claude/CLAUDE.md`'s prose *and* link to
   `#the-design-rules-mr-1mr-14` — for no analytic benefit.
5. The rule's known coverage limit is documented alongside it: it inspects
   `shell` actions only, so a rule table restated in **prose inside a `prompt`
   action** is not detected. See Known coverage gap below.

## Motivation

A restated (rather than imported) rule table doesn't just miss defects — when
the restatement is a proper subset of what the terminal gate checks, it
launders them: every downstream pass gets false confidence, and detection
gets pushed to a point where the retry topology can no longer reach the state
that made the mistake (as BUG-3326 describes for the resulting `emit_artifact`
retry). Catching this at lint time, at the state where the drift is
introduced, is strictly cheaper than debugging it after a run fails three
states later.

## Proposed Solution

Add `_validate_gate_completeness(fsm: FSMLoop) -> list[ValidationError]` to
`scripts/little_loops/fsm/validation/meta_rules.py`, following the shape of
the existing `_validate_*` MR functions there (e.g.
`_validate_artifact_isolation` for MR-3). Detection sketch:

```python
# Skip entirely if fsm.gate_completeness_ok
# For each state with action_type == "shell" whose action contains "python3":
#   find literal collection displays — {...}, [...], and (...) of string
#   literals, single- or double-quoted — by regex over the raw action string
#   (AC #1b: sets alone would miss the list/tuple shapes actually used)
#   for each literal:
#     if len(members) < 3: skip
#     # tables in specificity order, smallest first, so a literal that is a
#     # subset of both NON_LLM_EVALUATOR_TYPES and EVALUATOR_REQUIRED_FIELDS
#     # (the former is derived from the latter) is reported once, against the
#     # tighter of the two — see AC #1a
#     for table in (VALID_VISIBILITY, VALID_OPERATORS,
#                   NON_LLM_EVALUATOR_TYPES, EVALUATOR_REQUIRED_FIELDS.keys()):
#       if members <= table and the action does not already import that table:
#         emit a warning naming the state, the literal, and the table to
#         import instead
#         break   # at most one warning per literal
```

### Detection: regex, not `ast` — decided

Earlier drafts specified `ast.parse` "to avoid false positives on string
content". Use **regex over the raw action string** instead:

- **Consistency.** No rule in this package parses embedded shell or Python
  today — MR-3, MR-5, MR-6, and MR-7/9/11 in `shell_safety.py` are all
  regex-over-raw-string against module-level compiled `re.Pattern` constants.
  A single `ast`-based rule introduces a detection utility nothing else
  shares.
- **`ast` doesn't actually get a clean shot at the source.** The Python body
  is embedded inside a YAML shell action as `python3 -c "..."` — extracting it
  means handling quoting, `\"` escapes, and heredocs before `ast.parse` ever
  sees valid source. That extractor is its own mini-parser, and it is the part
  most likely to be wrong.
- **The cardinality floor does the work `ast` was meant to do.** Requiring ≥3
  members, all inside the table, is what suppresses incidental matches — not
  the parsing strategy.

This drops the effort estimate from Medium to Small (see Impact).

### Known coverage gap — prose restatement in `prompt` actions

The rule is scoped to `shell` gates, but the live drift risk in the very loop
that motivated this issue is **not** in a shell gate. `attach_evaluators`
(`workflow-generator.yaml:165-181`) is an `action_type: prompt` state whose
prompt hand-lists the entire allowed evaluator vocabulary *and* an English
copy of the `EVALUATOR_REQUIRED_FIELDS` table:

```
- exit_code — no companion fields
- output_contains — requires `pattern`
- output_numeric — requires `operator` and `target`
- output_json — requires `path`, `operator`, AND `target`
...
```

That table drifts silently the moment `EVALUATOR_REQUIRED_FIELDS` changes, and
a shell-only lint will never see it. This matters for AC #3: "zero violations
post-fix" is true, but it is true partly because the surviving restatement
lives where the rule does not look — not because the loop stopped restating.

Decide one of these explicitly during implementation and record the choice:

- **(a) Ship shell-only, document the gap** (recommended for v1) — state the
  limitation in the rule docstring and the guide entry, per AC #5, and treat
  prompt-side restatement as a known-uncovered case.
- **(b) Extend to `prompt` actions** — a second, looser regex over prose
  (e.g. ≥3 table members appearing as backticked tokens in one action), still
  `warning`-severity. Higher recall, meaningfully higher false-positive rate,
  since a prompt legitimately *needs* to name the vocabulary it is asking for
  — an LLM cannot `import` a frozenset. That last point is the real argument
  for (a): unlike a shell gate, a prompt has no import to offer instead, so
  the warning has no actionable fix to suggest.

If (a): consider filing the prompt-side drift as its own follow-up, since the
right remedy there is generative (emit the vocabulary into the prompt from the
table at runtime) rather than a lint.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation/meta_rules.py` — new
  `_validate_gate_completeness` function, registered alongside the other
  `_validate_*` MR checks
- `scripts/little_loops/fsm/validation/__init__.py` — export/wire the new
  rule into the validation pipeline (same pattern as `EVALUATOR_REQUIRED_FIELDS`,
  `NON_LLM_EVALUATOR_TYPES` re-exports at lines 47-49, 164-166)
- `scripts/little_loops/fsm/validation/_base.py:74` — tighten
  `VALID_OPERATORS` from a bare `set` to `frozenset[str]`, matching its two
  sibling tables (AC #1)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — add the new rule to § The
  Design Rules (MR-1..MR-14 table) and add the Non-Goal below as a review
  heuristic

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/structural_rules.py` — add
  `_validate_gate_completeness` to the `from little_loops.fsm.validation.meta_rules
  import (...)` block (alongside `_validate_artifact_isolation`,
  `_validate_meta_loop_evaluation`, etc.) and add its
  `errors.extend(_validate_gate_completeness(fsm))` call inside `validate_fsm()`,
  grouped with the other MR-1..MR-6 meta-rule calls (immediately after
  `errors.extend(_validate_missing_scope(fsm))`, before
  `errors.extend(_validate_bash_default_interpolation(fsm))`).
- `scripts/little_loops/fsm/validation/_base.py` — the escape-hatch flag
  needs a `gate_completeness_ok` entry in `KNOWN_TOP_LEVEL_KEYS`
  (`frozenset[str]`), or a loop that sets `gate_completeness_ok: true` to
  suppress the rule gets spuriously flagged as an "Unknown top-level keys"
  violation.
- `scripts/little_loops/fsm/schema.py` — the `gate_completeness_ok`
  suppression flag needs three additional touchpoints on the `FSMLoop`
  dataclass, following the exact pattern of the existing `abstention_route_ok`
  flag: (1) field declaration `gate_completeness_ok: bool = False`, (2)
  `from_dict` parsing `gate_completeness_ok=data.get("gate_completeness_ok",
  False)`, (3) `to_dict` round-trip `if self.gate_completeness_ok:
  result["gate_completeness_ok"] = self.gate_completeness_ok`. This is four
  total sites (this file's three plus `_base.py`'s `KNOWN_TOP_LEVEL_KEYS`),
  not the single top-level-flag mention the issue's own research implies.

### Dependent Files (Callers/Importers)
- `ll-loop validate` CLI — surfaces the new warning through its existing
  output path, no new integration needed

### Similar Patterns
- `_validate_artifact_isolation` (MR-3) and
  `_validate_meta_loop_evaluation` (MR-1/MR-2) in `meta_rules.py` are the
  closest existing shape: FSM-wide static checks returning
  `list[ValidationError]`

### Tests
- `scripts/tests/` — new test(s) for `_validate_gate_completeness`: positive
  case (≥3-member literal subset of `NON_LLM_EVALUATOR_TYPES` without import
  triggers warning), negative cases (import present; `gate_completeness_ok:
  true`; literal below the 3-member floor; literal containing a member outside
  the table), and a full-suite run confirming zero violations against current
  built-in loops. Two further cases from the AC revisions:
  - **single-emission** (AC #1a): a literal that is a subset of *both*
    `NON_LLM_EVALUATOR_TYPES` and `EVALUATOR_REQUIRED_FIELDS.keys()` — which
    is every subset of the former, since it is derived from the latter —
    produces exactly one `ValidationError`, naming the more specific table.
  - **`VALID_OPERATORS` coverage** (AC #1): a literal `{"eq", "ne", "lt"}` in
    an action that does not import `VALID_OPERATORS` is flagged; the same
    action with the import present is not.
  - **bracket-class coverage** (AC #1b): the same ≥3-member restatement written
    as a **list** (`['operator', 'target', 'path']` vs
    `EVALUATOR_REQUIRED_FIELDS`) and as a **tuple**
    (`('eq', 'ne', 'lt')` vs `VALID_OPERATORS`) is flagged identically to the
    set form — parametrize over the three bracket shapes so a set-only regex
    fails the suite.
  - **below-floor tuple stays clean**: the in-repo `('done', 'failed')` literal
    (`workflow-generator.yaml:206`) is **not** flagged — the 2-member case that
    keeps AC #3 at zero violations once lists and tuples are in scope.
- Use `workflow-generator.yaml`'s `validate_evaluators` state as the in-repo
  "correct" fixture for the import-present negative case — it imports both
  tables directly and carries an inline comment stating the
  import-not-restate rationale

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_validation_meta_rules.py` — add a `TestGateCompleteness`
  class following the existing `TestArtifactIsolation` (MR-3) shape (lines
  294-369): a `_simple_fsm(...)` builder constructing a minimal `FSMLoop`
  directly, then direct calls to `_validate_gate_completeness(fsm)` for
  positive/negative/suppression cases, plus a
  `test_gate_completeness_runs_via_validate_fsm` end-to-end wiring check
  mirroring `test_mr3_runs_via_validate_fsm`.
- `scripts/tests/test_ll_loop_commands.py::TestCmdValidate` (lines 407-466)
  has a paired CLI-level precedent for a WARNING-severity rule:
  `test_validate_no_json_warns_mr13_hardcoded_success_verdict` (non-JSON
  path, asserts via `caplog.at_level("WARNING")`) and
  `test_validate_json_warns_mr13_hardcoded_success_verdict` (JSON path,
  asserts via `capsys` + `json.loads(...)["violations"]`). Add the same
  paired pair for the new rule to prove it surfaces through `ll-loop
  validate` end-to-end, not just via the direct function call.
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles` (offenders-list
  + optional exempt-dict pattern at `test_no_failure_edge_routes_to_a_success_terminal`,
  lines 59-98) is the template for AC #3's "zero violations against the
  current built-in loop set" test — iterate `builtin_loops`, call
  `_validate_gate_completeness` per file, assert no offenders.
- Confirmed: no test enumerates a fixed MR-rule count/list (`validate_fsm`'s
  dispatcher is a flat `errors.extend(...)` sequence with no registry
  object), so adding the new rule requires no update to any "N rules total"
  assertion.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — § The Design Rules (new
  **unnumbered named** rule entry, per AC #4), the `prompt`-action coverage
  gap (AC #5), and a new heuristic note for retry-reachability (see Non-Goal)

_Wiring pass added by `/ll:wire-issue` — **choice now made: unnumbered.**
The analysis below is retained as the rationale; no renumbering touchpoints
apply, so `.claude/CLAUDE.md` and the section heading are left alone:_
- If the new rule is numbered `MR-15` (per AC #4's "its own MR number"), four
  spots need updating, not just the table row: the section heading `## The
  Design Rules (MR-1…MR-14)` itself (→ `MR-1…MR-15`, which drives the GFM
  anchor slug); `.claude/CLAUDE.md`'s Loop Authoring section, which both
  hardcodes the prose `` `ll-loop validate` enforces these plus MR-1..MR-14 ``
  and links to the anchor `#the-design-rules-mr-1mr-14` (both go stale on a
  heading rename); and two enumerated-list sentences inside
  `HARNESS_OPTIMIZATION_GUIDE.md` itself that spell out the full WARNING
  rule set by number (a code-block comment and a matching bullet a few lines
  later) — both need `MR-15` appended. **Alternative**: ship as an unnumbered
  named rule (e.g. `**gate-completeness**`) following the existing
  `policy-table`/`terminal-action-ok` precedent in the same table, which
  avoids all four renumbering touchpoints. Flag this choice explicitly during
  implementation rather than defaulting to a numbered slot.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- Confirmed exact shape of `ValidationError`/`ValidationSeverity` in `scripts/little_loops/fsm/validation/_base.py`: `ValidationSeverity` is a two-value `Enum` (`ERROR`, `WARNING`); `ValidationError` is a `@dataclass` with `message: str`, `path: str | None = None`, `severity: ValidationSeverity = ValidationSeverity.ERROR`.
- Confirmed MR registration pipeline: `validate_fsm(fsm, orchestration_request_path=None) -> list[ValidationError]` in `structural_rules.py` calls every `_validate_*` check via `errors.extend(_validate_XXX(fsm))` in a fixed sequence. Adding a new rule requires: (1) implement `_validate_gate_completeness(fsm: FSMLoop) -> list[ValidationError]` in `meta_rules.py`, (2) import it into `structural_rules.py`, (3) add its `errors.extend(...)` call inside `validate_fsm()`, (4) re-export the function and any new constants from `scripts/little_loops/fsm/validation/__init__.py` in both the `from ... import (...)` block and `__all__` (matches the issue's own citation of lines 47-49/164-166 for the existing re-exports).
- Confirmed `_validate_artifact_isolation` (MR-3) and `_validate_meta_loop_evaluation` (MR-1/MR-2) shapes as the sibling pattern: both operate on `state.action` as a raw string via compiled module-level `re.Pattern` constants (`_SHARED_TMP_PATH_RE`, `_META_LOOP_ACTION_PATTERNS`) — **no rule in this package uses `ast.parse`, `ast`, or `shlex` on embedded shell/Python bodies today**; every action-text lint (MR-3, MR-5, MR-6, MR-7/9/11 in `shell_safety.py`) is regex-over-raw-string. A new rule wanting more than substring/regex matching on literal set/frozenset syntax would need to introduce its own detection utility — none is currently shared/reusable.
- Confirmed `NON_LLM_EVALUATOR_TYPES` is *derived*, not hand-listed: `frozenset[str] = frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {"llm_structured", "comparator", "contract", "advisor_consult"}` in `_base.py`. This directly supports the issue's rationale — a literal copy of this set drifts silently whenever `EVALUATOR_REQUIRED_FIELDS` changes, since the derived set updates automatically but a pasted literal does not.
- **Escape-hatch convention correction**: no inline source-comment suppression convention (e.g. the issue's proposed `# gate-completeness: intentional-subset`) exists anywhere in `fsm/validation` today. Every existing MR rule's escape hatch is a top-level loop YAML boolean flag instead (e.g. `meta_self_eval_ok`, `shared_state_ok`, `generator_fix_ok`, `partial_route_ok`, all enumerated in `KNOWN_TOP_LEVEL_KEYS` in `_base.py`), referenced directly in the `ValidationError.message` text. A `gate_completeness_ok: true` top-level flag would match established convention; an inline comment marker would be a new, inconsistent suppression mechanism for this codebase.
- ~~`ll-loop validate` severity surfacing: plain-text mode ... does not currently print WARNING-severity results in its success path ... silent in the default CLI success output until/unless that gap is separately addressed.~~ **This finding is wrong — corrected 2026-08-26.** `cmd_validate`'s own success path does discard its return value, but `load_and_validate` emits every warning via `logger.warning(str(warning))` at `structural_rules.py:1848` (stdlib `logging`), which reaches stderr through logging's lastResort handler. Verified end-to-end:
  ```
  $ ll-loop validate scripts/little_loops/loops/adopt-third-party-api.yaml
  [14:39:07] ...is valid                                       # stdout
  [WARNING] states.enumerate.evaluate.prompt: ... (ENH-2342 MR-8)   # stderr
  ```
  A new WARNING-severity rule is therefore visible in **both** the default CLI path and `--json`, with no additional plumbing. Do not add CLI work for this — the original bullet would have sent implementation down a dead end.
- Reference implementation already in-repo: `workflow-generator.yaml`'s `validate_evaluators` state is the positive control this rule must not flag (imports `EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES` directly, with an inline comment stating the import-not-restate rationale) — useful as the concrete "correct" fixture for the rule's negative test case.

## Program Design

### Types

- `ValidationError` — existing type returned by all `_validate_*` MR
  functions in `meta_rules.py`; reused, not extended

### Signatures

- `_validate_gate_completeness(fsm: FSMLoop) -> list[ValidationError]`

### Call Path

`_validate_artifact_isolation` (existing MR-3 check, same file, same
`FSMLoop -> list[ValidationError]` shape) is the sibling `_validate_gate_completeness`
is added next to in `meta_rules.py`; the validation pipeline invokes both the
same way: `ll-loop validate` -> validation pipeline
(`scripts/little_loops/fsm/validation/__init__.py`) -> `_validate_gate_completeness`
-> per offending `shell` state, parses the `python3 -c` action body and checks
literal set/frozenset displays against the exported tables in
`scripts/little_loops/fsm/validation/_base.py`

## Implementation Steps

0. Confirm BUG-3326 has landed (see Ordering) — AC #3 depends on it.
1. Implement `_validate_gate_completeness` in `meta_rules.py` using a
   module-level compiled `re.Pattern` over the raw action string, matching set,
   frozenset, list, and tuple displays (AC #1b), with the ≥3-member /
   no-outside-members floor from AC #1, the full linted-table list
   (including `VALID_OPERATORS`), and the smallest-first / one-warning-per-
   literal ordering from AC #1a.
1a. Tighten `VALID_OPERATORS` to `frozenset[str]` in `_base.py:74` (AC #1) so
   the three linted tables are uniform.
2. Add the `gate_completeness_ok` flag: `KNOWN_TOP_LEVEL_KEYS` in `_base.py`,
   plus the three `FSMLoop` sites in `schema.py` (field, `from_dict`,
   `to_dict`) following `abstention_route_ok`.
3. Wire the check into `validate_fsm()` in `structural_rules.py` and re-export
   from `fsm/validation/__init__.py` (both the import block and `__all__`).
4. Add tests: positive (unimported ≥3-member subset triggers warning),
   negative (import present; below the cardinality floor; a literal with
   members outside the table; `gate_completeness_ok: true`), the
   single-emission case (AC #1a) and the `VALID_OPERATORS` pair, the
   `validate_evaluators` state as the in-repo correct fixture, the CLI-level
   pair, and the zero-violations sweep over built-in loops.
5. Document the rule in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as an
   unnumbered named rule (AC #4), including its `prompt`-action coverage gap
   (AC #5) and the retry-reachability non-goal heuristic.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/validation/structural_rules.py` — import
  `_validate_gate_completeness` and add its `errors.extend(...)` call inside
  `validate_fsm()`, grouped with the other MR-1..MR-6 meta-rule calls.
- Update `scripts/little_loops/fsm/validation/_base.py` — add
  `gate_completeness_ok` to `KNOWN_TOP_LEVEL_KEYS`.
- Update `scripts/little_loops/fsm/schema.py` — add `gate_completeness_ok`
  as an `FSMLoop` dataclass field, `from_dict` parse, and `to_dict` emit
  (three sites, following the `abstention_route_ok` pattern).
- Update `scripts/tests/test_ll_loop_commands.py::TestCmdValidate` — add a
  paired non-JSON/`caplog` + JSON/`capsys` CLI-level test mirroring
  `test_validate_no_json_warns_mr13_hardcoded_success_verdict` /
  `test_validate_json_warns_mr13_hardcoded_success_verdict`.
- Update `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles` — add a
  zero-violations test over `builtin_loops` per AC #3, following the
  offenders-list pattern in `test_no_failure_edge_routes_to_a_success_terminal`.
- ~~Decide numbered vs. unnumbered before writing the docs update.~~
  **Decided: unnumbered named rule** (`**gate-completeness**`), per AC #4 — no
  renumbering touchpoints, so `.claude/CLAUDE.md` and the
  `## The Design Rules (MR-1…MR-14)` heading are untouched.
- Also document the `prompt`-action coverage gap in the guide entry, per
  AC #5 and the Known coverage gap section.

## Impact

- **Priority**: P3 — a forward guard against a failure class that has
  occurred once and is now fixed; no current violations, so no urgency, but
  meaningful to prevent recurrence
- **Effort**: Small — revised down from Medium. Dropping `ast` for
  regex-over-raw-string (see Detection above) removes the embedded-body
  extractor, which was the bulk of the estimate; what remains is one
  `_validate_*` function in the established shape, a four-site boolean flag,
  and tests
- **Risk**: Low — additive `warning`-severity check with an escape hatch; does
  not change existing loop behavior or fail builds
- **Breaking Change**: No

## Proposed Rule

**gate-completeness** (unnumbered named rule, per AC #4). For a loop whose
terminal gate is a little-loops validator, flag any intermediate `shell` gate that
hardcodes a literal set of values which the validator exposes as an importable
table — e.g. a literal evaluator-type set instead of `NON_LLM_EVALUATOR_TYPES`, or
literal required-field lists instead of `EVALUATOR_REQUIRED_FIELDS`. Where the
terminal gate exposes its rules as data, import rather than restate.

Detection: in `fsm/validation`, for each `action_type: shell` state whose action
contains `python3`, look for a literal collection display — set, frozenset,
list, or tuple of string literals — of **≥3 members, all of them**
members of a known exported table (`EVALUATOR_REQUIRED_FIELDS` keys,
`NON_LLM_EVALUATOR_TYPES`, `VALID_OPERATORS`, optionally `VALID_VISIBILITY`), in
an action that does not import that table. Tables are checked smallest-first and
at most one warning is emitted per literal, since `NON_LLM_EVALUATOR_TYPES` is
derived from `EVALUATOR_REQUIRED_FIELDS` and would otherwise double-report.
Severity `warning` — a restatement is sometimes deliberate (a *narrower* curated
vocabulary) — suppressed by `gate_completeness_ok: true`.

Current blast radius: `workflow-generator.yaml`'s `validate_evaluators` was the
only built-in doing this in a `shell` gate, and it has been fixed, so the rule
ships with zero violations and acts purely as a forward guard. Re-confirmed
after adding `VALID_OPERATORS` to the linted set: no built-in loop restates an
operator vocabulary — the only `"eq"` occurrence across `loops/**.yaml` is
`docs-sync.yaml:72`'s `operator: "eq"`, a single evaluator field, not a
collection display, and well under the ≥3-member floor. Re-confirmed again
after widening detection to list and tuple displays (AC #1b): the only literals
that widening newly brings into scope are the 2-member `('done', 'failed')`
tuples in `workflow-generator.yaml:206,259`, both below the floor. Caveat: the same
loop still restates the table in prose inside `attach_evaluators`'s **prompt**,
which this rule does not inspect — see Known coverage gap.

## Non-Goal (document, don't mechanize)

**Retry reachability** — for each bounded-retry edge, can the state it routes to
actually repair every fault class that triggers it? Real and worth checking, but the
fault-class-to-state mapping is semantic and resists static analysis. Add this to
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as a review heuristic alongside the MR
rule table rather than attempting a lint.

Two live instances make the case for the heuristic and are worth citing in the
guide entry as worked examples:

- **BUG-3326's Rejected Alternative** — routing an `.evaluate:` fault from
  `count_emit_retry` back to `attach_evaluators` looks reachable but blames the
  wrong state and discards two passes; the fix belonged upstream, at the gate
  that owns the fault.
- **BUG-3327's containment gate** — a scope violation routed to `capture_intent`
  is *structurally* unrepairable (the out-of-scope file is already written), and
  the edge is unbounded, so the loop wedges until `max_steps`. "Can this state
  repair this fault?" catches it; no static rule does.

## Ordering

Land **BUG-3326 first**. It adds a `VALID_OPERATORS` import to
`workflow-generator.yaml`'s `validate_evaluators` — the same
import-don't-restate move this rule lints for — and AC #3 ("zero violations
against the current built-in loop set") assumes that tree.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §6.

## Related Key Documentation

- `.claude/CLAUDE.md` — `## Loop Authoring` documents the MR-1..MR-14 rule set enforced by `ll-loop validate`, which this issue extends with a new MR rule.
- `docs/reference/API.md` — documents `little_loops.fsm.validation`, the module this issue's new `_validate_gate_completeness` function is added to.

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-26T20:09:17 - `fdfe1063-50b8-41a2-aae7-c524a32eadad.jsonl`
- `/ll:wire-issue` - 2026-08-26T19:28:19 - `1f462280-8e7a-4295-8360-c2cd201baeea.jsonl`
- `/ll:refine-issue` - 2026-08-26T19:14:22 - `0809cdb6-a88f-42a7-9e51-e57ee8a63f3a.jsonl`
- `/ll:format-issue` - 2026-08-26T19:09:04 - `8c47cf34-66af-4a75-8c4b-c7a8efe5d7ec.jsonl`
