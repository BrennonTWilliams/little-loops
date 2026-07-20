---
id: ENH-2701
title: Call detect_documents() from _run_yes (headless/TUI parity)
type: ENH
priority: P3
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
parent: EPIC-2700
labels:
- init
- cli
- detection
decision_needed: false
---

# ENH-2701: Call `detect_documents()` from `_run_yes` (headless/TUI parity)

## Summary

`detect_documents()` (scripts/little_loops/init/detect.py:71-121) globs
architecture and product docs (`**/architecture*.md`, `**/design*.md`,
`**/api*.md`, `docs/*.md`, `**/goal*.md`, `**/roadmap*.md`, …) into a
`documents.categories` dict — but it is only called from the TUI
(init/tui.py:557). The headless `_run_yes` flow (init/cli.py:214-452) and
`_run_plan` (cli.py:455-488) never invoke it, so `--yes` and `--plan` always
emit configs with no `documents` block even when the repo has obvious docs.

## Current Behavior

`ll-init --yes` on a repo with `docs/architecture.md` and `roadmap.md` writes
a config with no `documents.categories`. The TUI on the same repo pre-populates
both categories.

## Expected Behavior

Headless init benefits from the same auto-discovery: `_run_yes` and
`_run_plan` call `detect_documents(project_root)` and, when non-empty, include
the result as `documents.categories` in the built config — subject to the
same existing-config pre-population rule as other values (an existing
`documents` section in `ll-config.json` wins; detection only fills the
fresh-init / missing-section case, preserving BUG-2310 merge semantics).

## Proposed Solution

- In `_run_yes` (after `detect_project_type`, before `build_config`), call
  `detect_documents()` and pass the result through — either as a new
  `documents_categories` choice consumed by `build_config()`
  (init/core.py:77-200) or merged into `config` before
  `merge_with_existing` at cli.py:399.
- Same call in `_run_plan` so the plan JSON shows what would be written.
- Print a one-line summary (`Detected N architecture docs, M product docs`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

`build_config()` (`init/core.py:77-200`) has **no `documents`/`documents_categories`
handling whatsoever** — its docstring's "Recognised keys" list (lines 91-104)
never mentions it, and `documents` is explicitly called out at `cli.py:16-19`
as one of the "richer features" that "remain interactive-only." The TUI does
not route it through `build_config()` either — it assembles `config["documents"]`
directly as a post-processing step in `_build_final_config()`
(`tui.py:704-708`), after `build_config()` already returned. This narrows the
"either/or" in the bullet above to a concrete choice:

**Option A**: Add a `documents_categories` parameter/choices-key to
`build_config()` (`init/core.py`), threading detected categories through the
same `choices` dict as other modeled sections (project, scan, analytics, …).

**Option B**: Call `detect_documents(project_root)` in `_run_yes`/`_run_plan`
and assemble `config["documents"] = {"enabled": True, "categories": {...}}`
directly after `build_config()` returns — mirroring the TUI's existing
`_build_final_config()` pattern verbatim (`tui.py:552-557` compute step,
`tui.py:704-708` assembly step).

> **Selected:** Option B — mirrors the TUI's proven `_build_final_config()` assembly and the existing `install_source` post-`build_config()` idiom in `_run_yes`; only a new existing-config guard is required.

**Recommended**: Option B — mirrors a pattern already proven by the TUI,
avoids widening `build_config()`'s already-large modeled-section surface
(project/issues/scan/learning_tests/analytics/context_monitor/product/decisions/
scratch_pad/session_capture/prompt_optimization/history/loops) with a section
that has no template-driven defaults, and keeps `_run_plan`'s "detect + build +
emit JSON" purity intact (it never loads `existing_config` today —
`_run_plan` has no `merge_with_existing` call at all).

**Merge-semantics caveat (BUG-2310)**: `merge_with_existing()`
(`writers.py:123-146`) calls `deep_merge(existing_config, strip_none_leaves(new_config))`
— the **new_config side wins** at the leaf level, not `existing_config`. Today
`documents.categories` survives re-init only because `_run_yes` never
populates `new_config["documents"]` at all (nothing to override with). Once
this issue wires in `detect_documents()`, the call site must explicitly guard
against clobbering a user's existing `documents.categories` on re-init — e.g.
only assemble/inject the detected `documents` section when
`existing_config.get("documents")` is falsy — otherwise a plain `--yes`
re-run would silently overwrite hand-edited categories with freshly detected
ones. `test_yes_preserves_unmodeled_keys` (`test_init_core.py:1408`) already
asserts the current (accidental) preservation behavior and must keep passing.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-19.

**Selected**: Option B — call `detect_documents()` in `_run_yes`/`_run_plan` and
assemble `config["documents"]` directly after `build_config()` returns.

**Reasoning**: The exact assembly shape already exists verbatim in the TUI's
`_build_final_config()` (`tui.py:552-557`, `704-708`), and `_run_yes` already
uses the identical post-`build_config()` direct-assignment idiom for
`install_source` (`cli.py:401-402`) — so Option B is a copy of proven code plus
one new existing-config guard. Option A would restructure a deliberate
architectural boundary: `documents` is explicitly modeled *outside*
`build_config()` today (tested as an "unmodeled section" at
`test_init_core.py:1408`), and `build_config()` has no precedent for a
data-carrying (non-scalar) `choices` key.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (build_config param) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option B (post-build_config assembly) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |

**Key evidence**:
- Option A: `detect_documents()` output shape is reusable, but `build_config()`
  has no data-carrying-choices-key precedent and `documents` is architected as a
  section `build_config()` never emits — Option A restructures that boundary
  (reuse score 1).
- Option B: mirrors `tui.py:704-708` verbatim, reuses the unmodified
  `detect_documents()` detector, and follows the existing `install_source`
  post-build assignment precedent; the only genuinely new logic is the
  `existing_config.get("documents")` guard needed to keep
  `test_yes_preserves_unmodeled_keys` passing (reuse score 2).

## Acceptance Criteria

- Fresh `ll-init --yes` on a fixture repo with matching docs writes a
  populated `documents.categories`.
- Re-init on a repo whose existing config already has a `documents` section
  leaves it untouched.
- `ll-init --plan` includes the detected categories in `proposed_config`.
- `python -m pytest scripts/tests/` exits 0; new test covers headless doc
  detection.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_run_yes()` (lines 214-452): insert
  the `detect_documents()` call after `detect_project_type` (line 359),
  before `build_config` (line 395). `_run_plan()` (lines 455-488): insert
  after `detect_project_type` (line 465), before `build_config` (line 469).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/tui.py:552-557` — existing `detect_documents()`
  compute-step call site (gated on `"documents" in selected_set`) to mirror.
- `scripts/little_loops/init/tui.py:704-708` — existing assembly of
  `config["documents"]` from `documents_categories`, run *after*
  `build_config()` returns — the exact shape `_run_yes`/`_run_plan` need to
  replicate.
- `scripts/little_loops/init/writers.py:123-146` — `merge_with_existing()`
  (BUG-2310); see the merge-semantics caveat under Proposed Solution above.
- `scripts/little_loops/init/cli.py:16-19` — comment enumerating `documents`
  among features that "remain interactive-only"; update once this lands.

### Similar Patterns
- `scripts/little_loops/init/cli.py:359` (`_run_yes`) and `:465` (`_run_plan`)
  — `detect_project_type()` call pattern already wired into both headless
  entry points, including the function-local
  `from little_loops.init.detect import detect_project_type` import
  convention to follow for `detect_documents`.

### Tests
- `scripts/tests/test_init_core.py:2462` — `TestDetectDocuments`: existing
  unit coverage of the detector's glob/exclude logic itself (no changes
  needed — only the wiring is untested).
- `scripts/tests/test_init_core.py:1408` — `test_yes_preserves_unmodeled_keys`
  — must keep passing once `_run_yes` actively populates `documents`.
- `scripts/tests/integration/test_init_e2e.py` — `TestInitHeadlessEndToEnd`
  (`_run_init()` helper + `tmp_path` fixture project) — pattern to model the
  new headless-detection e2e test after: write real
  `docs/architecture.md`/`roadmap.md` fixtures, run `--yes`, assert
  `.ll/ll-config.json` contains populated `documents.categories`.

## Scope Boundaries

- **In**: wiring the existing detector into `_run_yes`/`_run_plan`.
- **Out**: changing the glob patterns themselves; TUI behavior.

## Impact

- **Priority**: P3 — cheapest win in the epic; pure asymmetry bug.
- **Effort**: Small — the detector already exists and is tested via the TUI
  path.
- **Risk**: Low — additive, guarded by existing-config precedence.

## Status

**Open** | Created: 2026-07-19 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-07-19T23:54:32 - `bc31c482-dece-432a-a346-aa0a810887d7.jsonl`
- `/ll:refine-issue` - 2026-07-19T22:41:29 - `926de526-7a59-4baf-abfe-5ac37cfae19f.jsonl`
