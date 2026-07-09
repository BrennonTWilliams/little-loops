---
id: FEAT-2413
title: Real code run-gate oracle wired into rn-implement/rn-remediate
type: FEAT
priority: P2
status: done
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
completed_at: 2026-07-09T01:50:00Z
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Large
relates_to:
- EPIC-2412
- FEAT-2414
- ENH-2415
labels:
- loops
- verification
- greenfield
- rn-implement
- rn-remediate
decision_needed: false
learning_tests_required:
- pytest-json-report
confidence_score: 99
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 12
---

# FEAT-2413: Real code run-gate oracle wired into rn-implement/rn-remediate

## Summary

Add a reusable **code run-gate oracle** that actually runs the generated project —
build, test, typecheck, lint, and (for services) start-the-process + health probe —
scored by non-LLM evaluators (`exit_code`, `output_numeric`), and make
`rn-remediate`'s `IMPLEMENTED` verdict **require** it to pass. Today the entire
implement path judges completion from LLM-scored issue prose plus "a git diff exists,"
so plausible-but-broken code earns `IMPLEMENTED`.

## Current Behavior

The implement path judges completion from LLM-scored issue prose plus a "git diff
exists" check; `rn-implement`/`rn-remediate` never build, test, typecheck, lint, or run
the generated project. `implement`'s `on_yes → emit_implemented` fires on `ll-auto`
exit 0, and `ll-auto`'s verify phase only reads `status:` frontmatter and confirms a
diff exists.

## Expected Behavior

A reusable code run-gate oracle actually executes the generated project (build, test,
typecheck, lint, and optional service start + health probe), scored by non-LLM
evaluators. `rn-remediate`'s `IMPLEMENTED` verdict requires the gate to pass; broken
code routes to `IMPLEMENT_FAILED`.

## Use Case

**Who**: A developer running `rn-remediate` (directly or via `ll-auto`) on a
greenfield issue.

**Context**: The loop has produced a code change and is about to emit a completion
verdict.

**Goal**: Trust that an `IMPLEMENTED` verdict means the code actually builds and passes
tests, not merely that a diff exists.

**Outcome**: Implementations that fail to compile or fail tests terminate as
`IMPLEMENT_FAILED`, closing the biggest robustness hole in the greenfield family.

## Motivation

`rn-implement`/`rn-remediate` never compile, test, or run anything. `implement`'s
`on_yes → emit_implemented` fires on `ll-auto` exit 0, and `ll-auto`'s own "verify"
phase only reads `status:` frontmatter (`verify_issue_completed`,
`issue_lifecycle.py:407`) and checks a diff exists (`work_verification.py`). This is
the single biggest robustness hole in the greenfield family and directly violates the
MR-1 doctrine the repo enforces on meta-loops (LLM self-grades are 33–55% accurate).

The proven pattern already exists twice and should be generalized, not reinvented:
`oracles/generator-evaluator.yaml` (renders the artifact, snapshots per-iteration,
pairs an LLM rubric with a non-LLM `diff_stall` gate) and `cli-anything-bootstrap.yaml`
(fresh venv `pip install -e`, `--help` coverage walk, `pytest --json-report`
pass-rate — an LLM state explicitly forbidden from reading source, judging only the
measured numbers).

## Proposed Solution

Create `scripts/little_loops/loops/oracles/code-run-gate.yaml` (a `from:`-inheritable
oracle) that runs a caller-supplied command matrix and emits non-LLM verdicts:

- `build` → resolve from `.ll/ll-config.json` `project.build_cmd` (archetype default);
  gate on `exit_code`.
- `test` → `project.test_cmd` (fallback `pytest --json-report`); gate on exit code and
  a real `test_pass_rate` (`output_numeric`), captured to `${run_dir}/`.
- `typecheck`/`lint` → `project.typecheck_cmd` / `lint_cmd` (e.g. `mypy`, `ruff`);
  gate on `exit_code`.
- `service_health` (optional, archetype-driven) → start the process, poll a health
  endpoint with a bounded timeout, assert 2xx; tear down on exit.
- All quality/LLM scoring reads ONLY the measured `.txt`/`.json` files (never source),
  per the `cli-anything-bootstrap` pattern.

### Options (Codebase Research Findings)

_Added by `/ll:refine-issue` — research surfaced two distinct wiring strategies.
Recommendation is Option B (matches the analyzer's "where exactly to plug in"
finding). Use `/ll:decide-issue FEAT-2413` to formally pick before wiring._

**Option A — Inline gate states within `rn-remediate.yaml`** (faster to ship, less reusable)
- Add new states (`run_build_gate`, `run_test_gate`, `run_typecheck_gate`,
  `run_lint_gate`) directly inside `rn-remediate`, between
  `implement.on_yes` and `emit_implemented`, each using the `shell_exit`
  fragment from `loops/lib/common.yaml:15-21` for `exit_code` gating.
- Pros: no new file; minimal diff to a single YAML; no sub-loop dispatch cost.
- Cons: only `rn-remediate` benefits. FEAT-2414 (`rn-build` acceptance phase)
  and FEAT-2416 (project archetypes) cannot reuse — each would reimplement
  the same shell states. Counter coupling is more awkward (must duplicate
  the `output_numeric` budget logic).

**Option B — Sub-loop oracle `oracles/code-run-gate.yaml`** (recommended;
mirrors the proven `cli-anything-bootstrap` + `generator-evaluator-cli` pattern)

> **Selected:** Option B — Sub-loop oracle `oracles/code-run-gate.yaml` — every primitive (`from:` inheritance, `_execute_sub_loop` dispatch, `subloop_outcome_<ID>.txt` token protocol, Tier-1 evaluators) has a project-wide precedent; reuse score 3/3 vs Option A's 2/3.

- Author the oracle under
  `scripts/little_loops/loops/oracles/code-run-gate.yaml`; call it from a new
  `run_code_gate` state in `rn-remediate.yaml:483-500` via
  `loop: code-run-gate` + `with:` bindings (mirroring
  `rn-implement.yaml:695-718` `run_remediation`).
- The oracle emits `GATE_PASS` / `GATE_FAILED` / `GATE_SKIP` tokens to
  `${context.run_dir}/subloop_outcome_<ID>.txt` (the existing parent↔sub-loop
  protocol reused in `rn-implement.yaml:720-735`).
- Pros: matches `oracles/generator-evaluator.yaml` +
  `oracles/generator-evaluator-cli.yaml` (FEAT-2269) `from:` inheritance —
  archetype variants (e.g., `code-run-gate-python.yaml`) drop in trivially;
  reusable across `rn-build` and `rn-implement` standalone; MR-1 satisfied
  via single source of truth (the oracle uses only `exit_code` /
  `output_numeric` / `classify` evaluators, no LLM judge at all).
- Cons: extra FSM load (~30 ms); one new file to maintain.

### Codebase Research Findings (Proposed Solution)

_Added by `/ll:refine-issue` — concrete anchor references and design corrections:_

- The five gate states (build / test / typecheck / lint / service_health) map
  almost 1-to-1 onto the existing evaluator types listed in
  `scripts/little_loops/fsm/evaluators.py:7-23`. All are Tier-1 deterministic
  evaluators — the gate has zero LLM cost, which is exactly the point.

- For the `test` state's `test_pass_rate`, follow
  `cli-anything-bootstrap.yaml:304-337`: install `pytest pytest-json-report`
  inside the project's venv (or assume they're already on `PYTHONPATH`),
  invoke with `--json-report --json-report-file=${run_dir}/pytest.json`, parse
  `summary.passed / summary.total` via
  `python3 -c "import json; d=json.load(...); print(round(d['summary']['passed']/d['summary']['total'],3))"`,
  then write `pytest_rc`, `test_total`, `test_passed`, `test_pass_rate` to
  `${run_dir}/test-results.txt`. Wire `on_yes: score` against
  `output_numeric` (`operator: ge, target: ${context.min_pass_rate}`,
  defaulting to `1.0`).

- For the aggregate state (knits build/test/typecheck/lint/health outcomes
  into a single `GATE_PASS` / `GATE_FAILED` token), use a shell state that
  reads the sidecar `.txt` files and emits the literal token, paired with
  `evaluate.type: classify` (dispatch table) — see
  `scripts/little_loops/loops/cli-anything-bootstrap.yaml:483-499` for the
  counter-progression shape and `scripts/little_loops/fsm/evaluators.py:453-504`
  for `evaluate_classify`. **Do NOT use `llm_structured` here** — that would
  re-introduce the very LLM self-grade the issue is fighting.

- For `service_health`: launch the process with `&`, write PID to
  `${run_dir}/service.pid`, poll `${health_url}` with `curl --fail --max-time
  $BOUND`, assert HTTP 2xx; tear down with `kill $(cat ${run_dir}/service.pid)`
  in an `on_yes`/`on_no`/`on_error` ensure-via `trap` shell expression so the
  process never lingers.

- **Schema correction** — `scripts/little_loops/config-schema.json:20-59`
  already exposes `build_cmd`, `type_cmd`, `lint_cmd`, `run_cmd`, `test_cmd`.
  The issue's Step 2 lists `typecheck_cmd` and `start_cmd` as new fields, but
  those are renames of existing keys. Decide:
  (i) accept both names (`typecheck_cmd or type_cmd`, `start_cmd or run_cmd`)
      for back-compat, or
  (ii) rename in schema + add a migration for existing `.ll/ll-config.json`
       consumers. Only `health_url` is genuinely missing from the schema.

- **MR-1 trivial satisfaction** — per
  `scripts/little_loops/fsm/validation.py:84-88`, an evaluator-only oracle
  with `exit_code` / `output_numeric` / `classify` evaluators passes MR-1
  without needing `meta_self_eval_ok: true`. The gate oracle should not
  set `meta_self_eval_ok`.

- **MR-3 / run_dir isolation** — per
  `scripts/little_loops/fsm/validation.py:_SHARED_TMP_PATH_RE`, the oracle
  must write all artifacts under `${context.run_dir}/` (resolved via the
  `case "${context.run_dir}" in /*) ABS_DIR=... ;; *) ABS_DIR="$(pwd)/..." ;; esac`
  idiom from `oracles/generator-evaluator.yaml:71-74`). Do NOT use
  `.loops/tmp/` — that's the per-host shared path and breaks under
  concurrent runs.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-08.

**Selected**: Option B — Sub-loop oracle `oracles/code-run-gate.yaml`

**Reasoning**: Option B reuses every primitive it needs from established project infrastructure — `from:`-inheritable oracle pattern (FEAT-2269 `oracles/generator-evaluator-cli.yaml:1-56`), `_execute_sub_loop` dispatch (`fsm/executor.py:734-855`), parent↔sub-loop `subloop_outcome_<ID>.txt` token protocol (`rn-implement.yaml:720-735`, `lib/common.yaml:368`), and Tier-1 evaluators (`exit_code` / `output_numeric` / `classify`) that satisfy MR-1 without `meta_self_eval_ok` (`fsm/validation.py:84-88`). Option A would have to port the `pytest --json-report` `test_pass_rate` parsing inline (no precedent outside `cli-anything-bootstrap.yaml:304-337`) and navigate an awkward counter-coupling scheme with `check_remediation_budget` at `rn-remediate.yaml:782-800` (double-count risk vs. loss of `check_convergence`'s dimensional diagnosis). Reusability matters too — 7+ loops (`rn-remediate`, `rn-implement`, `rn-build`, `recursive-refine`, `proof-first-task`, `autodev`, `scan-and-implement`) all generate runnable code; Option A's inline states can only be reused by promoting to `lib/common.yaml` fragments, defeating the "minimal diff" benefit.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Inline gate states | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option B — Sub-loop oracle | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:

- **Option A** (reuse_score 2/3): Reuses `shell_exit` fragment (`lib/common.yaml:15-21`) and Tier-1 evaluators directly; 4 inline test-gate precedents exist (`harness-single-shot.yaml:54-71`, `fix-quality-and-tests.yaml:56-76`, `test-coverage-improvement.yaml:141-157`, `incremental-refactor.yaml:30-35`). Loses the score because (1) `test_pass_rate` JSON parsing has no inline precedent — would be a fresh port from `cli-anything-bootstrap.yaml:304-337`; (2) counter-coupling with `check_remediation_budget` creates double-count risk via `check_convergence` or parallel-counter drift; (3) cannot serve FEAT-2414 (`rn-build`) / FEAT-2416 (archetypes) without copy-paste or fragment promotion; (4) docs-only `GATE_SKIP` guard requires an extra preliminary state.
- **Option B** (reuse_score 3/3): Every primitive has project-wide precedent. `from:`-inheritable oracle (FEAT-2269), `loop:` + `with:` dispatch (`fsm/executor.py:772-806`), `subloop_outcome_<ID>.txt` token protocol (`rn-implement.yaml:720-735`), MR-3 `${run_dir}` isolation idiom (`oracles/generator-evaluator.yaml:71-74`), `TestSubloopSidecarContract` auto-enforcement (`test_builtin_loops.py:296-316`), schema resolution fallback (`general-task.yaml:33-37`, `:469-477`). One new file plus one caller; no new FSM primitive.

## Implementation Steps

1. Author `oracles/code-run-gate.yaml` with `build`/`test`/`typecheck`/`lint`/
   `service_health` states, per-iteration artifact snapshots under `${run_dir}/`, and
   `on_error` routes on every state.
2. Extend `.ll/ll-config.json` / `config-schema.json` with optional
   `project.{build_cmd,typecheck_cmd,lint_cmd,health_url,start_cmd}` (test_cmd exists).
3. Wire `rn-remediate`: after `implement`, invoke `code-run-gate` as a sub-loop before
   `emit_implemented`; a failing gate routes to a remediation pass (respecting
   `max_remediation_passes`) or `IMPLEMENT_FAILED`, not `IMPLEMENTED`.
4. Thread the gate's outcome token through `rn-implement`'s `classify_remediation`
   routing so counters/summary reflect real build status.
5. Ensure the gate is a no-op-pass for issues that legitimately produce no runnable
   code (docs-only), guarded by config/archetype, not by an LLM.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchor references per step:_

1. **Authoring (`oracles/code-run-gate.yaml`)** — model after the proven 3-state
   `cli-anything-bootstrap.yaml:252-337` pattern (`verify-cli` fresh-venv install
   + `run-cli-tests` pytest --json-report). Add `service_health` modeled on
   `verify-cli`'s subprocess polling. Use the `${run_dir}` → absolute-path idiom
   from `oracles/generator-evaluator.yaml:71-74`. Per-iteration snapshot mirror
   `oracles/generator-evaluator.yaml:80-94` (writes under `${context.run_dir}/`
   to satisfy MR-3).

2. **Config schema** — only add `health_url` and **alias** the existing
   `type_cmd` / `run_cmd` (or rename for consistency). Resolution pattern from
   `general-task.yaml:35`: `python3 -c "import json,pathlib; p=pathlib.Path('.ll/ll-config.json'); cfg=json.loads(p.read_text()) if p.exists() else {}; print(cfg.get('project',{}).get('test_cmd','pytest'))"`.
   Apply same idiom for all six fields. Defaults: `test_cmd=pytest`,
   `build_cmd=null`, `type_cmd=mypy`, `lint_cmd=ruff check .`, `run_cmd=null`,
   `health_url=null`.

3. **Wiring `rn-remediate`** — pattern from `rn-implement.yaml:695-718`
   (`run_remediation`). New state `run_code_gate` after `implement` (line 499)
   and before `emit_implemented` (line 810):

   ```yaml
   run_code_gate:
     loop: code-run-gate
     with:
       issue_id: "${context.issue_id}"
       run_dir: "${context.run_dir}"
       min_pass_rate: "${context.min_pass_rate}"   # default 1.0 if absent
     on_success: emit_implemented
     on_failure: record_gate_failure    # writes GATE_FAILED to token channel
     on_error:   record_gate_error      # on_error is for child-crash, not failure
   ```

   `on_failure` increments `remediation_count_<ID>.txt` (counter shared with
   `check_remediation_budget` at `:782-800`) so `max_remediation_passes` is
   naturally respected without a parallel counter mechanism.

4. **Token thread to `rn-implement`** — no change needed. The existing
   `classify_remediation` at `rn-implement.yaml:720-735` reads
   `subloop_outcome_<ID>.txt` and the existing `route_rem_*` chain (next ~200
   lines) classifies every known failure token. `GATE_FAILED` falls through to
   `record_failure` at `:941` because no preceding `output_contains` matches.
   For diagnostic counter separation, add `route_rem_gate_failed` next to
   `route_rem_scores_missing` (mirrors `:898-910`).

5. **Docs-only no-op-pass** — implement as a config/archetype guard inside
   `code-run-gate` itself, NOT as an LLM call. Concretely: the first state of
   the oracle (`resolve_commands`) writes `commands.json` to `${run_dir}/`,
   exits 0 with `GATE_SKIP` if **all of** `test_cmd`/`build_cmd`/`type_cmd`/
   `lint_cmd`/`run_cmd`/`health_url` resolve to null/empty (i.e., the project
   archetype declares itself docs-only or no commands configured). Emit
   `GATE_SKIP` to the token channel so `rn-remediate` treats it the same as
   `GATE_PASS` (proceed to `emit_implemented`). See
   `loops/cli-anything-bootstrap.yaml:97-105` for a similar "missing artifact"
   graceful-skip pattern.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation commit. Each item below corresponds to a row in the Integration
Map sections appended above (look for `_Wiring pass added by `/ll:wire-issue`:_`)._

6. **Update `scripts/little_loops/config/core.py:142-161, 554-559`** — BLOCKER for
   the implementation commit. Add `health_url: str | None = None` to `ProjectConfig`,
   read it in `.from_dict()` (line ~161), serialize it in `.to_dict()`. Without
   this, the new schema key is silently dropped on `.ll/ll-config.json` round-trip;
   the gate's `service_health` state will never see the health URL even when set.
7. **Update existing tests that will break**:
   - `scripts/tests/test_rn_remediate.py:482-486` (`test_implement_routes_to_done`)
     and `:1374-1379` (`test_implement_success_emits_implemented`) — change
     assertion from `on_yes == "emit_implemented"` → `on_yes == "run_code_gate"`.
   - `scripts/tests/test_builtin_loops.py:333-361` (`TestSubloopSidecarContract`) —
     decide (a) `SUBLOOPS += ("oracles/code-run-gate.yaml",)` and add a sidecar
     write to the oracle's terminal-routing states, OR (b) keep the parent
     contract unchanged and let `rn-remediate` translate the oracle's verdict into
     the standard `IMPLEMENTED`/`IMPLEMENT_FAILED` token (matches the docs-only
     no-op-pass plan above at lines 277-286).
   - `scripts/tests/test_builtin_loops.py:46-54` (`test_all_validate_as_valid_fsm`)
     — confirm the new oracle validates cleanly (MR-1 trivial; no LLM judges;
     `${run_dir}`-isolated artifacts).
   - `scripts/tests/test_rn_implement.py:9132-9166` — if `route_rem_gate_failed`
     is added, mirror the `route_rem_scores_missing` test class.
8. **Add `health_url` to `scripts/little_loops/config-schema.json`** — append
   `"health_url": {"type": ["string", "null"], "default": null}` to
   `project.properties` (block at lines 30-59). Required because
   `additionalProperties: false` at line 61 rejects unknown keys.
9. **Make the alias-or-rename decision for `typecheck_cmd`/`start_cmd`**:
   - Recommended path: **accept both names**. Inside the new oracle's
     `resolve_commands` state, read via
     `cfg.get('typecheck_cmd') or cfg.get('type_cmd')` (and
     `cfg.get('start_cmd') or cfg.get('run_cmd')`). Existing 14+ consumers
     of `type_cmd` / `run_cmd` stay unchanged.
   - Alternative (wide mechanical sweep): rename `type_cmd → typecheck_cmd`
     and `run_cmd → start_cmd` across schema, `ProjectConfig`, and 14+ loops'
     inline `cfg.get(...)` patterns.
   - Record the decision in `.ll/decisions.yaml` per existing schema-coupling
     decision pattern.
10. **Add `health_url` row to `docs/reference/CONFIGURATION.md:281-286`**
    (alongside the existing project-commands rows).
11. **(Advisory, not blocking)** Add `_ask_command`-style TUI prompt for
    `health_url` in `scripts/little_loops/init/tui.py:282-308` (mirrors the
    existing `test_cmd`/`lint_cmd`/`type_cmd`/`format_cmd` prompt surface;
    defaults to `null` for non-service projects).
12. **(Advisory, defer to release prep)** Add a one-line entry to
    `CHANGELOG.md` under a concrete `## [X.Y.Z] - DATE` section (NOT
    `[Unreleased]` per memory `feedback_changelog_no_unreleased.md`).
13. **(Advisory, defer to FEAT-2416)** Per-archetype `health_url` defaults in
    `scripts/little_loops/templates/{python-generic,javascript,typescript,
    rust,java-gradle,java-maven,go,dotnet,generic}.json`. The JSON Schema's
    `null` default and `additionalProperties: false` permit omission in the
    meantime, so no immediate template change is required.

## Acceptance Criteria

- A deliberately broken implementation (compile error or failing test) yields
  `IMPLEMENT_FAILED`, never `IMPLEMENTED`.
- `test_pass_rate` and build/typecheck/lint exit codes are captured to `${run_dir}/`
  and are the routing signal (non-LLM), satisfying MR-1.
- `ll-loop validate rn-remediate` passes; the new oracle passes MR-1/MR-3.
- Integration test: `rn-remediate` on a seeded failing issue does not terminate as
  implemented.

## Scope Boundaries

- Reuses existing evaluator types; no new FSM primitive.
- Deployment/CD is out of scope — `service_health` is a local start + probe only.

## Integration Map

- New: `oracles/code-run-gate.yaml`; config schema additions.
- Modified: `rn-remediate.yaml` (implement → gate → emit_*), `rn-implement.yaml`
  (token routing).
- Pattern sources: `oracles/generator-evaluator.yaml`, `cli-anything-bootstrap.yaml`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Files to Modify (with anchor refs)

- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — **NEW FILE**, not yet on disk.
  Must be authored as a `from:`-inheritable oracle mirroring
  `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml:1-56` (FEAT-2269).
- `scripts/little_loops/loops/rn-remediate.yaml:483-500` — Insert a new
  `run_code_gate` state between `implement.on_yes` and `emit_implemented`.
  Reuse the `shell_exit` fragment from `loops/lib/common.yaml:15-21` for the
  simplest `exit_code` gate.
- `scripts/little_loops/loops/rn-implement.yaml:720-735` (`classify_remediation`
  + `route_rem_implemented`) — already routes via `output_contains` on
  `subloop_outcome_<ID>.txt`. **Reuse this token channel rather than rethread**
  — the gate failure path can write `GATE_FAILED` (and the existing `route_rem_*`
  chain falls through to `record_failure` at `:941` for any non-`IMPLEMENTED`
  token).
- `scripts/little_loops/config/core.py:142-161, 554-559` — **BLOCKER** (not in prior plan).
  `ProjectConfig` dataclass must add `health_url: str | None = None` and `.from_dict()`
  must read it (line ~161: `health_url=data.get("health_url")`); `.to_dict()` at `:554-559`
  must serialize the key. Without this, the new `health_url` schema field will be
  silently dropped on `.ll/ll-config.json` round-trip — the loop reads config via
  this dataclass, so a missing field means the gate's `service_health` state never
  sees the health URL even when set.
- `scripts/little_loops/init/tui.py:282-308, 560-668, 737-740` — Add a `_ask_command`-style
  prompt for `health_url` (defaulting to `null` for non-service projects). Mirrors
  the existing `test_cmd`/`lint_cmd`/`type_cmd`/`format_cmd` prompt surface.
  Advisory (non-blocking; users with no service can leave blank).
- `scripts/little_loops/templates/{python-generic,javascript,typescript,rust,java-gradle,java-maven,go,dotnet,generic}.json` — 9 archetype templates may need a parallel `health_url: null` row.
  **Defers to FEAT-2416** per the issue's Scope. JSON Schema's `additionalProperties: false`
  at `config-schema.json:61` permits omission (default null), so no immediate template
  change required for FEAT-2413 itself; flagged here so the deferral is explicit.
- `docs/reference/loops.md:389-489` — Add a new `## \`oracles/code-run-gate\`` section
  mirroring the auto-generated `oracles/generator-evaluator-cli` entry. The reference
  is auto-generated, so the entry will be picked up next time docs are regenerated.
- `CHANGELOG.md` — Entry under a concrete `## [X.Y.Z] - DATE` section (NOT
  `[Unreleased]` — see `feedback_changelog_no_unreleased.md`). Add at release prep
  time, not during implementation.

#### Dependent Files / Consumers

- `scripts/little_loops/loops/rn-remediate.yaml:810-820` (`emit_implemented`)
  and `:996-1000` (`emit_implement_failed`) write verdict tokens to
  `${context.run_dir}/subloop_outcome_<ID>.txt`.
- `scripts/little_loops/loops/rn-remediate.yaml:782-800`
  (`check_remediation_budget`) already enforces `max_remediation_passes` via
  `output_numeric` against `remediation_count_<ID>.txt`. The gate failure path
  should increment this same counter so a gate fail consumes a remediation pass
  (FEAT-2413 step 3 AC).
- `scripts/little_loops/issue_lifecycle.py:444-478` (`verify_issue_completed`)
  — **issue-cited `:407` is wrong; actual function lives at `:444`**. Pure
  `status:` frontmatter check (`status in ("done", "cancelled")`).
- `scripts/little_loops/work_verification.py:44-161` (`verify_work_was_done`)
  — diff-existence-only gate via `git diff --name-only` filtered through
  `EXCLUDED_DIRECTORIES` (`.issues/`, `issues/`, `.speckit/`, `thoughts/`,
  `.worktrees/`, `.auto-manage`). This is what `IMPLEMENTED` currently relies
  on; the new gate sits orthogonal to this flow.
- `scripts/little_loops/issue_manager.py:1002` — Phase 3 verify calls
  `verify_issue_completed`; lines `:1020`, `:1057` fall back to
  `verify_work_was_done`.

_Wiring pass added by `/ll:wire-issue`:_

The following callers consume the `rn-implement`/`rn-remediate` token channel transitively
and inherit the gate for free (no per-loop edits required, but listed for completeness):

- `scripts/little_loops/loops/autodev.yaml:80, 435` — parent orchestrator; delegates to
  `ll-auto --only` which routes to `rn-implement` → `rn-remediate`. The gate is invoked
  transparently for any issue routed through `autodev` → `ll-auto` → `rn-implement` →
  `rn-remediate` → `code-run-gate`. **No direct change.**
- `scripts/little_loops/loops/scan-and-implement.yaml:75` — `loop: autodev`. Inherits
  gate transitively. **No direct change.**
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:133` — `loop: autodev`.
  Inherits transitively. **No direct change.**
- `scripts/little_loops/loops/rn-build.yaml:535` — dispatches `rn-implement(value_ranked)`.
  Inherits gate transitively. **No direct change.**
- `scripts/little_loops/loops/goal-cluster.yaml:533` — dispatches batches to
  `rn-implement`. Inherits transitively. **No direct change.**
- `scripts/little_loops/recursive_finalize.py` — `rn-implement` lifecycle integration.
  The `GATE_FAILED` token will appear in any completion summary it produces; verify
  the lifecycle bookkeeping handles the new token gracefully (likely falls through to
  existing `failure` branch — see the routing analysis above).
- `scripts/little_loops/workflow_sequence/analysis.py` — sequence analysis treats
  `rn-implement` runs as "plan → implement → verify" steps. The new gate inserts a
  "gate" step between implement and verify; verify the analyzer handles the new
  intermediate step (advisory — should fall through by default).

Confirmed orthogonal (no change required) — these complete verification via a different
mechanism and never see `subloop_outcome_*.txt`:

- `scripts/little_loops/issue_lifecycle.py:444` (`verify_issue_completed`)
- `scripts/little_loops/work_verification.py:44` (`verify_work_was_done`)
- `scripts/little_loops/parallel/worker_pool.py:567, 1149, 1173` (uses `verify_work_was_done`)
- `scripts/little_loops/git_operations.py:18` (imports `verify_work_was_done`)
- `scripts/little_loops/cli/auto.py`, `parallel/worker_pool.py`, `cli/sprint.py`,
  `cli/session.py`, `cli/history.py`, `cli/artifact.py` — none read the gate's
  token channel.
- `.claude-plugin/plugin.json` — oracles are NOT individually registered (only
  commands/skills/agents listed); the new oracle is auto-discovered by
  `cli/loop/info.py:160` (`rglob("*.yaml")`) and runtime schema validation. **No
  manifest change required.**
- `.ll/decisions.yaml:4600-4606` — already records the FEAT-2413 decision (no further
  decision entry needed unless a follow-on schema decision is required).

#### Similar Patterns to Follow

- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — minimal-valid
  template: `evaluate` → `snapshot` (per-iteration artifact versioning) →
  `score` → `check_stall` → `check_diff_stall` → `done`.
- `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml:1-56` —
  first `from:`-inheritable oracle (FEAT-2269); overrides `evaluate`
  (output_contains) and `snapshot` (multi-view artifact) only.
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml:252-302`
  (`verify-cli`) — `exit_code` from `pip install -e .` in fresh venv, writes
  measurable metrics to `verify-cli.txt` (MR-1 pattern).
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml:304-337`
  (`run-cli-tests`) — pytest JSON report → `test_pass_rate` → `test-results.txt`
  (closest analog for the `test` state).
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml:339-379`
  (`score-bootstrap`) — LLM judge **forbidden from inspecting source code**,
  reads ONLY `.txt`/`.json` files.
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml:483-499`
  (`count-refine-cycle`) — `output_numeric` against `refine_count.txt` with
  `operator: lt, target: ${max_refine_cycles}`; mirrors the proposed
  `max_remediation_passes` enforcement.

#### Tests

- `scripts/tests/test_rn_implement.py` — `TestImplementAndEmitImplemented`
  class (~line 1347-1622) covers IMPLEMENTED token routing; extend to cover
  the new gate failure path.
- `scripts/tests/test_rn_remediate.py` — covers `run_remediation must pass
  run_dir to rn-remediate` (line 257); add tests for `run_code_gate` sub-loop
  dispatch and gate-failure token routing.
- `scripts/tests/test_builtin_loops.py` — cross-loop validator; will exercise
  the new oracle's `ll-loop validate` (MR-1 + MR-3 + MR-4 must pass).
- `scripts/tests/test_work_verification.py` and
  `scripts/tests/test_issue_lifecycle.py` — unchanged; they belong to the
  existing broken gate, not the new oracle.

_Wiring pass added by `/ll:wire-issue`:_

**WILL BREAK (must update in same commit as the implementation):**

- `scripts/tests/test_rn_remediate.py:482-486` — `test_implement_routes_to_done`
  asserts `implement.on_yes == "emit_implemented"`. After FEAT-2413 this MUST
  change to `on_yes == "run_code_gate"`. The pre-gate direct route to
  `emit_implemented` is being broken intentionally.
- `scripts/tests/test_rn_remediate.py:1374-1379` — `test_implement_success_emits_implemented`
  (in `TestOutcomeTokenChannel`). Same assertion; update identically.
- `scripts/tests/test_builtin_loops.py:46-54` — `test_all_validate_as_valid_fsm`
  auto-iterates `BUILTIN_LOOPS_DIR.rglob("*.yaml")` and runs `validate_fsm`. The
  new `oracles/code-run-gate.yaml` MUST validate without ERROR severity (MR-1
  trivial via `exit_code`/`output_numeric`/`classify` only; MR-3 artifact writes
  under `${run_dir}`; no LLM-judge states).
- `scripts/tests/test_builtin_loops.py:333-361` — `TestSubloopSidecarContract.test_terminal_routing_states_write_sidecar`
  iterates `SUBLOOPS = ("rn-remediate", "rn-decompose")`. Either:
  (a) add `"oracles/code-run-gate.yaml"` to `SUBLOOPS` if the new oracle writes
  directly to `subloop_outcome_<ID>.txt` (matches a strict reading of the issue's
  "emit GATE_PASS/FAILED/SKIP to the token channel" plan at `:128-129`), OR
  (b) keep the oracle out of this sweep and write a dedicated `TestCodeRunGateOracle`
  (the `rn-remediate` parent re-emits `IMPLEMENTED`/`IMPLEMENT_FAILED` so the
  contract invariant holds if sidecar tokens are translated inside `rn-remediate`,
  matching issue `:280-286`).
  The implementation commit MUST pick (a) or (b) and update accordingly.
- `scripts/tests/test_rn_implement.py:9132-9166, :8264-8273` — `route_rem_scores_missing`
  test class. If the new `route_rem_gate_failed` state is added adjacent to
  `route_rem_scores_missing` (per issue `:274-275`), these tests need a sibling
  class (see New tests below).

**MAY NEED REVIEW (no direct assertion, but interact with new code):**

- `scripts/tests/test_fsm_persistence.py:3028-3041` — `rn-implement` snapshots.
  If the implement path's on_yes routing changes (only via `rn-remediate`, not
  `rn-implement` directly), no snapshot change is needed.
- `scripts/tests/test_rn_implement.py:454-471` — `test_report_writes_per_issue_array_with_outcome_per_id`
  synthesizes sidecars with `IMPLEMENTED`/`MANUAL_REVIEW_RECOMMENDED`/`LEARNING_GATE_BLOCKED`.
  Does not assert exhaustive token coverage; a new `GATE_FAILED` token will flow
  through the report without breaking the test (the test asserts presence of the
  3 known keys, not full enumeration). Review the `report` action body at `:416-452`
  to confirm it reads tokens generically.
- `scripts/tests/test_rn_implement.py:494-553` — `test_report_malformed_sidecar_does_not_crash_run`
  + `test_report_preserves_existing_scalar_keys`. Same — verify the report action
  handles new tokens without crashing.

**NEW tests to write (per implementation plan):**

In `scripts/tests/test_rn_remediate.py`, add a `TestRunCodeGate` class (mirror
`TestSubLoopDelegation` at `:233-350` in `test_rn_implement.py`):

- `test_run_code_gate_state_exists` — `run_code_gate` state is added to `rn-remediate`.
- `test_run_code_gate_is_subloop_delegation` — `state["loop"] == "code-run-gate"`.
- `test_run_code_gate_has_with_bindings` — passes `issue_id`, `run_dir`, `min_pass_rate`
  (default 1.0).
- `test_run_code_gate_routes_on_success_to_emit_implemented`.
- `test_run_code_gate_routes_on_failure_to_record_gate_failure`.
- `test_run_code_gate_routes_on_error_to_record_gate_error`.
- `test_implement_on_yes_routes_to_run_code_gate` — replaces
  `test_implement_routes_to_done` assertion.

In `scripts/tests/test_rn_implement.py`, add a `TestRouteRemGateFailed` class (mirror
`route_rem_scores_missing` tests at `:898-910`):

- `test_route_rem_gate_failed_state_exists`.
- `test_route_rem_gate_failed_matches_gate_failed_token` — `evaluate.pattern == "GATE_FAILED"`.
- `test_route_rem_gate_failed_routes_to_record_failure` (or new `record_gate_failure`).
- `test_route_rem_gate_failed_source_uses_rem_outcome_capture`.
- `test_classifier_states_exist` (`:798-815`) needs `"route_rem_gate_failed"` added to
  its tuple (or kept simple by relying on fall-through to `record_failure`).

In `scripts/tests/test_builtin_loops.py`, add a `TestCodeRunGateOracle` class (mirror
`TestGeneratorEvaluatorOracle` at `:6808-6883`):

- `test_required_top_level_fields` — `name == "code-run-gate"`, `initial` matches.
- `test_has_parameters_block` — declares `run_dir`, `issue_id`, `min_pass_rate` plus
  the six command fields.
- `test_required_states_exist` — at minimum `resolve_commands`, `run_build`, `run_test`,
  `run_typecheck`, `run_lint`, `service_health`, `aggregate`, `done`, `failed`.
- `test_only_uses_non_llm_evaluators` — MR-1 trivial satisfaction; assert no state uses
  `action_type in ("prompt", "slash_command")` paired with `llm_structured`/`check_semantic`.
- `test_no_writes_to_bare_loops_tmp` — MR-3: `${context.run_dir}` everywhere; `.loops/tmp/`
  never appears in any action body.
- `test_docs_only_noop_emits_gate_skip` — `resolve_commands` must emit `GATE_SKIP`
  (and write `subloop_outcome_<ID>.txt` if option (a) above) when ALL command fields
  resolve to null/empty.

In `scripts/tests/test_config_schema.py` (mirror `test_learning_tests_in_schema`
at `:188-230`):

- `test_health_url_in_schema` — `data["properties"]["project"]["properties"]["health_url"]`
  exists; `type == ["string", "null"]`; default null. Required because of
  `additionalProperties: false` at `config-schema.json:61`.
- If alias-or-rename is decided: `test_typecheck_cmd_alias_or_rename` and
  `test_start_cmd_alias_or_rename` per the decision recorded in Implementation
  Step 6.

**NO CHANGE required** — these are orthogonal:

- `scripts/tests/test_issue_manager.py` (extensive mocking of `verify_issue_completed`
  / `verify_work_was_done` at lines 1742, 1886, 2024, 2355, 2422, 2431, 2465, 2474,
  2505, 2545, 2554, 2562, 2565, 2594, 2607, 2645, 2654, 2695, 2700, 2775, 3606,
  3631, 3784, 3816, 3840) — orthogonal.
- `scripts/tests/test_work_verification.py`, `test_issue_lifecycle.py:37,429-527`,
  `test_subprocess_mocks.py:434,451-470` — orthogonal.
- `scripts/tests/test_fsm_executor.py` (sub-loop dispatch is generic).
- `scripts/tests/test_fsm_validation.py` (auto-sweep catches MR-1 trivial).

#### Configuration

- `scripts/little_loops/config-schema.json:20-59` — `project.*` block ALREADY
  contains `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`, `build_cmd`,
  `run_cmd` (see `loops/general-task.yaml:35` resolution pattern).
  **Correction to Step 2 of "Implementation Steps"**: only `health_url` is
  genuinely missing. `typecheck_cmd` (existing: `type_cmd`) and `start_cmd`
  (existing: `run_cmd`) are rename-or-aliased choices — either rename for
  consistency OR accept both as aliases via
  `cfg.get("typecheck_cmd") or cfg.get("type_cmd")` etc.
- `docs/reference/CONFIGURATION.md:272-286` — config docs table; add
  `health_url` row.
- `scripts/little_loops/templates/*.json` (12 archetype templates under
  `scripts/little_loops/templates/`) — provide per-archetype defaults for
  the new schema fields once `health_url` is added (FEAT-2416 sister issue
  picks this up).

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/config/core.py:142-161` — **BLOCKER** for the implementation
  commit. `ProjectConfig` dataclass fields list must include
  `health_url: str | None = None`. Without this, the new schema key is silently
  dropped during `.from_dict()`. The 14+ existing consumers that read via
  `cfg.get('project', {}).get('test_cmd')` (e.g., `loops/general-task.yaml:35,476`,
  `loops/fix-quality-and-tests.yaml:64`, `loops/evaluation-quality.yaml:49`,
  `loops/dead-code-cleanup.yaml:75`, `loops/harness-single-shot.yaml:64`,
  `loops/harness-multi-item.yaml:92`,
  `loops/harness-plan-research-implement-report.yaml:124`,
  `loops/test-coverage-improvement.yaml:43,150`, `loops/rl-coding-agent.yaml:15-66`,
  `loops/incremental-refactor.yaml:10,31`) all use the `.get()` fallback idiom,
  so a new `health_url` key in the dict (even if not on the dataclass) would still
  be settable — but `to_dict()` round-trip will silently drop it.
- `scripts/little_loops/config/core.py:554-559` — symmetric update: `.to_dict()`
  must serialize `health_url`.
- `scripts/little_loops/init/validate.py:102-122` — `_check_tool_commands` cmd_fields
  list (test_cmd/lint_cmd/type_cmd/format_cmd) is unaffected because `health_url`
  is a URL, not a command. No update needed here.
- **Alias-vs-rename decision needed before Implementation Step 6**: the codebase
  has 14+ loops reading `cfg.get('type_cmd')` / `cfg.get('run_cmd')`. **Recommendation**:
  *accept both names* — `cfg.get('typecheck_cmd') or cfg.get('type_cmd')` etc.,
  scoped to the new oracle. This keeps the existing schema consumers unchanged
  and avoids a wide-but-mechanical sweep. (Issue's `:174-179` correction already
  calls this out as the path of least disruption.)

#### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:94-107` — MR-1 doctrine source.
  A code-run-gate oracle using ONLY `exit_code` / `output_numeric` /
  `classify` evaluators satisfies MR-1 **trivially** — no
  `meta_self_eval_ok` suppression needed.
- `docs/ARCHITECTURE.md` — references the `verify_issue_completed` /
  `verify_work_was_done` flow the issue calls out; will need a paragraph
  noting the gate sits orthogonal to that flow.
- `.claude/CLAUDE.md` — project instructions table summarizing MR-1…MR-10;
  cite once the oracle lands.

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/loops.md:389-489` — Add a new `## \`oracles/code-run-gate\``
  reference section mirroring the auto-generated `oracles/generator-evaluator-cli`
  entry. Cross-link from the existing `recursive-refine` and `rn-implement`
  descriptions.
- `docs/guides/LOOPS_REFERENCE.md:1306, 1324` — descriptive prose mentions the
  sibling oracles; review whether `oracles/code-run-gate` warrants a mention
  when called by a named harness (advisory — defer until first harness caller).
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:1196-1197` — same — cross-link if
  used by `hitl-compare` or another named harness.
- `docs/reference/API.md:2160-2220, 2379-2382, 4357` — already documents
  `verify_work_was_done`/`verify_issue_completed`. Consider a brief addendum
  noting the gate sits orthogonal to these — defer to `docs/ARCHITECTURE.md`
  instead to avoid duplication.
- `scripts/little_loops/loops/README.md:151` — already mentions the orthogonal
  verification flow; no change unless the README is being rewritten.
- `CHANGELOG.md` — Add a one-line entry under a concrete `## [X.Y.Z] - DATE`
  section at release prep time (NOT `[Unreleased]` per
  `feedback_changelog_no_unreleased.md`).
- `skills/audit-loop-run/SKILL.md:285, 292` — surfaces `rn-implement`'s
  `implemented` counter as claimed-success signal. Verify the audit still
  reflects the new gate as a real signal (gate-pass + diff-exists + status=done =
  full success).
- `skills/distill-traces/SKILL.md:217-221` — distill `rn-remediate` traces.
  The new gate inserts an intermediate step; verify the distill regex still
  groups correctly (likely falls through by default).
- `skills/decide-issue/SKILL.md:485` — references `rn-remediate` as FSM-driven
  deterministic companion. No change unless the skill calls out gate behavior.
- `.claude/CLAUDE.md` — MR-1 doctrine table does NOT need a new entry (the
  oracle satisfies MR-1 trivially; no `meta_self_eval_ok` suppression needed).
  Confirmed by `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:94-107` docstring.

#### Validation Hooks

- `scripts/little_loops/fsm/validation.py:1275-1354` — `_is_meta_loop` +
  `_validate_meta_loop_evaluation` is the MR-1 gate. `NON_LLM_EVALUATOR_TYPES`
  at `validation.py:84-88` includes `exit_code`, `output_numeric`,
  `output_json`, `output_contains`, `convergence`, `diff_stall`,
  `score_stall`, `classify` — any of these satisfies MR-1.
- `scripts/little_loops/fsm/validation.py:1575-1616`
  (`_validate_partial_route_dead_end` — MR-4) only fires on LLM-judged states
  (`action_type in ("prompt", "slash_command")`); shell-based states are
  exempt — the run-gate oracle is naturally MR-4-clean.
- `scripts/little_loops/fsm/executor.py:734-855` — `_execute_sub_loop`
  does the `loop:` + `with:` dispatch; see `rn-implement.yaml:695-718`
  (`run_remediation`) for a working example.

## Impact

- **Priority**: P2 - Single biggest robustness hole in the greenfield family; directly
  enforces the MR-1 doctrine (LLM self-grades are 33–55% accurate) on the implement path.
- **Effort**: Large - New reusable oracle plus config-schema additions and rewiring of
  two loops (`rn-remediate`, `rn-implement`); reuses existing evaluator types and two
  proven gate patterns.
- **Risk**: Medium - Changes the completion verdict of the core implement path; a
  docs-only no-op-pass guard is required to avoid false failures.
- **Breaking Change**: No

## Status

**Done** | Created: 2026-06-30 | Completed: 2026-07-09 | Priority: P2 | Split 2026-07-08 → FEAT-2551 / FEAT-2552


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-08_

**Readiness Score**: 99/100 → PROCEED (threshold 85)
**Outcome Confidence**: 68/100 → MODERATE (threshold 75)

### Outcome Risk Factors
- Broad blast radius across 12+ files (oracle authoring, FSM rewiring of `rn-remediate`/`rn-implement`, config schema additions in `config-schema.json`/`config/core.py`, 5+ test files, docs). The fanout spans `loops/`, `scripts/little_loops/config/`, `scripts/tests/`, and `docs/`; consider splitting the work into two PRs (oracle + config + tests first; FSM rewiring second) to localize the failure surface and ease review.
- Transitive token-channel fanout — 7+ loops inherit the new gate behavior via `rn-implement`/`rn-remediate`'s `subloop_outcome_<ID>.txt` channel (`autodev`, `scan-and-implement`, `auto-refine-and-implement`, `rn-build`, `goal-cluster`, `recursive_finalize`, `workflow_sequence/analysis`). A bug in the new gate or its routing propagates across the entire greenfield family.
- Implementation step 9 (alias-vs-rename choice for `typecheck_cmd`/`start_cmd`) needs formal ratification in `.ll/decisions.yaml` per the existing schema-coupling decision pattern; the issue recommends the alias path. Without ratification, the implementation may drift toward the more invasive rename variant during execution.

_Added by `/ll:confidence-check` on 2026-07-08 (split pass)_

**Split decision**: outcome confidence was 68/100 (MODERATE) dominated
by 12+ site breadth and 7+ transitive token-channel consumers, not
ambiguity. Decomposed into FEAT-2551 (asset layer — oracle + config
schema, expected HIGH) and FEAT-2552 (FSM wiring — `rn-remediate`
state insertion + `rn-implement` token routing, expected MODERATE)
along the natural data-flow seam. Each lands as its own PR; this
umbrella stays `status: open` until both children are done. No spec
content lost — every anchor, decision, and acceptance criterion
moved to its owning child. See FEAT-2551 § "Pattern Sources" and
FEAT-2552 § "Pattern Sources" for the read-only anchor references
extracted from this umbrella.

## Session Log
- `/ll:split-issue` - 2026-07-08T23:10:00 - `a081f85a-6f32-4531-b0ca-f9df5eae6f9f.jsonl`
- `/ll:wire-issue` - 2026-07-08T22:30:01 - `46f3165f-475b-46d1-9f6a-42a681f82923.jsonl`
- `/ll:decide-issue` - 2026-07-08T22:18:53 - `9ce3375d-2192-453a-b3da-0c8939b8625f.jsonl`
- `/ll:refine-issue` - 2026-07-08T21:56:45 - `9a5c737e-9bcb-4dc7-8899-d03fef2d8a23.jsonl`
- `/ll:confidence-check` - 2026-07-08T17:38:00 - `46f3165f-475b-46d1-9f6a-42a681f82923.jsonl`
- `/ll:confidence-check` - 2026-07-08T22:55:00 - `a081f85a-6f32-4531-b0ca-f9df5eae6f9f.jsonl`
