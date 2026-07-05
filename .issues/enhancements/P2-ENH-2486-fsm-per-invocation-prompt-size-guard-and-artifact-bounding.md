---
id: ENH-2486
title: "FSM engine \u2014 per-invocation prompt-size guard + bound re-embedded growing\
  \ artifacts"
type: ENH
priority: P2
status: open
captured_at: '2026-07-05T22:27:50Z'
discovered_date: 2026-07-05
discovered_by: capture-issue
labels:
- fsm
- loops
- token-cost
- observability
- general-task
relates_to:
- EPIC-2456
- ENH-2293
confidence_score: 100
outcome_confidence: 72
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 15
decision_needed: false
---

# ENH-2486: FSM engine — per-invocation prompt-size guard + bound re-embedded growing artifacts

## Summary

An FSM `general-task` run (observed in another project on this machine) emitted a
worker warning that its context had "ballooned to 11M+ cached tokens per iteration"
and suggested it was "replaying full prior history each iteration." Tracing our
engine shows we do **not** replay a transcript across states — every FSM state is a
fresh host session (`fsm/runners.py:149` calls `run_claude_command(...)` with no
`resume_session=True`, so `--continue`/`--resume` is never appended; `host_runner.py:859,1017`).
No built-in loop uses the opt-in history-accumulation path either
(`append_to_messages` / `${messages}` interpolation — zero matches under
`scripts/little_loops/loops/`).

So the ballooning is **not** cross-iteration transcript replay and **not** a systemic
engine bug. It comes from two design-level sources our engine does not currently
guard against:

1. **Within a single long-running agentic state.** A `prompt` state (e.g.
   `general-task` `do_work`, 900s timeout) runs many internal tool-call turns; that
   one session's transcript grows and is prompt-cached each turn. "11M **cached**
   tokens/iteration" is the signature of one long agent session, not FSM replay.
   (ENH-2293 addressed the OOM/SIGKILL *failure mode* of this; it did not add a
   preventive size signal.)
2. **Monotonically growing captured outputs / artifacts re-embedded per iteration.**
   `general-task` `check_done` (`general-task.yaml:286-336`) embeds
   `${captured.work_result.output}` + `${captured.selected_step.output}` **and** reads
   `dod.md`/`plan.md`. Those files grow every iteration — `## Sample Verification`
   sections accumulate and `continue_work` appends remediation steps — so each fresh
   invocation carries a larger prompt over a long run.

## Motivation

Cache reads are cheap per token (~10% of input price) but 11M/iteration is still real
recurring cost and a silent one — nothing surfaces it until the bill or an OOM
(exit -9) does. A generalizable, engine-level size signal turns an invisible failure
into an observable, actionable one for **every** loop (ours and user-authored), which
is exactly the leverage point EPIC-2456 targets (`fsm/runners` prompt-assembly path).

## Scope / Proposed Change

Two independent, separately-shippable parts:

### Part A — Engine: per-invocation prompt-size guard (generalizable)
- In the FSM action-assembly path (`fsm/runners.py` / `fsm/executor.py`), measure the
  size of each fully-interpolated `prompt`/`slash_command` action before dispatch.
- Emit a WARN when the interpolated prompt exceeds a configurable threshold (chars or
  a token estimate). Threshold sourced from config with a sane default; disable-able.
- Surface it in run output and (if cheap) in run metadata so `ll-loop`/diagnostics can
  flag ballooning states after the fact.
- Optional follow-on (do NOT block Part A on it): a hard cap that routes to
  `on_error`/diagnose instead of dispatching an oversized prompt.

### Part B — general-task: bound the growing re-embedded artifacts
- `check_done` already *replaces* its own `## Sample Verification` section; ensure the
  DoD/plan content it re-embeds does not grow without bound over long runs (e.g. cap
  or summarize accumulated verification prose before re-embedding, and/or stop
  re-embedding full `${captured.*.output}` when a file reference suffices).
- Keep the file-based state-passing architecture; the fix is bounding *what gets
  re-embedded per iteration*, not changing the mechanism.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Part A — files to modify

- `scripts/little_loops/fsm/executor.py` — **primary insertion point.**
  `FSMExecutor._run_action()` (starts `executor.py:1308`) is the *single* choke
  point: the fully-interpolated string is the local `action = interpolate(action_template, ctx)`
  at `executor.py:1326`, shared by every downstream branch (prompt, slash_command,
  shell, contributed, mcp_tool) — those branch *after* this line
  (`executor.py:1348/1356`). Measure `len(action)` here, before the dispatch
  block. Loop/state identity already in scope: `self.fsm.name` and
  `self.current_state`. Emit via `self._emit(PROMPT_SIZE_WARN_EVENT, {...})`
  mirroring the existing `THROTTLE_WARN_EVENT` (module const `executor.py:97`;
  emission `executor.py:1018-1028`) — **not** `logging.getLogger().warning()`,
  which the runtime path reserves for corrupt-file/static-validation warnings.
- `scripts/little_loops/fsm/schema.py` — add a per-loop config object on `FSMLoop`
  (follow `HostGuardConfig`: field `schema.py:1020`, `to_dict` skip-if-default
  `schema.py:1101-1103`, `from_dict` `schema.py:1150-1152`). A `PromptSizeGuardConfig`
  dataclass (analogous to `ThrottleConfig` at `schema.py:282`, or
  `fsm/host_guard.py:HostGuardConfig`) is the established shape — prefer this over
  a bare module constant so it is per-loop overridable and disable-able.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON-schema entry for the new
  block (model on the `host_guard` object at `fsm-loop-schema.json:274-282`:
  `enabled` boolean default `true`, `0 = disabled` convention at `:317-319`).
- `config-schema.json` — top-level doc mirror if a project-level default is wanted
  (model on `history.compaction` at `config-schema.json:1732-1768`, which pairs
  with `CompactionConfig` in `config/features.py:866-898` — the EPIC-2456 budget
  to cross-check against per Implementation Step 5).

### Part A — reusable helper (resolves the "threshold unit" Open Question)

- `scripts/little_loops/session_store.py:1915-1917` — `_estimate_tokens(text) -> int`
  = `len(text) // 4` (the "LCM convention", 4 chars/token), unit-tested at
  `scripts/tests/test_session_store.py:2450-2472`. The same `len(...) // 4`
  heuristic recurs at `doc_counts.py:324-353`. **No BPE/tokenizer exists anywhere
  in the codebase** — raw-char (or this `//4` derivative) *is* the established
  convention, so the guard should measure `len(action)` (chars) or reuse
  `_estimate_tokens`; a real tokenizer would be a new dependency.

### Part A — metadata surfacing (no extra plumbing needed)

- `scripts/little_loops/fsm/persistence.py:669-675` — `PersistentExecutor._handle_event`
  → `StatePersistence.append_event` writes *every* emitted event to
  `<run>.events.jsonl` automatically, so a new `self._emit(...)` surfaces in run
  output for free. An optional dedicated side-file under `run_dir` would follow
  the `usage.jsonl` branch at `persistence.py:679-697`.

### Part A — additional wiring (Files to Modify)

_Wiring pass added by `/ll:wire-issue` — every existing per-loop guard config
(`host_guard`, `throttle`) touches these same parity points; `PromptSizeGuardConfig`
must mirror them or the new config silently fails to validate, serialize, export,
or propagate:_

- `scripts/little_loops/fsm/__init__.py` — **public export decision [hard].**
  `ThrottleConfig` (`:147`, `__all__` `:220`) and `THROTTLE_WARN_EVENT` (`:104`,
  `__all__` `:219`) are re-exported from the package root; `HostGuardConfig` is
  **not** (imported directly from `fsm.host_guard`). Decide which pattern the new
  `PromptSizeGuardConfig` + `PROMPT_SIZE_WARN_EVENT` follow, and if exported, add
  both the import and `__all__` entries here (+ the module-docstring "Public
  exports" list `:7-50`) [Agent 1/2 finding].
- `scripts/little_loops/fsm/validation.py` — **validation parity [hard].**
  `_validate_host_guard(fsm, defined_states)` (`:2051`) is dispatched from
  `validate_fsm` at `:1157` (`errors.extend(_validate_host_guard(...))`); the inline
  `throttle` validation block sits at `:875-907`. `ll-loop validate` surfaces these
  `ValidationError`s. A new `_validate_prompt_size_guard()` (or inline block) must be
  wired into the same dispatch or an invalid guard config passes silently [Agent 2
  finding].
- `scripts/little_loops/cli/loop/__init__.py` — **argparse flag parity.** The
  `--no-host-guard` / `--host-guard-budget-mb` flags are defined at `:151-165`
  **and duplicated** in the second `run_parser` block at `:460-462` (both must
  change). Per CLAUDE.md's "check existing flags first" rule, evaluate whether a
  generalized numeric-override flag can be reused before adding a new
  `--no-prompt-size-guard` / `--prompt-size-threshold` pair [Agent 2 finding].
- `scripts/little_loops/cli/loop/run.py:131-134` — **CLI-override parity.** Mutates
  `fsm.host_guard.enabled` / `fsm.host_guard.max_cumulative_subproc_mb` from args
  *after* `FSMLoop.from_dict()`. A new guard's disable/threshold flags need the same
  post-load mutation here [Agent 2 finding].
- `scripts/little_loops/cli/loop/lifecycle.py:513-514` — same CLI-override parity
  for the resume/status path (`fsm.host_guard.enabled = False`) [Agent 2 finding].
- `scripts/little_loops/cli/loop/_helpers.py:~1311-1363` — **[advisory]** worker
  subprocess flag re-serialization (`cmd.extend([...])`). NOTE: `host_guard` flags
  are **not** currently propagated here, so this is only load-bearing *if* the new
  guard's CLI flags must survive `ll-parallel`/worker spawns; matching `host_guard`'s
  existing (non-propagating) behavior is acceptable [Agent 2 finding].
- `scripts/little_loops/generate_schemas.py:251-286` — **generated-schema source
  [hard for the doc AC].** The hand-authored `_schema("throttle_warn", …)` entries
  (`:251`, `:264`, `:279`) are the maintainer-tool source for
  `docs/reference/schemas/*.json`. Add a `prompt_size_warn` `_schema(...)` entry whose
  `required` key list matches the actual `_emit(PROMPT_SIZE_WARN_EVENT, {...})`
  payload, then regenerate via `ll-generate-schemas` (produces
  `docs/reference/schemas/prompt_size_warn.json`) [Agent 2 finding].

### Part B — general-task artifact bounding

- `scripts/little_loops/loops/general-task.yaml` — `check_done` (`:286-336`,
  embeds `${captured.work_result.output}` + `${captured.selected_step.output}`,
  reads `dod.md`/`plan.md`) and `continue_work` (`:535+`, appends remediation).
  Bound *what is re-embedded per iteration*; keep the file-based state mechanism.

### Documentation

_Wiring pass added by `/ll:wire-issue` — both `throttle` and `host_guard` are
documented in each of these; a new loop-level guard + its WARN event needs a
parallel entry in all of them:_

- `docs/reference/API.md` — add a `PromptSizeGuardConfig` subsection (model on
  `ThrottleConfig` `:4547-4567` or the `little_loops.fsm.host_guard` §
  `:5354-5381`), a module-index row (`:4335` style), and a `PROMPT_SIZE_WARN_EVENT`
  row in the event-constant table (mirrors `THROTTLE_WARN_EVENT` `:4565`) [Agent 2
  finding].
- `docs/reference/EVENT-SCHEMA.md` — three couplings, all mirroring `throttle_warn`:
  the prose section `:417-432` (fields table + JSON example), the generated-schema
  file-tree listing `:970` (insert `prompt_size_warn.json` alphabetically), and the
  FSM event-registry table row `:1060` (`| prompt_size_warn | FSM | fsm/executor.py |`)
  [Agent 2 finding].
- `docs/reference/CONFIGURATION.md:842-852` — add a `prompt_size_guard` block section
  parallel to the `throttle` per-state block (fields table + EVENT-SCHEMA link)
  [Agent 2 finding].
- `docs/guides/LOOPS_GUIDE.md` — add a guard section following the `### Host Guard
  (host_guard)` pattern (`:149-162`) and the throttle example (`:663-677`), plus a
  `prompt_size_guard` row in the loop-config summary table (`:125`) [Agent 2 finding].
- `docs/reference/schemas/prompt_size_warn.json` — **generated file**, do not
  hand-edit; produced by `ll-generate-schemas` after the `generate_schemas.py` entry
  is added [Agent 2 finding].

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — **WILL BREAK [hard].** 143 exact-substring
  assertions on `check_done`/`continue_work` `action`/`evaluate.prompt` text
  (`dod.md`, `plan.md`, `## Sample Verification`, `captured.work_result.exit_code`,
  `-9`/`OOM`/`SIGKILL`, `diagnose`, …). Any Part-B edit that truncates or summarizes
  those states must preserve the asserted substrings or update these assertions in
  lockstep [Agent 3 finding].
- `scripts/tests/test_fsm_schema.py` — add a `TestPromptSizeGuardConfig` class
  modeled on `TestThrottleConfig` (`:2694-2786`) / `TestHostGuardConfig` pattern
  (`from_dict` all/partial/empty, `to_dict` skip-if-default-or-None, round-trip, +
  `FSMLoop`-scoped round-trip asserting `data["prompt_size_guard"] == {...}` and
  default-omits-key). FSMLoop round-trip asserts are scoped to the new key, so
  existing `TestFSMLoop`/`TestThrottleConfig` tests won't break [Agent 3 finding].
- `scripts/tests/test_config_schema.py` — if a project-level `config-schema.json`
  mirror is added, add a structural test modeled on the `history.compaction`
  precedent (`test_*_in_schema` style, `:15+`; asserts `additionalProperties`, per-field
  `type`/`default`) — no `jsonschema` dependency, structural-key assertions only
  [Agent 2/3 finding].
- `scripts/tests/test_fsm_validation.py` — add validation-error coverage for the new
  `_validate_prompt_size_guard()` (parity with existing host_guard/throttle validation
  tests) [Agent 2 finding].
- `scripts/tests/test_fsm_schema_fuzz.py` — extend fuzz-robustness coverage to the new
  config dataclass (parity with `ThrottleConfig`/`HostGuardConfig`) [Agent 2 finding].
- `scripts/tests/test_fsm_executor.py` — model the WARN-emission test on
  `test_warn_event_emitted_at_warn_max` (`:7238-7256`): use
  `patch.multiple("little_loops.fsm.executor", _DEFAULT_..._MAX=...)` to force
  threshold crossing, assert the `prompt_size_warn` event fires once with the
  `{state, size, threshold}`-shaped payload [Agent 3 finding].

- `scripts/tests/test_host_guard.py` — model the above/below-threshold pytest here:
  `collect_events(executor)` helper (`:92-96`) + `class TestExecutorRssBudget`
  (`:509-573`). `test_budget_route` = "above threshold → fires with right payload";
  `test_budget_disabled_no_rss_events` = "disabled/below → silent". Uses a fake
  `action_runner` + `make_budget_fsm` fixture (no real subprocess). This
  event-collector shape fits an `_emit`-based WARN better than `caplog`
  (caplog example: `test_events.py:157-169`).
- `scripts/tests/test_builtin_loops.py` — `class TestGeneralTaskLoop` (`:8360`)
  loads the YAML via a `data` fixture; append an artifact-bounding assertion in
  the substring-on-`action` style of `test_continue_work_prompt_preserves_...`
  (`:8483-8491`) — e.g. assert a cap/replace marker present or an unbounded-append
  instruction absent in `check_done`'s `action`.
- Unit-level runner/interpolation coverage lives in
  `scripts/tests/test_fsm_executor.py` and `scripts/tests/test_fsm_interpolation.py`.

## Implementation Steps

1. Add a prompt-size measurement + WARN in the interpolated-action dispatch path.
   **Refined location (research):** insert at `fsm/executor.py:1326` inside
   `FSMExecutor._run_action`, right after `action = interpolate(...)` and before
   the dispatch branch — this is the single choke point covering *all* action
   types. (The issue's original pointer to `fsm/runners.py:149` is only the
   `slash_command` branch, downstream of the split, and would miss `shell`/prompt
   paths.)
2. Wire a config knob (threshold + enable flag) with a default; document it.
3. Add a pytest asserting the WARN fires above threshold and is silent below.
4. (Part B) Audit `general-task.yaml` `check_done`/`continue_work` for unbounded
   re-embedded artifacts; bound them; add/extend a `test_builtin_loops.py` assertion.
5. Cross-check against EPIC-2456's `history.compaction` budget so the two do not
   double-count or conflict.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation — each mirrors how the existing `host_guard`/`throttle` configs are
wired end-to-end:_

6. Wire `_validate_prompt_size_guard()` into `fsm/validation.py` and register it in
   the `validate_fsm` dispatch (`:1157`, next to `_validate_host_guard`) so
   `ll-loop validate` catches invalid guard config.
7. Decide the export path for `PromptSizeGuardConfig` + `PROMPT_SIZE_WARN_EVENT` in
   `fsm/__init__.py` (follow `ThrottleConfig`'s re-export or `HostGuardConfig`'s
   direct-import convention) and update `__all__` + the docstring exports list if
   exported.
8. If CLI override/disable is wanted, add parity argparse flags in
   `cli/loop/__init__.py` (both `run_parser` blocks, `:151-165` **and** `:460-462`)
   and the post-`from_dict` mutation in `cli/loop/run.py:131-134` +
   `cli/loop/lifecycle.py:513-514`. Match `host_guard`'s (non-)propagation behavior
   in `_helpers.py` worker re-serialization.
9. Add a `prompt_size_warn` entry to `generate_schemas.py:251-286` (payload keys
   matching the emitted event) and run `ll-generate-schemas` to regenerate
   `docs/reference/schemas/prompt_size_warn.json`.
10. Update docs in lockstep: `API.md`, `EVENT-SCHEMA.md` (3 spots), `CONFIGURATION.md`,
    `LOOPS_GUIDE.md` — each parallel to the existing `throttle`/`host_guard` entry.
11. Add/extend tests: `TestPromptSizeGuardConfig` in `test_fsm_schema.py`, WARN-emission
    test in `test_fsm_executor.py`, validation coverage in `test_fsm_validation.py`,
    fuzz coverage in `test_fsm_schema_fuzz.py`, config-schema structural test in
    `test_config_schema.py` (if project-level mirror added).
12. (Part B guard) After editing `general-task.yaml` `check_done`/`continue_work`,
    run `test_general_task_loop.py` + `test_builtin_loops.py::TestGeneralTaskLoop`
    and reconcile any broken substring assertions.

## Acceptance Criteria

- [ ] An interpolated action whose size exceeds the configured threshold emits a WARN
      identifying the loop + state; below threshold emits nothing [hard]
- [ ] The guard is config-gated with a default and can be disabled [hard]
- [ ] A pytest exercises both above- and below-threshold cases [hard]
- [ ] `general-task` long-run re-embedded artifacts are bounded (Sample Verification
      prose / captured outputs do not grow monotonically into the prompt) [hard]
- [ ] `python -m pytest scripts/tests/` exits 0 [hard]
- [ ] No new host `--continue`/`--resume` behavior introduced (fresh-session-per-state
      invariant preserved)

## Open Questions

- Threshold unit: raw chars (cheap, portable) vs. a token estimate (more accurate,
  needs a tokenizer). Lean chars for the guard, token estimate only if already
  available from usage callbacks. ✅ **RESOLVED** (2026-07-05 by `/ll:decide-issue`) —
  **chars** (or `len//4` via `_estimate_tokens`). Research found no tokenizer anywhere
  in the codebase; `len(text) // 4` is the established convention
  (`session_store.py:1915-1917`, `doc_counts.py:324`). No new dependency. See Codebase
  Research Findings below.
- Should Part A's optional hard-cap ship now or as a separate ENH? ✅ **RESOLVED**
  (2026-07-05 by `/ll:decide-issue`) — **separate ENH.** Part A ships the WARN-only
  guard; the hard-cap that routes to `on_error`/diagnose is a follow-on and must not
  block Part A.

### Codebase Research Findings

_Added by `/ll:refine-issue` — resolves the threshold-unit question:_

- **Threshold unit → chars (or `len//4`).** Research found no tokenizer anywhere in
  the codebase; the only token measurement is the `len(text) // 4` heuristic
  (`session_store.py:1915-1917` `_estimate_tokens`, reused in `doc_counts.py:324`).
  So "token estimate only if already available from usage callbacks" collapses to:
  measure `len(action)` chars, or reuse `_estimate_tokens` for a token-ish number —
  both are cheap and already-conventional. No new dependency required.
- **WARN mechanism is settled, not open:** emit via `self._emit(EVENT_CONST, {...})`
  (structured event), not `logging`. It auto-persists to `events.jsonl`
  (`persistence.py:669-675`), satisfying the "surface in run output + metadata" AC
  with zero extra plumbing.

## Notes

- Diagnostic trace this session: fresh-session-per-state confirmed at
  `fsm/runners.py:149`, `subprocess_utils.py:329-336`, `host_runner.py:859/1017`;
  no loop uses `append_to_messages`/`${messages}`.
- Distinct from ENH-2293 (done): that handled the OOM/SIGKILL *failure* of an oversized
  `do_work`; this adds *preventive detection* generalized to all loops + artifact
  bounding.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-05_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~20+ touched files (executor, schema, two JSON schemas,
  exports, validation, CLI flags in two blocks, worker re-serialization, generated
  schemas, five docs files, seven+ test files) — wide breadth even though each
  individual site follows an established, verified pattern.
- `test_general_task_loop.py` carries 143 exact-substring assertions on
  `check_done`/`continue_work` text that WILL break under any Part-B artifact-bounding
  edit; reconciling them in lockstep is real, non-optional work, not incidental cleanup.
- Open decision: whether `PromptSizeGuardConfig`/`PROMPT_SIZE_WARN_EVENT` follow
  `ThrottleConfig`'s re-export convention or `HostGuardConfig`'s direct-import
  convention in `fsm/__init__.py` — resolve before implementing the export/`__all__`
  changes so the parity touchpoints in Integration Map don't diverge mid-implementation.

## Session Log
- `/ll:decide-issue` - 2026-07-05T22:55:36 - `976b8aed-cb56-4d7d-82b3-5b22833d5918.jsonl`
- `/ll:confidence-check` - 2026-07-05T23:00:00 - `39618ae6-5700-4f66-8f16-0412c1c26178.jsonl`
- `/ll:wire-issue` - 2026-07-05T22:45:51 - `efa03064-1a5b-4099-8035-a96c38ff99fc.jsonl`
- `/ll:refine-issue` - 2026-07-05T22:34:17 - `42209f54-f54c-4f75-95c3-22dd47940c1c.jsonl`
- `/ll:capture-issue` - 2026-07-05T22:27:50Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ff7c133-226a-436a-ba23-7e5882937d67.jsonl`

---

## Status

**Current Status**: open
