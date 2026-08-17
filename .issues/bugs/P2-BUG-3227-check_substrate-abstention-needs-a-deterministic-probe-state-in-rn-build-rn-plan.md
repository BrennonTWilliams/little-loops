---
id: BUG-3227
type: BUG
title: check_substrate abstention needs a deterministic probe state in rn-build/rn-plan
priority: P2
testable: true
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
parent: EPIC-3217
supersedes:
- BUG-3219
confidence_score: 100
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 19
score_ambiguity: 24
score_change_surface: 22
---

# BUG-3227: check_substrate abstention needs a deterministic probe state in rn-build/rn-plan

## Summary

`rn-build.yaml`/`rn-plan.yaml`'s `check_substrate` gates are two of the thirteen judged
gates named in BUG-3219 that declare neither `on_cannot_judge` nor `on_error`, so an
abstaining judge holds twice and then terminates the run via "No valid transition". Unlike
the other eleven gates (BUG-3226), this pair can't be fixed by routing to an
already-existing target, and no probe state exists anywhere in the repo today. This issue
is the one sub-task BUG-3219 itself flags as needing more design than a route addition, and
lands independently of BUG-3226.

### Correction to this issue's original premise

Earlier revisions of this issue (and of BUG-3219) described `check_substrate` as asking
"does the substrate exist", a question they reasoned was directly probe-able. **That is not
what the gate asks.** Both states are ENH-2098 *feasibility* gates with an identical prompt
(`rn-build.yaml:387-396`, `rn-plan.yaml:158-168`, canonical copy at
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:449-464`):

> Enumerate the target execution environment's known constraints: shell command
> availability, MCP tool access, file write permissions, token budget. Validate each
> proposed action in the plan against these constraints. Answer YES if every action is
> feasible in the target environment.

This reframes the root cause and the fix. The judge is asked to enumerate *environment*
facts, but its `source:` is only the design/plan document
(`${captured.design_artifacts.output}` / `${captured.plan_for_substrate.output}`) — the
environment facts are simply not in the evidence it was handed. `cannot_judge` is therefore
the *correct* verdict here, not an anomaly, and an honest judge should return it often.

Consequences:

- The probe cannot **replace** the judge, because "does each proposed action fit these
  constraints" is a semantic reading of a design document. It can only **supply the missing
  evidence**.
- So the abstention route is a genuine "capture evidence, then judge again" chain — the
  shape this issue previously noted does not exist in the repo. It is being introduced here.
- The anti-cycle argument in the earlier resolution (that a re-judge sees identical input
  and abstains again) **does not apply**, because the probe strictly increases the evidence.
  The cycle is instead prevented structurally: the re-judge is a *separate one-shot state*,
  not a re-entry into `check_substrate`.

## Parent Issue

Supersedes BUG-3219 (decomposed): Judged gates with neither on_cannot_judge nor on_error
terminate the run on abstention. BUG-3226 is the sibling successor covering the other
eleven gates.

Relationship to BUG-3228 (`_uncertain` suffix fallback): independent, per EPIC-3217
Sequencing. This issue declares `on_cannot_judge` only; `cannot_judge_uncertain` inherits
the same route once BUG-3228 lands.

## Current Behavior

| loop | state |
|---|---|
| `rn-build.yaml` | `check_substrate` (382-396) |
| `rn-plan.yaml` | `check_substrate` (152-168) |

Both are `evaluate.type: llm_structured`, judging `${captured.design_artifacts.output}`/
`${captured.plan_for_substrate.output}` (a plan/design doc), with `on_yes`/`on_no`(`/on_partial`)
but no `on_cannot_judge` and no `on_error`. A run reaching either and abstaining holds
twice (re-running the state's action each hold via `_route_abstention_hold()`,
`scripts/little_loops/fsm/executor.py:2683-2697`) then dies after three attempts with
"No valid transition".

## Steps to Reproduce

1. Run `rn-build.yaml` (or `rn-plan.yaml`) far enough to reach `check_substrate` — in
   `rn-build.yaml` via `commit_design` (364-377), which routes there unconditionally; in
   `rn-plan.yaml` via `generate_rubric` (77-147).
2. Have the judge abstain on the captured plan/design doc — i.e. the document does not
   contain enough to decide whether the substrate exists, which is exactly the case that
   motivates a deterministic probe.
3. Observe `check_substrate` re-enter itself twice (re-running its `echo`/`cat` action and
   re-judging each hold), then the run terminate with `error="No valid transition"`.

## Impact

Two gates in the two `rn-*` planning loops kill their run on abstention, and unlike the
BUG-3226 gates the correct destination is not a route that already exists — "does the
substrate exist" is a deterministic question the judge should never have been asked. Left
unfixed, the run dies with a generic transition error at the exact point where a one-line
shell test would have answered definitively.

## Expected Behavior

Abstention on `check_substrate` should run a deterministic probe rather than guess
`design_artifacts`. Deterministic existence/capability probes in this codebase are plain
`action_type: shell` states using `command -v`/file-existence tests, evaluated with `type:
exit_code` or `type: output_contains` — never `llm_structured` (evidence:
`cua-agent-desktop.yaml:101-118` `check_install`, `cua-agent-desktop.yaml:125-152`
`check_permissions`, `rn-build.yaml:108-128` `check_structure`, `rn-build.yaml:155-171`
`verify_structure`). `check_substrate` itself is the target of this fix, not an existing
example of the pattern — no "capture evidence and re-run the judge" state exists yet
anywhere in the repo; the nearest structural precedents are `rn-build.yaml:308-336`'s
`check_research_written` (probes whether an upstream prompt's expected artifact exists,
writes a placeholder stub if not) and `rn-build.yaml:1231-1250`'s `finalize_build_failed`
(reads run-dir state before declaring failure).

Where the probe determines the substrate genuinely doesn't exist, route to a
failure-shaped terminal (`terminal: true`, `failure: true`) rather than leaving the gate to
die on "No valid transition".

### RESOLVED: probe gathers environment evidence, then a separate one-shot state re-judges

The chain is `check_substrate` --(`cannot_judge`)--> `probe_substrate` -->
`check_substrate_probed`, where:

- `probe_substrate` is deterministic (`action_type: shell`, `evaluate.type:
  output_contains`), gathers the four constraint classes the judge's prompt names, and
  captures them to `substrate_env`. It always `exit 0`s — it is evidence-gathering, not a
  pass/fail gate — following `check_research_written`'s (`rn-build.yaml:308-336`) precedent.
- `check_substrate_probed` re-asks the *same feasibility question* with both the design/plan
  doc and the probe output in evidence, and carries the loop's original `on_yes`/`on_no`
  targets.
- It is **one-shot**: `check_substrate_probed` declares `on_cannot_judge: substrate_unknown`.
  A judge that still cannot decide with strictly more evidence than it had the first time is
  not going to decide on a third pass, so it fails closed. No counter or hold budget is
  needed, and there is no path back into `check_substrate` — the cycle is impossible by
  construction rather than by bound.

This supersedes the earlier "bypass the judge entirely" resolution, which rested on the
mistaken premise corrected in Summary.

### Drafted probe states

Both loops take the same probe; only the interpolation refs, the judged `source:`, and the
forward targets differ. **Verified**: with these states inserted, `ll-loop validate` reports
both loops valid with no new warnings, all four states resolve as reachable, and
`StateConfig.from_dict()` parses `cannot_judge` into `extra_routes` (so
`_abstention_declared()` returns `True` and the abstention routes without a hold). The probe
script was also run standalone against both a writable and an unwritable directory.

Note the bash in `action:` deliberately uses `$VAR` and never `${VAR}` — the FSM
interpolates `${...}` before bash sees it, so brace form would need `$${...}` escaping (the
same reason `check_structure` writes `"$${SPEC_LIST[@]}"` at `rn-build.yaml:116`).

**`rn-build.yaml`** — add `on_cannot_judge` to `check_substrate`, then the three new states:

```yaml
  check_substrate:
    # ... existing action/evaluate unchanged ...
    on_yes: scope_project
    on_no: design_artifacts
    on_partial: design_artifacts
    on_cannot_judge: probe_substrate  # BUG-3227: gather env facts, then re-judge once

  # BUG-3227: check_substrate's judge is asked to enumerate execution-environment
  # constraints, but its only `source:` is the design doc — the environment facts are
  # not in the evidence. `cannot_judge` is the correct verdict there, so the abstention
  # route gathers the missing facts deterministically and re-judges ONCE, rather than
  # re-entering check_substrate (which would re-judge the same evidence and abstain again).
  probe_substrate:
    action_type: shell
    timeout: 60
    action: |
      RUN_DIR="${context.run_dir}"
      echo "=== SUBSTRATE PROBE ==="
      echo "--- shell command availability ---"
      for C in git python3 pip node npm gh jq rg curl ll-issues ll-loop claude codex; do
        if command -v "$C" >/dev/null 2>&1; then
          echo "CMD_AVAILABLE: $C"
        else
          echo "CMD_MISSING: $C"
        fi
      done
      echo "--- file write permissions ---"
      for D in "$RUN_DIR" "$PWD"; do
        [ -z "$D" ] && continue
        PROBE_FILE="$D/.substrate-probe.tmp"
        if mkdir -p "$D" 2>/dev/null && touch "$PROBE_FILE" 2>/dev/null; then
          echo "WRITABLE: $D"
          rm -f "$PROBE_FILE" 2>/dev/null
        else
          echo "NOT_WRITABLE: $D"
        fi
      done
      echo "--- network egress ---"
      if curl -sS -m 5 -o /dev/null https://api.anthropic.com 2>/dev/null; then
        echo "NETWORK_EGRESS: reachable"
      else
        echo "NETWORK_EGRESS: unreachable_or_blocked"
      fi
      echo "--- MCP tool access ---"
      MCP_FOUND=0
      for F in .mcp.json .claude/settings.json .claude/settings.local.json; do
        if [ -f "$F" ]; then
          NAMES=$(jq -r 'try (.mcpServers // {}) | keys[]' "$F" 2>/dev/null | tr '\n' ' ')
          if [ -n "$NAMES" ]; then
            echo "MCP_SERVERS: $F: $NAMES"
            MCP_FOUND=1
          fi
        fi
      done
      [ "$MCP_FOUND" -eq 0 ] && echo "MCP_SERVERS: none_configured"
      echo "--- token budget ---"
      echo "TOKEN_BUDGET: UNKNOWN (not observable from the shell; treat as non-blocking)"
      echo "SUBSTRATE_PROBE_COMPLETE"
      exit 0
    capture: substrate_env
    evaluate:
      type: output_contains
      pattern: "SUBSTRATE_PROBE_COMPLETE"
    on_yes: check_substrate_probed
    # A probe that could not run leaves the judge no better off than before, so it is
    # fail-closed rather than routed into a re-judge that would abstain again.
    on_no: substrate_unknown
    on_error: substrate_unknown

  check_substrate_probed:
    action: "echo 'Re-checking substrate constraints with probed environment facts'"
    action_type: shell
    evaluate:
      type: llm_structured
      source: "${captured.design_artifacts.output}"
      prompt: >
        The target execution environment's constraints were probed directly. Probe output:
        ${captured.substrate_env.output}

        Treat the probe output as authoritative for shell command availability, file write
        permissions, network egress, and MCP tool access. Lines marked UNKNOWN are not
        observable and must be treated as non-blocking.

        Validate each proposed action in the design artifacts against these constraints.
        Answer YES if every action is feasible in the target environment. Otherwise NO,
        quoting the verbatim design-artifact text of each infeasible action alongside the
        verbatim probe line stating the constraint it violates.
    on_yes: scope_project
    on_no: design_artifacts
    on_partial: design_artifacts
    # One-shot: the enriched judge has strictly more evidence than check_substrate did.
    # If it still cannot decide, the question is not answerable here — fail closed rather
    # than loop.
    on_cannot_judge: substrate_unknown
    on_error: substrate_unknown

  substrate_unknown:
    terminal: true
    failure: true
    description: >
      Design-artifact feasibility could not be established even after probing the
      execution environment directly (BUG-3227). Inspect the probe output in the run
      transcript to see which constraint class was indeterminate.
```

**`rn-plan.yaml`** — identical states with these substitutions:

| in `rn-build` | in `rn-plan` |
|---|---|
| `RUN_DIR="${context.run_dir}"` | `RUN_DIR="${captured.run_dir.output}"` |
| `source: "${captured.design_artifacts.output}"` | `source: "${captured.plan_for_substrate.output}"` |
| "each proposed action in the design artifacts" | "each proposed action in the plan" |
| "verbatim design-artifact text" | "verbatim plan text" |
| `on_yes: scope_project` | `on_yes: research_iteration` |
| `on_no`/`on_partial: design_artifacts` | `on_no`/`on_partial: generate_rubric` |
| "Design-artifact feasibility …" (description) | "Plan feasibility …" |

### Why these four constraint classes, and what the probe honestly cannot answer

The probe reports facts; the judge does the matching. That split is deliberate — enumerating
which commands exist is deterministic, but deciding whether a design's proposed actions fit
them is not.

| constraint (from the judge's prompt) | probe approach | determinacy |
|---|---|---|
| shell command availability | `command -v` over a fixed inventory | fully deterministic |
| file write permissions | `touch` probe in run dir and CWD, then clean up | fully deterministic |
| MCP tool access | `mcpServers` keys in `.mcp.json` / `.claude/settings*.json` | deterministic for *configured* servers; cannot confirm a server actually starts |
| token budget | reported `UNKNOWN` | **not** shell-observable |

`NETWORK_EGRESS` is added beyond the prompt's four because "air-gapped target" is one of the
documented reasons to enable `check_substrate` at all
(`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:438-443`).

Reporting `TOKEN_BUDGET: UNKNOWN` rather than guessing is the point: the re-judge prompt
instructs that UNKNOWN lines are non-blocking, so an unobservable class cannot silently
become a NO. If it were omitted entirely, the judge would be left to infer it and abstain
again — which is the original defect.

The command inventory is a fixed list, which means a design proposing a tool outside it gets
no `CMD_*` line. The re-judge prompt's "treat the probe output as authoritative" wording
covers the classes probed, not tool-by-tool completeness; if a run shows this mattering,
extending the inventory is a one-line change.

## Root Cause

Same executor mechanism as BUG-3219/BUG-3226 —
`FSMExecutor._abstention_fallback()` (`scripts/little_loops/fsm/executor.py:2669-2681`)
returns `None` when neither `route.error` nor `on_error` is set, and the main execution
loop's `next_state is None` branch (758-774) calls `self._finish("error", error="No valid
transition")`. `check_substrate` was authored before ENH-3185 introduced the `cannot_judge`
verdict and declares only `on_yes`/`on_no`.

## Proposed Solution

Add three states per loop, drafted and validated in full under Expected Behavior § Drafted
probe states:

1. `probe_substrate` — deterministic shell probe (`output_contains` sentinel) that gathers
   the execution-environment constraint facts the judge's prompt names but its `source:`
   never contained, captured to `substrate_env`.
2. `check_substrate_probed` — the same feasibility question re-asked with the probe output
   in evidence, carrying the loop's original `on_yes`/`on_no` targets, and one-shot via
   `on_cannot_judge: substrate_unknown`.
3. `substrate_unknown` — `terminal: true` / `failure: true`, fail-closed.

`check_substrate` gains only `on_cannot_judge: probe_substrate`; its existing routes are
untouched.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/rn-build.yaml` — `check_substrate` (382-396, `evaluate.type: llm_structured`, judging `${captured.design_artifacts.output}`) lacks `on_cannot_judge`/`on_error`. `design_artifacts` (340-360) captures the judged content; `commit_design` (364-377) routes unconditionally to `check_substrate`.
- `scripts/little_loops/loops/rn-plan.yaml` — `check_substrate` (152-168, judging `${captured.plan_for_substrate.output}`, itself captured by a `cat "${captured.run_dir.output}/plan.md"` shell action in the same state) lacks `on_cannot_judge`/`on_error`. `plan.md` is written by `generate_rubric` (77-147), which routes to `check_substrate`.

### Dependent Files (Callers/Importers)
- No Python callers beyond the FSM loader — `FSMExecutor._abstention_fallback()` (`scripts/little_loops/fsm/executor.py:2669-2681`) is the sole consumer of the routing gap and needs no code changes; the new probe state is expressed purely as loop YAML.

### Conventions in Force
- Deterministic existence/capability probes in this codebase are `action_type: shell` states whose `evaluate.type` is `output_contains` or `exit_code` — never `llm_structured` — evidence: `cua-agent-desktop.yaml:101-118` (`check_install`), `cua-agent-desktop.yaml:125-152` (`check_permissions`), `rn-build.yaml:108-128` (`check_structure`), `rn-build.yaml:155-171` (`verify_structure`). All four declare `on_yes`/`on_no`/`on_error` explicitly rather than leaving any unhandled.
- The probe's "not found" branch conventionally routes to a `terminal: true`/`failure: true` state with a short, condition-describing name (`not_installed`, `perm_denied`, `failed`, `build_failed`) — evidence: `cua-agent-desktop.yaml:120-123,154-159`, `harness-single-shot.yaml:174-177`, `rn-build.yaml:1252-1254`.
- The probe's "found, continue" branch routes forward into the normal pipeline, not back to a judge — evidence: `check_install` → `check_permissions`, `check_structure` on_yes → `tech_research`, `verify_structure` on_yes → `load_normalized`.
- `on_error` handling for these deterministic probes is not uniform: `check_install`/`check_permissions`/`verify_structure` route `on_error` to the same failure state as `on_no`; `check_structure` instead routes `on_error` forward to `tech_research`, treating a shell-mechanics error as non-fatal — a disagreement to resolve deliberately, not by copying either example blindly.
- `rn-build.yaml:308-336`'s `check_research_written` is the closest existing precedent for "probe an upstream artifact directly, self-heal (write a stub) if missing, then continue" — it always `exit 0`s and funnels `on_yes`/`on_no`/`on_error` all to the same next state (`design_artifacts`), rather than branching to a failure terminal on a missing artifact.
- No "judge abstains → deterministic probe → route based on probe result" chain exists anywhere in the repo today (grep-confirmed zero `on_cannot_judge` matches across all `loops/` files) — `check_substrate` is the first instance of this exact shape, not a case of copying an existing example.
- `rn-build.yaml:1225-1251`'s `finalize_build_failed` is the precedent for reading run-dir state tolerantly (`2>/dev/null || echo ""`) before declaring a failure terminal.

### Tests
- `scripts/tests/test_builtin_loops.py::TestCheckSubstrateOptionalState` (13635; line refs in this section are advisory and have already drifted once) already covers both loops' `check_substrate` states via string-slice assertions (locate state start/next-state boundary in `.read_text()`, assert route keys present in the slice) — e.g. `test_rn_build_check_substrate_has_full_routing` (13709-13720), `test_rn_plan_check_substrate_has_full_routing` (13670-13681), plus positional-ordering assertions (13722-13736, 13683-13697). A structurally analogous precedent for asserting a specific route *target* (not just key presence) after a gate was repointed to a new state exists at `test_rn_build_check_harness_name_no_longer_routes_to_synthesize` (13763-13776) and `test_rn_build_has_harness_missing_states`/`test_rn_build_harness_missing_has_full_routing` (13740-13761, added for ENH-2415's `harness_missing` state) — the closest model for asserting a newly-added probe state's own routing.
- `scripts/tests/test_rn_build.py`, `scripts/tests/test_rn_plan.py` — loop-specific test files; unclear whether either currently has assertions touching `check_substrate` beyond `test_builtin_loops.py`'s coverage — needs a dedicated check during implementation.
- `TestValidatorWarningBudget` (`test_builtin_loops.py:13779-13907`) — corpus-wide lint ratchet; a new probe state that is unreachable or mis-referenced trips its `"unreachable"` (`not reachable from initial state`, message source `fsm/validation/structural_rules.py:1052`) or `"loop-reference"` (`does not resolve to any file`, message source `fsm/validation/reachability.py:93`) categories. `ALLOWLIST` entries require a comment citing the owning issue; ENH-2748's in-YAML `capture_reachability_ok: true` flag is a documented alternative for at least the `capture-ordering` category, but no equivalent flag exists for `unreachable`/`loop-reference`.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — canonical `check_substrate` "State Shape" YAML block (449-464) needs updating to show the new `on_cannot_judge` → probe route.
- `docs/guides/LOOPS_REFERENCE.md` — `check_substrate` prose (286, 297, 714) needs updating for the new route.
- `skills/create-loop/loop-types.md` — Specialist Pipeline template `check_semantic` (1354-1394) and the commented `# OPTIONAL: check_substrate` block (1327-1346) need updating; cross-check `skills/create-loop/reference.md`'s routing-key field reference stays consistent.

## Program Design

### Signatures
- `FSMExecutor._abstention_declared(state: StateConfig, verdict: str) -> bool` — becomes `True` for `check_substrate` once `on_cannot_judge: <probe_state_name>` is declared, routing the abstention to the new probe state instead of holding; see `scripts/little_loops/fsm/executor.py:2656-2667`.
- `FSMExecutor._route_abstention_hold(state: StateConfig, state_name: str, ctx: InterpolationContext) -> str | None` — holds `check_substrate` up to `_ABSTENTION_HOLD_CAP` (2) times, re-running the state's action (the `echo`/`cat` in `rn-build.yaml`/`rn-plan.yaml`) and re-judging each hold, before falling through to `_abstention_fallback()`; see `scripts/little_loops/fsm/executor.py:2683-2697`.
- `FSMExecutor._abstention_fallback(state: StateConfig, ctx: InterpolationContext) -> str | None` — same fallback mechanism as BUG-3226; returns `None` today for both `check_substrate` states since neither declares `route.error` nor `on_error`; see `scripts/little_loops/fsm/executor.py:2669-2681`.

### Types
N/A — no new data shape. The new probe state is a standard `StateConfig` YAML dict (`action_type: shell`, `evaluate.type: exit_code`/`output_contains`); no schema change is required.

### Call Path
`FSMExecutor._abstention_declared` -> `FSMExecutor._route_abstention_hold` -> `FSMExecutor._abstention_fallback` -> `FSMExecutor._finish`.

Today, for both loops: `check_substrate` (`evaluate.type: llm_structured`) abstains → `FSMExecutor._abstention_declared` returns `False` (no route declared) → `FSMExecutor._route_abstention_hold` holds 2× → `FSMExecutor._abstention_fallback` returns `None` → main loop `next_state is None` (`scripts/little_loops/fsm/executor.py:758-774`) → `FSMExecutor._finish("error", "No valid transition")`. Target call path after the fix: `check_substrate` abstains → `on_cannot_judge: probe_substrate` → `probe_substrate` gathers execution-environment facts deterministically (`action_type: shell` + `output_contains` sentinel) and captures them to `substrate_env` → `check_substrate_probed` re-asks the feasibility question with both the design/plan doc and the probe output in evidence → its `on_yes` proceeds to the loop's normal forward target (`scope_project` / `research_iteration`), `on_no`/`on_partial` back to the revise state (`design_artifacts` / `generate_rubric`), and `on_cannot_judge`/`on_error` to the new `substrate_unknown` failure terminal. `FSMExecutor._abstention_fallback` is never reached in either loop.

### Decision Rules
- New gap kind introduced by this issue: an `on_cannot_judge` route from an `llm_structured` gate into a freshly-added *evidence-gathering* chain, rather than to an existing target (contrast with BUG-3226's gates, which route to something that already exists).
- Division of labor: the probe reports deterministic environment facts; the re-judge does the semantic matching of proposed actions against those facts. The probe never decides feasibility, because "does this design's actions fit these constraints" is a reading of a document, not a shell test.
- Exact inputs: the four constraint classes named in the judge's own prompt (shell command availability, MCP tool access, file write permissions, token budget), plus network egress. See Expected Behavior for which are deterministic and which are reported `UNKNOWN`.
- Threshold/exit condition: the probe always `exit 0`s and surfaces via `evaluate.type: output_contains` on the `SUBSTRATE_PROBE_COMPLETE` sentinel — it is evidence-gathering, not a pass/fail gate. A missing sentinel means the probe itself failed to run.
- Unobservable classes are reported `UNKNOWN` and the re-judge prompt declares them non-blocking, so an unprobe-able constraint cannot silently become a NO.
- Escape hatch / dismissal: `check_substrate_probed` is one-shot — `on_cannot_judge: substrate_unknown` (`terminal: true` / `failure: true`). A judge that cannot decide with strictly more evidence will not decide on a third pass. There is no route back into `check_substrate`, so the cycle is impossible by construction rather than bounded by a counter.
- `on_error` on the probe routes to the failure terminal rather than forward (the `check_install`/`check_permissions`/`verify_structure` convention, not `check_structure`'s forward-on-error): a probe that could not run leaves the judge exactly as evidence-starved as before, so proceeding would just abstain again.

## Implementation Steps

1. Add `on_cannot_judge: probe_substrate` to `check_substrate` in both loops, and add the
   `probe_substrate` / `check_substrate_probed` / `substrate_unknown` states exactly as
   drafted in Expected Behavior § Drafted probe states (with the `rn-plan.yaml`
   substitutions from the table there). Existing `check_substrate` routes are untouched.
2. Confirm the invariants the draft was validated against: `ll-loop validate` clean on both
   loops with no new warnings; all three new states reachable; `substrate_unknown` carries
   both `terminal: true` and `failure: true`; the bash uses `$VAR` and never `${VAR}`.
3. Update `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s canonical `check_substrate` "State
   Shape" YAML block (lines 449-464) and `docs/guides/LOOPS_REFERENCE.md`'s
   `check_substrate` prose (lines 286, 297, 714 — "infeasible plans route back to...") to
   describe the new `on_cannot_judge` → probe route.
4. Update `skills/create-loop/loop-types.md`'s Specialist Pipeline template `check_semantic`
   (lines 1354-1394) and the commented `# OPTIONAL: check_substrate` block (lines
   1327-1346) to show the new route, and cross-check
   `skills/create-loop/reference.md`'s routing-key field reference is consistent.
5. Add/extend test coverage: `TestCheckSubstrateOptionalState`
   (`scripts/tests/test_builtin_loops.py:13635`) already covers both loops' `check_substrate`
   states — extend it for the new route; check whether `scripts/tests/test_rn_build.py`
   and `scripts/tests/test_rn_plan.py` need a dedicated assertion for the new probe state
   too.
6. `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_rn_build.py
   scripts/tests/test_rn_plan.py scripts/tests/test_fsm_executor.py -v` passes, and
   `ll-loop validate` runs clean against `rn-build.yaml`/`rn-plan.yaml`, including against
   `TestValidatorWarningBudget`'s corpus-wide lint ratchet
   (`test_builtin_loops.py:13779-13907`) — an unreachable or mis-referenced new probe state
   trips `"unreachable"`/`"loop-reference"` and needs either a fix or a new owned-by-issue
   `ALLOWLIST` entry.

## Sequencing Notes

- Independent of BUG-3228; see Parent Issue.
- **Do not run in parallel with BUG-3226.** Both edit `skills/create-loop/loop-types.md`
  (this issue: the Specialist Pipeline `check_semantic` template and the
  `# OPTIONAL: check_substrate` block; BUG-3226: the Variant A/B and `harness-refine-issue`
  scaffolds) and `skills/create-loop/reference.md`'s routing-key field reference. Under
  `parallel.epic_branches` these land as conflicting edits to the same two files.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` — `_abstention_fallback()` semantics
- `.claude/CLAUDE.md` `## Loop Authoring` — meta-loop shape rules referenced by `ll-loop
  validate`
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — canonical
  `check_substrate` documentation that needs updating alongside the fix

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-17T03:38:40 - `d25ab1c5-ed42-4023-87f3-5b04e53ad7b9.jsonl`
- `/ll:refine-issue` - 2026-08-17T01:20:21 - `f9d03c8c-c328-4dfd-93cf-1b2bf5193b15.jsonl`
- `/ll:issue-size-review` - 2026-08-17T01:13:51 - `aac72723-ff3b-4a56-8e20-e1cf00b2242c.jsonl`
