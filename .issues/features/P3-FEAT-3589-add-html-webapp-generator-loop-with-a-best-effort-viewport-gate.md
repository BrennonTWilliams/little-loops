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

`ll-loop run html-webapp-generator "<description>"` attempts to converge on a self-contained `index.html` app-shell (header / sidebar / main panes) that fills the viewport (`100dvh`) with no document-level scroll at every configured viewport (default 1440x900, 1024x768, 375x667). Overflow belongs in internal scroll panes. The non-LLM `viewport_gate` appends per-viewport measurements to the run's `critique.md` and routes failures back to `run_gen_eval` until its cap; at the cap it measures the **current** page and reports a visible best-effort `VIEWPORT_UNFIT` status if overflow remains. Harness faults route to `failed`.

## Motivation

No existing loop forces single-viewport output:

- `html-website-generator` (`scripts/little_loops/loops/html-website-generator.yaml`) builds scrolling single-page websites. Its rubric explicitly scores a full-page screenshot.
- `html-anything` classifies the artifact type (`html-dashboard`, `html-website`, ...), but no rubric requires fitting one viewport. It exposes no type override either: its only inputs are `description` and `artifact_mode`. Adding an `html-webapp` type there would make routing non-deterministic, because the classifier could pick `html-dashboard` for the same description. A standalone loop gives deterministic behavior and has no coupling to `html-anything`.

## Proposed Solution

Copy the thin-wrapper shape of `html-website-generator`:

```
plan → run_gen_eval (loop: oracles/generator-evaluator) → smoke_test → viewport_gate → vision_gate → done
```

1. **Generator prompt**: require an app-shell layout sized to the viewport (`100dvh`). No document scroll. Internal scroll panes are allowed (message lists, sidebars, tables). Require responsive collapse at narrow widths (sidebar → off-canvas/hamburger, multi-column grids → single column) so an app shell is feasible at 375x667 — without this the generator fights the viewport gate every round at mobile size. Do **not** mandate `overflow: hidden` on `body`: that invites the generator to clip content off-screen to pass the check. Closed off-canvas drawers must be hidden semantically — `[inert]`, `[hidden]`, `[aria-hidden="true"]`, or `visibility: hidden` — never merely translated off-screen: the viewport gate skips semantically hidden subtrees, but a drawer only slid off-screen keeps its links outside the window and false-fails at 375x667 (prototype finding, 2026-09-25).
2. **Rubrics (both)**: the wrapper passes two rubrics — the oracle `rubric:` binding and vision_gate's inline Python rubric. Keep the website-generator criteria in both and add an app-shell / layout-fit criterion to both (primary regions visible, no content cut off, sensible pane-level scrolling). `viewport_gate` covers geometry deterministically; the rubric criterion catches non-interactive content clipped in non-scrollable panes, which the gate's interactive-element check deliberately does not.
3. **`viewport_gate`** (new non-LLM shell state, same Playwright pattern as `smoke_test`; deliver the node script as a quoted heredoc, `node - <<'JS'` — prototype-validated over `node -e "..."`, which has nested-quoting problems, while still keeping `${` out of the script body). At each viewport size (proposed: 1440x900, 1024x768, 375x667):
   - assert `document.documentElement.scrollHeight <= innerHeight` and `scrollWidth <= innerWidth`. `scrollHeight` counts overflowed content even under `overflow: hidden`, so page-level clipping is still caught (prototype-confirmed: a `body{overflow:hidden}` page still fails the height check).
   - assert the bounding boxes of key interactive elements (`button`, `a`, `input`, `select`, `textarea`, `[role=button]`) that are visible and not inside a scrollable ancestor lie within the viewport. This catches content clipped inside `overflow: hidden` containers. Elements inside semantically hidden subtrees (`[inert]`, `[hidden]`, `[aria-hidden="true"]`, `visibility: hidden`) are excluded — a closed off-canvas drawer hidden only by translation sits outside the viewport and would otherwise false-fail at mobile size. Coverage note: interactive elements only — non-interactive content clipped in an `overflow: hidden` (non-scrollable) pane is caught by the rubric layout-fit criterion and the full-page screenshot, not by this gate.
4. **Feedback on failure**: before routing back to `run_gen_eval`, `viewport_gate` must append the measured dimensions and overflow amounts per viewport to `${context.run_dir}/critique.md` under an `## Issues to Address` heading, as `vision_gate` does. `smoke_test` writes nothing on failure, which would leave the regeneration pass blind to why it failed.
5. **Exit-code contract** (matches `smoke_test`): an artifact failure prints `FAIL:...` and exits 0 → `on_no: run_gen_eval`. A harness fault (node/Playwright missing, unreadable path) exits non-zero → `on_error: failed`. Bound viewport ping-pong with a per-run round-cap file. At the cap, **measure before accepting** and print `VIEWPORT_UNFIT` plus the failing per-viewport measurements in the acceptance line and critique.md; a clean pass prints `VIEWPORT_PASS`. A later vision-driven regeneration must be measured again. Bound `smoke_test` failures separately: the first two failures append critique and retry, while a third failure routes to `failed`. Docs must say "best-effort viewport fit, up to 3 viewport refine rounds", never "never ships an overflowing page".

### Explicitly out of scope: the shared oracle

Do **not** modify `scripts/little_loops/loops/oracles/generator-evaluator.yaml`. Its evaluate state hardcodes `playwright screenshot --full-page`, and 7 loops consume the oracle. No change is needed: for a page that doesn't scroll, a full-page screenshot equals the viewport screenshot. For a page that overflows, the full-page screenshot shows the overflow to the LLM scorer, which is better evidence than a viewport crop.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Routing mechanism: the gate's `evaluate:` must be `output_contains` on a PASS token — smoke_test's contract is `type: output_contains` / `pattern: "SMOKE_PASS"` (`scripts/little_loops/loops/html-website-generator.yaml:170-171`). The `FAIL:` stdout text never drives routing; it is feedback for the log/critique. A non-zero exit short-circuits to verdict `error` BEFORE `output_contains` runs (`_EXIT_CODE_AWARE_EVALUATORS` gate, `scripts/little_loops/fsm/evaluators.py:1879-1892` — `output_contains` is not in the exit-code-aware set, BUG-1815), and exit 124 (timeout) is always `error`. Complete contract: PASS token + exit 0 → `on_yes`; exit 0 without token → `on_no: run_gen_eval`; non-zero exit → `on_error: failed`.
- Interpolation constraints on the embedded node script: the whole `action:` string is FSM-interpolated before bash sees it (`scripts/little_loops/fsm/executor.py:2459`), so the JS must contain zero `${` sequences — use string concatenation and hand paths over via `export ABS_DIR` → `process.env.ABS_DIR`, exactly as smoke_test does: `await page.goto('file://' + process.env.ABS_DIR + '/index.html');` (`html-website-generator.yaml:158`). Bash parameter defaults must be written `$${VAR:-x}` — vision_gate: `if [ -z "$${VISION_BASE_URL:-}" ]` (`html-website-generator.yaml:202`). Avoid `$$(` and `$$VAR` over-escapes (MR-9; bash expands them to PID). Test-side enforcement: `scripts/tests/test_builtin_loops.py:327-390` fails any unescaped bash `${...}` in shell actions, including the `:-` default form.
- Round-cap precedent: vision_gate's `.vision_rounds` counter (`html-website-generator.yaml:213`) uses `ROUND_CAP = 3` (line 215) and at exhaustion ACCEPTS best-so-far — `print("VISION_PASS: round cap (%d) reached, accepting" % ROUND_CAP); sys.exit(0)` (lines 220-221) — routing to `done`, not `failed`. The counter increments only on fail rounds (`open(rc_file, "w").write(str(rc + 1))`, line 272). The issue's open question (fail vs accept at cap) has an established codebase answer: accept-at-cap.
- critique.md append idiom: vision_gate appends via embedded python3 heredoc, not bash — `with open(crit, "a") as f:` (`html-website-generator.yaml:278`) writing `## Issues to Address (external vision critique, round N)`-headed blocks with `%`-formatting (never `${}` in the Python either — the FSM interpolator ran before bash, quoting the heredoc does not protect it). `${context.run_dir}` is absolutized by a shell case-statement before the heredoc (lines 196-200) because the script's cwd differs from the run dir; a `viewport_gate` append must do the same and use a distinguishing heading (e.g. `## Issues to Address (viewport gate, round N)`) so the generator can attribute the feedback. Confirmed: `smoke_test` writes nothing on failure — its node script only logs to stdout.

## Program Design

### Types

- Loop context contract mirrors `html-website-generator` (`pass_threshold`, `design_tokens_context`, `design_guidance_context`) plus `viewports: str` — space-separated `WxH` entries, default `"1440x900 1024x768 375x667"`, parsed inside the `viewport_gate` node script. Both dimensions must be positive integers at most 8192; `0x0` and oversized entries are malformed. Interpolate it into the gate action as `${context.viewports:shell}`: the `:shell` suffix safely quotes the resolved value. `run_dir` reaches the script only via the `ABS_DIR` env var, never interpolation, per the interpolation-baseline ratchet. Malformed entries are skipped with a warning on stdout; zero valid viewports is a harness fault (non-zero exit → `failed`).
- Budget: the viewport-plus-vision worst path is 27 steps, but the copied `smoke_test.on_no → run_gen_eval` adds two steps per failure and has no cap today. Allow **two smoke-failure retries** globally (a third failure routes to `failed`) and reserve four more steps: worst path 31, `max_steps: 32` (one-step margin), loop-level `timeout: 7200`. The structure test must count both gate caps and the smoke budget; any exhausted smoke cap routes to `failed`, never silently accepts.

### Signatures

- `cmd_validate(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` — existing `ll-loop validate` entry; validates the new YAML with no code change.
- `test_expected_loops_exist() -> None` — existing builtin-loop inventory test; extend its expected-name list with `html-webapp-generator`.
- `test_html_webapp_generator_structure(builtin_loops: list[Path]) -> None` — new: asserts the state set (`plan → run_gen_eval → smoke_test → viewport_gate → vision_gate → done`), the `viewport_gate` exit-code routing, and the critique-append contract.

### Call Path

`resolve_loop_path(loop_name, loops_dir)` (little_loops.fsm.loop_paths) -> `load_and_validate(path)` (little_loops.fsm.validation) -> FSM executor dispatches the `viewport_gate` shell action (non-LLM inline node Playwright probe, delivered as a quoted heredoc) -> on `FAIL:` appends measurements to `${context.run_dir}/critique.md` and routes `on_no: run_gen_eval`.

No Python source changes: the loop is package data picked up by `get_builtin_loops_dir()` automatically; the only touched Python files are tests.

### Decision Rules

- `viewport_gate` FAIL condition, evaluated at each viewport in `viewports` (default `1440x900 1024x768 375x667`): document-level scroll present (`document.documentElement.scrollHeight > window.innerHeight` or `scrollWidth > window.innerWidth`), OR any visible interactive element (`button`, `a`, `input`, `select`, `textarea`, `[role=button]`) not inside a scrollable ancestor has a bounding box extending past the viewport edges — excluding elements inside semantically hidden subtrees (`[inert]`, `[hidden]`, `[aria-hidden="true"]`, `visibility: hidden`), so closed off-canvas drawers hidden that way do not false-fail at 375x667 (prototype finding, 2026-09-25: a translation-only-hidden drawer failed the gate at mobile size). Every configured viewport must pass for the gate to pass.
- Exit-code mapping: artifact failure → exit 0 with `FAIL:` detail lines and no PASS token; harness fault (node/Playwright missing, unreadable artifact path, exit 124 timeout) → non-zero exit → verdict `error` → `on_error: failed`.
- Round cap: `.viewport_rounds` counter file in `${context.run_dir}`, cap `3`; increment only on gate-fail rounds. At exhaustion, measure the current page before **accept-at-cap** and emit `VIEWPORT_UNFIT` plus failing per-viewport measurements in the run log and critique. Run this measurement again after any vision-driven regeneration. A clean measured pass emits `VIEWPORT_PASS`.
- Smoke cap: `.smoke_rounds` counts failures across the run; the first two append detail to critique and retry, and a third routes to `failed`.
- Escape hatch: a per-run `viewports` context value overrides the default list; it is a loop-context value, never a `with:` binding. Malformed, zero, or over-8192 dimensions are skipped with a warning; no valid viewports is a harness fault.

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
- `smoke_test` / `vision_gate` states — Playwright `node -e` shell pattern, `FAIL:` exit-0 contract, and `.vision_rounds` round-cap file to mirror in `viewport_gate`

### Tests
- `scripts/tests/test_builtin_loops.py` — `builtin_loops` fixture auto-includes the new YAML (parse/validate/gate-completeness suites run over it); add name to `test_expected_loops_exist` (~line 254); add loop-specific structure tests next to the website-generator ones
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py:446` — `test_doc_counts_all_match()` is the pytest gate behind the README loop-count bump; fails until `README.md:185` is updated [Agent 1 finding]
- `scripts/tests/test_packaging_duplicate_files.py:18` — `test_readme_matches_repo_root()` enforces byte-equality `README.md` == `scripts/README.md` after the bump [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestHtmlWebsiteGeneratorLoop` is the clone template for `TestHtmlWebAppGeneratorLoop`: state set incl. `viewport_gate`/`vision_gate`, `smoke_test.on_yes == "viewport_gate"`, critique append, both gate caps, the new global smoke cap, `viewports` context default, and a max-steps formula covering all three retry paths.
- New behavioral test file (pattern: `scripts/tests/test_rlhf_svg_evaluate_smoke.py:86-136`) — regex-extract the `viewport_gate` inline node script (quoted heredoc), stub Playwright (`setViewportSize`/`evaluate` returning `scrollHeight`/`innerHeight`), assert PASS/FAIL tokens, exit codes, and the critique.md append; guard with `require_node()` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:21025` + `scripts/tests/data/loop_interpolation_baseline.json` — exact-set interpolation ratchet; the `viewport_gate` critique-append must hand paths via env var (`ABS_DIR`, like `vision_gate`) or the baseline gains entries its own `_comment` forbids [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py:307` — gate token must be compound (e.g. `VIEWPORT_PASS`), never bare `PASS` [Agent 2 finding]
- `scripts/tests/test_builtin_loop_interpolation.py` and `scripts/tests/test_builtin_loop_hardcode_gate.py` — parametrized corpus gates auto-sweep the new YAML (no this-repo paths in actions); no edit, must pass [Agent 3 finding]
- Learning-test registry: `.ll/learning-tests/playwright.md` and `node.md` already exist for `learning_tests_required: [playwright, node]`; gate runs at manage-time, nothing to add [Agent 3 finding]

### Documentation
- `docs/reference/loops.md`, `docs/guides/LOOPS_REFERENCE.md` — add the loop alongside `html-website-generator`
- README loop-count bump trips mirror gates (see Files to Modify)
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md:504` — the generator-evaluator "Used by" enumeration gains `html-webapp-generator`; note there is **no** per-loop `html-website-generator` section in this file, so "add alongside" here means the delegation list (or a brand-new section), not an existing anchor [Agents 1+2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — catalog row (~line 1504), chooser prose (~1536/1606), a new per-loop section modeled on `### html-website-generator` (~1722), and the harness-loop consumer enumeration (~3616) [Agent 1 finding]
- `docs/generalized-fsm-loop.md` (~line 1115) — the `design_guidance_context` row claims "Consumed only by `html-website-generator.yaml` (ENH-3267)"; becomes false once the new loop consumes it — update [Agent 1 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (~1246-1249) — real-world generator-evaluator harness example list naming `html-anything`/`html-website-generator`; optional add [Agent 1 finding]
- README prose additions must stay end-user phrased — `scripts/tests/test_docs_audience_gate.py` gates README/docs (`ll-audience-ok:` suppression exists) [Agent 2 finding]

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

- Prototype: a consumer-project loop definition following this issue's design; `ll-loop validate` passes with no warnings.
- End-to-end: `ll-loop run html-webapp-generator "kanban board for a 4-person team"` passed every gate on the **first try**, 11m 37s over 5 steps (run dir `html-webapp-generator-20260925T191636`). Page height matched the window exactly at all three sizes; vision scores 8/7/8/9 and `layout_fit` 9. At 1440x900 the columns scroll inside their own panes; at 375x667 the layout collapsed to a menu button with a horizontally scrolling board — the responsive-collapse requirement works.
- **Prototype budget history**: the original prototype used `max_steps: 28` and `timeout: 7200` after counting 27 viewport/vision steps. This omitted smoke failures; the current implementation target is `max_steps: 32` with a two-failure smoke cap (see § Program Design, Budget).
- **Off-screen-drawer false fail**: a closed off-canvas menu translated off-screen (not semantically hidden) fails the gate at 375px because its links sit outside the window. Folded into the design: the gate skips `[inert]`/`[hidden]`/`[aria-hidden="true"]`/`visibility: hidden` subtrees, and the generator prompt requires closed drawers to be hidden that way (§ Proposed Solution, § Decision Rules).
- **`viewports` interpolation**: `${context.viewports:shell}` — the plain quoted form gets an MR-11 shell-safety warning; the `:shell` form resolves the value safely (`shlex.quote`, `scripts/little_loops/fsm/interpolation.py:280-341`) and needs no suppression marker.
- **Gate script delivery**: quoted heredoc (`node - <<'JS'`) instead of `node -e "..."` — avoids the quoting problems and still keeps `${` out of the script.
- **Gate tests on hand-made sample pages (no LLM)**: `viewports="abc 800x600 12x"` → warns about the two bad entries and measures only at 800x600; no valid viewports → exit 2; missing `index.html` → exit 1 (both route to `failed`). The `body{overflow:hidden}` claim holds: page height still counts clipped content, so the gate catches it.
- **Regenerate path unexercised end to end**: the generated page passed the gate on its first try, so the fail → critique → regenerate path is covered only by the hand-made-page gate tests; Implementation Step 6 now asks for a long-page-prone description (e.g., a documentation site) to close that gap.
- **Unrelated upstream warning**: the run log prints "Loop declares no 'scope:'" — it comes from `oracles/generator-evaluator.yaml`, which has no `scope:` line (the wrapper declares one); not a defect in this loop, and the oracle stays unchanged per § Explicitly out of scope.

## Implementation Steps

1. Create `scripts/little_loops/loops/html-webapp-generator.yaml` (new file) from `html-website-generator.yaml` with the app-shell generator prompt (including the responsive-collapse requirement) and rubrics. Keep the `generate_prompt` paragraph directing the generator to read `critique.md`'s "Issues to Address" (`html-website-generator.yaml:69-72`) verbatim — it is load-bearing: without it, `viewport_gate`'s critique append is write-only.
2. Add the `viewport_gate` state (multi-viewport overflow + bounding-box check, critique append, measured status at the accept-at-cap disposition). Allow two `smoke_test` failure retries, append those failures to critique, and route a third failure to `failed`. Set `max_steps: 32` and loop-level `timeout: 7200` (31-step worst path with both gate caps and two smoke failures — see § Program Design, Budget).
3. Run `ll-loop validate html-webapp-generator` (MR rules, per-run artifacts under `${context.run_dir}`).
4. Update the README.md loop count and sync mirrors (`command cp -f README.md scripts/README.md`). Add the loop to the loop docs / catalog alongside `html-website-generator`.
5. Add tests for the loop's structure/validation, following the existing tests for `html-website-generator`.
6. Do one manual end-to-end run with a description that tends to produce long pages (e.g., a documentation site) to confirm the gate fails, writes critique.md, and converges — the prototype's kanban run passed every gate on the first try, so the fail → critique → regenerate path was never exercised end to end.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/loops/README.md` — add the `html-webapp-generator` catalog row (next to line 153) and extend the `oracles/generator-evaluator` "used by" list (line 187)
- Update `docs/guides/LOOPS_REFERENCE.md` — catalog row (~1504), new per-loop section (~1722), harness consumer enumeration (~3616)
- Update `docs/reference/loops.md:504` — add `html-webapp-generator` to the generator-evaluator "Used by" enumeration (no per-loop section exists in this file to sit "alongside")
- Update `docs/generalized-fsm-loop.md` — `design_guidance_context` row (~1115) is no longer "Consumed only by" the website generator
- Bump `README.md:185` loop count and byte-mirror with `command cp -f README.md scripts/README.md` — enforced by `test_doc_counts_all_match` (`scripts/tests/test_wiring_guides_and_meta.py:446`) and `test_readme_matches_repo_root` (`scripts/tests/test_packaging_duplicate_files.py:18`); keep new README prose end-user phrased (`test_docs_audience_gate.py`)
- Add `TestHtmlWebAppGeneratorLoop` (clone of `TestHtmlWebsiteGeneratorLoop`, `scripts/tests/test_builtin_loops.py:10494`) and a behavioral viewport-gate test file (pattern: `scripts/tests/test_rlhf_svg_evaluate_smoke.py`)
- Carry `artifact_versioning_ok: true` in the new YAML — `TestValidatorWarningBudget` artifact-versioning category
- Keep `scripts/tests/data/loop_interpolation_baseline.json` unchanged — hand `run_dir` via env var (`ABS_DIR`) inside the `viewport_gate` scripts, never `${context.run_dir}` interpolation in script bodies (`TestInterpSweepBaseline` exact-set ratchet)
- Optional: add the loop to the real-world harness list in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (~1249)

## Impact

- **Priority**: P3 - additive generator variant; no consumer blocked, quality-of-life for HTML artifact workflows
- **Effort**: Medium - one new loop YAML with a new non-LLM gate state plus tests and doc/mirror updates; no Python source changes
- **Risk**: Low - purely additive; `oracles/generator-evaluator.yaml` and its 7 consumers untouched
- **Breaking Change**: No

## Use Case

A user runs `ll-loop run html-webapp-generator "kanban board for a 4-person team"`. The result is a self-contained `index.html` that fills the browser window like an app (header / sidebar / main pane). Long lists scroll inside their own panes, and the page itself never scrolls at 1440x900, 1024x768 or 375x667.

## API/Interface

New loop `html-webapp-generator` with `input_key: description` and `required_inputs: ["description"]`. Context mirrors `html-website-generator` (`pass_threshold`, `design_tokens_context`, `design_guidance_context`), with an optional `viewports` context value (default `"1440x900 1024x768 375x667"`).

## Open Questions

_None remaining — both were resolved during pre-implementation review (2026-09-25):_

- **Mobile semantics → keep 375x667 fully in the gate** ("no document scroll; internal scroll panes allowed"), made feasible by requiring responsive collapse (sidebar → off-canvas/hamburger, grids → single column) in the generator prompt. Exempting mobile would remove the gate's highest-value check — narrow viewports are where overflow breaks most.
- **Round-cap exhaustion → measured accept-at-cap** with a visible `VIEWPORT_UNFIT` status and failing per-viewport measurements in the acceptance line (see § Decision Rules).

## Acceptance Criteria

- [ ] `ll-loop validate html-webapp-generator` passes.
- [ ] `viewport_gate` fails (exit 0, `FAIL:` output) for a page whose document scrolls at any configured viewport, and appends per-viewport measurements to `critique.md`.
- [ ] `viewport_gate` passes for an app-shell page whose overflow is confined to internal scroll panes.
- [ ] Harness faults route to `failed`, not back to `run_gen_eval`.
- [ ] A per-run `viewports` override is honored (the gate measures at the overridden sizes); malformed entries are skipped with a warning.
- [ ] At the round cap, `viewport_gate` measures the current page before accepting and emits `VIEWPORT_UNFIT` with failing per-viewport measurements; after a later vision-driven regeneration it measures again. A clean pass emits `VIEWPORT_PASS`.
- [ ] `smoke_test` appends failure detail to critique; the first two failures retry and a third routes to `failed`.
- [ ] `max_steps` (≥ 32) covers the 27-step viewport/vision path plus two smoke retries (four steps), with one step of margin.
- [ ] `viewport_gate` excludes elements in semantically hidden subtrees (`[inert]`, `[hidden]`, `[aria-hidden="true"]`, `visibility: hidden`) from the interactive-element bounding-box check, and the generator prompt requires closed off-canvas drawers to be hidden that way.
- [ ] A per-run viewport override accepts only positive dimensions at most 8192; `0x0` and oversized values are warned and skipped, and zero valid viewports routes to `failed`.
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
