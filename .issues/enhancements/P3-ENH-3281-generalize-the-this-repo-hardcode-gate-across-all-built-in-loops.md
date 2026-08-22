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
blocked_by:
- ENH-3277
verify_verdict: VALID
confidence_score: 75
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
size: Very Large
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
state's action body, with a small documented exemption set.

## Motivation

A hardcoded this-repo path in a shipped loop is silent in this repo and broken everywhere else.
`.claude/CLAUDE.md` is explicit that all little-loops projects on this machine are
`local-editable` against this checkout, so a bad path is live in every one of them with no
reinstall step. This is the `_PENDING_CONVERSION` protection applied to the sibling defect class:
ENH-3277 converts the one known instance (`evaluation-quality.yaml:63`), which leaves the class
open to a next instance.

## Proposed Solution

Parametrize over all built-in loop files with an `_EXEMPT`-style set, mirroring
`test_bug3269_test_cmd_resolution_gate.py`.

**Scope the gate to action bodies, not comments.** A naive text match over whole files produces
mostly-illegitimate hits (see the survey below); restricting to `states[*].action` removes two of
the four non-target hits outright and makes the exemption set small enough to be meaningful.

### Exemption survey — verified 2026-08-21

ENH-3277 step 6b claimed *"only legitimate hits to exempt today are `loop-specialist-eval.yaml:12,23`"*.
That was wrong. `grep -rlE "scripts/tests|ruff check scripts|mypy scripts|scripts/little_loops"`
over `scripts/little_loops/loops/**/*.yaml` returns five files:

| File | Hit | Disposition |
|---|---|---|
| `loop-specialist-eval.yaml:12,23` | `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` | **Exempt** — genuine this-repo eval fixture; the loop only makes sense in this repo |
| `cli-anything-bootstrap.yaml:453` | `scripts/little_loops/loops/lib/task-templates/…` | **Exempt** — package-internal path, not a consuming-project layout guess. Arguably should resolve via `importlib.resources` instead, but that is a separate change |
| `oracles/code-run-gate.yaml:407` | source citation inside a comment | **Not a hit** once the gate is scoped to action bodies |
| `harness-single-shot.yaml:60` | `# action: "python -m pytest scripts/tests/ -q --tb=no"` | **Change, do not exempt** — an `# EXAMPLE:` scaffold users clone, so it teaches the anti-pattern (same load-bearing-comment argument ENH-3277 makes for the three `harness-*` fallback comments). Comment-scoping the gate means it will not be caught automatically; fix it by hand in this issue |
| `evaluation-quality.yaml:63` | `ruff check scripts/` | **Already fixed** by ENH-3277 step 5 — verify it is gone before landing the gate |

Net exemption set after this issue: **one file** (`cli-anything-bootstrap.yaml`). An earlier
framing of this line said "two files", counting `loop-specialist-eval.yaml` — but once the gate
is scoped to `states[*].action` as this section specifies, that file's two hits (`:12` a `scope:`
list entry, `:23` a `context:` default) fall outside scope and need no exemption entry. The
refine-pass finding below is the correction; the Implementation Steps use the one-entry set.

**Known instance outside the gate's scope — flagged, not covered here.**
`dead-code-cleanup.yaml:8-9` ships `scope: ["scripts/"]` — a this-repo layout default in a
generic built-in loop. `scope:` entries are deliberately outside this gate (see Program Design →
Decision Rules), and unlike `loop-specialist-eval` (a this-repo eval loop whose scope hit is
legitimate), this one is a genuine layout guess shipped to consuming projects. Not this issue's
work: capture it as a separate issue rather than widening the gate here, so the "scope: is out
of scope" rule does not silently bless it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Exemption set revision**: scoping the gate to `states[*].action` bodies (as this section already specifies) changes the exemption set from the two files the survey table claims. `loop-specialist-eval.yaml`'s two hits (`:12` a `scope:` list entry, `:23` a `context:` default) both fall *outside* `states[*].action` once the scope restriction is applied literally — neither needs an exemption entry under that scoping. `cli-anything-bootstrap.yaml:453` remains the one confirmed in-scope hit needing exemption (package-internal task-template path inside an `action` body). Net: one exemption, not two, if the gate is implemented exactly as scoped here.
- **`evaluation-quality.yaml:63` re-verified 2026-08-21**: `ruff check scripts/ 2>&1 | tee ${context.run_dir}/eval-lint-results.txt || true`, inside `states.evaluate_code.action` — still present in the current tree. The survey table's "Already fixed by ENH-3277 step 5" disposition does not hold as of this research pass; Implementation Step 1 ("Land ENH-3277 step 5 first, or confirm it landed") should resolve to "not landed" today.

## Integration Map

### Files to Modify

- `scripts/tests/test_builtin_loops.py` — the incremental-refactor-only assertion it replaces
- a new gate module, or an added parametrized test alongside
  `scripts/tests/test_bug3269_test_cmd_resolution_gate.py`
- `scripts/little_loops/loops/harness-single-shot.yaml:60` — the example-comment fix

### Tests

- The gate itself is the test. Add a negative fixture (a loop YAML with a hardcoded
  `scripts/tests/` path in an action body) asserting the gate fails on it, so the gate cannot
  silently stop matching.

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
| `scripts/tests/test_builtin_loops.py::TestIncrementalRefactorLoop::test_no_state_hardcodes_this_repo_test_path` | Asserts no `scripts/tests` literal appears anywhere in `incremental-refactor.yaml`'s full `yaml.dump`'d parsed content (whole-file scope, single loop) | DROPPED (per Implementation Step 4: "Retire or narrow") | Subsumed by the new parametrized gate, which covers the same loop plus all other built-in loops, scoped to `states[*].action` (narrower per-state scope, broader per-file scope) |
| `scripts/tests/test_builtin_loops.py::TestIncrementalRefactorLoop::test_context_test_cmd_has_no_hardcoded_literal` | Asserts `data["context"]["test_cmd"] == ""` for `incremental-refactor.yaml` specifically | PRESERVED | Out of scope for this issue — checks a different key (`context.test_cmd` default) than the new gate (`states[*].action` body text); not superseded or touched |

## Program Design

### Codebase Research Findings

### Types
- N/A — no new data types; the gate walks existing parsed YAML mappings.

### Signatures
- `action: str` — per-state field on the `yaml.safe_load`'d loop dict; always a plain string, block-scalar (`|`/`>`) vs. quoted-string YAML style is not distinguishable post-parse, only content. Absent on terminal states (`{"terminal": true}` / `{"terminal": true, "failure": true}`), e.g. `scripts/little_loops/loops/incremental-refactor.yaml:171-176`.
- `evaluate: dict[str, str]` — sibling per-state field whose `prompt`/`source` keys are also plain strings that can carry shell/prompt text with an interpolated or literal this-repo path, e.g. `loop-specialist-eval.yaml:50-60`.

### Call Path
`yaml.safe_load(loop_file.read_text())` → `data.get("states", {}).values()` → read `.get("action", "")` (and, if in scope, `.get("evaluate", {}).get("prompt"/"source", "")`) from each state dict → regex/substring match against the hardcode pattern set → `pytest.mark.parametrize` assertion per file, mirroring `ALL_LOOP_FILES = sorted(BUILTIN_LOOPS_DIR.glob("**/*.yaml"))` in `scripts/tests/test_bug3269_test_cmd_resolution_gate.py:92-93`.

### Decision Rules
- Gate scope: `states[*]["action"]` is the minimum required scope per the issue. `states[*]["evaluate"]["prompt"]`/`["source"]` are NOT scanned by any hit in the current 6-hit inventory, but are structurally identical string fields that could carry the same defect class. **DECIDED (2026-08-21): scope this issue's gate to `action` bodies only.** No current hit lives in an evaluate field, so widening now buys nothing and would force a fresh exemption survey over prompt text (e.g. `loop-specialist-eval.yaml:50-60` interpolates its fixture path into an `evaluate` block, which would need an exemption the action-only gate avoids). If an evaluate-field instance ever appears, widen this same gate rather than adding a second one.
- Explicitly OUT of scope (confirmed not exec-time content, so a hardcoded path there is not the live defect): `scope:` list entries (`loop-specialist-eval.yaml:12`), `context:` defaults (`loop-specialist-eval.yaml:23`, and the pattern BUG-3276/`test_context_test_cmd_has_no_hardcoded_literal` already gates separately), `description:` fields, and `#`-prefixed comments.
- Match pattern set per the issue's own grep: `scripts/tests`, `scripts/little_loops`, `ruff check scripts`, `mypy scripts`.
- Exemption set after full-inventory verification (2026-08-21 re-check): `cli-anything-bootstrap.yaml` (`:453`, package-internal task-template path, inside an `action` body) is the only entry actually inside `states[*].action` scope. `loop-specialist-eval.yaml` does NOT need an exemption once scoped to `action` bodies — its two hits (`:12` scope list, `:23` context default) fall outside that scope already, contradicting the issue's claim of a two-file exemption set.
- `evaluation-quality.yaml:63` (`ruff check scripts/ 2>&1 | tee ...`, inside `states.evaluate_code.action`) is **confirmed still present**, not yet fixed by ENH-3277 step 5, as of this research pass (2026-08-21) — the issue's Exemption survey table marks it "Already fixed"; that is currently false. The gate cannot land until this line is fixed or the file is added to a temporary exemption.

## Implementation Steps

1. Land ENH-3277 step 5 first (or confirm it landed) — otherwise the new gate fails on
   `evaluation-quality.yaml:63` immediately.
2. Verify `harness-single-shot.yaml:60`'s example comment no longer carries the `scripts/tests/`
   path — ENH-3277's pinned replacement text (its *Two defects in `harness-single-shot`'s
   `# Replace` block* section) already rewrites it to `#   action: "pytest -q --tb=no"`, and this
   issue is `blocked_by: ENH-3277`. Fix it by hand only if that rewrite somehow did not land; do
   not double-edit a line ENH-3277 owns.
3. Write the parametrized gate over `states[*].action` bodies with the **one-entry** exemption
   set (`cli-anything-bootstrap.yaml` — see the survey correction), modeled on
   `test_bug3269_test_cmd_resolution_gate.py`.
4. Retire or narrow `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
   once the general gate subsumes it.
5. Verify `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Drift claim retracted (2026-08-21 re-verification)~~ — an earlier wiring pass asserted here
  that the survey's citations had drifted (`cli-anything-bootstrap.yaml:453` and
  `oracles/code-run-gate.yaml:407` "no longer contain the hits"; `evaluation-quality.yaml` "has
  no `scripts/tests` literal"). **That claim is false.** A fresh run of the survey grep against
  the tree (2026-08-21) reproduces **all six hits exactly as the survey table states**. The
  survey table and the refine-pass findings are authoritative; the drift note was itself
  fabricated drift — the same defect class ENH-3283/BUG-3282 exist to catch. Still re-run the
  grep once at implementation time as ordinary hygiene, but expect it to match the table.
- Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:562-582` — name/link the new gate alongside the
  existing `test_bug3269_test_cmd_resolution_gate.py` description, and connect it to the
  "never hardcode a project command literal" rule it now enforces
- Add an exemption-hygiene guard test (mirroring the `test_pending_conversion_sites_still_exist`
  *pattern* from `test_bug3269_test_cmd_resolution_gate.py`) so a renamed/deleted exempted file
  forces the exemption set to shrink instead of silently dangling. Note **ENH-3288 step 6 deletes
  that test** along with `_PENDING_CONVERSION` — copy the shape, do not import or reference the
  test itself. Sequencing: this issue and ENH-3288 both edit the gate module's neighborhood;
  recommended order is ENH-3277 → ENH-3288 → this issue, and if this lands first, expect ENH-3288
  to touch the same file.

## Impact

- **Priority**: P3 — no known live defect once ENH-3277 step 5 lands; this is class-closure
  against the next instance
- **Effort**: Small
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
- `blocked_by: ENH-3277` is unresolved (status: open) — Phase 1.7's Dependencies Hard Override
  forces STOP regardless of the aggregate readiness score. ENH-3277 step 5 (the
  `evaluation-quality.yaml:63` fix) must land first; per the issue's own Codebase Research
  Findings, that fix is confirmed still absent as of 2026-08-21, and Implementation Step 1
  depends on it landing before the gate can be written without an immediate failure.

## Session Log
- `/ll:confidence-check` - 2026-08-21T18:08:52 - `73da6192-349c-4cd0-b9a2-b714f2801296.jsonl`
- `/ll:verify-issues` - 2026-08-21T18:07:11 - `ad33897f-96b1-481f-b16b-43023e17a769.jsonl`
- `/ll:refine-issue` - 2026-08-21T18:04:54 - `836eb96e-ed7e-4c93-858e-4d06a5ead426.jsonl`
- `/ll:confidence-check` - 2026-08-21T18:02:19 - `e8b100f2-1d69-4959-840b-2aa9aba3993f.jsonl`
- `/ll:verify-issues` - 2026-08-21T18:00:21 - `90966598-488c-4ef1-8069-bfc434c54604.jsonl`
- `/ll:wire-issue` - 2026-08-21T17:57:42 - `11ecedd7-fd91-44be-ac81-328fd4fc2358.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T17:52:57 - `f27d8342-f3ba-42ea-95ca-41ad79008fbf.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:49:14 - `355dc853-4da1-435d-a210-8405db6125ba.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:58:40 - `da526826-2179-460f-b823-35695378ac55.jsonl`
