---
id: ENH-3358
type: ENH
title: Convert MR-11-marked interpolation sites to safe forms (ENH-3342 corpus triage)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-29'
captured_at: '2026-08-29T19:44:17Z'
confidence_score: 100
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3358: Convert MR-11-marked interpolation sites to safe forms (ENH-3342 corpus triage)

## Summary

ENH-3342 widened MR-11 (drop the fixed seven-key allowlist, add the
`captured`/`prev` namespaces, and delegate to `interp_sweep.classify_site()`).
Running the widened rule across the built-in loop corpus surfaced 665
pre-existing findings across 60 loop YAML files — far more than ENH-3342's
own triage step could convert in that session without risking dozens of
production automation loops. Per ENH-3342's `# ll-lint: mr11-ok(<var>)
<reason>` marker mechanism (added for exactly this situation), every one of
those 665 sites was marked with a well-formed marker citing this issue, so
the corpus stays `ll-loop validate`-clean while the actual conversion work is
tracked here.

## Current Behavior

665 `# ll-lint: mr11-ok(...)` markers across 60 files, citing this issue
(ENH-3358), each suppressing one otherwise-live MR-11 WARNING.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Actual current corpus count differs from the cited totals: `grep -rl "ll-lint: mr11-ok" scripts/little_loops/loops/` finds the marker in 55 files (not 60), and `grep -ro "ll-lint: mr11-ok" scripts/little_loops/loops/` finds 585 individual marker lines (not 665). The corpus state was already 55 files / 585 markers at ENH-3342's own landing commit (`401b7418a`); no commit since has touched `scripts/little_loops/loops/`, so the 665/60 figures in this issue's Summary/Current Behavior predate that commit's final marker count rather than describing the present corpus.
- `TestMr11MarkerSet::test_marker_set_matches_enumeration` (`scripts/tests/test_builtin_loops.py:19861`) tracks 187 deduplicated `(file, namespace.key, issue_id)` tuples in `MR11_MARKER_ALLOWLIST` (`scripts/tests/test_builtin_loops.py:19645`) — fewer than 585 because several files repeat the same `namespace.key` marker on multiple lines, which the allowlist tracks once per file.
- Marker concentration is uneven: `rn-refine.yaml` (67), `rn-implement.yaml` (54), `rn-remediate.yaml` (48), `autodev.yaml` (46), and `cua-agent-desktop.yaml` (40) together hold 255 of the 585 markers (~44%); the top 10 files hold ~63%. Prioritizing these files converts the bulk of the corpus in the fewest passes.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- **Correction to the commit-touch claim above**: "no commit since [`401b7418a`] has touched `scripts/little_loops/loops/`" is false. `git log --oneline 401b7418a..HEAD -- scripts/little_loops/loops/` returns 3 commits: `8ceeb024c` (3-line edit to `refine-to-ready-issue.yaml`), `ff709f91b` (9 files, 204 insertions — adds/edits `rn-build.yaml`, `integrate-sdk.yaml`, `loop-router.yaml`, etc.), and `a38e266e6` (rewrites `workflow-generator.yaml`, 39 changed lines). The 55-file / 585-marker corpus count is still independently confirmed current as of this pass (`grep -rl "ll-lint: mr11-ok" scripts/little_loops/loops/ | wc -l` → 55; `grep -ro ... | wc -l` → 585), it just isn't unchanged for the reason originally stated — the corpus was touched by these 3 commits without net effect on marker count, which was never established.
- **Correction to the `TestMr11MarkerSet` citation above**: `class TestMr11MarkerSet:` is at `scripts/tests/test_builtin_loops.py:19856` (not 19855) and `def test_marker_set_matches_enumeration` is at `:19862` (not 19861). The 187-tuple count is independently reconfirmed correct as stated (parsed `MR11_MARKER_ALLOWLIST`'s set literal directly via `ast.literal_eval`: 187 tuples, all `("...", "...", "ENH-3358")`, all unique; `python -m pytest scripts/tests/test_builtin_loops.py -k TestMr11MarkerSet -q` passes, confirming the corpus's discovered set equals the 187-tuple allowlist exactly).
- **Correction to the "~63%" figure above**: using the same per-file counts already cited (67+54+48+46+40+34+25+23+21+19 for the top 10), the actual share is 377/585 ≈ 64.4%, not ~63%.

## Expected Behavior

Zero `# ll-lint: mr11-ok(...)` markers in `scripts/little_loops/loops/**`;
`ll-loop validate` stays clean because every site is actually safe, not
because it is marked.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- **"Zero markers" is necessary but not sufficient — the loop-wide escape hatch must also stay unset.** `_validate_unsafe_context_interpolation()` (`scripts/little_loops/fsm/validation/shell_safety.py:533`) returns `[]` (skips `_scan_state_for_mr11` entirely) for any loop file where `fsm.unsafe_context_interpolation_ok: true` is set — this suppresses MR-11 scanning for the *whole file*, not one site. Today zero of the 55 marked files (or any other builtin loop) set this flag (`grep -rln "unsafe_context_interpolation_ok" scripts/little_loops/loops/` → 0 matches), and no test in `scripts/tests/test_builtin_loops.py` asserts it stays that way. A pass that deletes the 585 per-site markers and sets this flag loop-wide on the highest-marker-count files instead of converting them would satisfy "zero `mr11-ok` markers" and a clean `ll-loop validate`, while leaving every site's raw interpolation unfixed and now invisible to both `TestMr11MarkerSet` (nothing left to enumerate) and `TestValidatorWarningBudget` (no WARNING is ever emitted to hit its budget). "Every site is actually safe" therefore also requires: no builtin loop file this issue touches sets `unsafe_context_interpolation_ok: true` as a substitute for per-site conversion.

## Motivation

ENH-3342's own Impact section: "if the residual marker set comes out large,
that is a signal to convert more, not to accept it." 665 is large. This issue
is the accepted deviation from ENH-3342's original AC 8 ("triaged... in this
issue") — recorded as a deliberate follow-up rather than silently absorbed
into ENH-3342's own session, per user decision on 2026-08-29.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Two safe forms are already documented and named, not invented by this issue: `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:137-171` ("MR-11's two safe interpolation idioms (ENH-3342)"). Idiom 1 — `LL_ARG_` environment hoist: bind the value with `:shell` at a real bash-token position on the `python3` invocation line (`LL_ARG_X=${namespace.key:shell} python3 << 'PYEOF'`), read it via `os.environ["LL_ARG_X"]` inside the body. Idiom 2 — heredoc-to-file: write the value to a file with `printf '%s' "${namespace.key:shell}" > "${context.run_dir}/<state>-<capture>.txt"` at a bash-token position, then have the Python body read that file instead of embedding the value as a literal. The guide states a preference rule: idiom 1 for short scalars (a threshold, a flag, an id); idiom 2 for long-form text (a plan, a review, an LLM response) that would be awkward as a single env var.
- Idiom 1 already has 23 files' worth of precedent in the corpus today (e.g. `apply-research.yaml:216`, `brainstorm.yaml:165`, `autodev.yaml:1636`, `auto-refine-and-implement.yaml:138`) — converting a bash-token-position marker to idiom 1 is following an established convention, not introducing a new one.
- Idiom 2 (heredoc-to-file) has no existing occurrence in `scripts/little_loops/loops/` today (searched for the `printf ... :shell ... > .../run_dir/...` shape used in the guide's own example) — the first conversion that needs it will be introducing the pattern into the corpus fresh, from the guide's example rather than from an in-repo precedent.
- For a bash-token-position finding that is not inside a Python literal, the simpler fix from the same guide section (MR-11 row, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:104`) applies instead of either idiom: add `:shell` directly at that token position, or wrap the value in a single-quoted string — no `python3` involvement, no LL_ARG_ hoist needed. Which of the three forms (`:shell`-in-place, idiom 1, idiom 2) applies to a given marked site depends on whether the site is a bash token or inside an embedded Python literal, per `_scan_state_for_mr11`'s two-scan-path split described in Program Design below.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Findings below cover the files to touch, the enforced marker/finding convention, test coverage, and the documentation that defines the safe forms.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- **Correction to "Conventions in Force" above**: the cited range `shell_safety.py:286-329` covers only `_scan_state_for_mr11`'s signature, docstring, and marker-parsing preamble — it ends before either scan path begins. The two scan paths it describes are actually at `shell_safety.py:338-401` (Half 1, bash-token-position line walk) and `:403-423` (Half 2, delegated `interp_sweep.scan_action()` call); the function itself continues through its stale-marker detection to `return bash_findings + python_findings, marker_errors` at `:441`.
- **Correction to "Tests" above**: `class TestMr11MarkerSet:` is at `scripts/tests/test_builtin_loops.py:19856` (not 19855) and `def test_marker_set_matches_enumeration` is at `:19862` (not 19861) — same correction as filed under Current Behavior.
- **Correction to "Documentation" above**: the marker-grammar subsection of `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s "MR-11's two safe interpolation idioms" material ends at line 203 ("...exempted has been converted or removed."), not 215 — lines 204-215 are the start of an unrelated "Review heuristic — retry reachability (not mechanized)" section (MR-4/BUG-3326/FEAT-3332 worked examples). The correct range is `:137-203`.
- **Test-coverage gap — all three named gates are static/lint-only.** `TestMr11MarkerSet`, `ll-loop validate`, and `TestValidatorWarningBudget` all derive from grep/AST-level scans of the loop YAML text; none execute a converted state's shell action. This matters most for idiom 2 (heredoc-to-file, Proposed Solution): it has zero existing occurrences in `scripts/little_loops/loops/` today, so the first conversion using it introduces a brand-new runtime pattern into production loops with no runtime/smoke verification named anywhere in this issue. A site can be `ll-loop validate`-clean and `MR11_MARKER_ALLOWLIST`-consistent while still being wrong at runtime — an `LL_ARG_X` name collision, a heredoc-to-file path collision under `${context.run_dir}`, or an `os.environ` read on a mismatched key — and none of the three named gates would catch it.
- **Two files under `### Files to Modify` cannot be independently validated by `ll-loop validate <file>`.** `scripts/little_loops/loops/lib/common.yaml` (1 marker: `context.issue_id`, line 458) and `scripts/little_loops/loops/lib/harness.yaml` (2 markers: `context.file_url`, `context.screenshot_path`, lines 11-12) are `loops/lib/` fragment-library files (top-level `fragments:` key, no `name`/`initial`/`states`). `is_runnable_loop()` (`scripts/little_loops/fsm/validation/structural_rules.py:1654-1667`) documents "Library fragments under `loops/lib/` still return False", and running `ll-loop validate` on either file directly confirms it: both fail immediately with `FSM file missing required fields: name, initial, states (or flow)` — a structural error unrelated to MR-11, unaffected by whether the site is converted. These fragments are only MR-11-scanned when an *importing* loop that pulls them in (e.g. `harness-multi-item.yaml`, `autodev.yaml`, `integrate-sdk.yaml`, `brainstorm.yaml`, and others — `grep -rln "lib/common.yaml\|lib/harness" scripts/little_loops/loops/` lists 10 importers) is itself validated — so these 3 sites' "clean `ll-loop validate`" check must run against an importing loop, not the fragment file itself.

### Files to Modify
- The full, current file set is not hand-enumerated here because it shrinks with each conversion pass (a static list would go stale the moment one file is done). Enumerate live with `grep -rln "ll-lint: mr11-ok" scripts/little_loops/loops/` (55 files as of this refine) or `grep -rn "ll-lint: mr11-ok" scripts/little_loops/loops/` for per-site detail (585 lines).
- Highest-concentration files, worth converting first: `loops/rn-refine.yaml` (67 markers), `loops/rn-implement.yaml` (54), `loops/rn-remediate.yaml` (48), `loops/autodev.yaml` (46), `loops/cua-agent-desktop.yaml` (40), `loops/recursive-refine.yaml` (34), `loops/mechanize-skills.yaml` (25), `loops/refine-to-ready-issue.yaml` (23), `loops/oracles/plan-node-refine.yaml` (21), `loops/workflow-generator.yaml` / `loops/cli-anything-bootstrap.yaml` (19 each).
- `scripts/tests/test_builtin_loops.py` (`MR11_MARKER_ALLOWLIST`, `scripts/tests/test_builtin_loops.py:19645-19852`) must be edited in lockstep with every marker removal — the allowlist is a set literal enumerating every `(file, namespace.key, "ENH-3358")` tuple; removing a corpus marker without removing its matching tuple fails `TestMr11MarkerSet::test_marker_set_matches_enumeration` as a stale allowlist entry.
- `scripts/tests/test_builtin_loops.py` also gains two new tests from this issue: the `unsafe_context_interpolation_ok` zero-occurrence guard (Implementation Steps step 6) and the idiom-2 round-trip proof (step 7).

### Conventions in Force
- Every marked site follows one convention today: the generic reason text `ENH-3358 - ENH-3342 widening residual, tracked for conversion` (e.g. `loops/autodev.yaml:197,223,227,229,271`) — none of the 585 markers carry a site-specific reason distinguishing which safe form applies, so that classification is this issue's own work, not something recoverable from the marker text.
- The marker/finding split is enforced structurally, not just documented: `_scan_state_for_mr11()` (`scripts/little_loops/fsm/validation/shell_safety.py:286-329`) runs two independent scan paths — a bash-token-position line walk, and a delegated Python-literal-position scan via `interp_sweep.scan_action()` — both keyed through `classify_site(namespace, key)` (`scripts/little_loops/fsm/interp_sweep.py:59`). A marker only "consumes" (silences) a finding on the scan path that actually produced it; converting a site removes both its marker line and the underlying interpolation, not just the marker.

### Tests
- `scripts/tests/test_builtin_loops.py::TestMr11MarkerSet::test_marker_set_matches_enumeration` (class at line 19855, test at 19861) is the ratchet: it asserts the corpus's discovered `(file, namespace.key, issue_id)` set equals `MR11_MARKER_ALLOWLIST` exactly, so it fails loudly on both an unenumerated new marker and a stale (unremoved) allowlist entry.
- `ll-loop validate <loop-file>` re-runs the live MR-11 scan per file and is the fastest per-site feedback loop while converting one file at a time (per `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:414,427`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget::test_deterministic_warning_categories_do_not_regrow` (class at line 16346) is a second, independent corpus-wide gate: it runs `load_and_validate()` over every builtin loop and fails on any WARNING whose message matches `"interpolates user-controlled context raw into a shell body"` (the `unsafe-context-interp` category) that isn't in its own `ALLOWLIST`. That category currently has zero `ALLOWLIST` entries because every real MR-11 finding today is marker-suppressed; if a conversion removes a marker without actually fixing the site (or fixes it incorrectly), `_scan_state_for_mr11` emits a live MR-11 finding whose message this test's pattern catches — a safety net on top of, not a replacement for, `ll-loop validate` and `TestMr11MarkerSet`. No `ALLOWLIST` entry should ever be added here for this issue's work; a hit means the conversion at that site is wrong, not that it needs allowlisting.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:104` (MR-11 row) and `:137-215` ("MR-11's two safe interpolation idioms" through the marker-grammar subsection) is the authoritative source for both safe forms and the marker escape hatch — this issue converts markers away, it does not change this documentation.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- Findings below cover the concrete signatures a converted site must still classify correctly under, the validation call path `ll-loop validate` runs, and why no new decision logic applies.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- **Correction to the `scan_action` signature above**: the actual definition at `scripts/little_loops/fsm/interp_sweep.py:128` is `def scan_action(action: str, *, state: str, file: str) -> list[InterpSite]:` — `state` and `file` are keyword-only (note the `*`), not positional. Calling it as `scan_action(action, state, file)` raises `TypeError`; the call must use `scan_action(action, state=..., file=...)`.

### Signatures
- `classify_site(namespace: str, key: str) -> str` (`scripts/little_loops/fsm/interp_sweep.py:59`) — returns the trust class (`"A"`/`"B"`/`"C"`) that both scan paths key off of; unchanged by this issue, cited here because it is what a converted site must still classify correctly under.
- `scan_action(action: str, state: str, file: str) -> list[InterpSite]` (`scripts/little_loops/fsm/interp_sweep.py:128`) — the delegated Python-literal-position scan; a converted heredoc/`-c` site must produce zero live `InterpSite` findings (or a well-formed, still-justified marker — not applicable here since the goal is zero markers).
- `_scan_state_for_mr11(state_name: str, action: str, fsm_name: str) -> tuple[list[_Mr11Finding], list[ValidationError]]` (`scripts/little_loops/fsm/validation/shell_safety.py:286`) — the two-scan-path entry point `ll-loop validate` invokes per state; both findings lists must come back empty for a fully converted file (no markers, no residual MR-11 WARNINGs).

### Call Path
`ll-loop validate <file>` -> `_scan_state_for_mr11()` (`shell_safety.py:286`) -> bash-token-position line walk (`_UNSAFE_CONTEXT_INTERP_RE`, same file) and delegated `interp_sweep.scan_action()` (`interp_sweep.py:128`) -> both call `classify_site()` (`interp_sweep.py:59`) to decide trust class -> a finding on either path is either silenced by a matching `# ll-lint: mr11-ok(...)` marker (today's state, being removed) or, post-conversion, does not occur at all because the site now uses `:shell`/single-quoting (bash-token position) or the `LL_ARG_` hoist / heredoc-to-file idiom (Python-literal position).

### Decision Rules
N/A — no new decision logic. This issue converts existing sites to two already-documented safe forms (`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:137-171`); it does not introduce a new gap kind, gate, threshold, or classification rule.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

1. Every site under `scripts/little_loops/loops/` matching `# ll-lint: mr11-ok(...)` (585 lines / 55 files as of this refine, enumerable via `grep -rn "ll-lint: mr11-ok" scripts/little_loops/loops/`) converts to one of three safe forms depending on the site's position — `:shell`-in-place / single-quoting for a bare bash-token site, the `LL_ARG_` env hoist for a short scalar inside a Python literal, or heredoc-to-file for long-form text inside a Python literal (see Proposed Solution, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:104,137-171`) — and its marker line is removed.
2. Each removed marker's matching `(file, namespace.key, "ENH-3358")` tuple is removed from `MR11_MARKER_ALLOWLIST` (`scripts/tests/test_builtin_loops.py:19645-19852`) in the same pass — the two must move together or `TestMr11MarkerSet::test_marker_set_matches_enumeration` fails on the drift, not just at the end.
3. `ll-loop validate <file>` on each touched file returns clean (no MR-11 WARNING, no malformed/stale-marker ERROR) before moving to the next file.
   > ⚠ Superseded — stale-marker is WARNING; 2 lib/ files need alt verification; see § Codebase Research Findings under Implementation Steps
4. `python -m pytest scripts/tests/test_builtin_loops.py -k TestMr11MarkerSet` passes once the converted sites' markers and allowlist entries are both removed; it fails loudly (naming the drifted tuples) if only one side was updated.
5. When the corpus's marker count reaches zero, `MR11_MARKER_ALLOWLIST` is an empty set and `Expected Behavior`'s "zero markers" criterion is met.
6. A guard test is added to `scripts/tests/test_builtin_loops.py` asserting zero occurrences of `unsafe_context_interpolation_ok` in `scripts/little_loops/loops/**` — closing the loop-wide escape hatch identified under Expected Behavior. This test lands with the *first* conversion pass, not the last, so the loophole is sealed for the entire duration of the work.
7. Before the first idiom-2 (heredoc-to-file) conversion — which has zero corpus precedent — the pattern is proven with a small unit test (or spike per `/ll:spike`): `printf '%s' "<value>" > file` + Python `open(...).read()` must round-trip newlines, single/double quotes, empty values, and `$(...)`-shaped text intact. This test stays in the suite as the runtime backstop for all subsequent idiom-2 conversions.

### Per-pass completion model

This issue will span multiple sessions. A **pass = one loop file** (or one
importing loop, for the 2 `loops/lib/` fragments), and each pass is a valid,
committable stopping point:

1. Convert every marked site in the file to its applicable safe form; remove each marker line.
2. Remove the matching `(file, namespace.key, "ENH-3358")` tuples from `MR11_MARKER_ALLOWLIST`.
3. `ll-loop validate <file>` (or the importing loop) returns clean.
4. `python -m pytest scripts/tests/test_builtin_loops.py -k "TestMr11MarkerSet or TestValidatorWarningBudget" -q` passes.
5. Commit.

The `TestMr11MarkerSet` ratchet keeps marker/allowlist lockstep at every
intermediate state, so partial progress never leaves the repo inconsistent.
The issue itself closes only when the corpus marker count is zero. Work
highest-concentration files first (see Integration Map → Files to Modify).

### Per-site conversion cautions

- **Conversions are not purely mechanical.** `:shell` quotes the value; a site that intentionally interpolated raw (multi-token arguments, an unquoted path segment inside a larger word) changes behavior when converted. Review the surrounding shell line at each site, not just the interpolation token.
- **`LL_ARG_` name collisions**: when multiple hoists land on one `python3` invocation line, each binding needs a distinct name and each `os.environ` read must match its binding exactly.
- **Heredoc-to-file path collisions**: idiom-2 file names under `${context.run_dir}/` must be unique per `<state>-<capture>` within a run.

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

- **Correction to Step 3's "clean" definition**: `_scan_state_for_mr11` (`scripts/little_loops/fsm/validation/shell_safety.py:424-439`) emits a stale-marker diagnostic at `severity=ValidationSeverity.WARNING`, not ERROR — only a malformed marker (missing reason/parens, or containing `${`, `:330`) is ERROR. Step 3's "(no MR-11 WARNING, no malformed/stale-marker ERROR)" wording lumps stale-marker in with the ERROR bucket; in the actual code stale-marker sits at the same WARNING tier as a live MR-11 finding.
- **Step 3 cannot return "clean" for 2 of the 55 files by running `ll-loop validate <file>` on the file itself**: `loops/lib/common.yaml` and `loops/lib/harness.yaml` are `loops/lib/` fragments (`is_runnable_loop()` returns `False` for them, `structural_rules.py:1654-1667`); `ll-loop validate` on either fails immediately with a structural "missing required fields" error, unrelated to MR-11. Their 3 marked sites (`context.issue_id`; `context.file_url`, `context.screenshot_path`) can only be verified clean by validating an *importing* loop (e.g. `autodev.yaml`, `integrate-sdk.yaml`, `harness-multi-item.yaml`) instead of the fragment file. See Integration Map → Files to Modify for the full importer list.

## Impact

- **Priority**: P3 - Deferred, tracked technical-debt cleanup, not incident remediation: every marked site is already `ll-loop validate`-clean via a well-formed, test-enforced marker (`TestMr11MarkerSet`), so nothing is silently unsafe today — this issue exists to remove the escape hatch, not to fix a live defect (see Motivation).
- **Effort**: Large - 585 marker sites across 55 files, each requiring per-site classification into one of three safe forms (bash-token `:shell`/quoting, `LL_ARG_` env hoist, or heredoc-to-file — the last with zero existing precedent in the corpus today), a matching `MR11_MARKER_ALLOWLIST` tuple removal, and a clean `ll-loop validate` re-run, verified one file (or one importing loop, for the 2 `loops/lib/` fragment files) at a time with no batch/automatable conversion path named.
- **Risk**: Medium - Touches the corpus's highest-marker-count production loops (`rn-refine.yaml`, `rn-implement.yaml`, `autodev.yaml`) but is guarded by two independent static gates (`TestMr11MarkerSet`'s allowlist ratchet and `TestValidatorWarningBudget`'s corpus-wide WARNING-category budget). The residual risk is that both gates, and `ll-loop validate` itself, are lint-only — no runtime verification is named anywhere in this issue to confirm a converted site (especially a first-ever heredoc-to-file idiom-2 conversion) is functionally equivalent, not just lint-clean (see Codebase Research Findings under Integration Map).
- **Breaking Change**: No - Rewrites interpolation syntax inside built-in loop YAML action bodies only; no CLI flag, config schema, issue schema, or external API surface changes.

## Scope

Convert the marked sites (one loop file, or one logical group of sites, per
pass) to a safe interpolation form and remove the marker at each site:

- bash-token position: add the `:shell` suffix (`${captured.run_dir.output:shell}`),
  or wrap in a single-quoted string / quoted heredoc where that fits the
  existing shape better.
- inside a Python literal (heredoc or `python3 -c "..."` body), short scalar:
  hoist the value to an `LL_ARG_X=...` environment binding on the `python3`
  invocation line and read it via `os.environ` inside the body, per
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s documented idiom 1.
- inside a Python literal, long-form text (a plan, a review, an LLM
  response): write it to a file with `printf '%s' "${...:shell}" >
  "${context.run_dir}/<state>-<capture>.txt"` at a bash-token position and
  have the Python body read that file (idiom 2; no corpus precedent yet —
  see Implementation Steps step 7 for the required round-trip proof).

Enumerate the current marker set with:

```
grep -rn "ll-lint: mr11-ok" scripts/little_loops/loops/
```

As each site converts, its marker is removed. When the corpus's marker count
reaches zero, `test_builtin_loops.py`'s enumerated marker-set assertion
(ENH-3342 AC 8c) drives that to completion — a removed marker with no
corresponding literal-set update fails that test, keeping this issue's
progress and the checked-in enumeration in lockstep.

## Status

**Open** | Created: 2026-08-29 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-30T02:30:46 - `2ccfc427-71e0-4829-bf66-b023da97bae4.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-08-30T02:19:05 - `b21d1213-6d66-4564-b8d2-88ca246f8982.jsonl`
- `/ll:confidence-check` - 2026-08-30T02:12:01 - `d17317a4-6f41-44f3-a144-01ed88f7016d.jsonl`
- `/ll:wire-issue` - 2026-08-30T02:00:50 - `2efc4cfb-bbbb-46a9-a8ab-64e90cf35402.jsonl`
- `/ll:refine-issue` - 2026-08-30T01:53:34 - `543d94ed-e5f6-4375-8dca-4a4196321654.jsonl`
