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
---

# FEAT-3589: Add html-webapp-generator loop with a best-effort viewport gate

## Summary

Add a standalone built-in FSM loop, `html-webapp-generator`, that aims for a single-viewport, webapp-style HTML artifact. A non-LLM Playwright gate measures layout and control reachability and requests up to three refinements. Remaining violations are accepted as best effort with a durable `VIEWPORT_UNFIT` report and a distinct `done_viewport_unfit` completion state.

## Current Behavior

No built-in loop produces a single-viewport app-shell HTML artifact:

- `html-website-generator` emits scrolling single-page websites and scores a full-page screenshot.
- `html-anything` classifies the artifact type but has no viewport-fit rubric or type override. Its only inputs are `description` and `artifact_mode`, so an app-shell request may select `html-dashboard` or `html-website`.

## Expected Behavior

`ll-loop run html-webapp-generator "<description>"` attempts a self-contained `index.html` app shell (header, navigation, main panes) that fills `100dvh` without document-level scrolling at every configured viewport (default 1440x900, 1024x768, 375x667). Long content remains reachable through internal user-scrollable panes, and navigation/columns collapse at narrow widths.

Every gate visit measures the current artifact, including after vision-driven regeneration. Fit reports `VIEWPORT_PASS`; violations consume a global three-refinement budget, then report `VIEWPORT_UNFIT` and advance to optional vision. After vision accepts or skips, a deterministic finalizer validates the report against the current artifact and routes to `done` or `done_viewport_unfit`. Both are nonfailure terminals; ordinary non-quiet completion output distinguishes them. Exhausted smoke retries and unrecovered action/child faults route to `failed`. The engine's overall timeout or step exhaustion is a separate non-success outcome and need not visit the YAML failure terminal.

## Motivation

A standalone loop makes app-shell behavior deterministic without coupling it to `html-anything` classification. The measured report separates actual viewport fit from best-effort acceptance and optional visual assessment.

## Proposed Solution

Follow the thin-wrapper pattern in `scripts/little_loops/loops/html-website-generator.yaml`, with these states:

```
validate_context → plan → run_gen_eval (loop: oracles/generator-evaluator) → smoke_test
     → viewport_gate → vision_gate → finalize → done | done_viewport_unfit
```

Retryable smoke, viewport, and vision failures return to `run_gen_eval`; unrecovered gate faults return to `failed`, subject to existing engine recovery and overall limits.

1. **Settings/planner/generator**: validate settings before the first model call and persist the normalized configuration. Provide the same valid viewport list to both prompts. Require a standards-mode document (`<!doctype html>`), mobile viewport meta, `100dvh` shell, responsive collapse, and reachable internal scrolling. Do not mandate body `overflow: hidden` or accept clipping as proof of fit. Closed drawers must be visually closed and unavailable to focus: `[hidden]`/`display: none`, or an off-canvas treatment with `inert` that also preserves root/body extent limits; `aria-hidden` alone is insufficient. Prefer non-rendered drawers or off-canvas placement inside a fitting wrapper. `inert` exempts descendant controls, not document/body overflow. Prompts must treat settings, counters, reports, and gate images as harness-owned files; generation writes only `index.html`. Consume every critique section whose heading starts with `## Issues to Address` before the oracle replaces it.
2. **Both rubrics**: score `design_quality`, `originality`, `craft`, `functionality`, and `layout_fit` on the same 0–10 scale. Every criterion compares against the validated run threshold (initial `context.pass_threshold`, default 6), including oracle binding, rubric format/instructions, and optional vision parsing. Remove copied four-score, hardcoded-threshold, and off-screen-immunity instructions. Layout fit considers visible primary regions, cut-off controls/content, and sensible internal scrolling.
3. **Deterministic gates**: use quoted Node heredocs (`node - <<'JS'`) with settings/paths supplied through environment variables using shell-safe interpolation. Embedded script source contains no FSM `${...}` expressions or JavaScript template literals with `${`. Measure fresh pages at configured sizes, with bounded load/font/frame waits and browser cleanup. Geometry and bounded scroll-reachability rules are specified below.
4. **Feedback/persistence**: append usable failure details under `## Issues to Address` before regeneration. Publish `viewport-report.json` with the measured artifact hash and disposition, independently of LLM-written critique. Atomically replace reports/counters and emit routing status only after required writes succeed.
5. **Honest completion**: finalization is a nonterminal shell state, not an action attached to a terminal. It verifies current artifact/report identity and routes to separate fit/unfit terminals. User docs describe best-effort fit and the report, not an unconditional fit guarantee.

### Scope boundaries

Do **not** modify `scripts/little_loops/loops/oracles/generator-evaluator.yaml`. Its evaluation uses `playwright screenshot --full-page` without an explicit viewport-size argument. Its `done` terminal can also follow score/diff plateau acceptance, so parent `on_yes` does not prove all five thresholds passed. Mandatory smoke/viewport checks still run afterward; visual quality remains best effort.

This is a file-only, self-contained HTML generator, with no server, network asset requirement, new agent, runtime Python change, or `html-anything` routing change. Geometry covers initial rendered layouts and bounded internal-scroll probes, not clicks/opened interaction states, continuous animation, general occlusion, or an accessibility audit. Rectangular overflow clipping is covered; arbitrary rotated/3D clips, clip-path/masks, and shadow-DOM control traversal are outside v1. Control checks conservatively use one `getBoundingClientRect()` union box: a wrapped inline link taller than its scrollport may fail even when its individual text fragments are reachable. Per-fragment reachability is outside v1; report this as a bounding-box violation rather than proof that all linked text is inaccessible. The unchanged oracle still scores a single full-page screenshot; optional vision uses one fresh wrapper-owned viewport screenshot, not multi-viewport vision. Neither exposes every CSS-clipped/internal-pane detail.

### Review Findings (2026-10-07)

Inspected branch: `main`; worktree: repository root. Independent code/FSM/integration reviews and real Chromium probes identified these remaining gaps:

- **Scrollability is not reachability**: a negative-position control inside `overflow: auto` had no reachable scroll offset; a viewport-fixed control did not move when its DOM ancestor scrolled. Conversely, a valid long list inside a fitting scroll pane was initially clipped by root `overflow: hidden` but reachable by internal scrolling. Exemptions must establish reachable positions and evaluate the qualifying scrollport through outer clips, rather than exempting all descendants or comparing every initial control box to every ancestor.
- **CSS clipping differs from DOM ancestry**: fixed controls and absolutely positioned controls with an outside containing block can escape an ancestor's overflow clip. A bordered clipping pane can hide a control that fits its outer border box. Use the applicable CSS clipping/containing-block chain and client scrollport bounds. See [CSS overflow clipping](https://www.w3.org/TR/CSS2/visufx.html#overflow-clipping) and [scrollports](https://www.w3.org/TR/css-overflow-3/#scrollport).
- **Invalid generated markup is an artifact failure**: Chromium returned `document.scrollingElement == null` for a quirks-mode page with root overflow hiding. Standards-mode/root preconditions must produce retryable feedback, rather than an accidental dereference crash classified as a harness fault.
- **Root size can hide body overflow**: at 800x600, `html, body { height: 100%; overflow: hidden }` with 1200px body content produced root scroll/client height 600/600 but body height 1200/600. Add a body extent check on hidden/clip axes. Nonmobile Chromium resizing also produces the requested dimensions without a viewport meta tag; check `width=device-width` explicitly rather than claiming mobile emulation.
- **Vision parser/counters cannot be copied unchanged**: the website wrapper accepts empty/incomplete score maps, while its broad counter-read exception resets corruption to zero. Require complete finite score validation and missing-file-only counter initialization.
- **Anchors alone do not protect status routing**: multiline page-error/control-label diagnostics can contain standalone success tokens; `evaluate_output_contains()` prioritizes its main match over `error_patterns`. Escape diagnostics to one line and reserve trusted status lines for measured outcomes after persistence.
- **Unfit must survive completion rendering**: ordinary nonverbose runs hide per-state stdout and the CLI completion tail prints the terminal name. `FSMExecutor.run()` recognizes normal terminals before executing their actions. Add `finalize` and `done_viewport_unfit`, rather than a terminal summary action.
- **Optional vision can receive a stale oracle image**: screenshot failure can flow through a skipped score to plateau acceptance. Capture a separate first-viewport image in the wrapper gate and bind its provenance to the report; leave the oracle image untouched.
- **Prior confidence scores predated these contracts**: removed the stale score fields. Reassess readiness after the learning-proof refresh and implementation-plan validation.

Browser evidence: Node v26.0.0, Node `@playwright/test` 1.60.0, Chromium 148.0.7778.96. These targeted probes establish the counterexamples, not correctness of the future shipped gate.

Follow-up review findings:

- **Smoke exhaustion needs explicit token routing**: the copied evaluator returns `error` for escaped one-line page diagnostics containing the substring `SMOKE_EXHAUSTED`; `error_patterns` is not a regex. Replace it with `classify, line: last` and explicit pass/retry/exhausted/fallback routes. Send diagnostics to stderr/report/critique, with no `2>&1`, and reserve stdout for gate-owned tokens. An actual copied-evaluator probe confirmed diagnostic text → `error`, `SMOKE_RETRY` → `no`, `SMOKE_PASS` → `yes`.
- **Engine limits differ from failure routes**: the overall deadline finishes with `terminated_by="timeout"`; it does not guarantee the YAML `failed` terminal. Engine transient recovery can also reexecute parent states and consume steps beyond the ordinary 32-execution artifact graph. Preserve runtime scope and document/test both distinctions.
- **Inert drawers still affect extents**: an absolute inert drawer at `left: 100%` produced body width 1000/800 at an 800x600 viewport while the root fit. Preserve unconditional extent checks and constrain permitted drawer placement; do not add an active-content attribution algorithm. A fitting internal scroll pane and fitting fixed/negative-placement drawer alternatives retained 800/600 extents.
- **Editing-host selection was incomplete**: empty-value and `plaintext-only` editable hosts remained outside a clipped pane while the literal `[contenteditable="true"]` selector found neither. Use effective editing hosts and `isContentEditable`; include case variants. See [HTML editing states](https://html.spec.whatwg.org/multipage/interaction.html#contenteditable).
- **Conservative geometry needs an explicit limit**: a five-line link had a 138px union box inside a 60px scrollport, although each 18px fragment was revealable. Keep union-box checking and document the conservative result rather than adding fragment traversal.
- **Integration checks need concrete coverage**: require Bash 3.2/BSD/GNU portability and actual module-discovery paths. The existing portability corpus scans tracked files, so directly scan the new YAML during development. Record the Node package/browser actually resolved by the action; the generic Playwright proof tracks Python metadata.

## Program Design

### Types

- Parent context: existing `description`, `pass_threshold`, `design_tokens_context`, `design_guidance_context`, plus `viewports: str`, default `"1440x900 1024x768 375x667"`. Initial shell state `validate_context` parses whitespace-separated lowercase `WxH`; dimensions are positive integers at most 8192. Warn/skip malformed, zero, or oversized entries; zero valid sizes is a harness fault. Preserve valid input order and persist normalized `settings.json` before planning. Prompts/gates use that same normalized list. `viewports` remains parent context, not an undeclared oracle `with:` key. Example: `--context 'viewports=800x600 375x667'`.
- `pass_threshold`: finite numeric value in [1, 10], with numeric CLI context text supported. Reject booleans, nonnumeric/nonfinite values, and out-of-range values before generation; never silently fall back. Freeze the normalized value/list for this run, including resume, so later raw context overrides cannot bypass validation. Shell input bindings use `:shell`; embedded scripts read environment data.
- `viewport-report.json`: `schema_version: 1`, `artifact_sha256`, `status` (`VIEWPORT_PASS`, `VIEWPORT_RETRY`, `VIEWPORT_UNFIT`), `refine_rounds`, `retry_cap: 3`, `runtime` (Node, Node Playwright package, Chromium versions), `vision_screenshot` (relative path, PNG hash, capture viewport, or null with an unavailable reason), and `viewports`. Every valid size records requested/window/document/body dimensions, excess before tolerance, artifact-precondition failures, total control-violation count, and the first 20 bounded control details (identifier, box, applicable clip/axis, reason). Limit each identifying text/message to 200 characters; retain total counts.
- Persistent counters: `.viewport_rounds` and `.vision_rounds` are integer refinement counts in [0, 3]; `.smoke_rounds` is an integer failed-check count in [0, 3]. Store one decimal digit with optional surrounding whitespace; validate trimmed text before numeric conversion. Initialize only a genuinely absent file to zero. Existing empty/whitespace-only files, other malformed text, unreadable files, negative counts, and out-of-range counts are harness faults; `Number("")` must not replenish the budget. Never reset on success, regeneration, skip, or resume.
- Budget: the ordinary artifact-routing graph requires at most **32 nonterminal parent executions**, excluding engine transient recovery: `1 validate_context + 1 plan + 9 run_gen_eval + 9 smoke_test + 7 viewport_gate + 4 vision_gate + 1 finalize`. Equivalently, initial 7 executions + `3×3` viewport refinements + `3×4` vision refinements + `2×2` smoke retries. The engine checks `max_steps` before terminal recognition: minimum 33; set `max_steps: 34` for one-step margin. Keep loop `timeout: 7200`; child steps are separate and child timeout is clamped to remaining parent time. Time exhaustion or extra engine transient retries can hit overall caps before all permitted artifact refinements complete. All configured viewports share the 120-second gate deadline; unusually large valid viewport lists can exhaust it.

### Signatures

- `cmd_validate(loop_name: str, args: argparse.Namespace, loops_dir: Path, logger: Logger) -> int` — existing validation entry.
- `test_expected_loops_exist() -> None` — extend existing exact inventory.
- New tests execute the shipped rendered actions through actual evaluator/FSM routing, with stubs for deterministic orchestration and real Chromium for DOM geometry.

### Call Path

Existing discovery/validation/execution requires no runtime code changes:

`resolve_loop_path()` → `load_and_validate()` → `FSMExecutor._execute_state()` / `_execute_sub_loop()` → rendered shell action → evaluator → retry, finalization, or failure terminal.

### Decision Rules

**Measurement and controls**

- Use fresh isolated browser contexts/pages per configured viewport, set the viewport before navigation, and wait for page load, `document.fonts.ready`, then two animation frames. Bound each wait and set viewport state `timeout: 120` for the entire action; give smoke its own explicit `timeout: 120`. Browser/context cleanup and scroll restoration run in `finally` on normal and handled-exception paths, including navigation/readiness/evaluation failure. Leave deadline headroom for cleanup; a hard action timeout uses the existing runner's process-group termination and cannot promise that in-script `finally` executes. Unrecovered runtime/browser/file/persistence faults and action timeouts follow `failed` routes, subject to engine transient recovery and overall limits. Overall timeout/step exhaustion is a separate non-success engine result.
- Use Node `pathToFileURL()` for Node-gate navigation to `index.html`, not raw `'file://' + path`. First attempt module resolution with the inherited environment and local packages; honor an existing usable `NODE_PATH` without requiring npm. Only if that lookup fails, use the documented global npm module lookup as fallback. Tests must exercise the complete rendered action's resolution, including usable `NODE_PATH`, a local package with npm absent, absent/unusable `NODE_PATH` with global fallback, missing module, and missing Chromium. Do not auto-install packages/browsers at run time. The unchanged oracle still has its own CLI/path limitations; do not promise broader whole-loop path support.
- Require `document.compatMode == 'CSS1Compat'`, a usable document scrolling element, and a viewport meta declaration containing `width=device-width` (case-insensitive name/declaration parsing). Missing prerequisites are measured artifact violations: record feedback and use the viewport refinement budget. For standards mode, document fit requires scrolling-element `scrollWidth`/`scrollHeight` ≤ `innerWidth`/`innerHeight` + **1 CSS pixel**. Also fail body extent beyond its client box on axes with computed overflow hidden/clip, which otherwise can hide long noninteractive content while the root fits. Record excess before tolerance; root/body checks stay unconditional even for hidden/inert subtrees. Body-extent failure feedback includes a fixed hint to check clipped content and off-canvas placement: `inert` does not remove overflow. These are desktop CSS viewport probes, not full mobile-device emulation.
- Inspect rendered `button`, `a[href]`, `input` except hidden inputs, `select`, `textarea`, `[role=button]`, `summary`, effective explicit editing hosts, and nonnegative `[tabindex]` controls. Select editing candidates with `[contenteditable]`, use `isContentEditable` and editing-host semantics (editable element with a noneditable parent), and cover empty, `true`, `plaintext-only`, and case variants; a literal-value selector is insufficient. Skip no-layout-box/display-none controls, computed `visibility: hidden`/`collapse`, and inert descendants. Honor a control's computed visibility, including a visible descendant of a visibility-hidden ancestor. Rendered focusable aria-hidden-only controls remain checked. Inert control exclusions do not exempt root/body extent checks.
- Apply the same 1-pixel tolerance to viewport and **applicable rectangular overflow clips**, using client/scrollport bounds excluding borders/scrollbars. DOM parentage alone does not prove an overflow clip applies; respect CSS containing-block behavior for absolute/fixed descendants. `overflow: hidden`/`clip` never supply a user-scrollability exemption, even when programmatic scrolling is possible.
- An `auto`/`scroll` exemption on an affected axis requires an actual reachable position inside that pane's client scrollport. Check the real clamped scroll range and observed control movement, including negative-side, fixed-position, and RTL cases; a matching overflow style alone cannot pass a control. Use bounded targeted scroll adjustments (at most leading/trailing-edge candidates per relevant ancestor/axis), with instant scrolling and offsets restored in `finally`; no unbounded wheel/search loop.
- Process nested reachable panes inside out. Check the qualifying pane's scrollport/projection against applicable outer non-scrollable clips and viewport, or establish reachability through outer user-scrollable panes. An initially below-fold list control is allowed inside a fitting scrollport; a genuinely off-screen/non-reachable pane or an unrelated scroller does not excuse clipping. A control must be fully revealable within the applicable scrollport; an oversized control that cannot fit fails. Large non-interactive content and ordinary vertical/horizontal internal scrolling remain allowed. Scroll-driven re-renders/virtualized content are a documented limitation of initial-layout probes.

**Persistence and status integrity**

- Hash `index.html` before and after the complete viewport measurement batch; differing hashes are a harness fault, so never publish a mixed-artifact report. On successful measurement, atomically replace the report via a same-directory temporary file. A report from an earlier generation can remain on disk during regeneration/failure; its hash makes it historical, not proof of current fit. The successful finalizer must reject a stale hash.
- Capture `viewport-screenshot.png` at the first valid viewport after readiness and before any reachability scrolling, with `fullPage: false`. Keep oracle `screenshot.png` untouched. Record capture viewport and PNG hash in the matching artifact report. Capture failure records unavailable provenance and makes optional vision skip; it cannot erase measured fit or reuse an earlier PNG. Vision validates artifact/PNG hashes and consumes only this reported image. Atomically replace successfully captured images under the run directory.
- Atomically replace counters and complete all required report/critique/counter writes before emitting any success or exhaustion token. Write failures route to `failed`, never silent acceptance. This is not a cross-file transaction: an interrupted attempt may conservatively consume a refinement, but must not reset or replenish the budget.
- Emit untrusted page-error/control-label details as escaped single-line text (for example JSON string encoding), with bounded text, to stderr/report/critique only. Reserve status-matched stdout for gate-owned routing tokens; do not merge stderr with `2>&1`. Escaping alone does not remove a literal exhaustion substring recognized by `error_patterns`. The report may retain escaped detail; only the gate emits standalone trusted routing lines.

**Routing and budgets**

- Preflight: `validate_context` writes normalized `settings.json`, emits only the canonical threshold (for example `6.5`) on stdout, warns on stderr, uses `capture: validated_threshold` and `evaluate: {type: exit_code}`, and routes success to `plan`, failure/error to `failed`. Bind oracle `with.pass_threshold` and all prompt threshold comparisons to `${captured.validated_threshold.output}`; this interpolated binding is canonical numeric text, which the existing oracle consumes in prompts. Gates read/validate `settings.json` and require its threshold to match the capture. JSON-property traversal inside a string capture is not supported. Captures persist on resume, so raw `--context pass_threshold/viewports` overrides after successful preflight are ignored; start a new run to change them. Planner/generator read the normalized list from the same harness-maintained settings file and must not modify it. Freezing raw context overrides is not tamper detection for arbitrary edits to that file.
- Viewport: exit 0 with status matched by `(?m)^VIEWPORT_(?:PASS|UNFIT)(?::[^\n]*)?$` → `on_yes: vision_gate`; retryable failure emits only `VIEWPORT_RETRY` on stdout, with escaped failure details in stderr/report/critique → `on_no: run_gen_eval`; nonzero/action timeout → `on_error: failed`, subject to engine recovery/limits. Never fabricate `VIEWPORT_PASS` on an unfit page.
- Delegation: `run_gen_eval` explicitly routes `on_yes: smoke_test`, `on_no: failed`, and `on_error: failed`; the oracle's failure/screenshot-abandon/max-steps outcomes are not accepted as fit.
- Measure on **every** viewport visit. Fit publishes `VIEWPORT_PASS` without changing the counter. Failure with viewport count < 3 increments, appends feedback, publishes `VIEWPORT_RETRY`, and requests regeneration. Failure at count 3 appends feedback, publishes/emits `VIEWPORT_UNFIT`, and advances without increment. The third failed visit requests refinement three; the fourth still-failing visit accepts best effort. Vision regeneration never resets this budget; a later repaired artifact can still pass.
- Smoke: safely inspect meaningful body text (minimum 20 trimmed characters) and uncaught page errors with normalized bounded messages. Missing/empty body or JS errors are artifact failures, not dereference crashes. Failed checks 1/2 append feedback, emit only `SMOKE_RETRY` on stdout, and regenerate; check 3 persists count 3, appends feedback, emits only `SMOKE_EXHAUSTED`, and exits 0. Successful checks emit only `SMOKE_PASS`. Use `evaluate: {type: classify, line: last}` with explicit routes `SMOKE_PASS: viewport_gate`, `SMOKE_RETRY: run_gen_eval`, `SMOKE_EXHAUSTED: failed`, `_: failed`, and `_error: failed`; do not use `error_patterns`. Emit the token only after persistence and as the absolute last stdout line. Artifact diagnostics remain on stderr/report/critique so literal exhaustion text cannot consume retries early. An exhausted resumed count cannot request another regeneration. Passes never reset the failed-check count; infrastructure/persistence failures exit nonzero. All regeneration paths replace the current artifact; no best-artifact retention is promised if a later generation exhausts smoke.
- Vision: validate its counter/settings before early skip paths; declare state `timeout: 180` around the existing bounded API request. Retain the optional three-refinement cap and fail-soft behavior for absent configuration, unavailable/stale gate image, network/API errors, or invalid response. A valid response contains all five named scores as finite non-boolean numbers in [0, 10] and an `issues` list of strings. Missing/wrong-type/nonfinite/out-of-range scores do not become a scored pass. Emit distinct anchored tokens `VISION_PASS` (real scored pass), `VISION_SKIPPED: <escaped reason>`, and `VISION_CAPPED`, accepting `(?m)^VISION_(?:PASS|SKIPPED|CAPPED)(?::[^\n]*)?$`; none consume a new refinement. A valid below-threshold score appends feedback, increments the counter, and regenerates without an acceptance token. Counter/feedback I/O faults are harness errors, not optional-service failures. Vision cannot override the viewport report.
- Finalize: use a nonterminal shell action to validate schema, allowed status, current artifact hash, and report/counter consistency. Permit only measured `VIEWPORT_PASS` or `VIEWPORT_UNFIT`; missing/invalid/stale/`VIEWPORT_RETRY` reports fail. Emit only the trusted status on the final stdout line, with `evaluate: {type: classify, line: last}` and explicit routes `VIEWPORT_PASS: done`, `VIEWPORT_UNFIT: done_viewport_unfit`, `_: failed`, `_error: failed`. Both success terminals have `terminal: true` and no failure flag; `failed` has `terminal: true, failure: true`. Normal terminal action bodies are not used for finalization. Overall engine timeout/step exhaustion may leave only a historical or `VIEWPORT_RETRY` report; it does not guarantee finalization, and no report alone converts an interrupted run to success.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/html-webapp-generator.yaml` (new file) — `category: harness`, `input_key: description`, required description, run-directory scope, `artifact_versioning_ok: true`.
- `scripts/tests/test_builtin_loops.py` — exact expected-loop inventory and structure checks near `TestHtmlWebsiteGeneratorLoop`.
- `scripts/tests/test_html_webapp_generator.py` (new file) — rendered-action, evaluator/FSM, real-browser, and direct new-YAML portability checks.
- `scripts/little_loops/loops/README.md` — add catalog row alongside `html-website-generator`; extend generator-evaluator consumer list.
- `README.md` — increment the current runnable-loop count obtained from `verify_documentation()`; no invented README catalog/list.
- `scripts/README.md` — byte-identical mirror of root README.
- `docs/guides/LOOPS_REFERENCE.md` — catalog, chooser, new per-loop section modeled on `### html-website-generator`, and oracle/fragment consumer lists.
- `docs/reference/loops.md` — generator-evaluator "Used by" list; there is no existing per-loop website-generator section to insert beside.
- `docs/generalized-fsm-loop.md` — correct `design_guidance_context` "Consumed only by" claim.
- Optional: `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — real-world generator-evaluator examples.

### Dependent Files and Similar Patterns

- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — consumed read-only. Its description's consumer enumeration may remain incomplete because this issue freezes the shared file.
- `little_loops.fsm.loop_paths::{get_builtin_loops_dir, resolve_loop_path}` and `scripts/little_loops/cli/loop/info.py::enumerate_loop_catalog` — automatic discovery; no registration.
- `scripts/pyproject.toml` — existing `little_loops/**` package-data glob ships the YAML; no packaging edit or new dependency pin.
- `scripts/little_loops/doc_counts.py::verify_documentation` — count enforcement used by docs/doctor/drift checks; no source edits.
- `html-website-generator` — wrapper/feedback pattern only; do not copy its raw shell interpolation, incomplete vision validation, threshold contradictions, or unlimited smoke retries.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml::aggregate` — explicit `classify` token routing with fallback/error routes.
- `scripts/tests/test_flux_image_generator.py` and `scripts/tests/test_rlhf_svg_evaluate_smoke.py` — tests of actual shipped/rendered actions rather than parallel logic.
- `scripts/tests/test_portability_gate.py::scan_portability` — reuse its Bash 3.2/BSD/GNU rules in a direct new-YAML check. Its corpus uses tracked-file discovery, which omits an untracked new loop during development; no portability-gate source edit is required.

### Tests and Documentation Contracts

Existing automatic gates must pass without new baseline/allowlist exceptions: builtin discovery/YAML validation, reachability/failure-terminal routing, gate completeness, no bare `PASS`, shell interpolation, MR-11, scope/artifact-versioning warning budget, `TestInterpSweepBaseline`, Bash 3.2/BSD/GNU portability, documentation counts, README mirror, and audience/hardcode gates. Directly scan the new YAML with the existing portability helper so an unstaged file cannot evade that check. Keep `scripts/tests/data/loop_interpolation_baseline.json` unchanged; hand paths into embedded scripts through environment data.

New tests execute the shipped FSM-rendered shell actions and actual evaluator. Mandatory deterministic cases cover parsing before model calls, frozen normalized settings on resume, malformed counters (including existing empty/whitespace files), persistence failures, report/hash/image consistency, escaped diagnostic tokens, complete/invalid vision verdicts, threshold overrides, and final-disposition routing. A smoke page-error message containing literal `SMOKE_EXHAUSTED` must still request the first two retries, and an injected newline plus `SMOKE_PASS` must never pass. Exercise the complete module-discovery shell action through inherited `NODE_PATH`, local lookup without npm, global fallback, and missing module/browser fault cases. Stub orchestration proves fail → feedback → repaired artifact → pass, viewport cap with vision skipped, vision regeneration after viewport exhaustion, cumulative smoke exhaustion, and the 32-execution ordinary artifact-route bound. Separate engine fixtures verify overall timeout/step exhaustion remains non-success without requiring a YAML `failed` terminal, and a transient reentry consumes extra parent steps.

Real Chromium fixtures cover document overflow on both axes, combined root/body overflow hiding, quirks mode/missing viewport meta, valid vertical/horizontal/nested scrolling, negative unreachable/fixed controls, RTL scroll range, outer/cross-axis clipping, border/client bounds, CSS containing-block escape, oversized controls, and non-rendered/inert versus aria-hidden-only controls. Include empty/true/plaintext-only/case-variant editing hosts, a fitting closed drawer, an inert drawer that enlarges body extents, and a wrapped-link union-box violation proving the documented conservative behavior. Verify screenshot capture at the first viewport before scrolling and no stale image reuse after failure. Tests must run the actual geometry callback, not canned `page.evaluate()` answers. Browser-only cases may skip clearly if Node/module/Chromium is absent; do not skip when dependencies are present but geometry/assertions fail. Use subprocess timeouts and existing `tests.helpers.require_node()` conventions; deterministic evaluator/FSM tests stay browser independent.

User docs must specify Node, a resolvable Node `@playwright/test` module, its matching installed Chromium, npm if global module discovery is used, and the Playwright CLI required by the unchanged oracle. Python-only Playwright installation does not satisfy Node-gate prerequisites. Explain supported module resolution, viewport/threshold overrides and frozen resume settings, tolerance, bounded scroll probes, caps, optional vision skip versus scored pass, latest report/hash/runtime, the first-viewport vision image, `done_viewport_unfit`, and screenshot/initial-layout limitations. Explain inert versus root/body extent checks, conservative wrapped-link bounding boxes, the shared viewport deadline, and engine timeout/step exhaustion versus the failure terminal; extra transient retries may exhaust the overall budget. Quiet mode suppresses the normal completion line; the durable report remains available.

### Learning Proof and Prior Evidence

`ll-learning-tests assess --issue FEAT-3589 --json` on 2026-10-07 reports `playwright=proven`, `node=stale` (60 days), reconfirmed during follow-up review. Keep the declared targets and refresh stale proof before implementation. The current Playwright record includes Node screenshot/error handling assertions but has Python package metadata; its `proven` result cannot detect drift in Node `@playwright/test` and does not prove the new geometry algorithm. Refresh evidence using the Node module/Chromium actually resolved by the rendered action and record their versions; do not expand the learning-registry runtime in this issue.

The 2026-09-25 consumer-project prototype validated and completed a first-try kanban run in 11m37s at the default sizes. It used an earlier budget and drawer exemption. The 2026-10-05 review subsequently strengthened ancestor clipping, inert/aria-hidden handling, global caps, report identity, smoke exhaustion, and oracle plateau disclosure. Treat the prototype as historical feasibility evidence, not proof of the strengthened contract or retry paths. The earlier 30-execution/32-step budget is superseded by preflight/finalization's 32-execution/34-step contract above. The prototype's no-scope warning came from the unchanged oracle.

Temporary actual-FSM/ordinary-CLI fixtures on 2026-10-07 verified fit and unfit terminal names with exit 0, invalid/stale reports reaching the failure terminal with CLI exit 2, and a restored numeric threshold capture surviving a conflicting raw resume override. A scripted oracle fixture reproduced stale screenshot → skipped score → plateau `done`. The nested-FSM route budget was checked before adding the one preflight execution. These prove engine contracts, not the future shipped loop.

The 2026-10-05 Opus consult could not run because its per-task budget was exhausted. The 2026-10-07 `/ll:advise` consult (`user_requested`, `claude-code`, `claude-opus-5-5`) succeeded with confidence 0.8: retain standalone YAML/shared-oracle scope, tighten reachability, preconditions, settings, persistence, diagnostic tokens, and vision validity/freshness. Main risks were CSS containing-block handling and scroll-driven re-renders. Its dissent favored documenting some geometry/freshness limits to keep scope small. Keep timeout-as-harness-fault and malformed-viewport warn/skip behavior from the existing issue; normalized settings remove planner/gate drift without reversing that product contract. Permit score 0 on the oracle's 0–10 scale, while thresholds remain [1, 10].

A follow-up `/ll:advise` consult on 2026-10-07 (`user_requested`, `claude-code`, `opus`) also succeeded, confidence 0.8: all supplied corrections were justified and no structural blocker remained. Adopt explicit smoke classification, preserve both-axis body checks with narrower drawer guidance, distinguish engine endings, and make portability/module-resolution evidence concrete. Add fixed feedback guidance to body-extent failures: check clipped content and off-canvas placement; `inert` does not remove overflow. Fixed drawers can acquire ancestor containing blocks, so actual extent measurements remain authoritative. Main residual risks are conservative unfit results, replacing an earlier good artifact during later refinements, and interrupted reports. Its dissent proposed a vertical-only body check but rejected that alternative because horizontally clipped noninteractive content could silently pass; keep both axes and avoid attribution/retention feature expansion. Direct new-YAML portability scanning avoids relying on staging solely to make the corpus discover it.

## Implementation Steps

1. Refresh learning proof and validate the plan against the measured counterexamples, including drawer extents, editable hosts, and conservative wrapped-link bounds. Establish real-browser fixture coverage of the bounded clipping/reachability contract while building the actual shipped gate; do not treat generic Playwright proof as geometry validation.
2. Add the standalone YAML with app-shell brief/prompt, all-five rubric/threshold contracts, feedback consumption, quoted environment-driven scripts, explicit failure terminal, and final-disposition state. Keep the shared oracle unchanged.
3. Implement pre-generation configuration validation, measured artifact preconditions, geometry/reachability, atomic report/counter/image publication, safe diagnostics, smoke/vision validation, and global caps. Use `max_steps: 34`, loop `timeout: 7200`, smoke/viewport `timeout: 120`, and vision `timeout: 180`.
4. Pass existing corpus/interpolation/warning/portability ratchets without exceptions; directly scan the new YAML during development and keep all generated files and temporary persistence files under `${context.run_dir}`.
5. Update catalogs/counts/docs and README mirror with the documented prerequisites, measured status, distinct completion terminals, and limits.
6. Run new structure/rendered-action/browser/FSM tests and the authoritative local suite (`python -m pytest scripts/tests/`). A manual model-backed run is supplementary; record its runtime versions and report. A first-try pass does not establish regeneration correctness.

## Impact

- **Priority**: P3 — additive generator variant for HTML artifact workflows.
- **Effort**: Large — one loop YAML, but bounded nested CSS clipping/reachability and the rendered-action/FSM/fault test matrix are substantial. Geometry is the primary implementation uncertainty; no runtime Python source changes.
- **Risk**: Moderate — CSS clipping/reachability and persistence/routing semantics require behavioral tests; existing consumers and shared oracle are outside the change.
- **Breaking Change**: No.

## Use Case

A user runs `ll-loop run html-webapp-generator "kanban board for a 4-person team"`. The app fills the browser window and scrolls long lists inside panes at all default sizes. `viewport-report.json` records measured fit or remaining violations. Best-effort acceptance ends at `done_viewport_unfit`, so ordinary completion does not imply a fitting page.

## API/Interface

New loop `html-webapp-generator`, required `description`, with optional parent context values `viewports` and `pass_threshold`. Existing runner-injected design tokens/guidance are preserved. No new `.ll/ll-config.json` setting or classifier type.

## Open Questions

No unresolved product decision. Keep 375x667 in the gate with responsive collapse; cap exhaustion accepts the measured artifact as best effort. The concrete implementation and tests must establish the bounded CSS/reachability rules rather than relaxing them to mere scrollable ancestry.

## Acceptance Criteria

- [ ] New YAML ships/discovers automatically, validates, and passes existing inventory/interpolation/warning/portability/count/mirror/audience gates without ratchet exceptions; direct portability scanning covers the new YAML before staging; shared oracle unchanged.
- [ ] Planner/generator receive configured viewport settings and require standards mode, mobile viewport meta, responsive app shell, reachable internal panes, and visually closed/unfocusable drawers.
- [ ] Actual browser fixtures prove document/body overflow and doctype/meta precondition failures retry; legitimate vertical/horizontal/nested scrolling passes; unreachable negative/fixed controls, outer/cross-axis/client-edge clipping, and oversized controls fail. Applicable containing-block escape and RTL reachability behave correctly.
- [ ] Visibility handling distinguishes non-rendered/inert controls from rendered aria-hidden-only controls; root/body overflow measurements stay unconditional. Empty/true/plaintext-only/case-variant editing hosts are checked. Fixtures prove inert drawer extents are not exempt and pin conservative wrapped-link union-box behavior.
- [ ] Fresh pages are sized before navigation; load/font/frame/probe waits and resources are bounded, and scroll offsets/browser resources are restored/closed on normal and handled-exception paths. Hard action timeout uses existing process-group termination.
- [ ] Settings validate before model calls: viewport parsing warns/skips invalid entries; zero valid sizes or invalid threshold is a configuration fault. Normalized settings remain consistent across prompts/gates and resume. Missing runtime/browser/files, corrupt/unreadable/empty counters, changed measured artifact, and write failures follow `failed` routes subject to existing engine recovery/limits. Tests distinguish action timeout from overall engine timeout/step exhaustion, which must remain non-success.
- [ ] Global viewport refinements are at most three, never reset; exhausted gates remeasure and publish honest `VIEWPORT_UNFIT`, while later repairs publish `VIEWPORT_PASS`.
- [ ] Atomic reports contain matching artifact hash, disposition, count, runtime, all valid viewport measurements, total violations, and bounded details. Hash-changing batches cannot publish or pass; stale reports cannot finalize. Optional vision uses only the matching first-viewport screenshot, captured before scroll probes; image failure/staleness skips explicitly without hiding geometry results.
- [ ] All artifact diagnostics are escaped and bounded on stderr/report/critique; stdout contains only trusted routing tokens. Injected newline/status tokens cannot cause false acceptance, and literal `SMOKE_EXHAUSTED` in a page error cannot exhaust the first two retries.
- [ ] Smoke classifies only its final trusted pass/retry/exhaustion token with explicit fallback/error routes. Failures 1/2 append feedback and retry; failure 3 explicitly exhausts to `failed`. Counts survive passes/regeneration/resume and cannot reset from file corruption.
- [ ] Both rubrics score all five criteria with a valid overridden threshold. Vision rejects malformed/incomplete score schemas as explicit fail-soft skips; valid low `layout_fit` requests bounded refinement. Persistence faults are not masked as optional-service failures.
- [ ] Finalize verifies current report/schema/hash/counters and routes fit to `done`, unfit to nonfailure `done_viewport_unfit`, all invalid outcomes to `failed`. Ordinary nonverbose completion identifies best-effort acceptance; no normal-terminal action is relied upon.
- [ ] Deterministic FSM tests prove feedback/regeneration, viewport cap with skipped vision, vision regeneration after exhaustion, smoke exhaustion/resume, and the 32-execution ordinary artifact path with terminal recognition at `max_steps: 34`. Engine transient reentries consume additional steps rather than replenishing budgets.
- [ ] Tests prove inherited/local/global Node-module discovery and missing-runtime failure paths. Docs state runnable Node/module/browser/CLI prerequisites, supported resolution, overrides, tolerance, caps, optional vision, report/completion semantics, conservative geometry/screenshot limits, and no best-artifact retention after later failures.
- [ ] Learning proof is refreshed before implementation; real-browser evidence names actual runtime versions; `python -m pytest scripts/tests/` passes after implementation.

## Related Key Documentation

`docs/guides/LOOPS_REFERENCE.md`, `docs/reference/loops.md`, and `scripts/little_loops/loops/README.md`.

## Status

**Open** | Created: 2026-09-25 | Priority: P3

## Session Log
- Pre-implementation review — 2026-10-07 — consolidated contract; corrected reachability/clipping, root/body and doctype/meta checks, preflight settings, verdicts/counters/report/image integrity, diagnostic routing, unfit completion, and 32-execution/34-step budget. Opus consult succeeded (confidence 0.8).
- Follow-up pre-implementation review — 2026-10-07 — fixed smoke token classification, editable-host coverage, drawer/body contract, timeout/step and cleanup semantics, counter grammar, portability/module-resolution evidence, and conservative geometry limits; raised effort to Large. Opus consult found no structural blocker (confidence 0.8); stale Node proof still requires refresh before implementation.
- `/ll:refine-issue` - 2026-10-05T20:23:40 - `e4d031f4-efb7-4acd-b532-6b7d02eab780.jsonl`
- proof-run findings fold-in (consumer-project prototype: e2e kanban run passed first try in 11m37s; max_steps 28 / timeout 7200 budget correction, off-screen-drawer gate exclusion, `${context.viewports:shell}`, heredoc gate delivery, oracle scope-warning attribution) - 2026-09-25
- `/ll:confidence-check` - 2026-09-26T00:19:46 - `3ba6a46a-761b-4ab5-89c0-ab0b42db6625.jsonl`
- `/ll:verify-issues` - 2026-09-26T00:12:27 - `98da18e9-798f-4617-bd29-6f3941aca3ff.jsonl`
- pre-implementation review fold-in (Claude review: resolved open questions, max_steps budget, prompt/rubric/AC gaps) - 2026-09-25
- `/ll:confidence-check` - 2026-09-25T23:27:42 - `d6bd211f-c643-48aa-aeac-10c8d9198fcd.jsonl`
- `/ll:wire-issue` - 2026-09-25T23:21:15 - `6f19f2e8-c7f6-4ad5-9b57-752e049be6a9.jsonl`
- `/ll:refine-issue` - 2026-09-25T23:01:04 - `3a51f6da-0505-450c-a253-261a60c5053b.jsonl`
- `/ll:format-issue` - 2026-09-25T22:12:18 - `8c81fde2-1b8f-4d35-a9d4-d9e034fb1af8.jsonl`
- `/ll:capture-issue` - 2026-09-25T02:02:39 - `09b7cc1a-1227-48d7-9d78-dac3ced876ba.jsonl`
