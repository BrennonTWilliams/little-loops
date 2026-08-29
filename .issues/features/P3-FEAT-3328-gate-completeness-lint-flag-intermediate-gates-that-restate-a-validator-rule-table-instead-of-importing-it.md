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
relates_to:
- ENH-3355
parent: EPIC-2087
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
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
`scripts/little_loops/fsm/validation/meta_rules.py`) that flags any
`action_type: shell` state whose action contains `python3` and hardcodes a
literal set/frozenset of values that is a subset of a known exported table's
keys (e.g. a literal evaluator-type set instead of importing
`NON_LLM_EVALUATOR_TYPES`, literal required-field lists instead of
`EVALUATOR_REQUIRED_FIELDS`, or a literal operator set instead of
`VALID_OPERATORS` — the full linted-table list is in AC #1). Severity is
`warning` — a restatement can be a
deliberate, narrower curated vocabulary — suppressible via a
`gate_completeness_ok` top-level flag (see Escape hatch below).

### Scoping — resolved: unconditional, no terminal-gate precondition

Earlier drafts (and the Proposed Rule section) framed the rule as applying
"for a loop whose terminal gate is a little-loops validator," while AC #1 and
the detection sketch apply it unconditionally to every `shell` state
containing `python3`. Nothing anywhere defined how to detect "terminal gate
is a validator," so the qualifier was an unimplementable precondition.
**Resolved: the rule is unconditional.** A restated table is drift regardless
of what the terminal gate is; the ≥3-member / no-outside-members floor
(AC #1) already does the noise suppression the qualifier was gesturing at.
The terminal-gate framing survives only as motivation prose, never as a
detection condition.

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

   **Define "already imports the table" precisely.** As loosely worded, any
   mention of the table's name anywhere in the action satisfies it — including
   inside a comment — which makes the rule trivially evadable by pasting
   `# NON_LLM_EVALUATOR_TYPES` above the restated literal. Require the
   identifier to appear on an **import statement** in the same action:

   Note the in-repo form is a **parenthesized multi-line import** — the
   identifier sits on a later line than the `import` keyword
   (`workflow-generator.yaml` `validate_evaluators` state, ~:479-483), so a single-line
   `^.*import.*<name>` pattern does not match it. Match the import *region*
   first, then test membership within it:

   ```python
   _IMPORT_BLOCK_RE = re.compile(
       r"^[ \t]*(?:from[ \t]+\S+[ \t]+)?import[ \t]+(?:\([^)]*\)|[^\n]*)",
       re.MULTILINE,
   )

   def _imports(action: str, name: str) -> bool:
       return any(
           re.search(rf"\b{re.escape(name)}\b", m.group(0))
           for m in _IMPORT_BLOCK_RE.finditer(action)
       )
   ```

   The heredoc gate form (`python3 << 'PYEOF'` — now the in-repo form of
   `validate_evaluators`, with EPIC-3336/BUG-3339 converting `python3 -c`
   sites to heredocs repo-wide) needs no special handling here: the heredoc
   body is part of the raw action string, so `_IMPORT_BLOCK_RE` (MULTILINE
   over that string) matches its import statements the same way.

   Add two tests: an action naming the table **only in a comment** is still
   flagged; an action importing it via the parenthesized multi-line form is
   **not** (this is exactly `validate_evaluators`'s shape, already the
   designated in-repo correct fixture, so a single-line-only pattern would fail
   the negative case and be caught).

1b. **Match set, frozenset, list, AND tuple displays — not sets alone.**
   Earlier drafts scoped detection to "a literal set/frozenset". That misses
   the likeliest restatement shape and would not have caught the defect in this
   issue's own Summary had the author written it as a list:
   - The literals that actually appear in these gates today are **tuples** —
     `('done', 'failed')` at `workflow-generator.yaml:486` (`validate_evaluators`
     state) and `:536` (`validate_routing` state).
   - `EVALUATOR_REQUIRED_FIELDS`'s values are `list[str]` (`_base.py:45-63`),
     so a hand-restated required-field table is naturally written
     `["operator", "target"]`, never `{"operator", "target"}`.
   - A restated `NON_LLM_EVALUATOR_TYPES` is just as plausible as a
     `("exit_code", "output_contains", "output_numeric")` membership tuple.

   The regex must therefore match `{...}`, `[...]`, and `(...)` displays of
   string literals (single- or double-quoted, since gate bodies are embedded
   as `python3 -c "…"` strings or as quoted heredocs — `python3 << 'PYEOF'`,
   the current `validate_evaluators` form, with EPIC-3336/BUG-3339 converting
   `-c` sites to heredocs repo-wide — and may use either quote style inside). The
   ≥3-member / no-outside-members floor from AC #1 still does all the
   noise suppression — widening the bracket class does not widen the false
   positive surface, it only stops the rule from being trivially evadable by
   choosing a different bracket. Note the existing 2-member `('done', 'failed')`
   tuples stay below the floor and remain unflagged.

   **Exclude call syntax from the paren class.** A regex for "parenthesized
   string literals" also matches **function calls** with ≥3 string-literal
   arguments — `print("operator", "target", "path")`,
   `check("eq", "ne", "lt")` — which are not collection displays. Require
   that the opening `(` not be immediately preceded by an identifier
   character or closing bracket: `(?<![\w)\]])\(`. Tuple displays still
   match (`in ('a', 'b', 'c')` — the `(` follows a space), calls do not.
   `frozenset({...})` is still caught via its inner brace display. Add a
   negative test: a call with 3 table-member string args is not flagged.

   **Displays may span lines.** A restated ≥3-member table is plausibly
   written one member per line with trailing commas. The display regex must
   tolerate newlines and a trailing comma inside the brackets — the same
   single-line-only failure mode AC #1's import-region pattern already
   guards against. Add a positive test with a multi-line literal.

   **Linted tables.** All are exported from
   `scripts/little_loops/fsm/validation/__init__.py`:
   - `EVALUATOR_REQUIRED_FIELDS` (**keys** — the evaluator *type* names:
     `exit_code`, `output_json`, …) — `_base.py:45`
   - `EVALUATOR_REQUIRED_FIELDS` (**values**, flattened — the *field* names:
     `frozenset(chain.from_iterable(EVALUATOR_REQUIRED_FIELDS.values()))` =
     `{operator, target, path, pattern, baseline_path, pairs, question,
     verdict_map}`). **This table is required, not optional — see the
     keys-vs-values correction below.**
   - `NON_LLM_EVALUATOR_TYPES` — `_base.py:66`
   - `VALID_OPERATORS` — `_base.py:74`. **Do not omit this one.** BUG-3326
     landed a `VALID_OPERATORS` import into `validate_evaluators` for exactly
     the reason this rule exists; a hand-restated `{"eq", "ne", "lt", "le",
     "gt", "ge"}` is the same defect class as a restated evaluator-type set,
     and leaving it unlinted means the rule does not cover the very move its
     own Ordering section previously depended on. **Confirmed** it is declared as a bare
     `set` (`VALID_OPERATORS = {"eq", "ne", "lt", "le", "gt", "ge"}`,
     `_base.py:74`), not an annotated `frozenset` like `NON_LLM_EVALUATOR_TYPES`
     (`:66`) and `VALID_VISIBILITY` (`:78`). **Tighten it to
     `VALID_OPERATORS: frozenset[str] = frozenset({...})` in this pass** — a
     one-line change that removes the normalize-on-read special case from the
     new rule and makes the three linted tables uniform. Grep first: it is
     re-exported from `fsm/validation/__init__.py:51,168`, so confirm no caller
     mutates it (none should — it is a vocabulary constant).
   - `VALID_VISIBILITY` (`_base.py:78`) — **included** (hedge dropped: with
     the call-syntax exclusion in AC #1b, the noise concern is gone). Three
     members total (`public`, `internal`, `example`), so any subset meeting
     the ≥3 floor is the *entire* table — a high-signal, zero-ambiguity case.

1c. **Keys vs. values — the required-field table must be linted on both.**
   Earlier drafts listed only `EVALUATOR_REQUIRED_FIELDS.keys()` among the
   linted tables while simultaneously prescribing (in AC #1b and in Tests) that
   a literal `['operator', 'target', 'path']` be flagged as a restated
   `EVALUATOR_REQUIRED_FIELDS`. **Those two are contradictory.**
   `EVALUATOR_REQUIRED_FIELDS`'s keys are evaluator *type* names (`exit_code`,
   `output_numeric`, `output_json`, … — `_base.py:45-63`); `operator`, `target`,
   and `path` are members of its **values**. A keys-only implementation would
   not flag that literal, so the prescribed test would fail against the
   prescribed implementation.

   Resolution: lint the **flattened values** as a fourth table, as listed above.
   A hand-restated required-field list (`["path", "operator", "target"]`) is a
   subset of it and is flagged; the ≥3-member / no-outside-members floor still
   does the noise suppression. Report it as "import `EVALUATOR_REQUIRED_FIELDS`
   and index it by evaluator type rather than restating its field lists."

   Note the two `EVALUATOR_REQUIRED_FIELDS`-derived tables are **disjoint**
   (type names vs. field names share no members), so they cannot double-report
   against each other and their relative order in the specificity chain does not
   matter. The AC #1a single-emission concern applies only to the
   `NON_LLM_EVALUATOR_TYPES` ⊆ `EVALUATOR_REQUIRED_FIELDS.keys()` pair.

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
   loop. BUG-3326 has landed (see Ordering); this AC is verified against the
   current tree, not a future one.

   **Verified 2026-08-26, including under AC #1b's widened bracket class.**
   Swept `scripts/little_loops/loops/**.yaml`: the only literal collection displays inside `python3`
   shell gates are the 2-member `('done', 'failed')` tuples
   (`workflow-generator.yaml:486`, `:536`), which sit below the ≥3 floor.
   `validate_evaluators` imports both `EVALUATOR_REQUIRED_FIELDS` and
   `NON_LLM_EVALUATOR_TYPES` directly. No built-in restates an operator
   vocabulary — the sole `"eq"` occurrence is `docs-sync.yaml:72`'s
   `operator: "eq"`, a scalar evaluator field, not a display. Zero violations
   holds both before and after BUG-3326.

   **Re-verified 2026-08-26 under AC #1c's flattened-values table** — the one
   addition that could newly bring literals into scope, since
   `operator`/`target`/`path`/`pattern` are ordinary words that plausibly appear
   in a gate body. Swept every `action_type: shell` state containing `python3`
   across all built-in loop YAMLs for ≥3-member `{}`/`[]`/`()` string-literal
   displays that are subsets of any of the **five** linted tables: **0 matches.**
   AC #3 holds under the full table set.

   **Re-verified 2026-08-28, post-FEAT-3332.** FEAT-3332's landing added new
   `python3` gate bodies to `workflow-generator.yaml` (`init`'s baseline
   capture and the `check_intent_scope` state); both were included in the
   sweep. The nearest candidate literals anywhere in the built-in set — the
   status-value set at `auto-refine-and-implement.yaml:607` and the score-key
   tuple at `autodev.yaml:2214` — each contain members outside every linted
   table (`in_progress`/`blocked`/`deferred`; `score_complexity` etc.), so
   they fail the no-outside-members condition. Still **0 violations**.
4. The rule is documented in
   `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § The Design Rules alongside
   MR-1..MR-14, as an **unnumbered named rule** (`**gate-completeness**`,
   following the existing `policy-table` / `terminal-action-ok` precedent in
   the same table), with the retry-reachability item (below) captured as a
   related-but-unmechanized heuristic. Taking a numbered `MR-15` slot instead
   would force four renumbering touchpoints — including the section heading
   (which drives the GFM anchor) and `.claude/CLAUDE.md`'s prose *and* link to
   `#the-design-rules-mr-1mr-14` — for no analytic benefit.
5. The rule's known coverage limits are documented alongside it (both in the
   rule docstring and the guide entry):
   - it inspects `shell` actions only, so a rule table restated in **prose
     inside a `prompt` action** is not detected (see Known coverage gap
     below);
   - a **dict-display restatement** — the likeliest *full* copy of
     `EVALUATOR_REQUIRED_FIELDS`, e.g. `{"exit_code": [], "output_json":
     ["path", "operator", "target"], ...}` — is not matched as a dict (the
     string-collection regex has no dict form); it is caught only
     *indirectly*, via any ≥3-member nested value list. Accepted
     deliberately: mechanizing dict parsing re-opens the embedded-body
     parsing problem the Detection section closed. Documenting both gaps
     keeps AC #3's "zero violations" from being over-read.

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
#   literals, single- or double-quoted, possibly spanning lines — by regex
#   over the raw action string; the ( case uses a lookbehind (?<![\w)\]])
#   so function calls with string args don't match (AC #1b)
#   (AC #1b: sets alone would miss the list/tuple shapes actually used)
#   for each literal:
#     if len(members) < 3: skip
#     # tables in specificity order, smallest first, so a literal that is a
#     # subset of both NON_LLM_EVALUATOR_TYPES and EVALUATOR_REQUIRED_FIELDS
#     # (the former is derived from the latter) is reported once, against the
#     # tighter of the two — see AC #1a
#     # EVALUATOR_REQUIRED_FIELDS is linted on BOTH its keys (type names) and
#     # its flattened values (field names) — the two are disjoint, so their
#     # relative order does not matter. See AC #1c.
#     for table in (VALID_VISIBILITY, VALID_OPERATORS,
#                   NON_LLM_EVALUATOR_TYPES,
#                   EVALUATOR_REQUIRED_FIELDS.keys(),
#                   frozenset(chain.from_iterable(
#                       EVALUATOR_REQUIRED_FIELDS.values()))):
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
  is embedded inside a YAML shell action as `python3 -c "..."` or a quoted
  heredoc (`python3 << 'PYEOF'`, the current `validate_evaluators` form) —
  extracting it means handling quoting, `\"` escapes, and heredoc delimiters
  before `ast.parse` ever sees valid source. That extractor is its own mini-parser, and it is the part
  most likely to be wrong.
- **The cardinality floor does the work `ast` was meant to do.** Requiring ≥3
  members, all inside the table, is what suppresses incidental matches — not
  the parsing strategy.

This drops the effort estimate from Medium to Small (see Impact).

### Known coverage gap — prose restatement in `prompt` actions

The rule is scoped to `shell` gates, but the live drift risk in the very loop
that motivated this issue is **not** in a shell gate. `attach_evaluators`
(`workflow-generator.yaml:409-465`) is an `action_type: prompt` state whose
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
a shell-only lint will never see it. (A second, smaller gap — a full
dict-display restatement of `EVALUATOR_REQUIRED_FIELDS` inside a shell gate is
caught only via its ≥3-member nested value lists, not as a dict — is
documented in AC #5.) This matters for AC #3: "zero violations
post-fix" is true, but it is true partly because the surviving restatement
lives where the rule does not look — not because the loop stopped restating.
(Note: the `attach_evaluators` citation above refreshed to `:409-465` after
FEAT-3332 shifted the file by ~200 lines.)

### This gap is a value question for the whole issue — SETTLED 2026-08-26

**Decision: ship (a) — shell-only, gap documented — and split (c) into its own
issue.** The evaluation below is retained as the rationale; it is no longer an
open implementation-time question, and Implementation Step 0a is now a
confirmation, not a decision.

Why the split rather than folding (c) in: (c) is a `workflow-generator.yaml`
change — an `init` generator block plus an `attach_evaluators` prompt edit — with
**no overlap** with this issue's surface (`fsm/validation/meta_rules.py`,
`_base.py`, `schema.py`, `structural_rules.py`). Different files, different
tests, different reviewer. Folding it in would make a P3 lint issue carry an
unrelated loop edit, and a revert of either would drag the other. (b) is
rejected outright: a `prompt` action has **no import to offer instead**, so the
warning would have no actionable fix, and prompts legitimately need to name the
vocabulary they ask for.

Accepted consequence, stated plainly: **this rule ships with zero findings and
is a pure forward guard.** That is a legitimate P3 deliverable — the failure
class has occurred once, in this very repo, and cost a full run — but it is not
a fix for anything currently broken. AC #3's zero-violations result is partly an
artifact of where the rule looks, and AC #5 requires saying so in both the rule
docstring and the guide entry.

_Original evaluation, retained:_

The consequence is sharper than "a known limitation". **This rule, as scoped,
cannot catch the one live restatement in the very loop that motivated it.** It
ships with zero findings by construction, and AC #3's zero-violations result is
partly an artifact of where the rule looks rather than evidence the codebase
stopped restating tables. That is a real but modest return for a new meta-rule,
a four-site suppression flag, and ~10 test cases, at P3.

Evaluate these three in order and record the decision before writing code:

- **(a) Ship shell-only, document the gap.** ✅ **CHOSEN.** State the limitation
  in the rule docstring and the guide entry, per AC #5. Honest, but leaves the
  live drift uncaught and the rule findingless.
- **(b) Extend to `prompt` actions** — a second, looser regex over prose (e.g.
  ≥3 table members appearing as backticked tokens in one action), still
  `warning`-severity. Higher recall, meaningfully higher false-positive rate,
  since a prompt legitimately *needs* to name the vocabulary it is asking for.
  And a prompt has **no import to offer instead**, so the warning has no
  actionable fix to suggest — which is what makes (b) weak on its own.
- **(c) Fix the live drift generatively, then re-price this rule.**
  ✅ **Split into its own issue — filed as ENH-3355 (2026-08-28).** The right
  remedy for `attach_evaluators` is not a lint at all: have `init` emit the
  vocabulary from the table itself —

  ```yaml
  # in init, alongside the existing mkdir/echo block
  python3 -c "
  from little_loops.fsm.validation import EVALUATOR_REQUIRED_FIELDS, NON_LLM_EVALUATOR_TYPES
  for t in sorted(NON_LLM_EVALUATOR_TYPES):
      req = EVALUATOR_REQUIRED_FIELDS[t]
      print(f'- {t} — ' + ('no companion fields' if not req else 'requires ' + ', '.join(req)))
  " > "$DIR/evaluator-vocab.md"
  ```

  — and have `attach_evaluators`'s prompt read `evaluator-vocab.md` instead of
  hand-listing it. That is smaller than the lint, eliminates the drift rather
  than warning about it, and is the same import-don't-restate principle applied
  where an import genuinely isn't available. It also mirrors the existing `init`
  stdout-contract constraint: write to a file, keep the `case`/`echo` block last.

Once (c) lands, this rule becomes a pure forward guard against a class with no
live instance anywhere in the tree. **That call has been made deliberately: it
is still worth P3** — a forward guard against a class that has already cost one
full run is a legitimate deliverable — and it is no longer inherited implicitly
from the Ordering section. (c) does **not** need to land first; the two are
independent, and this rule's AC #3 is unaffected by it either way (the prose
restatement lives in a `prompt` action the rule does not inspect).

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

_Wiring pass added by `/ll:wire-issue` (2026-08-27):_
- `CHANGELOG.md` — add an entry for the new rule, following the established
  precedent of a changelog line for every prior validation-rule addition
  (e.g. ENH-2896 → MR-14, ENH-2934 → tamper-guard, ENH-2997 → prepatch-check).
  This was the one wiring gap not already covered by the issue's own research.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/structural_rules.py` — add
  `_validate_gate_completeness` to the `from little_loops.fsm.validation.meta_rules
  import (...)` block (alongside `_validate_artifact_isolation`,
  `_validate_meta_loop_evaluation`, etc.) and add its
  `errors.extend(_validate_gate_completeness(fsm))` call inside `validate_fsm()`,
  grouped with the other MR-1..MR-6 meta-rule calls (immediately after
  `errors.extend(_validate_missing_scope(fsm))`, before
  `errors.extend(_validate_bash_default_interpolation(fsm))`).
  > ⚠ Superseded — not literal adjacency; 5 other calls sit between; see § Codebase Research Findings under Integration Map
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
    as a **list** (`['operator', 'target', 'path']` vs the flattened
    `EVALUATOR_REQUIRED_FIELDS` **values** — see AC #1c; this case does *not*
    match the table's keys and would silently pass a keys-only implementation)
    and as a **tuple** (`('eq', 'ne', 'lt')` vs `VALID_OPERATORS`) is flagged
    identically to the set form — parametrize over the three bracket shapes so
    a set-only regex fails the suite.
  - **keys-vs-values coverage** (AC #1c): a literal of evaluator *type* names
    (`['exit_code', 'output_json', 'convergence']`) and a literal of evaluator
    *field* names (`['path', 'operator', 'target']`) are **both** flagged, and
    each names the correct table in its message. This pair is what pins the
    keys/values distinction; a keys-only implementation passes the first and
    fails the second.
  - **call-syntax exclusion** (AC #1b): a function call with ≥3 table-member
    string args (`check("eq", "ne", "lt")`) is **not** flagged — pins the
    `(?<![\w)\]])` lookbehind.
  - **multi-line display** (AC #1b): a ≥3-member restatement written one
    member per line with a trailing comma is flagged — pins
    newline-tolerance inside the brackets.
  - **below-floor tuple stays clean**: the in-repo `('done', 'failed')` literal
    (`workflow-generator.yaml:486`, `validate_evaluators` state) is **not** flagged — the 2-member case that
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

_Wiring pass added by `/ll:wire-issue` (2026-08-27):_
- `gate_completeness_ok`'s round-trip test (schema.py field + `from_dict` +
  `to_dict`, per the Wiring Phase entry below) has an exact existing template:
  `TestPartialRouteOk` in `scripts/tests/test_fsm_schema.py:3664-3699` (three
  methods — `..._true_round_trips`, `..._false_omitted_from_dict`,
  `..._defaults_false`). A second instance of the same shape exists for
  `unsafe_context_interpolation_ok` at `test_fsm_schema.py:4154`, confirming
  this is the established convention, not a one-off.
- The "recognized as top-level key" check (i.e. that `gate_completeness_ok`
  in `KNOWN_TOP_LEVEL_KEYS` produces no "Unknown top-level" warning) is not
  automatically covered by the generic tests at `test_fsm_schema.py:1788-1827`
  (`test_unknown_top_level_keys_warn` / `test_known_keys_no_warning`) — those
  only test the generic mechanism. The per-flag precedent is
  `TestArtifactIsolation.test_shared_state_ok_recognized_as_top_level_key`
  (`test_fsm_validation_meta_rules.py:370-387`), and the equivalent for
  `unsafe_context_interpolation_ok` at `test_fsm_validation_shell_safety.py:180-199`.
  `TestGateCompleteness` needs its own such method, following this two-flag
  precedent.
- Closest existing fixture pattern for a rule scoped to `action_type: shell`
  states matched by substring (there `${context.*}`, here `python3` + a
  restated literal): `TestUnsafeContextInterpolation` in
  `scripts/tests/test_fsm_validation_shell_safety.py:202-279`. Its
  `_simple_fsm(action, *, action_type="shell", <suppression_flag>: bool =
  False)` helper builds a minimal two-state `work → done` `FSMLoop` with the
  shell action injected as a raw string — a more precise template than
  `TestArtifactIsolation` for this rule's specific shape (MR-3 does not gate
  on a `python3` substring).
- Confirmed `VALID_OPERATORS`'s `set` → `frozenset[str]` tightening (AC #1a,
  Implementation Step 1a) is safe: no test anywhere pins it as a `set` via
  `isinstance`/`type()`, and its only production consumers
  (`structural_rules.py`'s `operator not in VALID_OPERATORS` /
  `sorted(VALID_OPERATORS)`, and `workflow-generator.yaml`'s generated-shell
  membership assertion) use membership/iteration only — no mutation call
  sites (`.add(`/`.discard(`/`.remove(`/`.update(`/`|=`) exist anywhere in
  the repo. No existing test needs updating or will break.
- Confirmed `validate_fsm()`/`load_and_validate()` have callers beyond
  `ll-loop validate`'s `cmd_validate` — `executor.py:871` and
  `structural_rules.py:282` (sub-loop recursion), `cli/loop/edit_routes.py`,
  `scaffold_verify.py`, `scaffold_eval.py`, `cli/loop/_helpers.py`,
  `cli/loop/info.py`, `cli/loop/run.py`, and `cli/doctor.py` (health-check
  aggregation across all loops). All consume the returned warning list
  generically (append/aggregate), so the new WARNING-severity rule needs no
  additional wiring at any of these call sites — confirms the issue's
  existing "no new plumbing needed" finding extends beyond just the CLI.
- `docs/reference/CLI.md` and `docs/reference/API.md` each maintain their own
  independent MR-rule enumeration and are **already stale** relative to each
  other and to `HARNESS_OPTIMIZATION_GUIDE.md` (both are missing several
  already-shipped unnumbered rules, e.g. `abstention_route_ok`). Given this
  inconsistent precedent, adding a bullet for the new rule to either is
  optional, not required — `HARNESS_OPTIMIZATION_GUIDE.md` (already in Files
  to Modify) remains the one place full rule-table parity is expected.

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

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- **Insertion-point claim corrected**: the Wiring Phase's "immediately after `errors.extend(_validate_missing_scope(fsm))`, before `errors.extend(_validate_bash_default_interpolation(fsm))`" is not literal adjacency. Current sequence in `structural_rules.py` (`validate_fsm()`, calls at lines 1139-1155): `_validate_meta_loop_evaluation` (1139) → `_validate_input_key_without_guard` (1141) → `_validate_missing_scope` (1143) → `_validate_artifact_isolation` (1145) → `_validate_harness_multimodal_evaluator_blind_spot` (1147) → `_validate_partial_route_dead_end` (1149) → `_validate_artifact_overwrite` (1151) → `_validate_generator_fix_discipline` (1153) → `_validate_bash_default_interpolation` (1155). Five other rule calls sit between the two named anchors. The new call can go anywhere in this MR block (1139-1155) — precise adjacency to `_validate_missing_scope` is not required or accurate as stated.
- **`--json` vs plain-text warning exposure are two separate code paths, not one shared line.** `load_and_validate()` (`structural_rules.py:1736-1850`) branches on `raise_on_error`: when `False` (the `--json` case), it returns `error_list + all_warnings` at line 1840 *before* ever reaching the `logger.warning(...)` calls at lines 1847-1848 — those lines are plain-text-only. The `--json` path is wired instead through `cmd_validate()` in `scripts/little_loops/cli/loop/config_cmds.py` (starts line 14): `as_json = getattr(args, "json", False)` (line 24) sets `raise_on_error=not as_json` (line 35), and the returned violations are serialized via `print_json(...)` (~line 69-74). Both paths do expose WARNING-severity `ValidationError`s end-to-end with no new plumbing needed — the existing finding's conclusion holds — but citing `structural_rules.py:1848` as covering both paths is inaccurate; the `--json` path's actual site is `cmd_validate()` in `config_cmds.py`.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Correction**: `docs/reference/CLI.md` (lines 862-885) and `docs/reference/API.md` (lines 6406-6419, 5558-5574) already fully enumerate MR-1 through MR-14 with their suppression flags — both are current, not stale, contradicting the earlier Documentation note that both were "already stale ... missing several already-shipped unnumbered rules". The "optional, not required" call for updating these two files can stand, but not on an "inconsistent precedent" rationale — if strict parity is wanted, adding the new rule there is a straightforward addition to an already-current table, not a catch-up fix.
- A sibling rule-family module, `scripts/little_loops/fsm/validation/evaluator_rules.py`, exists and is not referenced anywhere in this issue's Integration Map or Similar Patterns. It houses MR-8/10/12/13 and other rules (`_validate_terminal_action_ok`, `_validate_parse_swallow`, `_validate_abandonment_verdict`, `_validate_pruning_profile`, `_validate_tamper_guard`, `_validate_prepatch_check`, `_validate_llm_evidence_contract`, `_validate_haiku_pinned_generator`, `_validate_session_mode_evaluator_inheritance`, `_validate_classify_route_default`). Its MR-13 detector (`_HARDCODE_VERDICT_SUCCESS_RE`) is the closest sibling precedent for "scan a `python3` shell body for a literal instead of an import", though it targets a single verdict string rather than a rule-table collection — `_validate_artifact_isolation` (MR-3), already cited, remains the closer structural match.
- Confirmed no existing rule anywhere in `fsm/validation` regex-matches a Python `import` statement (searched unfiltered for `import\s*\(` and equivalents — zero hits in any `.py` rule file). AC #1's `_IMPORT_BLOCK_RE` sketch is genuinely novel; there is no existing in-repo pattern to adapt for it.
- The escape-hatch flag convention is five touchpoints, not four as currently tallied: `KNOWN_TOP_LEVEL_KEYS` (`_base.py`) + `FSMLoop` field + `to_dict` + `from_dict` (`schema.py`, three sites) + the rule function's own `if fsm.<flag>: return []` guard clause (confirmed via `abstention_route_ok` at `structural_rules.py:1577`, and `partial_route_ok` at `meta_rules.py:235` and independently at `evaluator_rules.py:616`). The guard is already implied by the Proposed Solution's detection sketch ("Skip entirely if fsm.gate_completeness_ok") but was never counted as a distinct site in the "four total sites" tally.
- Confirmed `errors.extend(...)` call position inside `validate_fsm()`'s MR block is inert for correctness beyond same-severity ordering: `load_and_validate()` (`structural_rules.py:1836-1838`) buckets the flat `errors` list into `error_list` (severity==ERROR) and `all_warnings` (severity==WARNING) downstream, always placing all ERRORs before all WARNINGs in the final `--json` output regardless of `errors.extend(...)` call order. This corroborates the existing "the new call can go anywhere in this MR block" finding with the actual mechanism.
- New edge case for CLI-level test design: the plain-text `ll-loop validate` path suppresses **all** WARNINGs whenever the loop also has any ERROR-severity violation — `load_and_validate()` raises `ValueError` from `error_list` alone (`structural_rules.py` ~line 1843-1845) before ever reaching the `logger.warning(...)` loop. A CLI-level plain-text test for the new rule's WARNING (mirroring `test_validate_no_json_warns_mr13_hardcoded_success_verdict`) must use a fixture loop with zero ERROR-severity violations, or the warning will not appear in that output. The `--json` path is unaffected (returns `error_list + all_warnings` unconditionally).

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
-> per offending `shell` state, parses the `python3` gate body (`-c` string or
quoted heredoc) and checks
literal set/frozenset displays against the exported tables in
`scripts/little_loops/fsm/validation/_base.py`

## Implementation Steps

0. ~~Confirm BUG-3326 has landed (see Ordering) — AC #3 depends on it.~~
   **Confirmed landed** (status: done); no longer a blocking step.
0a. **Coverage-gap decision: SETTLED — (a), shell-only, gap documented; (c)
   split out.** No evaluation needed at implementation time. The one action
   item — file the (c) follow-up issue (generative `evaluator-vocab.md` in
   `workflow-generator.yaml`'s `init`, consumed by `attach_evaluators`'s
   prompt in place of its hand-listed vocabulary) — is **done: ENH-3355**
   (filed 2026-08-28). It is independent of this issue and need not land
   first.
1. Implement `_validate_gate_completeness` in `meta_rules.py` using a
   module-level compiled `re.Pattern` over the raw action string, matching set,
   frozenset, list, and tuple displays (AC #1b), with the ≥3-member /
   no-outside-members floor from AC #1, **all five linted tables** — including
   `VALID_OPERATORS` and, per AC #1c, `EVALUATOR_REQUIRED_FIELDS` on *both* its
   keys and its flattened values — and the smallest-first /
   one-warning-per-literal ordering from AC #1a.
1a. Tighten `VALID_OPERATORS` to `frozenset[str]` in `_base.py:74` (AC #1) so
   the three linted tables are uniform. **Land this as its own commit**, before
   or after the rule but never mixed into it: it is an unrelated type
   tightening riding along for convenience, and keeping it separate means a
   revert of the rule does not drag it back (or vice versa). Grep first —
   it is re-exported from `fsm/validation/__init__.py:51,168`; confirm no
   caller mutates it.
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
4a. Add the two import-detection tests: table name **only in a comment** is
   still flagged; the parenthesized multi-line import form is **not** flagged
   (AC #1, "Define 'already imports the table' precisely").
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
- Add a `CHANGELOG.md` entry for the new rule, per established precedent for
  prior validation-rule additions (added 2026-08-27).
- Add `TestGateCompletenessOk` round-trip tests to `test_fsm_schema.py`
  (template: `TestPartialRouteOk`, lines 3664-3699) and a
  `test_gate_completeness_ok_recognized_as_top_level_key` method inside
  `TestGateCompleteness` (template:
  `TestArtifactIsolation.test_shared_state_ok_recognized_as_top_level_key`,
  `test_fsm_validation_meta_rules.py:370-387`) (added 2026-08-27).

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

**gate-completeness** (unnumbered named rule, per AC #4). Flag any `shell`
gate that hardcodes a literal set of values which a little-loops validator
exposes as an importable table — e.g. a literal evaluator-type set instead of `NON_LLM_EVALUATOR_TYPES`, or
literal required-field lists instead of `EVALUATOR_REQUIRED_FIELDS`. Where the
terminal gate exposes its rules as data, import rather than restate.

Detection: in `fsm/validation`, for each `action_type: shell` state whose action
contains `python3` (unconditionally — no terminal-gate precondition, see
Scoping above), look for a literal collection display — set, frozenset,
list, or tuple of string literals; possibly multi-line; a `(` preceded by an
identifier character is call syntax, not a display (AC #1b) — of
**≥3 members, all of them**
members of a known exported table (`EVALUATOR_REQUIRED_FIELDS` **keys**,
`EVALUATOR_REQUIRED_FIELDS` **flattened values**, `NON_LLM_EVALUATOR_TYPES`,
`VALID_OPERATORS`, optionally `VALID_VISIBILITY`), in
an action that does not import that table. The keys/values split matters: a
restated required-*field* list (`['path', 'operator', 'target']`) is a subset of
the values, not the keys, and a keys-only rule would miss it entirely — see
AC #1c. Tables are checked smallest-first and
at most one warning is emitted per literal, since `NON_LLM_EVALUATOR_TYPES` is
derived from `EVALUATOR_REQUIRED_FIELDS` and would otherwise double-report.
Severity `warning` — a restatement is sometimes deliberate (a *narrower* curated
vocabulary) — suppressed by `gate_completeness_ok: true`.

Current blast radius: `workflow-generator.yaml`'s `validate_evaluators` was the
only built-in doing this in a `shell` gate, and it has been fixed, so the rule
ships with zero violations and acts purely as a forward guard. Re-confirmed
after adding `VALID_OPERATORS` to the linted set: no built-in loop restates an
operator vocabulary — the only `"eq"` occurrence across `scripts/little_loops/loops/**.yaml` is
`docs-sync.yaml:72`'s `operator: "eq"`, a single evaluator field, not a
collection display, and well under the ≥3-member floor. Re-confirmed again
after widening detection to list and tuple displays (AC #1b): the only literals
that widening newly brings into scope are the 2-member `('done', 'failed')`
tuples in `workflow-generator.yaml:486,536`, both below the floor. Re-confirmed
a third time after adding the flattened-`EVALUATOR_REQUIRED_FIELDS`-values table
(AC #1c): a sweep of every `python3` shell gate across all built-in loops for
≥3-member displays subset to any of the five tables returns **0 matches**.
Caveat: the same loop still restates the table in prose inside
`attach_evaluators`'s **prompt**, which this rule does not inspect — see Known
coverage gap. That live drift is tracked as ENH-3355, split out per the
settled coverage-gap decision.

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
- **FEAT-3332's containment gate** (split from BUG-3327) — a scope violation routed to `capture_intent`
  is *structurally* unrepairable (the out-of-scope file is already written), and
  the edge is unbounded, so the loop wedges until `max_steps`. "Can this state
  repair this fault?" catches it; no static rule does.
- **BUG-3326's operator-check predicate** — the *inverse* case, and the one this
  rule's own family is most likely to cause. An intermediate gate written
  slightly **stricter** than the terminal validator (`'operator' in ev` vs
  `operator is not None`) rejects artifacts the terminal gate accepts, and
  `validate_evaluators`'s `on_no: attach_evaluators` edge is unbounded, so a
  non-defect wedges the loop. The heuristic's second question follows from the
  first: not only "can this state repair this fault?" but "is this fault real —
  does the terminal gate agree?" Gate-completeness pushes authors to import the
  table; it does not stop them from mis-applying it, and a subset gate laundering
  defects and a superset gate wedging on non-defects are the two failure modes of
  the same move.

## Ordering

**BUG-3326 has landed** (status: done, confirmed 2026-08-27). It added the
`VALID_OPERATORS` import to `workflow-generator.yaml`'s `validate_evaluators`
— the same import-don't-restate move this rule lints for — and AC #3 ("zero
violations against the current built-in loop set") assumes that tree, which is
now the current tree. No ordering constraint remains; this issue can be
implemented directly.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §6.

## Related Key Documentation

- `.claude/CLAUDE.md` — `## Loop Authoring` documents the MR-1..MR-14 rule set enforced by `ll-loop validate`, which this issue extends with a new MR rule.
- `docs/reference/API.md` — documents `little_loops.fsm.validation`, the module this issue's new `_validate_gate_completeness` function is added to.

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-29T18:14:01 - `48e9d546-94fd-4111-9bec-ae917ba67439.jsonl`
- `/ll:confidence-check` - 2026-08-29T17:56:13 - `8447b8ae-6392-4778-9269-a7326a6ec15e.jsonl`
- `/ll:refine-issue` - 2026-08-29T17:52:27 - `b49cfdc1-e799-4d98-aa39-ef2212184ad7.jsonl`
- `/ll:refine-issue` - 2026-08-29T17:52:13 - `b49cfdc1-e799-4d98-aa39-ef2212184ad7.jsonl`
- `/ll:wire-issue` - 2026-08-27T15:27:35 - `2ab74eb6-4b00-4645-8ae0-d69b8041979f.jsonl`
- `/ll:refine-issue` - 2026-08-27T15:14:46 - `a812da17-9f21-4c2c-ad6d-806ac51d6467.jsonl`
- `/ll:refine-issue` - 2026-08-27T15:14:37 - `a812da17-9f21-4c2c-ad6d-806ac51d6467.jsonl`
- `/ll:confidence-check` - 2026-08-26T20:09:17 - `fdfe1063-50b8-41a2-aae7-c524a32eadad.jsonl`
- `/ll:wire-issue` - 2026-08-26T19:28:19 - `1f462280-8e7a-4295-8360-c2cd201baeea.jsonl`
- `/ll:refine-issue` - 2026-08-26T19:14:22 - `0809cdb6-a88f-42a7-9e51-e57ee8a63f3a.jsonl`
- `/ll:format-issue` - 2026-08-26T19:09:04 - `8c47cf34-66af-4a75-8c4b-c7a8efe5d7ec.jsonl`
