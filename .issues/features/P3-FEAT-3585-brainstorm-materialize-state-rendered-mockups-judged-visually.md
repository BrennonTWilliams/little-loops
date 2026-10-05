---
id: FEAT-3585
type: FEAT
title: 'Brainstorm materialize state: rendered mockups judged visually'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3687
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
- FEAT-3583
- FEAT-3667
learning_tests_required:
- playwright
reconcile_attempted: true
---

# FEAT-3585: Brainstorm materialize state: rendered mockups judged visually

## Summary

Add profile-gated visual materialize: author bounded standalone HTML/SVG mockups for surviving finalists, capture PNGs with optional Playwright, and use image judging when its capability check passes. HTML-source judging is the fallback only for candidates with valid authored source. No mid-tournament restart.

## Current Behavior

The core visual preset changes axes/lenses/rubric but judges text. It cannot compare rendered directions. The Playwright screenshot/route-abort learning claims were recorded on 2026-09-29 (node @playwright/test 1.60.0); the learning registry's Python proven_version is not the node version.

## Expected Behavior

- After generation floors, materialize_author makes one call and writes one self-contained HTML/SVG per current finalist under run_dir/mockups/<id>.html. Allow at most 4 KB and about 120 lines per source; inline CSS/SVG, no authored JavaScript, external assets or fonts. Read finalists.json/ideas.jsonl under scope to obtain the finalist set (no additional block state). The author has Read/Write tools scoped to the run artifacts, next/on_error and a finite timeout.
- materialize_render is one packaged inline node state, resolving Playwright via the existing LL_PLAYWRIGHT_ROOT / NODE_PATH / global npm convention. It checks source presence, size and in-run path before rendering. Fixed viewport, device scale, screenshot readiness and per-file deadline make results comparable and bound the state. Close pages/browser in finally.
- Missing/empty/oversized/unsafe mockup **source** is an artifact failure: exclude that candidate from both image and HTML judging and record a reason. A source-valid candidate with failed PNG capture may still be judged as HTML.
- Image mode requires at least two successfully rendered PNGs and a successful canary. With those prerequisites, select rendered candidates and drop source-valid render failures. If fewer than two PNGs exist, Playwright/node/browser is unavailable, or the canary fails, judge **all source-valid candidates** from HTML; restore source-valid render failures to eligibility, but never restore invalid/missing source. Fewer than two source-valid candidates fails pre_tournament floors, before any judge or sink. Compute this final set in one deterministic materialize-check operation; do not incrementally drop/restore IDs according to loop order.
- The renderer produces a control PNG with a random code. visual_canary is one Read-only prompt call reading that PNG; expected code is absent from its prompt and durable metadata stores only its SHA-256 digest. Renderer unavailability or absent control bypasses the canary and goes directly to materialize_check. Canary host error/timeout or mismatch also reaches materialize_check for HTML fallback. Malformed artifact results can degrade; a deterministic engine/I/O failure fails the run.
- Stamp each captured PNG after rendering by compositing in Playwright: screenshot the authored JS-disabled page, then setContent of a renderer-generated static wrapper in a fresh JS-disabled context (data-URI image of that capture plus a positioned text overlay) and capture the final PNG at the same viewport/device scale. The wrapper lives in memory and is never an authored HTML file; use escaped renderer-owned text, allow only inline/data resources, and do not log its code or markup. This uses the existing Playwright dependency and needs learning evidence for dimensions, visible stamp and JS-disabled behavior. Image verdicts echo both codes in presentation order as seen:[codeA,codeB]. record-round hashes echoed codes and compares with materialize.json code_sha256; missing/wrong proof is an abstention. Engine blocks expose selected asset paths and idea data, **never expected codes**. Judges/canary are instructed to read only the selected image/source files, never materialize.json, logs or code metadata. Digest-only expected metadata prevents a direct plaintext-metadata echo, but captured model answers can still reveal echoed codes and Read tools do not isolate artifact paths. Codes remain a capability sanity signal, not proof of design quality or an adversarial security boundary.
- Rendering uses a browser context with authored JavaScript disabled. Permit only the selected mockup document; abort network requests and other file: subrequests (inline CSS/SVG/data content is allowed). Verify document paths resolve inside the mockups directory, including symlinks. The prior blanket allowance of every file: request is insufficient. The loop does not depend on .loops/probes/ or machine-specific package paths.
- Round/probe prompts switch on finalists.json judge_mode and explicitly Read PNGs (image) or HTML paths (html), without inlining source into argv. Presentation order, batched rounds, reversed probe, scores and abstention thresholds remain the core tournament contract. Wrong codes never trigger a schedule restart.
- finalists.json judge_mode remains **text|image|html**. materialize.json is the committed manifest: {input_digest, judge_mode, degradation_reasons:[str], assets:{id:{html,png?,status,source_sha256?,png_sha256?,code_sha256?}}, canary:{expected_sha256?,passed?}}; status is source_invalid|render_failed|rendered, and reasons distinguish no_playwright, canary_failed, canary_error and render_floor. Persist no plaintext expected code in manifest, filenames, generated wrapper files or logs; raw model answers are untrusted echoes, not expected metadata. Do not substitute html_no_playwright into the canonical judge_mode enum. Paths must be validated against the run dir; judges see a redacted asset projection, without digest/control metadata.
- The deterministic render-report command adds a gallery and degradation notes. A successful HTML-only run shows source links and honestly states there are no images for the missing PNGs.

## Use Case

A user compares visual directions from actual mockups. Where image consumption is unavailable, the report visibly records HTML-source judging; an unauthored design cannot win through fallback.

## Motivation

Render validity, visual capability and idea quality are different checks. A capability canary plus explicit source-valid fallback avoids both silent text-only judging and phantom candidates with missing artifacts.

## Proposed Solution

Four additional parent states: materialize_author -> materialize_render -> visual_canary (when available) -> materialize_check. The existing generation-floor shell command creates/verifies materialize_input.json after its checks and before printing its routing token; no prompt state is asked to run deterministic setup. A committed manifest emits the added materialize_check token, explicitly routed straight to that existing state to verify/replay the finalist projection, bypassing author/render/canary with no extra gate state. All artifact validation, canary comparison, fallback selection and finalist-file rewrites live in brainstorm_engine; only browser capture/compositing stays JS in a packaged loop action. The two existing floor states are already counted and are not additional materialize visits. If reference authoring truncates at eight candidates, record the failure and deliberately change to two batches with the corresponding step/call/time update; do not add an unbounded retry loop.

## Program Design

### Types

- MockupResult: {idea_id: str, html_path: str, png_path: str | null, source_valid: bool, rendered: bool, reason: str | null}.
- MaterializeResult: {input_digest: str, judge_mode: "image" | "html", degradation_reasons: list[str], assets: dict, canary: dict}; only SHA-256 expected-code digests remain engine/renderer metadata.

### Signatures

- check_visual_canary(expected_sha256: str, answer: str) -> bool — hash the stripped echoed answer and compare digests deterministically.
- apply_materialize(finalists: FinalistsFile, results: list[MockupResult], canary_passed: bool) -> FinalistsFile — deterministic whole-set eligibility/fallback decision.
- validate_mockup_path(path: Path, run_dir: Path) -> bool — in-run source validation, including symlinks.

CLI materialize-check --run-dir DIR --render-file F --canary-file F [--canary-error REASON] reads materialize_input/ideas/profile and staging results, commits materialize.json before its atomic finalists.json projection; exit 0 for a completed fallback/selection, exit 2 for engine failure. Source-count insufficiency is recorded and the existing pre_tournament floor fails it. Missing files caused by host author/render errors are classified explicitly, never mistaken for corrupt successful JSON. Use the real LL_PYTHON invocation in YAML.

### Call Path

shortlist_apply -> check_floors (generation) -> materialize_author -> materialize_render -> [visual_canary] -> materialize_check -> check_floors_pre_tournament -> tournament -> portfolio -> render_report -> validate_portfolio

Author error routes to materialize_check with available sources and error status; render error bypasses canary; canary error reaches materialize_check. Fewer than two valid sources still fails pre_tournament floors; do not silently switch to text judging or let an unauthored candidate win.

Before authoring, persist materialize_input.json containing the original shortlist's ordered finalists, prior dropped IDs and an input digest. This is the candidate universe for the entire operation, never the already-filtered finalists.json. Whole-set selection distinguishes source_invalid (ineligible in both modes) from render_failed (source valid, eligible only in HTML fallback). Grounded-false and prior shortlist-dropped IDs cannot enter this snapshot. Compute the final set before publishing it; the existing no-promotion v1 contract stays intact.

materialize-check commits materialize.json once, then atomically projects its selected eligible IDs/assets into finalists.json. If interrupted between these replacements, replay verifies the snapshot/manifest and source/PNG hashes and regenerates only the missing finalist projection. A completed manifest is reused without authoring, rendering or canary calls, so codes and judging inputs cannot change under committed verdicts. Changed input/source/image hashes fail explicitly; they do not silently re-render or degrade. An interrupted operation with no committed manifest or verdicts may regenerate its staging artifacts. The core judging-input digest includes the committed manifest and asset hashes (FEAT-3667); next-round/probe-plan/record-round verify them. Separate replacements are not a multi-file transaction.

## Integration Map

### Behavior Parity

| Artifact | Behavior | Disposition |
|---|---|---|
| brainstorm.yaml | materialize=none | Preserved; zero added visits |
| brainstorm-tournament.yaml | Text pairs, schedule and scoring | Preserved; add image/html branches and code check |
| visual.json | materialize=none | Changed to render with capability enablement |
| brainstorm_engine.py | Finalist integrity and deterministic report | Extended with source-valid filtering/gallery; slot rules preserved |

### Files to Modify
- scripts/little_loops/loops/brainstorm.yaml — four states, bounded browser action, error/fallback routes.
- scripts/little_loops/loops/brainstorm-tournament.yaml — image/html judge prompts with Read-only tools and finite judge timeouts.
- scripts/little_loops/brainstorm_engine.py — materialize-check, asset/path validation, redacted judge blocks, per-verdict code validation, gallery/report and capability allowlist.
- scripts/little_loops/loops/brainstorm-profiles/visual.json — materialize=render.
- scripts/little_loops/fsm/fence.py, scripts/tests/test_builtin_loops.py, scripts/tests/data/loop_interpolation_baseline.json — prompt/fence/capture/JS interpolation updates.
- scripts/tests/test_brainstorm_engine.py and scripts/tests/test_brainstorm.py — deterministic selection and orchestration fixtures.

### Dependent Files
- finalists.json is the core filter contract; tournament reads only surviving IDs/assets; ENH-3734 verifies combined grounding/materialize/pre-mortem.
- No source-repo .loops/ dependency; browser use follows html-website-generator.yaml's packaged inline convention.

### Tests
- Ordinary pytest uses stubbed browser/canary outputs and direct-import selection/proof tests; it launches no browser.
- Extend the on-demand Playwright learning evidence for selected-document file confinement, disabled JavaScript, fixed viewport, screenshot deadlines and the static-wrapper stamped PNG (unchanged dimensions and readable overlay, no authored script execution or external requests) before enabling the preset. Existing screenshot/network-abort claims are already proven and need not be repeated without a changed mechanism.

### Documentation
- scripts/little_loops/loops/README.md, docs/guides/LOOPS_GUIDE.md, docs/guides/LOOPS_REFERENCE.md — visual gallery, source/image fallbacks, prerequisites and signal limitations.

## Implementation Steps

1. Recheck the landed core artifact contract; extend only the additional browser learning claims.
2. Implement source-valid selection, asset-path confinement, redacted judge blocks and code checks with deterministic tests.
3. Add bounded author/render/canary/check states and image/html tournament prompts; escape inline JS interpolation.
4. Enable BUILT_CAPABILITIES/materialize and the visual preset together; derive the exact +4 success-path visits (or document a justified changed count) and bounded time increment.
5. Record this issue's visual reference run with at least three rendered finalists and a ranked gallery; verify ordinary pytest, portability and both loops' validation.

## Impact

- **Priority**: P3 — improves visual mode independently of other optional capabilities.
- **Effort**: Large — browser artifacts, image consumption and tested fallback selection.
- **Risk**: Medium — local browser/image capability varies; contained by visible fallback and source-valid floors.
- **Breaking Change**: No.

## Acceptance Criteria

- All artifacts stay in the run dir; sources are bounded and candidate IDs/path assets are validated; no expected code leaks through judge blocks, filenames or authored HTML.
- Stubbed tests cover missing/empty/oversized source, >=2 rendered PNGs, one/zero PNGs with >=2 valid sources, <2 valid sources, missing browser, canary mismatch/error/timeout, and render-error routing bypassing the canary.
- No candidate without valid authored HTML is judged or reaches sinks; partial image failure selects the entire final eligible set deterministically; pre_tournament floors run after it.
- Canonical judge_mode is text|image|html; degradation reasons remain separate and visible in the report.
- Reversed image verdict code order is hash-checked correctly; expected codes are absent from durable metadata/blocks. Malformed/missing proof contributes to the core abstention rate, with no mid-tournament restart. Fixtures cover interrupted manifest/finalist publication, HTML restoration of render_failed sources, reuse after committed verdicts without new author/render/canary calls, and changed source/PNG hashes causing explicit failure.
- Screenshot action confines the document/files, blocks network, disables authored JavaScript and has fixed viewport/deadlines, supported by on-demand learning evidence. Ordinary pytest has no Playwright dependency.
- Enablement/preset flip/profile-token wiring and exact step/time bump land together; ENH-3734 owns cumulative combinations. Author/canary states add no hidden evaluator calls or unbounded rate-limit waits.
- This issue records its own reference run, at least three rendered finalists, ranked gallery, import origin and actual cost/latency. FEAT-3596 does not gate or own that run.

## Review History

_2026-10-05 follow-up, `/ll:advise` with Opus (confidence 0.72):_ accepted static-wrapper compositing, digest-only expected-code metadata, a stable input snapshot/committed manifest and replay fixtures. Retained the existing <2-valid-source failure: the advisor's new text-only fallback would allow unauthored candidates and is unnecessary because the floor already handles this path. Code echoes remain an instruction-scoped sanity signal; hashing is not claimed as read isolation. Browser/stamp learning proof and real visual evidence remain pending implementation.

Historical rationale only; the reconciled directive sections above define current scope (2026-10-05).

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus):_ this issue moved to **EPIC-3687** (optional capabilities) so it no longer gates EPIC-3581 or FEAT-3596. Re-run `/ll:reconcile-issue` and `/ll:confidence-check` after FEAT-3667 lands (scores are missing or stale). Its own enablement change (widen `BUILT_CAPABILITIES`, flip the preset knob, wiring test, `max_steps`) and its own reference run stay in scope.

_Added 2026-09-29 (EPIC-3581 pre-implementation review, `/ll:advise` with Opus):_

- **Batched authoring instead of a materialize sub-loop**: one authoring call for all finalists + one screenshot-all state keeps the step cost fixed (≈ 5) and avoids a second child loop. Dissent recorded: a sub-loop is defensible if a single call proves unreliable in output size/quality — if the reference run (FEAT-3596) shows truncated or missing files, fall back to authoring in two batches, still without per-finalist steps.
- Round-1 proof check and the abstention accounting replace the after-the-fact ">half of verdicts" rule.
- **Learning test done (2026-09-29)**: `.ll/learning-tests/playwright.md` now proves (6 new passing claims, node `@playwright/test` 1.60.0, chromium): `page.screenshot` of a `file://` page writes a valid PNG at exactly the viewport size and is byte-identical across two consecutive shots; with `page.route('**/*')` continuing `file:` and aborting everything else, `goto('file://…')` still loads, `img`/stylesheet/`fetch()` requests to a local http server are aborted (0 server hits vs 3 in the no-route control) and the in-page `fetch()` rejects rather than hanging. Raw output appended to `.ll/learning-tests/raw/playwright.txt`. Caveat: the record's `proven_version: 1.57.0` is the *Python* `playwright` distribution stamped by `ll-learning-tests`; the node package used here is 1.60.0, so the older `pageerror` claims were proven under a different version than the new ones. The mockup-author page must not rely on a stamped-pixel OCR claim — reading the stamped code back out of a PNG is judged by the model and checked by the canary, not proven here.

_Added 2026-09-29 (EPIC-3581 third review, `/ll:advise` with Opus):_ `fallback_html` restart removed (see Scope Note; `record-round` prints only `ok`|`fail`); authoring output capped per mockup; judge prompts reference file paths, never inline HTML; the `materialize` states are prompt/shell states with `next:` + `on_error:` and no hidden evaluator calls; the mockup files are written via the Write tool; `materialize` routes are classify-safe (`_: finalize_failed`).

_Added 2026-09-29 (EPIC-3581 second review):_

- The canary/verdict-code comparison and the `finalists.json` rewrite (`judge_mode`, `assets`, `dropped`) are `little_loops.brainstorm_engine` commands, tested by direct import; the Playwright `node -e` screenshot step stays an inline shell state (it is JS). Floor enforcement is `check_floors --stage pre_tournament` (FEAT-3582 Review Decision 25). The tournament child reads `judge_mode`/`assets` from `finalists.json` (FEAT-3582 § Tournament Specification → Child loop).
- ~~Open: the "more than half of verdicts fail proof" fallback can only be decided after the tournament ends~~ — **resolved 2026-09-29**: decided after round 1 inside the tournament child (see Expected Behavior).

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

- One canary proves one call, not each judgement → per-screenshot stamped codes echoed in every verdict and script-checked.
- LLM-authored HTML renders with network aborted.
- Playwright screenshot learning test promoted to a hard prerequisite (registry currently lacks it).
- Removed the stale `none` default; `materialize` inherits via `""`.

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- Follow-up pre-implementation review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.72; no new live measurements) - 2026-10-05
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:27 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:17 - `f2fe6fc2-4dc3-4f38-a10c-f2bd8be05a0c.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:46 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:47:08 - `344bbaba-06f1-4c37-b3c7-3b36aa7bfabc.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:48 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
