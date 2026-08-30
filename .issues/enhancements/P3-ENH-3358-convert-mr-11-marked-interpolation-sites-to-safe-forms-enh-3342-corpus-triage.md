---
id: ENH-3358
type: ENH
title: Convert MR-11-marked interpolation sites to safe forms (ENH-3342 corpus triage)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-29'
captured_at: '2026-08-29T19:44:17Z'
verify_verdict: NON_VALID
confidence_score: 90
outcome_confidence: 77
score_complexity: 9
score_test_coverage: 25
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

## Expected Behavior

Zero `# ll-lint: mr11-ok(...)` markers in `scripts/little_loops/loops/**`;
`ll-loop validate` stays clean because every site is actually safe, not
because it is marked.

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

### Files to Modify
- The full, current file set is not hand-enumerated here because it shrinks with each conversion pass (a static list would go stale the moment one file is done). Enumerate live with `grep -rln "ll-lint: mr11-ok" scripts/little_loops/loops/` (55 files as of this refine) or `grep -rn "ll-lint: mr11-ok" scripts/little_loops/loops/` for per-site detail (585 lines).
- Highest-concentration files, worth converting first: `loops/rn-refine.yaml` (67 markers), `loops/rn-implement.yaml` (54), `loops/rn-remediate.yaml` (48), `loops/autodev.yaml` (46), `loops/cua-agent-desktop.yaml` (40), `loops/recursive-refine.yaml` (34), `loops/mechanize-skills.yaml` (25), `loops/refine-to-ready-issue.yaml` (23), `loops/oracles/plan-node-refine.yaml` (21), `loops/workflow-generator.yaml` / `loops/cli-anything-bootstrap.yaml` (19 each).
- `scripts/tests/test_builtin_loops.py` (`MR11_MARKER_ALLOWLIST`, `scripts/tests/test_builtin_loops.py:19645-19852`) must be edited in lockstep with every marker removal — the allowlist is a set literal enumerating every `(file, namespace.key, "ENH-3358")` tuple; removing a corpus marker without removing its matching tuple fails `TestMr11MarkerSet::test_marker_set_matches_enumeration` as a stale allowlist entry.

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
4. `python -m pytest scripts/tests/test_builtin_loops.py -k TestMr11MarkerSet` passes once the converted sites' markers and allowlist entries are both removed; it fails loudly (naming the drifted tuples) if only one side was updated.
5. When the corpus's marker count reaches zero, `MR11_MARKER_ALLOWLIST` is an empty set and `Expected Behavior`'s "zero markers" criterion is met.

## Impact

- **Priority**: P3 - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Scope

Convert the marked sites (one loop file, or one logical group of sites, per
pass) to a safe interpolation form and remove the marker at each site:

- bash-token position: add the `:shell` suffix (`${captured.run_dir.output:shell}`),
  or wrap in a single-quoted string / quoted heredoc where that fits the
  existing shape better.
- inside a Python literal (heredoc or `python3 -c "..."` body): hoist the
  value to an `LL_ARG_X=...` environment binding on the `python3` invocation
  line and read it via `os.environ` inside the body, per
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s documented idiom.

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
- `/ll:confidence-check` - 2026-08-30T02:12:01 - `d17317a4-6f41-44f3-a144-01ed88f7016d.jsonl`
- `/ll:wire-issue` - 2026-08-30T02:00:50 - `2efc4cfb-bbbb-46a9-a8ab-64e90cf35402.jsonl`
- `/ll:refine-issue` - 2026-08-30T01:53:34 - `543d94ed-e5f6-4375-8dca-4a4196321654.jsonl`
