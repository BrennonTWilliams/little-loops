---
id: ENH-3281
type: ENH
title: Generalize the this-repo-hardcode gate across all built-in loops
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:58:33Z'
labels:
- loops
- gate
- hardcode
- test-coverage
- follow-up
relates_to:
- ENH-3277
- BUG-3276
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 95
score_complexity: 23
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 24
size: Small
---

# ENH-3281: Generalize the this-repo-hardcode gate across all built-in loops

## Summary

Split out of **ENH-3277** step 6b (2026-08-21). BUG-3276 fixed one built-in loop that hardcoded
this repo's layout; `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
guards that one loop. The defect *class* — a shipped built-in loop hardcoding `scripts/`,
`scripts/tests/`, or `scripts/little_loops/`, live in every `local-editable` consuming project —
has no gate. Promote that assertion to a gate parametrized over all built-in loop files, the same
shape `test_no_inline_project_command_config_read` already uses.

## Current Behavior

`scripts/tests/test_builtin_loops.py`'s `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
asserts over `incremental-refactor.yaml` only. Any other built-in loop may hardcode a this-repo
path without failing anything.

## Expected Behavior

A parametrized gate over `scripts/little_loops/loops/**/*.yaml` fails on a this-repo path in a
state's action body **or in a top-level `context:` default value**, with a small documented
exemption set.

## Motivation

A hardcoded this-repo path in a shipped loop is silent in this repo and broken everywhere else.
`.claude/CLAUDE.md` is explicit that all little-loops projects on this machine are
`local-editable` against this checkout, so a bad path is live in every one of them with no
reinstall step. This is the `_PENDING_CONVERSION` protection applied to the sibling defect class:
ENH-3277 converts the one known instance (`evaluation-quality.yaml:63`), which leaves the class
open to a next instance.

## Scope Boundaries

**In scope**: one parametrized gate over `states[*].action` bodies **and top-level `context:`
values** in `scripts/little_loops/loops/**/*.yaml` (including `lib/`, excluding dot-directories),
a two-entry exemption set, an exemption-hygiene guard, a module-level detector helper so the
negative test is possible, a one-line dot-directory fix to the sibling gate's enumeration,
retiring the superseded incremental-refactor assertion, one `HARNESS_OPTIMIZATION_GUIDE.md`
bullet, and capturing the `dead-code-cleanup.yaml` `scope:` follow-up.

**Out of scope**:

- **`scope:` list entries, `description:` fields, and `#` comments.** See Program Design →
  Decision Rules: these are not exec-time content, so a path there is not the live defect this
  gate exists to catch.
- **`states[*].evaluate.prompt` / `.source`.** Structurally identical string fields that could
  carry the same defect class, but no hit in the current inventory lives there, and widening
  would force a fresh exemption survey over prompt text. If an instance ever appears, widen this
  same gate rather than adding a second one (DECIDED 2026-08-21).

> **`context:` defaults moved OUT of the out-of-scope list — REVISED 2026-08-22.** Two earlier
> revisions excluded them on the grounds that they "are not exec-time content" and that
> `test_context_test_cmd_has_no_hardcoded_literal` gates them separately. **Both premises are
> wrong**, and together they left this gate closing the class *around* the very instance that
> motivated it:
>
> - A `context:` default **is** exec-time content. It is the value substituted into
>   `${context.test_cmd}` when a state action runs — that substitution is the whole mechanism.
> - **BUG-3276 was a `context:` default, not an action-body literal.** Its Summary
>   (`.issues/bugs/P2-BUG-3276-*.md:31-33`) reads: "`incremental-refactor.yaml` declares
>   `test_cmd: "python -m pytest scripts/tests/"` as a context default (`:12`) and executes it
>   bare as an exit-code-gated state (`:31-36`)." An action-only gate would not have caught the
>   defect this issue exists to generalize.
> - `test_context_test_cmd_has_no_hardcoded_literal` is **not** a class gate. It is a method on
>   `TestIncrementalRefactorLoop` (`scripts/tests/test_builtin_loops.py:12666-12669`) asserting
>   `data["context"]["test_cmd"] == ""` for **one loop and one key**. The other 113 loop files
>   have no context-default coverage at all.
>
> Cost of widening, measured: the survey grep returns exactly **one** context-value hit in the
> whole tree (`loop-specialist-eval.yaml:23`), already a known-legitimate this-repo eval loop.
> So the widening costs one additional exemption entry and closes the actual BUG-3276 surface
> across all 114 loop files.
- **Fixing `dead-code-cleanup.yaml:8-9`'s `scope: ["scripts/"]` itself.** A real layout guess
  shipped to consuming projects, but out of this gate's scope by the rule above. Implementation
  Step 5 captures it as its own issue rather than widening the gate here.
- **Converting `cli-anything-bootstrap.yaml:453` to `importlib.resources`.** Its path is
  package-internal, not a consuming-project layout guess, so it is exempted rather than fixed;
  the resolution change is a separate concern.

## Proposed Solution

Parametrize over all built-in loop files with an `_EXEMPT`-style set, mirroring
`test_bug3269_test_cmd_resolution_gate.py`.

**Scope the gate to exec-time content, not comments.** A naive text match over whole files
produces mostly-illegitimate hits (see the survey below); restricting to `states[*].action` plus
top-level `context:` values excludes the comment hit outright and keeps the exemption set small
enough to be meaningful, while still covering BUG-3276's actual surface (see the Scope
Boundaries revision note).

### Exemption survey — verified 2026-08-21

ENH-3277 step 6b claimed *"only legitimate hits to exempt today are `loop-specialist-eval.yaml:12,23`"*.
That was wrong. `grep -rlE "scripts/tests|ruff check scripts|mypy scripts|scripts/little_loops"`
over `scripts/little_loops/loops/**/*.yaml` returned five files when this survey was written
(2026-08-21).

> **Re-verified 2026-08-22 — the survey is now 4 hits across 3 files, not 6 across 5.** ENH-3277
> landed (`Completed`), removing both of the "must change" rows below: `evaluation-quality.yaml:63`
> and `harness-single-shot.yaml:60` no longer match. The three remaining files are
> `cli-anything-bootstrap.yaml:453`, `loop-specialist-eval.yaml:12,23`, and
> `oracles/code-run-gate.yaml:407`. **Re-confirmed by a third run of the same grep on
> 2026-08-22** during the pre-implementation review: same 4 hits, same 3 files, no drift.
> Table rows are kept for provenance with their dispositions updated in place.

| File | Hit | Disposition |
|---|---|---|
| `loop-specialist-eval.yaml:12,23` | `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` | **Exempt** — genuine this-repo eval fixture; the loop only makes sense in this repo. `:23` is a `context:` value, which is **in** the gate's scope as of the 2026-08-22 widening, so this file does need an exemption entry after all (`:12` is a `scope:` entry and remains out of scope independently) |
| `cli-anything-bootstrap.yaml:453` | `scripts/little_loops/loops/lib/task-templates/…` | **Exempt** — package-internal path, not a consuming-project layout guess. Arguably should resolve via `importlib.resources` instead, but that is a separate change |
| `oracles/code-run-gate.yaml:407` | source citation inside a comment | **Not a hit** once the gate is scoped to action bodies — confirmed 2026-08-22: the comment block sits at state level inside `states.aggregate`, *above* that state's `description:`/`action_type:` keys, so it is a YAML comment stripped by `safe_load`, not text inside a block scalar |
| `harness-single-shot.yaml:60` | `# action: "python -m pytest scripts/tests/ -q --tb=no"` | **FIXED — verified gone 2026-08-22.** Was an `# EXAMPLE:` scaffold users clone, so it taught the anti-pattern. ENH-3277's rewrite landed; the line now reads `#   action: "pytest -q --tb=no"`. No hand-fix needed |
| `evaluation-quality.yaml:63` | `ruff check scripts/` | **FIXED — verified gone 2026-08-22.** ENH-3277 step 5 landed (ENH-3277 is `Completed`); the survey grep no longer returns this file at all |

Net exemption set after this issue: **two files** — `cli-anything-bootstrap.yaml` (its `:453`
hit is inside a `states[*].action` body) and `loop-specialist-eval.yaml` (its `:23` hit is a
`context:` value).

> **This count has now moved twice; read the history so it does not move a third time.** The
> original text said two files. A refine pass narrowed it to one, correctly, *given* an
> action-only gate. The 2026-08-22 review then widened the gate to include `context:` values
> (see Scope Boundaries), which brings `loop-specialist-eval.yaml` back in. **Two is final for
> the gate as now specified.** If a later pass narrows the scope back to actions only, it must
> also drop `loop-specialist-eval.yaml` from the exemption set — and it must first read the
> Scope Boundaries revision note explaining why narrowing misses BUG-3276's own surface.

**Exemptions are file-level, matching the sibling gate's precedent.** `_PERMANENT_EXEMPTIONS`
in `test_bug3269_test_cmd_resolution_gate.py:58-62` keys whole files, and this gate does the
same for consistency. Consequence to accept knowingly: exempting `loop-specialist-eval.yaml`
for its `context:` value also stops checking its action bodies, and likewise for
`cli-anything-bootstrap.yaml`. Both are single-purpose files where that is tolerable; do not
extend the pattern to a widely-edited loop without switching to per-surface exemptions.

**Known instance outside the gate's scope — flagged, not covered here.**
`dead-code-cleanup.yaml:8-9` ships `scope: ["scripts/"]` — a this-repo layout default in a
generic built-in loop. `scope:` entries are deliberately outside this gate (see Program Design →
Decision Rules), and unlike `loop-specialist-eval` (a this-repo eval loop whose scope hit is
legitimate), this one is a genuine layout guess shipped to consuming projects. Not this issue's
work: capture it as a separate issue rather than widening the gate here, so the "scope: is out
of scope" rule does not silently bless it. **Status 2026-08-22: still uncaptured** — no issue in
`.issues/` covers it. Promoted to Implementation Step 5 so it cannot be dropped again.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- ~~**Exemption set revision**: scoping the gate to `states[*].action` bodies (as this section already specifies) changes the exemption set from the two files the survey table claims. `loop-specialist-eval.yaml`'s two hits (`:12` a `scope:` list entry, `:23` a `context:` default) both fall *outside* `states[*].action` once the scope restriction is applied literally — neither needs an exemption entry under that scoping. `cli-anything-bootstrap.yaml:453` remains the one confirmed in-scope hit needing exemption (package-internal task-template path inside an `action` body). Net: one exemption, not two, if the gate is implemented exactly as scoped here.~~
  **Superseded 2026-08-22 (scope widening).** This finding was a correct deduction from a premise that has since changed: the gate now covers top-level `context:` values as well as action bodies, because BUG-3276's own defect lived in a `context:` default (see Scope Boundaries). `loop-specialist-eval.yaml:23` is therefore back in scope and back in the exemption set. **Net: two exemptions.** The finding's reasoning about `:12` (a `scope:` list entry) still holds — that hit remains out of scope.
- ~~**`evaluation-quality.yaml:63` re-verified 2026-08-21**: `ruff check scripts/ 2>&1 | tee ${context.run_dir}/eval-lint-results.txt || true`, inside `states.evaluate_code.action` — still present in the current tree. The survey table's "Already fixed by ENH-3277 step 5" disposition does not hold as of this research pass; Implementation Step 1 ("Land ENH-3277 step 5 first, or confirm it landed") should resolve to "not landed" today.~~
  **Superseded 2026-08-22 — this finding has inverted.** ENH-3277 is now `Completed`; its step 5 landed and the `ruff check scripts/` line is gone. The survey table's original "Already fixed" disposition is the correct one after all, and **Implementation Step 1 resolves to "landed"**. Nothing blocks the gate on this file.

## Integration Map

### Files to Modify

- **New module** `test_builtin_loop_hardcode_gate.py`, to be created under `scripts/tests/`
  (decision below) — the gate itself. Cited without a full path deliberately: it does not exist
  yet, and `ll-issues format-check` reports any untracked path as a `stale_file_ref`
- `scripts/tests/test_builtin_loops.py:12671-12675` — the incremental-refactor-only assertion it
  replaces. **Anchor corrected 2026-08-22**: two earlier revisions cited `:12331-12335`, which is
  ~340 lines off; the real location of
  `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path` is `:12671-12675`,
  with `test_context_test_cmd_has_no_hardcoded_literal` immediately above at `:12666-12669`
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:98-99` — one-line dot-directory fix to
  `_all_loop_files()` (see Implementation Step 3b)
- ~~`scripts/little_loops/loops/harness-single-shot.yaml:60` — the example-comment fix~~ — **no
  longer a target**; ENH-3277 already rewrote this line (verified 2026-08-22)

**New module, not an addition to the bug3269 gate. DECIDED 2026-08-22.** The Integration Map
previously left this as "a new gate module, **or** an added parametrized test alongside
`test_bug3269_test_cmd_resolution_gate.py`" — an unresolved fork, and one that silently decides
the enumeration question below, so it cannot stay open. Go with a new module,
`test_builtin_loop_hardcode_gate.py` under `scripts/tests/`, because: that module's docstring
(`:1-35`) scopes it tightly to BUG-3269's two named assertions and ENH-3288 just closed its
conversion pass out; a third, unrelated rule about path literals would make the module's stated
contract false. Cost of the split is duplicating `_all_loop_files()`/`_relative()` — ~6 lines,
and the new copy has to differ anyway (dot-directory exclusion, see Program Design → Decision
Rules).

### Tests

- The gate itself is the test.
- **A negative test requires a module-level detector helper — the fixture-file framing does not
  work.** Two earlier revisions said "add a negative fixture (a loop YAML with a hardcoded
  `scripts/tests/` path in an action body) asserting the gate fails on it". That is not
  implementable: the gate is `pytest.mark.parametrize`d over the real files under
  `scripts/little_loops/loops/`, so a fixture YAML placed there would **fail the gate** rather
  than be tested by it, and one placed anywhere else would never be enumerated. Factor the match
  into a module-level `_hardcode_hits(text: str) -> list[str]` (see Program Design → Signatures)
  and have the negative test call it directly on an inline string. That is what keeps the gate
  from silently stopping matching, which was the real intent.
- An exemption-hygiene guard (see the Wiring Phase note).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug3269_test_cmd_resolution_gate.py` — `_PENDING_CONVERSION` (line ~61) already
  exempts `harness-single-shot.yaml` from that gate's inline-config-read check, tied to ENH-3277 —
  a different rule than the new hardcode-literal gate this issue adds, but the same file, so editing
  this module for the new gate touches a set that already names this filename for an unrelated reason
  [Agent 1/3 finding]
- `scripts/tests/test_fsm_loop_paths.py:71-80` — `LOOPS_DIR.rglob("*.yaml")` collector helper excludes
  dot-directories (`.history/`, `.running/`); the new gate's file-enumeration should apply the same
  exclusion if it walks the loops dir independently of `_all_loop_files()` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:562-582` — names/links `test_bug3269_test_cmd_resolution_gate.py`
  as "a static mirror-drift gate" covering only its two existing checks, and separately states the
  "never hardcode a project command literal" rule without pointing to any gate that enforces it;
  needs a third bullet or amended description once the new gate lands [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

> ⚠ Anchor `scripts/tests/test_fsm_loop_paths.py:71-80` (cited above under Dependent Files (Callers/Importers)) no longer resolves — `test_fsm_loop_paths.py` is 61 lines total, so lines 71-80 fall past EOF; `resolve_anchor()` clamps out-of-range line numbers rather than failing, so the citation silently resolved to the file's last function instead of erroring. The dot-directory-exclusion `.rglob("*.yaml")` collector the citation describes lives at `scripts/tests/test_builtin_loop_interpolation.py:76-77` instead, not in `test_fsm_loop_paths.py`.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `scripts/tests/test_builtin_loops.py:12671-12675::TestIncrementalRefactorLoop::test_no_state_hardcodes_this_repo_test_path` | Asserts no `scripts/tests` literal appears anywhere in `incremental-refactor.yaml`'s full `yaml.dump`'d parsed content (whole-file scope, single loop) | **KEPT — reversed 2026-08-22** (was: DROPPED) | See the coverage-delta note below |
| `scripts/tests/test_builtin_loops.py:12666-12669::TestIncrementalRefactorLoop::test_context_test_cmd_has_no_hardcoded_literal` | Asserts `data["context"]["test_cmd"] == ""` for `incremental-refactor.yaml` specifically | PRESERVED | Now **overlaps** the new gate rather than being disjoint from it, since the gate covers `context:` values as of the 2026-08-22 widening. Keep it anyway: it asserts the stronger `== ""` override-slot contract, not merely the absence of a this-repo literal |

**Coverage delta — why the old assertion is kept, not retired.** Earlier revisions said dropping
`test_no_state_hardcodes_this_repo_test_path` "loses no coverage" because the `context:` surface
is separately gated. That was overstated in two ways. First, the old assertion runs over the
whole `yaml.dump`'d document, so for `incremental-refactor.yaml` it also covers `scope:`,
`description:`, and `evaluate.prompt` — three surfaces the new gate deliberately excludes.
Second, its own message ("no state action **or context default** may hardcode this repo's test
path") shows it was written as a two-surface check. The honest accounting: retiring it trades a
real, if narrow, loss for tidiness. It is four lines, it is green today, and it costs nothing to
leave in place, so **keep it** and let the new gate subsume it in practice rather than on paper.

## Program Design

### Codebase Research Findings

### Types
- N/A — no new data types; the gate walks existing parsed YAML mappings.

### Signatures
- `action: str` — per-state field on the `yaml.safe_load`'d loop dict; always a plain string, block-scalar (`|`/`>`) vs. quoted-string YAML style is not distinguishable post-parse, only content. Absent on terminal states (`{"terminal": true}` / `{"terminal": true, "failure": true}`), e.g. `scripts/little_loops/loops/incremental-refactor.yaml:171-176`.
- `context: dict[str, Any]` — top-level mapping of interpolation defaults. Values are usually `str` but not always (ints, bools, and lists appear across the corpus), so the scan must filter to `str` the same way the action scan does. This is BUG-3276's surface — see Scope Boundaries.
- `evaluate: dict[str, str]` — sibling per-state field whose `prompt`/`source` keys are also plain strings that can carry shell/prompt text with an interpolated or literal this-repo path, e.g. `loop-specialist-eval.yaml:50-60`. **Out of scope** (see Scope Boundaries); listed here so a later widening knows the field shape.
- `_hardcode_hits(text: str) -> list[str]` — **new, module-level.** Returns the matched hardcode patterns found in one string, empty when clean. Both the parametrized gate and the negative test call this; it exists specifically so the negative test can pass an inline string instead of needing a fixture file inside the enumerated loops directory (see Integration Map → Tests).
- `_scanned_strings(data: dict) -> Iterator[tuple[str, str]]` — **new, module-level.** Yields `(location_label, text)` for every in-scope string in one parsed loop: each `states[*].action` and each top-level `context:` value. The label is what makes the assertion message name the offending surface rather than just the file.

### Call Path
`yaml.safe_load(loop_file.read_text())` → `_scanned_strings(data)` → for each yielded string, `_hardcode_hits(text)` → per-file parametrized assertion.

Both halves of that path already exist in the tree and are copied, not invented:

- Enumeration + parametrize + exemption lookup: `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:98-123` — `_all_loop_files()` (`:98-99`), `_relative()` (`:102-103`), `ALL_LOOP_FILES` (`:106`), and the `@pytest.mark.parametrize("loop_file", ALL_LOOP_FILES, ids=_relative)` + `if rel in _EXEMPT: return` opening of `test_no_inline_project_command_config_read` (`:109-112`).
- Dot-directory filter to add on top of it: `_builtin_loop_files()` at `scripts/tests/test_builtin_loop_interpolation.py:69-79`.
- Exemption-hygiene guard to mirror: `test_permanent_exemptions_still_exist` at `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:153-162`.
- Assertion being generalized: `scripts/tests/test_builtin_loops.py:12671-12675`.

### Decision Rules
- **Gate scope: `states[*]["action"]` + top-level `context:` values. REVISED 2026-08-22.** An earlier rule here read "scope this issue's gate to `action` bodies only (DECIDED 2026-08-21)". That decision is **overturned for `context:`** — it excluded the exact surface BUG-3276 fired on, and its stated justification (that `context:` is separately gated) rests on a single-loop, single-key assertion. Full reasoning and evidence in Scope Boundaries. `states[*]["evaluate"]["prompt"]`/`["source"]` **stay out**: no hit in the current inventory lives there, and widening would force a fresh exemption survey over prompt text (e.g. `loop-specialist-eval.yaml:50-60` interpolates its fixture path into an `evaluate` block). If an evaluate-field instance ever appears, widen this same gate rather than adding a second one.
- Explicitly OUT of scope (confirmed not exec-time content, so a hardcoded path there is not the live defect): `scope:` list entries (`loop-specialist-eval.yaml:12`), `description:` fields, and `#`-prefixed comments.
- **Match pattern set: `scripts/tests`, `scripts/little_loops`, `ruff check scripts`, `mypy scripts` — and be honest that this is the survey grep, not a definition of the defect class.** It is deliberately narrow to keep false positives at zero on the first landing, but the consequence must be written down or a later reader will assume the class is closed: a bare `scripts/` (which is exactly `dead-code-cleanup.yaml:8-9`'s `scope: ["scripts/"]`, Implementation Step 5's follow-up) does **not** match, and neither would `python -m pytest scripts/ -q` in an action body. BUG-3276's own literal (`python -m pytest scripts/tests/`) does match, via `scripts/tests`. Widening toward a command-position `scripts/` match is a reasonable follow-up once this gate has been green for a while; it is not this issue's work.
- **Exemption set: two files.** `cli-anything-bootstrap.yaml` (`:453`, package-internal task-template path, inside an `action` body) and `loop-specialist-eval.yaml` (`:23`, this-repo eval fixture path, a `context:` value now in scope). A 2026-08-21 refine pass argued for a one-file set; that was correct under the action-only scope and is superseded by the widening. See the survey's "moved twice" note before changing this count again.
- ~~`evaluation-quality.yaml:63` (`ruff check scripts/ 2>&1 | tee ...`, inside `states.evaluate_code.action`) is **confirmed still present**, not yet fixed by ENH-3277 step 5, as of this research pass (2026-08-21) — the issue's Exemption survey table marks it "Already fixed"; that is currently false. The gate cannot land until this line is fixed or the file is added to a temporary exemption.~~ **Inverted 2026-08-22**: ENH-3277 is `Completed`, the line is gone, and no temporary exemption is needed. The survey table was right.
- **File enumeration — `lib/` is IN scope. DECIDED 2026-08-22.** The model gate's `_all_loop_files()` globs `BUILTIN_LOOPS_DIR.glob("**/*.yaml")`, which already includes `scripts/little_loops/loops/lib/`. Keep that. A fragment's action body is exec-time content exactly like a loop's, so a hardcode there ships just as broadly. Note the current pass is partly *accidental*: only `lib/apo-base.yaml` has a top-level `states:` key; the other ten lib files have none, so `data.get("states", {})` yields `{}` and they pass vacuously rather than by inspection. That is the correct outcome, but state it deliberately so a later reader does not "fix" the enumeration.
- **Exclude dot-directories from enumeration. DECIDED 2026-08-22.** `scripts/little_loops/loops/` contains `.running/`, `.history/`, `.ll/`, and `.DS_Store` in a working checkout. They hold no `.yaml` at this instant — re-verified 2026-08-22 with `find scripts/little_loops/loops -path '*/.*' -name '*.yaml'`, which returns nothing against a 114-file corpus — so the existing bug3269 gate has never tripped on them. But `pathlib.Path.glob` traverses hidden directories, so a single leftover run artifact would fail the parametrized gate against a non-source file. Mirror the exclusion helper `_builtin_loop_files()` at `scripts/tests/test_builtin_loop_interpolation.py:69-79`, which filters on `any(part.startswith(".") for part in path.relative_to(LOOPS_DIR).parts)`. (An earlier wiring note raised this against a bad anchor in `test_fsm_loop_paths.py` and the anchor was correctly retracted; the underlying concern is real and is hereby re-adopted on its own evidence.)
- **The sibling gate has the same enumeration gap; fix it in passing. DECIDED 2026-08-22.** `_all_loop_files()` (`scripts/tests/test_bug3269_test_cmd_resolution_gate.py:98-99`) is a bare `sorted(BUILTIN_LOOPS_DIR.glob("**/*.yaml"))` with no dot-directory filter, so both of that module's parametrized gates are exposed to exactly the leftover-artifact failure described above. Since this issue is already establishing the filter as the convention, apply the same one-line filter there rather than leaving two adjacent gates enumerating differently. Zero behavior change today (no dot-dir YAML exists); it is the divergence that is the defect. See Implementation Step 3b.
- **Exemption keys are repo-relative paths, not basenames.** The model gate keys `_EXEMPT` on `_relative(path)` — e.g. `"oracles/code-run-gate.yaml"`, not `"code-run-gate.yaml"`. Both of this issue's entries are top-level files, so the two forms coincide for them — but the lookup must use the relative form so a future nested exemption works.
- **Guard non-string / absent `action` values, and non-string `context:` values.** Terminal states are `{"terminal": true}` with no `action` key (`incremental-refactor.yaml:171-176`). Read via `.get("action", "")` and skip anything that is not a `str`. Apply the same `isinstance(v, str)` filter to `context:` values, which are not uniformly strings across the corpus (ints, bools, and lists all appear) — so a malformed or aliased YAML raises no `TypeError` in place of a clean assertion.

## Implementation Steps

1. ~~Land ENH-3277 step 5 first (or confirm it landed)~~ — **DONE.** ENH-3277 is `Completed`
   (2026-08-22) and `evaluation-quality.yaml:63` is verified gone. No action.
2. ~~Verify `harness-single-shot.yaml:60`'s example comment no longer carries the `scripts/tests/`
   path~~ — **DONE.** ENH-3277's rewrite landed; the line reads `#   action: "pytest -q --tb=no"`.
   No hand-fix, and do not double-edit a line ENH-3277 owns.
3. Write the parametrized gate in a **new module**, `test_builtin_loop_hardcode_gate.py` under
   `scripts/tests/` (see Integration Map for why not inside the bug3269 module), covering **`states[*].action`
   bodies and top-level `context:` values**, with the **two-entry** exemption set
   (`cli-anything-bootstrap.yaml`, `loop-specialist-eval.yaml`). Model the parametrize/exemption
   shape on `test_bug3269_test_cmd_resolution_gate.py`. Factor the match into the module-level
   `_hardcode_hits()` / `_scanned_strings()` helpers in Program Design → Signatures — the negative
   test in step 3c depends on `_hardcode_hits()` being callable on a bare string. Apply the
   robustness decisions in Program Design → Decision Rules: `lib/` in scope, dot-directories
   excluded, exemption keys as repo-relative paths, non-string/absent `action` and non-string
   `context:` values guarded.
   - **3b.** Add the same dot-directory filter to `_all_loop_files()` in
     `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:98-99`, so the two adjacent gates
     enumerate identically. One line, no behavior change today.
   - **3c.** Add the negative test: call `_hardcode_hits()` directly on an inline string
     containing a hardcoded `scripts/tests/` path and assert it returns a hit. Do **not** add a
     fixture YAML under `scripts/little_loops/loops/` — that directory is the gate's own
     parametrize corpus, so a fixture there would fail the gate instead of testing it.
4. **Keep** `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
   (`scripts/tests/test_builtin_loops.py:12671-12675`). **Reversed 2026-08-22** — two earlier
   revisions said "retire or narrow … dropping it loses no coverage", which was overstated: it
   asserts over the whole `yaml.dump`'d document and so also covers `scope:`, `description:`, and
   `evaluate.prompt` for that loop, none of which the new gate scans. It is four lines and green;
   leave it. See Behavior Parity → coverage-delta note.
5. **Capture the `dead-code-cleanup.yaml:8-9` `scope: ["scripts/"]` follow-up as its own issue.**
   Not optional bookkeeping: the *Known instance outside the gate's scope* section above says this
   must be captured "so the `scope:` is out of scope rule does not silently bless it", and as of
   2026-08-22 **no such issue exists** — the rule is currently doing exactly what that section
   warns against. Capture it before or with this gate landing.
6. Verify `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Survey state as of 2026-08-22 (supersedes two earlier rounds of drift claim and retraction).**
  Current grep: **4 hits across 3 files** — `cli-anything-bootstrap.yaml:453`,
  `loop-specialist-eval.yaml:12,23`, `oracles/code-run-gate.yaml:407`. Confirmed a third time by
  the 2026-08-22 pre-implementation review. Under the widened scope, two of these are in-scope
  (`cli-anything-bootstrap.yaml:453` in an action body, `loop-specialist-eval.yaml:23` a
  `context:` value), so the exemption set is **two** entries; `loop-specialist-eval.yaml:12` is a
  `scope:` entry and `code-run-gate.yaml:407` is a comment, both out of scope. The two files that
  dropped out (`evaluation-quality.yaml`, `harness-single-shot.yaml`) were fixed by ENH-3277, not
  drifted. Re-run the grep once at implementation time as ordinary hygiene; expect these three
  files.
- Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:562-582` — name/link the new gate alongside the
  existing `test_bug3269_test_cmd_resolution_gate.py` description, and connect it to the
  "never hardcode a project command literal" rule it now enforces. That rule's own paragraph
  (`:576-587`) already states the invariant in both surfaces — "in a loop action **or context
  default**" — which is independent corroboration for the `context:` widening: the guide has been
  describing a two-surface rule that no parametrized gate enforced.
- **Sequencing is resolved — both blockers have landed. UPDATED 2026-08-22.** ENH-3277 and
  ENH-3288 are both `done`; the recommended-order note here is spent.
- Add an exemption-hygiene guard test so a renamed/deleted exempted file forces the exemption set
  to shrink instead of silently dangling. **Anchor corrected**: an earlier revision told the
  implementer to copy `test_pending_conversion_sites_still_exist` and warned that "ENH-3288 step 6
  deletes that test". ENH-3288 has since landed and did exactly that — `_PENDING_CONVERSION` and
  that test no longer exist. The live shape to mirror is
  `test_permanent_exemptions_still_exist` (`scripts/tests/test_bug3269_test_cmd_resolution_gate.py:153-162`),
  which asserts every listed exemption still exists on disk. Copy the shape into the new module;
  do not import it.

## Impact

- **Priority**: P3 — no known live defect; ENH-3277 step 5 landed and cleared the last one, so
  this is pure class-closure against the next instance
- **Effort**: Small (frontmatter `size:` corrected from `Very Large` to `Small` on 2026-08-22 to
  match — the work is one new test module, a one-line fix to a sibling module, a docs bullet, and
  a follow-up capture). The 2026-08-22 review's `context:` widening does not change the estimate:
  it adds one scanned surface and one exemption entry.
- **Risk**: Low — test-only; worst case is an over-broad match needing another exemption
- **Breaking Change**: No

## Related Key Documentation

- ENH-3277 — parent; its step 5 converts the one live instance, and its step 6b was this issue
- BUG-3276 — the original single-loop instance and the assertion being generalized

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-21_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 79/100 → MODERATE

### Gaps to Address
- ~~`blocked_by: ENH-3277` is unresolved (status: open) — Phase 1.7's Dependencies Hard Override
  forces STOP regardless of the aggregate readiness score. ENH-3277 step 5 (the
  `evaluation-quality.yaml:63` fix) must land first; per the issue's own Codebase Research
  Findings, that fix is confirmed still absent as of 2026-08-21, and Implementation Step 1
  depends on it landing before the gate can be written without an immediate failure.~~
  **RESOLVED 2026-08-22** — ENH-3277 is `Completed`, so the Dependencies Hard Override no longer
  applies and this was the only gap holding the STOP verdict. The `evaluation-quality.yaml:63`
  fix is verified present in the tree. Re-run `/ll:confidence-check` to refresh the score; the
  stored 75 predates the unblock.

_Added by pre-implementation review — 2026-08-22_

**Stored scores are stale in both directions — re-run before implementing.** Frontmatter carries
`confidence_score: 75`, `outcome_confidence: 79`, and `verify_verdict: VALID`. All three predate
this review, which (a) resolved the dependency that forced the STOP verdict, and (b) found a
design hole the `VALID` verdict did not catch: the gate as previously scoped excluded `context:`
defaults, i.e. the exact surface BUG-3276 fired on. The scope is now widened and the remaining
open decisions (new module vs. sibling module, negative-test shape, whether to retire the
incremental-refactor assertion) are all closed in text. Re-run `/ll:confidence-check` and
`/ll:verify-issues` to refresh.

## Session Log
- `/ll:confidence-check` - 2026-08-22T19:16:07 - `a4109bf2-b6ba-4ebb-95ea-4adc095f7bdc.jsonl`
- `/ll:review-issue (manual)` - 2026-08-22T18:08:45 - `8e5158e7-e170-4b3d-ab1f-2afbae53a801.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:08:52 - `73da6192-349c-4cd0-b9a2-b714f2801296.jsonl`
- `/ll:verify-issues` - 2026-08-21T18:07:11 - `ad33897f-96b1-481f-b16b-43023e17a769.jsonl`
- `/ll:refine-issue` - 2026-08-21T18:04:54 - `836eb96e-ed7e-4c93-858e-4d06a5ead426.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:02:19 - `e8b100f2-1d69-4959-840b-2aa9aba3993f.jsonl`
- `/ll:verify-issues` - 2026-08-21T18:00:21 - `90966598-488c-4ef1-8069-bfc434c54604.jsonl`
- `/ll:wire-issue` - 2026-08-21T17:57:42 - `11ecedd7-fd91-44be-ac81-328fd4fc2358.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T17:52:57 - `f27d8342-f3ba-42ea-95ca-41ad79008fbf.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:49:14 - `355dc853-4da1-435d-a210-8405db6125ba.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:58:40 - `da526826-2179-460f-b823-35695378ac55.jsonl`
