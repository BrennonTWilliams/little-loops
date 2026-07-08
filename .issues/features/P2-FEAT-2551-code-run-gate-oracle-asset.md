---
id: FEAT-2551
title: 'F2a — code-run-gate oracle + config schema (build/test/typecheck/lint/health)'
type: FEAT
priority: P2
status: open
captured_at: '2026-07-08T00:00:00Z'
discovered_date: 2026-07-08
discovered_by: split-from-FEAT-2413
parent: FEAT-2413
relates_to:
- EPIC-2412
- FEAT-2413
- FEAT-2552
- FEAT-2414
- FEAT-2416
- FEAT-2269
labels:
- loops
- verification
- oracles
- mr1
- tier-1
- greenfield
decision_needed: true
learning_tests_required:
- pytest-json-report
size: Medium
---

# FEAT-2551: F2a — code-run-gate oracle + config schema

> **Split from FEAT-2413** (split 2026-07-08; see FEAT-2413 for umbrella
> motivation, parent EPIC-2412 context, and original 13-step plan). F2a
> lands the **asset layer** — the new `oracles/code-run-gate.yaml` file,
> the config-schema additions (`health_url` + alias/rename decision for
> `typecheck_cmd`/`start_cmd`), and the `ProjectConfig` dataclass
> extensions. F2b (FEAT-2552) wires the asset into
> `rn-remediate`/`rn-implement` and updates the existing tests that the
> wiring breaks. The data-flow dependency is **a → b**.

> **Purely additive** — no existing behavior changes. F2a's oracle ships
> as a reusable artifact that is *not invoked* by any loop until F2b
> wires it in. This means F2a can land independently and stabilize
> before F2b's behavioral change touches the greenfield family.

## Summary

Author `scripts/little_loops/loops/oracles/code-run-gate.yaml` — a
`from:`-inheritable oracle that runs a caller-supplied command matrix
(`build` / `test` / `typecheck` / `lint` / `service_health`) and emits
non-LLM verdicts (`GATE_PASS` / `GATE_FAILED` / `GATE_SKIP`) to the
parent↔sub-loop token channel. Backed by config-schema additions
(`health_url`, alias support for `typecheck_cmd` / `start_cmd`) and the
matching `ProjectConfig` dataclass fields.

The oracle uses **only** Tier-1 deterministic evaluators (`exit_code`,
`output_numeric`, `classify`) — MR-1 is satisfied trivially without
`meta_self_eval_ok` (see `scripts/little_loops/fsm/validation.py:84-88`).

## Current Behavior

The implement path in `rn-remediate`/`rn-implement` judges completion
from LLM-scored issue prose plus a "git diff exists" check
(`scripts/little_loops/work_verification.py:44-161`). Plausible-but-broken
code earns `IMPLEMENTED`. This split doesn't change that — it only
**adds** the asset that F2b will plug in.

## Expected Behavior

After F2a:

- `oracles/code-run-gate.yaml` exists, validates cleanly via
  `ll-loop validate` (MR-1 trivial; MR-3 compliant — all artifacts
  written under `${context.run_dir}/`, never bare `.loops/tmp/`).
- `config-schema.json` accepts `project.health_url` (and accepts both
  `typecheck_cmd` / `type_cmd` and `start_cmd` / `run_cmd` aliases per
  the F2a decision).
- `ProjectConfig` (`config/core.py:142-161, 554-559`) round-trips the
  new field through `.from_dict()` / `.to_dict()`.
- The oracle is *not yet called* by any production loop. F2b wires it
  in. This split's AC stops at "asset exists, validates, and tests
  pass."

## Use Case

**Who**: An implementer running `ll-loop run oracles/code-run-gate`
directly (or via F2b's wiring).

**Context**: A code change has been generated; the caller wants to know
whether it actually builds, tests, typechecks, lints, and (for services)
responds on the health endpoint.

**Goal**: Get a non-LLM `GATE_PASS` / `GATE_FAILED` / `GATE_SKIP`
verdict from the same artifact that any harness can reuse.

**Outcome**: A reusable, MR-1-clean oracle that any future harness
(FEAT-2414 `rn-build`, FEAT-2416 archetypes, recursive-refine,
proof-first-task, autodev) can call without re-implementing gate
logic.

## Motivation

`rn-implement`/`rn-remediate` never compile, test, or run anything —
`implement`'s `on_yes → emit_implemented` fires on `ll-auto` exit 0,
and `ll-auto`'s verify phase only reads `status:` frontmatter
(`issue_lifecycle.py:444`, `work_verification.py:44`). This is the
single biggest robustness hole in the greenfield family.

The proven pattern already exists twice and should be generalized, not
reinvented:
- `oracles/generator-evaluator.yaml` — `from:`-inheritable, paired
  LLM rubric + non-LLM `diff_stall` gate.
- `cli-anything-bootstrap.yaml:252-337` — fresh venv `pip install -e`,
  `--help` coverage walk, `pytest --json-report` pass-rate; LLM state
  explicitly forbidden from reading source, judging only measured
  numbers.

F2a generalizes these into a reusable asset; F2b plugs it into the
implement path.

## Proposed Solution

Author the oracle under
`scripts/little_loops/loops/oracles/code-run-gate.yaml` (mirroring the
proven `oracles/generator-evaluator-cli.yaml:1-56` `from:` inheritance
pattern from FEAT-2269), with these states:

| State | Inputs | Output | Evaluator |
|-------|--------|--------|-----------|
| `resolve_commands` | `.ll/ll-config.json` `project.*` | `${run_dir}/commands.json` + token | (no eval — shell) |
| `run_build` | `commands.json.build_cmd` | `${run_dir}/build.txt` | `exit_code` |
| `run_test` | `commands.json.test_cmd` | `${run_dir}/test-results.txt` + `pytest.json` | `output_numeric` (pass_rate) |
| `run_typecheck` | `commands.json.typecheck_cmd` (or `type_cmd`) | `${run_dir}/typecheck.txt` | `exit_code` |
| `run_lint` | `commands.json.lint_cmd` | `${run_dir}/lint.txt` | `exit_code` |
| `service_health` | `commands.json.run_cmd` + `health_url` | `${run_dir}/health.txt` + `service.pid` | `exit_code` (HTTP 2xx) |
| `aggregate` | All sidecar files | `GATE_PASS` / `GATE_FAILED` / `GATE_SKIP` | `classify` (dispatch table) |

**Docs-only no-op-pass**: `resolve_commands` exits with `GATE_SKIP` when
**all** of `test_cmd` / `build_cmd` / `type_cmd` / `lint_cmd` / `run_cmd`
/ `health_url` resolve to null/empty. `GATE_SKIP` is treated identically
to `GATE_PASS` by F2b's wiring. Modeled on
`cli-anything-bootstrap.yaml:97-105` (missing-artifact graceful skip).

## Implementation Steps

1. **Author `oracles/code-run-gate.yaml`** with `from:` inheritance
   (FEAT-2269 precedent: `oracles/generator-evaluator-cli.yaml:1-56`)
   and the six states above. Use the `${context.run_dir}` →
   absolute-path idiom from `oracles/generator-evaluator.yaml:71-74`
   for every artifact write.
2. **Add `health_url` to `scripts/little_loops/config-schema.json`** —
   append `"health_url": {"type": ["string", "null"], "default": null}`
   to `project.properties` (block at `:30-59`). Required because
   `additionalProperties: false` at `:61` rejects unknown keys.
3. **Update `scripts/little_loops/config/core.py:142-161, 554-559`**
   (**BLOCKER** for the implementation commit):
   - `ProjectConfig` dataclass: add `health_url: str | None = None`.
   - `.from_dict()`: read `health_url=data.get("health_url")` at
     line ~161.
   - `.to_dict()` at `:554-559`: serialize the new key.
   - Without this, the new schema field is silently dropped on
     `.ll/ll-config.json` round-trip; `service_health` never sees the
     URL even when set.
4. **Make the alias-or-rename decision for `typecheck_cmd` /
   `start_cmd`** and record in `.ll/decisions.yaml` per the existing
   schema-coupling decision pattern. The candidate options are
   enumerated in
   [## Implementation Decision: alias vs rename](#implementation-decision-alias-vs-rename)
   below so `/ll:decide-issue` can score and lock in the winner
   (Pattern 1 of its Phase 3 extraction logic) before any
   consumer-side code is written.
5. **Add `health_url` row to `docs/reference/CONFIGURATION.md:281-286`**
   (alongside the existing project-commands rows).
6. **(Advisory, non-blocking)** Add a `_ask_command`-style TUI prompt
   for `health_url` in `scripts/little_loops/init/tui.py:282-308`
   (mirrors the existing `test_cmd` / `lint_cmd` / `type_cmd` /
   `format_cmd` prompt surface; defaults to `null` for non-service
   projects).
7. **(Advisory, defer to FEAT-2416)** Per-archetype `health_url`
   defaults in
   `scripts/little_loops/templates/{python-generic,javascript,typescript,rust,java-gradle,java-maven,go,dotnet,generic}.json`.
   The JSON Schema's `null` default and `additionalProperties: false`
   permit omission in the meantime; no immediate template change
   required.

### Codebase Research Findings

_Concrete anchor references per step (from FEAT-2413 refine-issue pass):_

- **Authoring (`oracles/code-run-gate.yaml`)** — model after the proven
  3-state `cli-anything-bootstrap.yaml:252-337` pattern (`verify-cli`
  fresh-venv install + `run-cli-tests` pytest --json-report). Add
  `service_health` modeled on `verify-cli`'s subprocess polling. Use
  the `${run_dir}` → absolute-path idiom from
  `oracles/generator-evaluator.yaml:71-74`. Per-iteration snapshot
  mirror `oracles/generator-evaluator.yaml:80-94`.

- **Config resolution idiom** — `python3 -c "import json,pathlib;
  p=pathlib.Path('.ll/ll-config.json'); cfg=json.loads(p.read_text()) if
  p.exists() else {}; print(cfg.get('project',{}).get('test_cmd','pytest'))"`
  (from `loops/general-task.yaml:35, 469-477`). Apply same idiom for
  all six fields. Defaults: `test_cmd=pytest`, `build_cmd=null`,
  `type_cmd=mypy`, `lint_cmd=ruff check .`, `run_cmd=null`,
  `health_url=null`.

- **MR-1 trivial satisfaction** — per
  `scripts/little_loops/fsm/validation.py:84-88`, an evaluator-only
  oracle with `exit_code` / `output_numeric` / `classify` evaluators
  passes MR-1 without needing `meta_self_eval_ok: true`. The oracle
  must NOT set `meta_self_eval_ok`.

- **MR-3 / run_dir isolation** — per
  `scripts/little_loops/fsm/validation.py:_SHARED_TMP_PATH_RE`, the
  oracle must write all artifacts under `${context.run_dir}/`. Do NOT
  use `.loops/tmp/` — that's the per-host shared path and breaks
  under concurrent runs.

- **Pattern source: aggregate state** — for the state that knits
  build/test/typecheck/lint/health outcomes into a single token, use
  `evaluate.type: classify` (dispatch table) — see
  `scripts/little_loops/loops/cli-anything-bootstrap.yaml:483-499`
  (`count-refine-cycle`) for the counter-progression shape and
  `scripts/little_loops/fsm/evaluators.py:453-504` for `evaluate_classify`.
  **Do NOT use `llm_structured` here** — that would re-introduce the
  very LLM self-grade the issue is fighting.

- **Pattern source: service_health** — launch the process with `&`,
  write PID to `${run_dir}/service.pid`, poll `${health_url}` with
  `curl --fail --max-time $BOUND`, assert HTTP 2xx; tear down with
  `kill $(cat ${run_dir}/service.pid)` in an `on_yes` / `on_no` /
  `on_error` ensure-via `trap` shell expression so the process never
  lingers.

- **Pattern source: docs-only no-op-pass** — see
  `loops/cli-anything-bootstrap.yaml:97-105` for a similar "missing
  artifact" graceful-skip pattern.

### Codebase Research Findings (2026-07-08 — auto pass)

_Additional anchor-level findings from parallel codebase research agents
(codebase-locator + codebase-analyzer + codebase-pattern-finder), appended
after the FEAT-2413 refine pass:_

- **MR-1 structurally inapplicable for this oracle** — per
  `scripts/little_loops/fsm/validation.py:_validate_meta_loop_evaluation()`
  (lines 1300-1354), MR-1 only fires on *meta-loops* — loops whose actions
  write to harness artifacts (`loops/*.yaml`, `skills/`, `agents/`,
  `commands/`, `.claude/CLAUDE.md`) per the `_META_LOOP_ACTION_PATTERNS`
  set. The code-run-gate oracle writes only to `${context.run_dir}/`
  (shell logs, command outputs, token files) — never to harness artifacts —
  so it is not classified as a meta-loop and MR-1 is silently skipped.
  Even if classification drifted, `exit_code` + `output_numeric` +
  `classify` are all members of `NON_LLM_EVALUATOR_TYPES` (derived at
  `validation.py:84-88`) and would still satisfy the gate.

- **MR-3 severity clarification (WARNING, not ERROR)** — per
  `scripts/little_loops/fsm/validation.py:_validate_artifact_isolation()`
  (lines 1523-1553) and `_find_shared_tmp_writes()` (lines 1482-1495), the
  `_SHARED_TMP_PATH_RE = re.compile(r"\.loops/tmp/[\w./-]+")` (defined at
  line 108) fires at WARNING severity, suppressible by top-level
  `shared_state_ok: true`. F2a's oracle should still write every artifact
  under `${context.run_dir}/` (per the absolute-path idiom at
  `oracles/generator-evaluator.yaml:71-74`) — the gate is non-blocking but
  cleanliness is enforced.

- **MR-4 silent for the aggregate state** — per
  `scripts/little_loops/fsm/validation.py:_is_llm_judged()` (lines
  1556-1572) and `_validate_partial_route_dead_end()` (lines 1575-1616),
  MR-4 only emits WARNING on LLM-judged states (`action_type in
  ("prompt", "slash_command")` paired with `llm_structured` or
  `check_semantic` evaluators). The `aggregate` state's
  `evaluate.type: classify` is non-LLM, so `_is_llm_judged()` returns
  `False` and MR-4 does not fire. The `route:` dispatch table for
  `GATE_PASS` / `GATE_FAILED` / `GATE_SKIP` is independent of MR-4
  entirely.

- **`_build_final_config` signature change for advisory TUI step (Step 6)** —
  per `scripts/little_loops/init/tui.py:_build_final_config()` (signature
  at lines 560-563; project-command plumbing at lines 663-668; summary
  table at lines 737-740), the function takes `test_cmd` / `lint_cmd` /
  `type_cmd` / `format_cmd` as keyword args and the summary table mirrors
  them. Adding the advisory `health_url` prompt requires three coordinated
  edits: (1) new `_ask_command` call in the block at `tui.py:282-308`
  (with default `None` for non-service projects), (2) new `health_url`
  keyword arg in `_build_final_config` signature, (3) new row in the
  summary table at `tui.py:737-740`. Pattern modeled on the existing
  `test_cmd` prompt at `tui.py:282-288`.

- **Existing alias precedent for the recommended F2a alias decision** —
  per `scripts/little_loops/config/core.py:_parse_config()` (lines
  204-240), `BRConfig` calls `ProjectConfig.from_dict(self._raw_config.get(
  "project", {}))` at line 206. This is the parse-once path that
  `ll-auto` and the FSM runner consume. The `typecheck_cmd`/`type_cmd`
  and `start_cmd`/`run_cmd` alias logic (Implementation Step 4) lives
  inside the new oracle's `resolve_commands` shell action via
  `cfg.get('typecheck_cmd') or cfg.get('type_cmd')` — the dataclass
  (`ProjectConfig`) and JSON Schema (`config-schema.json:30-58`) remain
  canonical at `type_cmd` / `run_cmd`, so no other consumer needs to
  change.

- **New documentation surface — `docs/reference/loops.md`** — the existing
  `## \`oracles/generator-evaluator\`` section starts at
  `docs/reference/loops.md:389`; `## \`oracles/generator-evaluator-cli\``
  starts at `:463-489` (FEAT-2269 precedent). A new
  `## \`oracles/code-run-gate\`` section should be added in the same
  shape: parameters table (six command fields + `run_dir` + `min_pass_rate`
  + `health_bound_seconds`), state diagram (the 6+ states), evaluator
  types used, and a one-line MR-1/3 compliance note. This doc location
  was not enumerated in the Integration Map → Files to Modify list.

- **Token channel compatibility (F2a → F2b handoff contract)** — the new
  oracle's `aggregate` state must emit its `GATE_PASS` / `GATE_FAILED` /
  `GATE_SKIP` verdict via `${context.run_dir}/subloop_outcome_<ID>.txt`
  so F2b's wiring can read it. The `classify` evaluator
  (`scripts/little_loops/fsm/evaluators.py:evaluate_classify()` at lines
  453-504) selects the verdict as the trimmed last non-empty stdout line;
  the `route:` table maps tokens to next states. The actual
  `subloop_outcome` file write happens in `aggregate`'s shell action
  (`echo "$VERDICT" > "${context.run_dir}/subloop_outcome_${ID}.txt"`),
  not in the evaluator. F2a's `aggregate` shell action must perform both
  the token echo (so `evaluate.type: classify` can route) and the file
  write (so F2b's reader sees it).

- **`run_dir` artifact isolation across concurrent runs** — per
  `scripts/little_loops/fsm/validation.py:_SHARED_TMP_PATH_RE` (line 108,
  `r"\.loops/tmp/[\w./-]+"`), the per-host shared `.loops/tmp/` path is
  rejected by MR-3 because concurrent `ll-loop run` invocations would
  clobber each other. The new oracle's `parameters.run_dir` is
  per-invocation (set by F2b's caller) and resolves to a fresh path
  like `.loops/runs/code-run-gate/<issue-id>/<run-uuid>/`. Use the
  `case "${context.run_dir}" in /*) ABS_DIR=...;; *) ABS_DIR="$(pwd)/..."`
  idiom from `oracles/generator-evaluator.yaml:71-74` to defend against
  relative paths.

- **Existing `route:`-table dispatch shape (canonical reference)** — per
  `scripts/little_loops/loops/rn-remediate.yaml:393-430` (`diagnose`
  state), the canonical dispatch shape for `evaluate.type: classify` is:

  ```yaml
  evaluate:
    type: classify
  route:
    IMPLEMENT: gate_implement
    DECIDE:    decide
    REFINE:    refine
    _:         emit_implement_failed
    _error:    emit_implement_failed
  ```

  The F2a `aggregate` state should follow this exact shape with
  `GATE_PASS` / `GATE_FAILED` / `GATE_SKIP` tokens. `ll-loop validate`
  warns when `classify` has a `route:` table with no `_:` default —
  suppression flag is `partial_route_ok: true` (per the meta-loop rules
  table at `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`).

## Implementation Decision: alias vs rename

The alias-vs-rename question must be resolved before any consumer-side
code is written. Two competing approaches are listed below in the
canonical `### Option [A-Z]` form so `/ll:decide-issue` can score and
lock in the winner via Pattern 1 of its Phase 3 extraction logic
(see `skills/decide-issue/SKILL.md` Phase 3 / Pattern 1).

### Option A (Recommended) — accept both names

Inside the new oracle's `resolve_commands` state, read via
`cfg.get('typecheck_cmd') or cfg.get('type_cmd')` and
`cfg.get('start_cmd') or cfg.get('run_cmd')`. Existing 14+ consumers
stay unchanged. The dataclass (`ProjectConfig`) and JSON Schema
(`config-schema.json:30-58`) remain canonical at `type_cmd` /
`run_cmd`; the alias logic lives only inside the new oracle's
`resolve_commands` shell action. Lower risk, additive-only — no
mechanical sweep across 14+ consumers required.

### Option B — wide mechanical rename

Rename `type_cmd → typecheck_cmd` and `run_cmd → start_cmd` across
schema, `ProjectConfig`, and 14+ loops' inline `cfg.get(...)`
patterns. Achieves cosmetic consistency at the cost of a wider
mechanical sweep across 14+ consumers and a one-time breakage of any
in-flight PR that touches those keys.

## Acceptance Criteria

- `oracles/code-run-gate.yaml` exists at
  `scripts/little_loops/loops/oracles/code-run-gate.yaml`.
- `ll-loop validate oracles/code-run-gate.yaml` exits 0 with no
  ERROR-severity findings; MR-1 and MR-3 pass.
- `python -m pytest scripts/tests/test_builtin_loops.py::TestCodeRunGateOracle`
  passes (all new oracle tests pass).
- `python -m pytest scripts/tests/test_config_schema.py::test_health_url_in_schema`
  passes.
- `ProjectConfig.from_dict(...)` round-trip preserves `health_url`
  through `.to_dict()`.
- The oracle is **not** invoked by any production loop yet (verified
  by `grep -r "loop: code-run-gate" scripts/little_loops/loops/`
  returning empty, modulo F2b's wiring).

## Scope Boundaries

- **Reuses** existing evaluator types — no new FSM primitive.
- **Does not** wire the oracle into any loop (that's F2b).
- **Does not** change `rn-implement`/`rn-remediate` behavior.
- Deployment/CD is out of scope — `service_health` is a local start +
  probe only.
- Per-archetype defaults are out of scope (defer to FEAT-2416).

## Integration Map

### Files to Create

- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — NEW FILE.

### Files to Modify

- `scripts/little_loops/config-schema.json` — append `health_url`
  property to `project.properties` (block at `:30-59`).
- `scripts/little_loops/config/core.py:142-161, 554-559` —
  `ProjectConfig` dataclass + `.from_dict()` + `.to_dict()`
  (**BLOCKER**).
- `docs/reference/CONFIGURATION.md:272-286` — add `health_url` row.
- `.ll/decisions.yaml` — record the alias-vs-rename decision.

### Files to Modify (Advisory, non-blocking)

- `scripts/little_loops/init/tui.py:282-308, 560-668, 737-740` — add
  `_ask_command`-style prompt for `health_url`.

### Pattern Sources (read-only references)

- `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml:1-56`
  — `from:` inheritance template (FEAT-2269).
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml:252-337` —
  test-state + pytest --json-report pass-rate pattern.
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml:483-499` —
  counter-progression + `classify` dispatch shape.
- `scripts/little_loops/fsm/validation.py:84-88` — MR-1 evaluator list.
- `scripts/little_loops/fsm/validation.py:_SHARED_TMP_PATH_RE` — MR-3
  `.loops/tmp/` rejection regex.

### Tests to Add

In `scripts/tests/test_builtin_loops.py`, add a `TestCodeRunGateOracle`
class (mirror `TestGeneratorEvaluatorOracle` at `:6808-6883`):

- `test_required_top_level_fields` — `name == "code-run-gate"`,
  `initial` matches.
- `test_has_parameters_block` — declares `run_dir`, `issue_id`,
  `min_pass_rate` plus the six command fields.
- `test_required_states_exist` — at minimum `resolve_commands`,
  `run_build`, `run_test`, `run_typecheck`, `run_lint`,
  `service_health`, `aggregate`, `done`, `failed`.
- `test_only_uses_non_llm_evaluators` — MR-1 trivial satisfaction;
  assert no state uses
  `action_type in ("prompt", "slash_command")` paired with
  `llm_structured` / `check_semantic`.
- `test_no_writes_to_bare_loops_tmp` — MR-3: `${context.run_dir}`
  everywhere; `.loops/tmp/` never appears in any action body.
- `test_docs_only_noop_emits_gate_skip` — `resolve_commands` must emit
  `GATE_SKIP` when ALL command fields resolve to null/empty.

In `scripts/tests/test_config_schema.py` (mirror
`test_learning_tests_in_schema` at `:188-230`):

- `test_health_url_in_schema` —
  `data["properties"]["project"]["properties"]["health_url"]` exists;
  `type == ["string", "null"]`; default null.
- `test_typecheck_cmd_alias_or_rename` and `test_start_cmd_alias_or_rename`
  per the decision recorded in Implementation Step 4.

In `scripts/tests/test_builtin_loops.py:46-54`
(`test_all_validate_as_valid_fsm`) — the auto-iterate over
`BUILTIN_LOOPS_DIR.rglob("*.yaml")` will pick up the new oracle and
assert it validates cleanly (MR-1 trivial; MR-3 compliant).

## Impact

- **Priority**: P2 — additive asset layer for the greenfield family; directly enforces the MR-1 doctrine (LLM self-grades are 33–55% accurate) on the implement path that lands in FEAT-2552.
- **Effort**: Medium — one new oracle file (~120 LOC equivalent) plus 3 small config-schema additions, all modeled on existing patterns.
- **Risk**: Low — purely additive; no existing behavior changes; F2a ships as a reusable artifact not yet invoked by any production loop.
- **Breaking Change**: No — `health_url` defaults to `null`; alias path accepts existing `type_cmd`/`run_cmd` names unchanged.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-08_

**Readiness Score**: 99/100 → PROCEED (threshold 85)
**Outcome Confidence**: 78/100 → MODERATE-POSITIVE (threshold 75)

### Outcome Risk Factors

- The alias-vs-rename decision (Implementation Step 4) must be locked
  in `.ll/decisions.yaml` *before* coding. The recommended path
  (accept both names) is documented but not yet ratified; without
  ratification the implementation may drift toward the more invasive
  rename variant mid-execution.
- The 6-state oracle is a new state-machine file; per-state shell
  semantics (`on_yes` / `on_no` / `on_error`) for `run_build`,
  `run_test`, etc. need careful MR-4 attention (each state must route
  to `aggregate` on every terminal branch — pre-empt the
  `_validate_partial_route_dead_end` warning at
  `fsm/validation.py:1575-1616`).

_No `decision_needed`, `missing_artifacts`, `mechanical_fanout_suppressed`,
or `implementation_order_risk` flag updates triggered by these risk
factors (no signal-phrase matches)._

## Session Log
- `/ll:decide-issue` - 2026-07-08T23:21:33 - `4159613b-e25e-4c7f-adcb-e3732fbe4519.jsonl`
- `/ll:format-issue` - 2026-07-08T23:18:49 - `545c6ef1-08b7-43c3-a62f-be48a9a4e635.jsonl`
- `/ll:refine-issue` - 2026-07-08T23:08:58 - `c647dd35-c503-4486-b782-2dcd71557c9e.jsonl`

- `/ll:confidence-check` - 2026-07-08T23:10:00 - `a081f85a-6f32-4531-b0ca-f9df5eae6f9f.jsonl`
- `/ll:split-issue` - 2026-07-08T23:10:00 - `a081f85a-6f32-4531-b0ca-f9df5eae6f9f.jsonl`

## Status

**Open** | Split from FEAT-2413 on 2026-07-08 | Priority: P2