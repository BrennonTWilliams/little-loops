---
id: FEAT-3589
type: FEAT
title: Add html-webapp-generator loop with a best-effort viewport gate
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T02:02:32Z'
learning_tests_required:
- playwright
- node
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-3589: Add html-webapp-generator loop with a best-effort viewport gate

## Summary

Add a standalone built-in FSM loop, `html-webapp-generator`, that aims for a single-viewport, webapp-style HTML artifact. A non-LLM Playwright viewport gate measures and retries layout failures; after its bounded retry cap the loop may accept an artifact with a clearly reported `VIEWPORT_UNFIT` result.

## Current Behavior

No built-in loop produces a single-viewport, app-shell HTML artifact:

- `html-website-generator` emits scrolling single-page websites (its rubric scores a full-page screenshot).
- `html-anything` classifies the artifact type but has no viewport-fit rubric and no type override (inputs are only `description` and `artifact_mode`), so an app-shell request can be routed to `html-dashboard`/`html-website` non-deterministically.

## Expected Behavior

`ll-loop run html-webapp-generator "<description>"` attempts to converge on a self-contained `index.html` app-shell (header / sidebar / main panes) that fills the viewport (`100dvh`) with no document-level scroll at every configured viewport (default 1440x900, 1024x768, 375x667). Overflow belongs in user-scrollable internal panes. The non-LLM `viewport_gate` appends failure measurements to `critique.md` and retries up to three times across the entire run. Every gate visit measures the **current** page, including after vision-driven regeneration. A measured fit reports `VIEWPORT_PASS`; remaining violations after the retry budget report `VIEWPORT_UNFIT` and advance to the optional vision gate. The latest measured result is saved independently of the LLM-written critique. Harness faults and exhausted smoke retries route to `failed`.

## Motivation

No existing loop forces single-viewport output:

- `html-website-generator` (`scripts/little_loops/loops/html-website-generator.yaml`) builds scrolling single-page websites. Its rubric explicitly scores a full-page screenshot.
- `html-anything` classifies the artifact type (`html-dashboard`, `html-website`, ...), but no rubric requires fitting one viewport. It exposes no type override either: its only inputs are `description` and `artifact_mode`. Adding an `html-webapp` type there would make routing non-deterministic, because the classifier could pick `html-dashboard` for the same description. A standalone loop gives deterministic behavior and has no coupling to `html-anything`.

## Proposed Solution

Use the thin-wrapper state contract demonstrated by `html-website-generator`, without copying its hardcoded thresholds or rubric contradictions:

```
plan → run_gen_eval (loop: oracles/generator-evaluator) → smoke_test → viewport_gate → vision_gate → done
```

1. **Generator prompt**: require a standards-mode document (`<!doctype html>`), a mobile viewport meta tag, and a viewport-sized app shell (`100dvh`). Keep long content reachable through internal scroll panes; require narrow-width collapse of navigation and columns. Supply the configured viewport list to both the planner and generator so custom sizes are actionable. Do not mandate `overflow: hidden` on `body`. Closed drawers must be visually closed and unavailable to focus: `[hidden]`/`display: none`, or an off-canvas treatment with `inert`. `aria-hidden="true"` alone is insufficient; it does not hide pixels or prevent keyboard focus.
2. **Rubrics (both)**: retain `design_quality`, `originality`, `craft`, and `functionality`, and add the named fifth score `layout_fit` to both the oracle rubric and vision JSON schema. Every score must meet `context.pass_threshold` (default 6); update the score format and all-five pass instructions together. The layout criterion considers visible primary regions, cut-off content, and sensible internal scrolling. Remove the copied instruction that off-screen detail cannot lower a score when it is evidence of a layout defect. Visual assessment remains best effort: a screenshot cannot reveal content hidden by CSS clipping, and the oracle's single screenshot does not show every configured viewport.
3. **`viewport_gate`**: a non-LLM shell state with a quoted Node heredoc (`node - <<'JS'`). Script bodies contain no FSM `${...}` interpolation; paths and settings arrive through environment variables. For each configured size, use a fresh page with its viewport set **before navigation**. Measure after page load, `document.fonts.ready`, and two animation frames, with bounded waits and browser cleanup on every path. This checks initial rendered layouts, not every interactive state or continuous animation. The deterministic geometry and visibility contract is specified under Program Design. `timeout: 120` bounds the entire gate action.
4. **Feedback and result**: append dimensions, overflow amounts, and identifying details for offending controls under `## Issues to Address` before any regeneration. `smoke_test` likewise appends its failure detail. Save the latest complete viewport measurements and measured disposition in `${context.run_dir}/viewport-report.json` on every successful measurement; do not rely on `critique.md` as the durable result because the oracle rewrites it. This report is associated with the measured `index.html` hash and records the cumulative retry count. Bound control details to the first 20 violations per viewport while retaining the total count.
5. **Routing and caps**: retryable artifact failures exit 0 without an acceptance token; harness faults exit non-zero. The viewport evaluator accepts anchored `VIEWPORT_PASS` **or** `VIEWPORT_UNFIT` lines, preserving their distinct meaning (see Decision Rules). The viewport retry count is global and saturates at 3; passes and vision-driven regeneration never reset it. Smoke failures have a separate global budget: two retries, then explicit exhaustion to `failed`. Docs say "best-effort viewport fit, up to 3 viewport refine rounds" and explain the report and optional vision gate.

### Explicitly out of scope: the shared oracle

Do **not** modify `scripts/little_loops/loops/oracles/generator-evaluator.yaml`. Its evaluate state uses `playwright screenshot --full-page` without an explicit viewport-size argument, and existing loops consume it. The new wrapper performs its own multi-viewport geometry checks. Full-page capture shows document overflow, but still honors CSS clipping and does not expose all internal pane content. This issue does not add multi-viewport vision scoring or guarantee detection of every clipped non-interactive element.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Routing mechanism: `evaluate_output_contains()` supports regex patterns and `error_patterns` (`scripts/little_loops/fsm/evaluators.py`). The viewport gate must accept both measured dispositions, rather than only `VIEWPORT_PASS`; otherwise cap acceptance retries forever. Retryable `FAIL:` output provides feedback but no acceptance token. Non-zero exits and exit 124 short-circuit to `error`; the explicit smoke-exhaustion token uses `error_patterns` with exit 0 to reach `failed` without relabeling a bad artifact as a harness fault.
- Interpolation constraints on the embedded node script: the whole `action:` string is FSM-interpolated before bash sees it (`scripts/little_loops/fsm/executor.py:2459`), so the JS must contain zero `${` sequences — use string concatenation and hand paths over via `export ABS_DIR` → `process.env.ABS_DIR`, exactly as smoke_test does: `await page.goto('file://' + process.env.ABS_DIR + '/index.html');` (`html-website-generator.yaml:158`). Bash parameter defaults must be written `$${VAR:-x}` — vision_gate: `if [ -z "$${VISION_BASE_URL:-}" ]` (`html-website-generator.yaml:202`). Avoid `$$(` and `$$VAR` over-escapes (MR-9; bash expands them to PID). Test-side enforcement: `scripts/tests/test_builtin_loops.py:327-390` fails any unescaped bash `${...}` in shell actions, including the `:-` default form.
- Round-cap precedent: vision_gate's `.vision_rounds` counter (`html-website-generator.yaml:213`) uses `ROUND_CAP = 3` (line 215) and at exhaustion ACCEPTS best-so-far — `print("VISION_PASS: round cap (%d) reached, accepting" % ROUND_CAP); sys.exit(0)` (lines 220-221) — routing to `done`, not `failed`. The counter increments only on fail rounds (`open(rc_file, "w").write(str(rc + 1))`, line 272). The issue's open question (fail vs accept at cap) has an established codebase answer: accept-at-cap.
- critique.md append idiom: vision_gate appends via embedded python3 heredoc, not bash — `with open(crit, "a") as f:` (`html-website-generator.yaml:278`) writing `## Issues to Address (external vision critique, round N)`-headed blocks with `%`-formatting (never `${}` in the Python either — the FSM interpolator ran before bash, quoting the heredoc does not protect it). `${context.run_dir}` is absolutized by a shell case-statement before the heredoc (lines 196-200) because the script's cwd differs from the run dir; a `viewport_gate` append must do the same and use a distinguishing heading (e.g. `## Issues to Address (viewport gate, round N)`) so the generator can attribute the feedback. Confirmed: `smoke_test` writes nothing on failure — its node script only logs to stdout.

## Program Design

### Types

- Loop context mirrors `html-website-generator` (`pass_threshold`, `design_tokens_context`, `design_guidance_context`) plus `viewports: str`: whitespace-separated `WxH` entries, default `"1440x900 1024x768 375x667"`. Accept only positive integer dimensions at most 8192. Warn and skip malformed entries; zero valid sizes is a harness fault. Bind shell values with `${context.viewports:shell}` and `${context.run_dir:shell}`; embedded scripts read `process.env` / `os.environ`, never interpolated source. `viewports` stays a parent context value, not an oracle `with:` key. Example: `--context 'viewports=800x600 375x667'`.
- Latest result shape: `viewport-report.json` has `schema_version: 1`, `artifact_sha256`, `status` (`VIEWPORT_PASS`, `VIEWPORT_RETRY`, or `VIEWPORT_UNFIT`), `refine_rounds`, `retry_cap: 3`, and a `viewports` array containing requested size, measured document/window dimensions, overflow amounts, total control-violation count, and bounded violation details. Each measurement replaces the previous report, including after vision regeneration; the final report must describe the final artifact. This status is independent of optional vision success/skips.
- Budget: at most **30 nonterminal parent executions**: `1 plan + 9 run_gen_eval + 9 smoke_test + 7 viewport_gate + 4 vision_gate`. Equivalently, initial 5 executions + `3×3` viewport retries + `3×4` vision retries + `2×2` smoke retries. The engine checks `max_steps` before terminal recognition, so 31 is the minimum and `max_steps: 32` leaves one-step margin. Keep loop `timeout: 7200`; child steps are separate, while child timeouts are clamped to the parent's remaining time. The time cap bounds the run and cannot promise every allowed retry completes.

### Signatures

- `cmd_validate(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` — existing `ll-loop validate` entry; validates the new YAML with no code change.
- `test_expected_loops_exist() -> None` — existing builtin-loop inventory test; extend its expected-name list with `html-webapp-generator`.
- New structure/behavior tests verify the state contract, both acceptance dispositions, smoke exhaustion, critique consumption, global counters, and the budget against the actual rendered actions and FSM evaluator.

### Call Path

`resolve_loop_path(loop_name, loops_dir)` (little_loops.fsm.loop_paths) -> `load_and_validate(path)` (little_loops.fsm.validation) -> `FSMExecutor._execute_state()` / `_execute_sub_loop()` -> shell action -> `evaluate_output_contains()` -> retry, optional vision gate, or explicit failure terminal. The generator reads gate feedback before the oracle's scoring prompt rewrites `critique.md`.

No Python source changes: the loop is package data picked up by `get_builtin_loops_dir()` automatically; the only touched Python files are tests.

### Decision Rules

- Document fit: at every valid viewport, compare the actual document scrolling element's `scrollHeight`/`scrollWidth` with `innerHeight`/`innerWidth`. Permit at most **1 CSS pixel** rounding tolerance, and report measured excess before tolerance. `VIEWPORT_PASS` requires every configured size to satisfy the geometry checks.
- Control fit: inspect rendered `button`, `a[href]`, `input` (excluding hidden inputs), `select`, `textarea`, `[role=button]`, `summary`, `[contenteditable="true"]`, and nonnegative `[tabindex]` controls. Check viewport bounds **and non-scrollable clipping ancestors**, per axis, with the same 1-pixel tolerance. A control clipped inside the window must fail even if its box fits the viewport. Exemption applies only to overflow reachable through `auto`/`scroll` on the affected axis; `hidden`/`clip` do not qualify. An inner scroll pane cannot excuse clipping by an outer non-scrollable ancestor or an off-screen pane. Long internal lists and horizontal boards remain allowed. This is a bounded control-geometry check, not a general occlusion or accessibility audit.
- Visibility: skip non-rendered controls (`display: none`, zero layout boxes, computed `visibility: hidden`/`collapse`) and inactive `inert` descendants. Do not skip a rendered focusable control solely because it or an ancestor has `aria-hidden="true"`. Honor the control's computed visibility, including a visible descendant of a visibility-hidden ancestor. The document-fit check remains unconditional; hiding/inactivating a subtree cannot erase root overflow from the measurements.
- Viewport routing: exit 0 with a status line matched by `(?m)^VIEWPORT_(?:PASS|UNFIT)(?::[^\n]*)?$` → `on_yes: vision_gate`. A retryable failure emits `FAIL:` details and neither status → `on_no: run_gen_eval`. Never fabricate `VIEWPORT_PASS` on an unfit page. Harness faults (missing runtime/browser, unreadable artifact/report path, timeout) exit non-zero → `on_error: failed`.
- Viewport cap: `.viewport_rounds` stores the cumulative number of requested refinements. Measure first on **every** visit. A fit emits `VIEWPORT_PASS` without changing/resetting the count. Failure with count `< 3` increments it, appends critique, and retries. Failure at count `3` appends/emits `VIEWPORT_UNFIT` and advances without incrementing. Thus the third failed visit requests the third refinement, and a fourth still-failing visit accepts. Subsequent vision-driven generations are remeasured with the same exhausted budget. Preserve counters on resume; malformed existing counter files are harness faults.
- Smoke cap: `.smoke_rounds` counts failures globally; passes never reset it. Failures 1 and 2 append critique and retry. Failure 3 appends its detail, emits `SMOKE_EXHAUSTED` without `SMOKE_PASS`, and exits 0; `error_patterns: ["SMOKE_EXHAUSTED"]` routes to `on_error: failed`. Match a standalone `SMOKE_PASS` line for success. State `max_retries` is unsuitable because intervening regeneration resets consecutive re-entry counts.
- Quality threshold: oracle `with.pass_threshold`, all five rubric comparisons, and the vision script use `context.pass_threshold` (default 6), rather than copying hardcoded sixes. The optional vision gate retains its global three-refinement cap and documented skip/fail-soft behavior; it cannot replace the viewport measurement status.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Shell dispatch chain: `_execute_state()` → `_run_action_or_route()` (`scripts/little_loops/fsm/executor.py:3855`; any raised exception converts to `on_error` routing at 3872-3882) → `_run_action()` interpolates the whole action string (executor.py:2459) → `DefaultActionRunner.run` shell branch (`scripts/little_loops/fsm/runners.py:300-373`) writes the rendered script to a temp file and spawns `bash <file>` with `start_new_session=True`, so timeout kills reap the whole bash→node→chrome tree. Shell states get a 3600s fallback wall-clock timeout unless `state.timeout` is declared (executor.py:2615-2622) — three viewport probes fit comfortably inside it.
- Verdict path: `_evaluate()` → the `evaluate()` dispatcher (`scripts/little_loops/fsm/evaluators.py:1839`) applies exit-code short-circuits first (124→`error`; any other non-zero→`error` for `output_contains`, lines 1879-1899), then `evaluate_output_contains()` (evaluators.py:381-435): pattern found → `yes`; not found → `no`; a declared `error_patterns` match → `error`.
- Sub-loop dispatch: `run_gen_eval` (loop: oracles/generator-evaluator) → `_execute_sub_loop()` (`scripts/little_loops/fsm/executor.py:1077`): child load at 1114-1116 (`resolve_loop_path` → `load_and_validate`), `with:` bindings interpolated at 1122, child FSM runs under a nested executor sharing the parent's action runner (1260-1300), and the child's terminal kind maps back to parent routing at 1346-1377.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-webapp-generator.yaml` (new file; the deliverable)
- `README.md` — loop count line (~185) and loop list
- `scripts/README.md` — mirror sync (`command cp -f README.md scripts/README.md`)
- `scripts/tests/test_builtin_loops.py` — extend `test_expected_loops_exist` name list; add structure tests
- `scripts/tests/test_html_webapp_generator.py` (new) — rendered-action/FSM routing tests plus real Chromium geometry fixtures; test the shipped gate rather than a reimplementation
- `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/loops.md`, `docs/generalized-fsm-loop.md` — documentation contracts listed below
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — shipped loop catalog (package data): add a `html-webapp-generator` row next to the `html-website-generator` row (line 153) and extend the `oracles/generator-evaluator` "used by" enumeration (line 187); per-loop tests assert this row exists (`test_documented_in_loops_readme`, `scripts/tests/test_flux_image_generator.py:213`) [Agents 1+2 finding]
- `scripts/little_loops/loops/html-webapp-generator.yaml:6` (new file) — must carry `artifact_versioning_ok: true` top-level, as `html-website-generator.yaml:6` does, or the `TestValidatorWarningBudget` artifact-versioning category fails [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — consumed read-only via the `run_gen_eval` state (loop: oracles/generator-evaluator); must remain unchanged
- `little_loops.fsm.loop_paths` (`get_builtin_loops_dir`, `resolve_loop_path`) — discovers the new loop automatically once the YAML lands in package data
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — `enumerate_loop_catalog()` (line 151, rglob at 184/208) auto-lists the new loop in `ll-loop list`, `ll-loop show`, and the MCP `loop_list` tool; no registration or edit needed [Agent 1 finding]
- `scripts/little_loops/doc_counts.py` — `verify_documentation()` (line 182) counts runnable loops via `rglob` and checks the README "N FSM loops" phrase; consumes the count bump, no edit [Agent 2 finding]
- `scripts/little_loops/cli/docs.py:91`, `scripts/little_loops/cli/doctor.py:886`, `scripts/little_loops/hooks/drift_check.py:143` — `ll-verify-docs`, `ll-doctor` docs check, and the session-start drift warning all surface a stale README loop count until the bump lands; no edits [Agent 2 finding]
- `scripts/little_loops/loops/fleet-loop-improve.yaml:55` — fleet meta-loop sweeps every builtin including the new one; no edit [Agent 1 finding]
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:8` — its description enumerates users ("Used by html-website-generator, html-anything, ..."); the AC freezing this file leaves that enumeration not naming the new consumer — accepted consequence, not a change [Agent 2 finding]
- `scripts/pyproject.toml:202-203` — loops YAMLs ship via the existing `little_loops/**` include glob; no packaging change [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml` — state skeleton to copy (`plan → run_gen_eval → smoke_test → vision_gate → done` thin wrapper)
- `html-anything` / `html-dashboard` — classification-based generators without viewport-fit rubrics (the gap this loop fills)
- `smoke_test` / `vision_gate` states — artifact failures use an exit-0 retry contract; retry counters live under the run directory. The new gate uses the quoted heredoc and explicit global-cap rules above.

### Tests
- `scripts/tests/test_builtin_loops.py` — `builtin_loops` fixture auto-includes the new YAML (parse/validate/gate-completeness suites run over it); add name to `test_expected_loops_exist` (~line 254); add loop-specific structure tests next to the website-generator ones
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py:446` — `test_doc_counts_all_match()` is the pytest gate behind the README loop-count bump; fails until `README.md:185` is updated [Agent 1 finding]
- `scripts/tests/test_packaging_duplicate_files.py:18` — `test_readme_matches_repo_root()` enforces byte-equality `README.md` == `scripts/README.md` after the bump [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestHtmlWebsiteGeneratorLoop` demonstrates wrapper structure invariants. The new loop needs assertions for viewport/smoke/vision routes, both viewport dispositions, all-five rubric/threshold consistency, feedback consumption, global counters, and the derived execution budget; copying the existing structure tests alone is insufficient.
- `scripts/tests/test_html_webapp_generator.py` — run the actual FSM-rendered shell action and evaluator against temporary artifacts. Stubs cover caps, parsing, report/critique writes, missing runtime/files, optional vision outcomes, and deterministic fail → feedback → regenerate → pass routing. `scripts/tests/test_rlhf_svg_evaluate_smoke.py::_extract_inline_node_script` is evidence for executing shipped scripts; a canned `page.evaluate()` result cannot prove the DOM geometry check.
- Real Chromium fixtures in that test file cover document overflow on both axes, negative off-screen control positions, root `overflow: hidden`, controls clipped within an otherwise fitting window, cross-axis and nested clipping, legitimate internal scrolling, and hidden/inert versus aria-hidden-only drawers. Missing Node, `@playwright/test`, or Chromium may skip browser-only cases clearly; subprocess timeouts prevent a hung browser from wedging the suite. Stub/FSM tests remain independent of installed browsers.
- `scripts/tests/test_builtin_loops.py:21025` + `scripts/tests/data/loop_interpolation_baseline.json` — exact-set interpolation ratchet; the `viewport_gate` critique-append must hand paths via env var (`ABS_DIR`, like `vision_gate`) or the baseline gains entries its own `_comment` forbids [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py:307` — gate token must be compound (e.g. `VIEWPORT_PASS`), never bare `PASS` [Agent 2 finding]
- `scripts/tests/test_builtin_loop_interpolation.py` and `scripts/tests/test_builtin_loop_hardcode_gate.py` — parametrized corpus gates auto-sweep the new YAML (no this-repo paths in actions); no edit, must pass [Agent 3 finding]
- Learning-test registry: keep `learning_tests_required: [playwright, node]`. `ll-learning-tests assess --issue FEAT-3589 --json` reports `node=stale` on 2026-10-05 (58 days old). Refresh stale proof before implementation through the existing learning workflow. The current Playwright record proves screenshots/error handling, not the new geometry semantics; browser fixture/proof results must identify the Node `@playwright/test` version actually exercised rather than assuming Python Playwright metadata covers it.

### Documentation
- `docs/reference/loops.md`, `docs/guides/LOOPS_REFERENCE.md` — add the loop alongside `html-website-generator`
- README loop-count bump trips mirror gates (see Files to Modify)
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md:504` — the generator-evaluator "Used by" enumeration gains `html-webapp-generator`; note there is **no** per-loop `html-website-generator` section in this file, so "add alongside" here means the delegation list (or a brand-new section), not an existing anchor [Agents 1+2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — catalog row (~line 1504), chooser prose (~1536/1606), a new per-loop section modeled on `### html-website-generator` (~1722), and the harness-loop consumer enumeration (~3616) [Agent 1 finding]
- `docs/generalized-fsm-loop.md` (~line 1115) — the `design_guidance_context` row claims "Consumed only by `html-website-generator.yaml` (ENH-3267)"; becomes false once the new loop consumes it — update [Agent 1 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (~1246-1249) — real-world generator-evaluator harness example list naming `html-anything`/`html-website-generator`; optional add [Agent 1 finding]
- README prose additions must stay end-user phrased — `scripts/tests/test_docs_audience_gate.py` gates README/docs (`ll-audience-ok:` suppression exists) [Agent 2 finding]
- The new per-loop section must list Node, a resolvable `@playwright/test` module (existing global `NODE_PATH` convention), and installed Chromium, along with the existing Playwright CLI oracle prerequisite. Document `--context 'viewports=800x600 375x667'`, valid dimension limits, three global viewport refinements, two smoke retries, optional vision behavior, the final report path, the 1-pixel tolerance, and the initial-layout/single-screenshot limitations.

### Configuration
- None required — the loop is self-contained; `viewports` is an optional per-run context override, not an `.ll/ll-config.json` key

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Validation surface: `ll-loop validate` (`scripts/little_loops/cli/loop/config_cmds.py:32-37`) → `load_and_validate` (`scripts/little_loops/fsm/validation/structural_rules.py:1873`), which runs `_validate_with_bindings` (rejects unknown `with:` keys vs the oracle's declared params — `viewports` must stay a parent loop-context value, never a `with:` binding) and `_validate_loop_references` (reachability — `oracles/generator-evaluator` must resolve; it does). Shell-safety rules that bite a Playwright probe state: MR-7 (unescaped `${VAR:-x}`), MR-11 (raw `${context.*}` in bash-token positions; per-site escape is a `# ll-lint: mr11-ok(<ns>.<key>) <reason>` marker, which must then be enumerated in `MR11_MARKER_ALLOWLIST`, `scripts/tests/test_builtin_loops.py:21088`, exact-equality assertion), MR-3 artifact isolation (satisfied by the top-level `scope: - "${context.run_dir}"` block, `html-website-generator.yaml:18-19`), and `_validate_missing_scope` (warns without it). MR-1/MR-2 meta-loop rules do not fire — an HTML generator's actions touch no harness artifacts.
- Test surface beyond the name list: `test_expected_loops_exist` (`scripts/tests/test_builtin_loops.py:204`) asserts exact set equality (`assert expected == actual`, line 304) — the `html-webapp-generator` stem must be added or the suite fails. The `builtin_loops` fixture (`rglob("*.yaml")` + `is_runnable_loop`, lines 62-68) auto-discovers the new YAML and auto-applies: YAML parse, full `load_and_validate` + `validate_fsm`, failure-edge→failure-terminal, gate-completeness, `description:` field, `scope:` field, no bare `PASS` pattern, no unescaped bash `${...}` (lines 327-390). `TestValidatorWarningBudget` (locate by class name) ratchets validator warnings — the new YAML must arrive warning-free (no-scope and unsafe-context-interp categories included) or that test fails.
- README loop count is gate-enforced, not cosmetic: use the **current** count reported by `verify_documentation()` (`scripts/little_loops/doc_counts.py`) and increment it for the new loop; mirror with `command cp -f README.md scripts/README.md` rather than copying a stale `~108` figure.
- Sub-loop routing facts: oracle `done` → parent `on_yes`; oracle `failed`/`screenshot_abandoned` → parent `on_no`; oracle max-steps → `on_no` (`scripts/little_loops/fsm/executor.py:1346-1377`). `run_gen_eval`'s `with:` block is `interpolate_dict`-ed before the child loads (executor.py:1122) and missing required child params (`run_dir`, `generate_prompt`) raise `ValueError` → `on_error` (executor.py:1124-1129) — the new loop binds them exactly as `html-website-generator.yaml:64-131` does.

### Prototype Validation Findings

_Added 2026-09-25 — a working prototype of this loop was built and validated in a consumer project's `.loops/` against this checkout (local-editable), before the built-in lands here:_

_Historical evidence for the initial design, not proof of the strengthened control-clipping, visibility, and cap-routing contracts added in the 2026-10-05 review below._

- Prototype: a consumer-project loop definition following this issue's design; `ll-loop validate` passes with no warnings.
- End-to-end: `ll-loop run html-webapp-generator "kanban board for a 4-person team"` passed every gate on the **first try**, 11m 37s over 5 steps (run dir `html-webapp-generator-20260925T191636`). Page height matched the window exactly at all three sizes; vision scores 8/7/8/9 and `layout_fit` 9. At 1440x900 the columns scroll inside their own panes; at 375x667 the layout collapsed to a menu button with a horizontally scrolling board — the responsive-collapse requirement works.
- **Prototype budget history**: the original prototype used `max_steps: 28` and `timeout: 7200` and omitted smoke failures. The implementation target remains `max_steps: 32` with a two-failure smoke retry budget; the exact execution count is clarified under Program Design.
- **Off-screen-drawer finding**: the prototype rejected a closed translated drawer at 375px and introduced semantic-subtree exemptions. The current design retains non-rendered/inert handling but removes the aria-hidden-only exemption, since it leaves interactive controls focusable (2026-10-05 browser check).
- **`viewports` interpolation**: `${context.viewports:shell}` — the plain quoted form gets an MR-11 shell-safety warning; the `:shell` form resolves the value safely (`shlex.quote`, `scripts/little_loops/fsm/interpolation.py:280-341`) and needs no suppression marker.
- **Gate script delivery**: quoted heredoc (`node - <<'JS'`) instead of `node -e "..."` — avoids the quoting problems and still keeps `${` out of the script.
- **Gate tests on hand-made sample pages (no LLM)**: `viewports="abc 800x600 12x"` → warns about the two bad entries and measures only at 800x600; no valid viewports → exit 2; missing `index.html` → exit 1 (both route to `failed`). The `body{overflow:hidden}` claim holds: page height still counts clipped content, so the gate catches it.
- **Regenerate path unexercised end to end**: the generated page passed on its first try. A naturally long-page-prone prompt cannot guarantee a failing first generation; deterministic route tests must seed an overflowing artifact and then a repaired artifact to prove feedback and regeneration. A manual model-backed run remains supplementary evidence.
- **Unrelated upstream warning**: the run log prints "Loop declares no 'scope:'" — it comes from `oracles/generator-evaluator.yaml`, which has no `scope:` line (the wrapper declares one); not a defect in this loop, and the oracle stays unchanged per § Explicitly out of scope.

## Implementation Steps

1. The standalone YAML satisfies the app-shell brief/prompt and all-five scoring contracts, including configured viewport/threshold values and explicit consumption of every gate's `critique.md` feedback. The shared oracle remains unchanged.
2. The rendered gate actions satisfy the deterministic geometry, result-report, visibility, global-cap, and routing contracts under Program Design. Keep `max_steps: 32`, loop `timeout: 7200`, and viewport state `timeout: 120`. Failure terminals are explicitly marked with `failure: true`.
3. `ll-loop validate html-webapp-generator` and the existing corpus/interpolation/warning ratchets pass without new baseline or allowlist exceptions. All artifacts stay under `${context.run_dir}`.
4. Catalogs, loop-count prose, user documentation, and the byte-identical README mirror agree with the new loop and its best-effort behavior. Counts come from current repository contents.
5. Structure, rendered-script, real-browser geometry, and deterministic FSM route tests cover the acceptance criteria, including exhausted viewport → optional vision → done, vision regeneration after exhaustion, and smoke exhaustion → failed. A scripted bad-first/repaired-next artifact closes the regeneration gap without depending on model output.
6. Learning proof is fresh before implementation starts; the relevant test groups and authoritative local suite (`python -m pytest scripts/tests/`) pass after implementation. A manual model-backed smoke run is supplementary and records its measured status/report; a first-try pass is not evidence of the retry route.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/loops/README.md` — add the `html-webapp-generator` catalog row (next to line 153) and extend the `oracles/generator-evaluator` "used by" list (line 187)
- Update `docs/guides/LOOPS_REFERENCE.md` — catalog row (~1504), new per-loop section (~1722), harness consumer enumeration (~3616)
- Update `docs/reference/loops.md:504` — add `html-webapp-generator` to the generator-evaluator "Used by" enumeration (no per-loop section exists in this file to sit "alongside")
- Update `docs/generalized-fsm-loop.md` — `design_guidance_context` row (~1115) is no longer "Consumed only by" the website generator
- Bump `README.md:185` loop count and byte-mirror with `command cp -f README.md scripts/README.md` — enforced by `test_doc_counts_all_match` (`scripts/tests/test_wiring_guides_and_meta.py:446`) and `test_readme_matches_repo_root` (`scripts/tests/test_packaging_duplicate_files.py:18`); keep new README prose end-user phrased (`test_docs_audience_gate.py`)
- Add loop-specific structure checks near `TestHtmlWebsiteGeneratorLoop` and rendered-action/browser/FSM behavior tests in `scripts/tests/test_html_webapp_generator.py`; do not reproduce old assumptions by cloning assertion text
- Carry `artifact_versioning_ok: true` in the new YAML — `TestValidatorWarningBudget` artifact-versioning category
- Keep `scripts/tests/data/loop_interpolation_baseline.json` unchanged — hand `run_dir` via env var (`ABS_DIR`) inside the `viewport_gate` scripts, never `${context.run_dir}` interpolation in script bodies (`TestInterpSweepBaseline` exact-set ratchet)
- Optional: add the loop to the real-world harness list in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (~1249)

## Impact

- **Priority**: P3 - additive generator variant; no consumer blocked, quality-of-life for HTML artifact workflows
- **Effort**: Medium - one new loop YAML with a new non-LLM gate state plus tests and doc/mirror updates; no Python source changes
- **Risk**: Moderate within the new loop - additive scope, but browser clipping/visibility semantics and terminal routing need behavioral coverage; shared oracle and existing consumers remain untouched
- **Breaking Change**: No

## Use Case

A user runs `ll-loop run html-webapp-generator "kanban board for a 4-person team"`. The loop aims for a self-contained `index.html` that fills the browser window like an app, with long lists scrolling inside their panes at 1440x900, 1024x768 and 375x667. The final `viewport-report.json` distinguishes measured fit from best-effort acceptance with remaining violations; `VIEWPORT_UNFIT` does not claim the page fits.

## API/Interface

New loop `html-webapp-generator` with `input_key: description` and `required_inputs: ["description"]`. Context mirrors `html-website-generator` (`pass_threshold`, `design_tokens_context`, `design_guidance_context`), with an optional `viewports` context value (default `"1440x900 1024x768 375x667"`).

## Open Questions

_The original product decisions remain resolved; the 2026-10-05 review pins down implementation contracts and validation gaps:_

- **Mobile semantics → keep 375x667 fully in the gate** ("no document scroll; internal scroll panes allowed"), made feasible by requiring responsive collapse (sidebar → off-canvas/hamburger, grids → single column) in the generator prompt. Exempting mobile would remove the gate's highest-value check — narrow viewports are where overflow breaks most.
- **Round-cap exhaustion → measured accept-at-cap** with a visible `VIEWPORT_UNFIT` status and failing per-viewport measurements in the acceptance line (see § Decision Rules).

## Acceptance Criteria

- [ ] `ll-loop validate html-webapp-generator` and existing inventory, interpolation, warning, documentation-count, README-mirror, and audience gates pass without new ratchet exceptions.
- [ ] Real-browser fixtures exercise the shipped gate: document overflow on either axis (> 1 CSS pixel tolerance) retries with `FAIL:` and per-viewport critique; valid vertical/horizontal internal scrolling passes.
- [ ] Controls clipped by non-scrollable ancestors fail even when their boxes fit the window; a scrollable ancestor on one axis or an inner pane cannot excuse clipping on another axis or by an outer ancestor.
- [ ] Non-rendered/inert controls are excluded appropriately; rendered focusable aria-hidden-only drawers are checked. The prompt requires visually closed, unfocusable drawers and does not rely on body clipping to fake fit.
- [ ] Each viewport is set before loading a fresh page, measurements wait for the specified readiness checks, and gate resources/waits are bounded. The generator and brief receive the same viewport configuration.
- [ ] A per-run override accepts only positive integer dimensions at most 8192; malformed/zero/oversized entries warn and skip. No valid sizes, unavailable runtime/browser, unreadable artifact/report paths, corrupted counters, and timeouts route to `failed`.
- [ ] Global viewport refinements occur at most three times, with no reset on a pass or vision regeneration. The exhausted gate still measures the current page; `VIEWPORT_UNFIT` follows `on_yes` to vision and can reach `done`, while a fit emits `VIEWPORT_PASS`. Neither disposition masquerades as the other.
- [ ] A later vision-driven generation refreshes `viewport-report.json` and the measured status for that artifact. A previously unfit page repaired after exhaustion reports `VIEWPORT_PASS`; optional/skipped vision does not erase an unfit result.
- [ ] The report includes the artifact hash, retry count, all valid viewport measurements, total violation counts, and bounded control details. Retryable and exhausted failures append usable feedback, and the generator reads it before critique replacement.
- [ ] Smoke failures 1 and 2 retry with critique; failure 3 exits 0 with explicit exhaustion routing to the failure terminal. Harness faults exit non-zero. Global smoke counters survive intervening generation and passes.
- [ ] Both rubric formats score all five named criteria, including `layout_fit`, and honor a valid `pass_threshold` override. Copied four-score/hardcoded-threshold/off-screen-immunity instructions are absent.
- [ ] Deterministic FSM tests prove fail → feedback → repaired artifact → pass, viewport-cap acceptance with vision skipped, vision rejection/regeneration after viewport exhaustion, and third smoke failure termination. The worst successful path uses 30 nonterminal parent executions and recognizes `done` with `max_steps: 32`.
- [ ] User documentation explains prerequisites, overrides, the latest report, best-effort acceptance, optional vision, geometry tolerance, and initial-layout/single-screenshot limitations; it makes no unconditional viewport-fit or clipping-detection promise.
- [ ] Learning proof is fresh when implementation begins, real-browser validation identifies the Node package/browser used, and `python -m pytest scripts/tests/` passes after implementation.
- [ ] `oracles/generator-evaluator.yaml` is unchanged.

## Related Key Documentation

`docs/guides/LOOPS_REFERENCE.md`, `docs/reference/loops.md`, and `scripts/little_loops/loops/README.md` (generator catalog).

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- proof-run findings fold-in (consumer-project prototype: e2e kanban run passed first try in 11m37s; max_steps 28 / timeout 7200 budget correction, off-screen-drawer gate exclusion, `${context.viewports:shell}`, heredoc gate delivery, oracle scope-warning attribution) - 2026-09-25
- `/ll:confidence-check` - 2026-09-26T00:19:46 - `3ba6a46a-761b-4ab5-89c0-ab0b42db6625.jsonl`
- `/ll:verify-issues` - 2026-09-26T00:12:27 - `98da18e9-798f-4617-bd29-6f3941aca3ff.jsonl`
- pre-implementation review fold-in (Claude review: resolved open questions, max_steps budget, prompt/rubric/AC gaps) - 2026-09-25
- `/ll:confidence-check` - 2026-09-25T23:27:42 - `d6bd211f-c643-48aa-aeac-10c8d9198fcd.jsonl`
- `/ll:wire-issue` - 2026-09-25T23:21:15 - `6f19f2e8-c7f6-4ad5-9b57-752e049be6a9.jsonl`
- `/ll:refine-issue` - 2026-09-25T23:01:04 - `3a51f6da-0505-450c-a253-261a60c5053b.jsonl`
- `/ll:format-issue` - 2026-09-25T22:12:18 - `8c81fde2-1b8f-4d35-a9d4-d9e034fb1af8.jsonl`
- `/ll:capture-issue` - 2026-09-25T02:02:39 - `09b7cc1a-1227-48d7-9d78-dac3ced876ba.jsonl`
