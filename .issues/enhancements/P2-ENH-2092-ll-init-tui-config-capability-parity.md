---
id: ENH-2092
title: Bring ll-init TUI to config-capability parity with /ll:init
type: enhancement
status: open
priority: P2
captured_at: "2026-06-11T19:02:25Z"
discovered_date: 2026-06-11
discovered_by: capture-issue
parent: EPIC-1978
blocks:
- ENH-1982
relates_to:
- EPIC-1978
- BUG-2042
- ENH-2043
- FEAT-1980
labels:
- init
- tui
- parity
---

# ENH-2092: Bring ll-init TUI to config-capability parity with /ll:init

## Summary

ENH-1982 will deprecate the ~1,250-line `/ll:init` skill to a thin stub that
auto-runs `ll-init --yes`, making `ll-init` the **only** init path. BUG-2042
already guaranteed byte-equivalent config for the same `--yes` inputs, but it
never brought the *interactive question set* to parity. The `ll-init` TUI
(`scripts/little_loops/init/tui.py`) collapsed the skill's ~12 guided rounds
into 5 questionary screens and silently dropped real config-producing
questions. After deprecation, anything `/ll:init` could produce that `ll-init`
cannot becomes a regression with no fallback. This issue closes that gap so
the skill can be safely retired.

Direction: **config-capability parity** — add every missing config-producing
question while keeping the streamlined questionary flow (not the exact
12-round structure), with **curated language-specific command menus** and
**document auto-detection**. All target config keys already exist in
`config-schema.json` (`sync`, `commands.confidence_gate`, `commands.tdd_mode`,
`parallel.worktree_copy_files`, `design_tokens.active`, `documents.categories`).

## Current Behavior

The `ll-init` interactive TUI presents 5 questionary screens and cannot
produce several config sections that `/ll:init`'s prose wizard could. The
following questions are silently absent or degraded:

| Gap | `/ll:init` produces | `ll-init` today |
|---|---|---|
| GitHub sync toggle | feature option → `sync` | absent |
| Confidence gate toggle | feature → `commands.confidence_gate` | absent |
| TDD mode toggle | feature → `commands.tdd_mode` | absent |
| Design-token **profile picker** | default / editorial-mono / warm-paper + custom → `design_tokens.active`/`path` | writes only `{enabled: true}` |
| Document **auto-detect + categories** | globs arch/product docs → `documents.categories` | writes only `{enabled: true}` |
| Parallel `worktree_copy_files` | multi-select .env/.env.local/.secrets | absent |
| Scan `focus_dirs` prompt | editable | template default only |
| Scan custom `exclude_patterns` | additive prompt | template default only |
| Session-digest enable prompt | yes/no | always-on, never asked |
| Settings target **Skip** | local/shared/**skip** | local/shared only |
| Curated command menus | language-specific multiple-choice | free-text only |

## Expected Behavior

The `ll-init` TUI exposes every config-producing question above, so a Python
(or any supported) project initialized interactively writes a config that is a
**superset** of what `/ll:init`'s wizard produced for equivalent answers — no
config section remains unreachable. The headless `--yes` path keeps its
current safe defaults unchanged; enrichment is TUI-side only (plus shared
helpers in `detect.py`).

## Motivation

Once ENH-1982 deletes the prose flow, the TUI is the only interactive init
path. Every question the TUI cannot ask becomes a permanent capability
regression. Closing the parity gap is a hard prerequisite for safely retiring
the skill — this issue blocks ENH-1982.

## Success Metrics

- **Config parity**: All 11 capability gaps listed in Current Behavior are reachable via `ll-init` TUI interactive flow; 0 config sections remain unreachable after deprecation of `/ll:init`.
- **Regression guard**: `ll-init --yes` output is byte-unchanged from pre-patch behavior for all 9 project-type templates.
- **Test coverage**: New TUI unit tests cover every new prompt (curated menus, profile picker, scan screen, worktree checkbox, session-digest confirm, settings-skip); `ruff check scripts/` and `python -m mypy scripts/little_loops/init/` pass.

## Proposed Solution

Work concentrates in `scripts/little_loops/init/` plus the 8 project-type
template JSONs. The `--yes` path (`cli.py::_run_yes` → `core.build_config`)
is untouched; enrichment lives in `tui.py::_build_final_config` and new prompt
screens, plus one new `detect.py` helper.

1. **Curated command menus — source data in templates.** Add an optional
   `_meta.command_options` block to each project-type template (`python-generic`,
   `typescript`, `javascript`, `go`, `rust`, `java-maven`, `java-gradle`,
   `dotnet`). Shape:

   ```json
   "_meta": {
     "command_options": {
       "test_cmd":   ["pytest", "pytest -v", "python -m pytest"],
       "lint_cmd":   ["ruff check .", "flake8", "pylint"],
       "format_cmd": ["ruff format .", "black .", "autopep8"]
     }
   }
   ```

   `generic.json` omits the block. In `tui.py` Screen 1, when
   `template.data["_meta"].get("command_options")` provides a list for a field,
   render `questionary.select` (detected/template default pre-selected) plus a
   final "Custom…" choice falling through to `questionary.text`; otherwise keep
   the existing `questionary.text`. Alternatives mirror the language lists in
   `skills/init/interactive.md`. Keeping data in templates keeps `tui.py`
   generic (no hardcoded language switch).

2. **Extend the feature checklist (`tui.py`).** Add `github_sync`,
   `confidence_gate`, `tdd` to `_FEATURE_CHOICES` / `_FEATURE_LABELS`, default
   **unchecked** (opt-in, matching the skill's Round 3a). In `_build_final_config`:
   - `github_sync` → `config["sync"] = {"enabled": True}`
   - `confidence_gate` → `config["commands"]["confidence_gate"] = {"enabled": True, "readiness_threshold": 85}`
   - `tdd` → `config["commands"]["tdd_mode"] = True`
   (create/merge a single `commands` block).

3. **Design-token profile picker (`tui.py`).** When `design_tokens` is selected,
   add a follow-up `questionary.select` (profiles discovered from
   `templates/design-tokens/profiles/`: `default`, `editorial-mono`,
   `warm-paper`) plus a "Custom path…" option. Write
   `design_tokens = {"enabled": True, "path": <path>, "active": <profile>}` and
   pass `active_profile=<profile>` to the existing `deploy_design_tokens(...)`
   call in `_apply_config` (param already exists, `writers.py:268`).

4. **Document auto-detection — new `detect.py` helper.** Add
   `detect_documents(project_root: Path) -> dict` globbing the same patterns the
   skill uses (arch: `**/architecture*.md`, `**/design*.md`, `**/api*.md`,
   `docs/*.md`; product: `**/goal*.md`, `**/roadmap*.md`, `**/vision*.md`,
   `**/requirements*.md`), excluding `.git`/`node_modules`/issues dir, returning
   a `categories` dict. When `documents` is selected, populate
   `config["documents"] = {"enabled": True, "categories": <detected>}` and show
   discovered files in the summary panel.

5. **Scan + parallel + session-digest prompts (`tui.py`).**
   - New **Scan** screen: `focus_dirs` (text, pre-filled comma-joined from
     template) and confirm "Add custom exclude patterns?" → text appended to
     template `exclude_patterns`.
   - `worktree_copy_files`: when `parallel` selected, a `questionary.checkbox`
     (.env / .env.local / .secrets) after the worker-count prompt →
     `parallel.worktree_copy_files`.
   - Session digest: a `questionary.confirm` ("Enable ambient session digest?",
     default True) → pass `session_digest_enabled` into `build_config` (already
     supported, `core.py:87`). Keep `char_cap` at `1200` (matches live config
     and `core.py`); the skill's `800` is stale — standardize on `1200`.

6. **Settings target "Skip" (`tui.py`).** Add a third `questionary.Choice`
   "Skip — don't write tool permissions" (value `skip`) to the Screen 4 select.
   In `_apply_config`, skip the `merge_settings(...)` call when
   `settings_target == "skip"`, and reflect it in the summary.

7. **Screen renumbering & summary.** Reflow rule headers (~6 screens: Project
   Basics → Scan → Features → Hosts → Settings → CLAUDE.md) and extend
   `_render_summary` to show sync / commands / design-token profile / documents
   categories / worktree files / session-digest rows.

## Scope Boundaries

- **In scope**: New/extended TUI prompts and `_build_final_config` /
  `_render_summary` / `_apply_config` logic in `tui.py`; `detect_documents()` in
  `detect.py`; `_meta.command_options` in the 8 project-type templates.
- **Out of scope**: The ENH-1982 stub conversion of `skills/init/SKILL.md`
  itself (this change is its prerequisite). The headless
  `--yes`/`--plan`/`apply` defaults (already adequate; only the interactive
  question set is expanded).

## Integration Map

### Files to Modify
- `scripts/little_loops/init/tui.py` — new prompts, extended `_FEATURE_CHOICES`,
  enriched `_build_final_config` & `_render_summary`, profile/scan/worktree/digest
  screens, settings "skip".
- `scripts/little_loops/init/detect.py` — add `detect_documents()`
  (`TemplateMatch` already exposes `.data` for `_meta.command_options`).
- `templates/*.json` (8 project-type templates) — add `_meta.command_options`.

### Dependent / Verify-Only Files
- `scripts/little_loops/init/writers.py` — no signature changes
  (`deploy_design_tokens` already takes `active_profile`); verify
  `merge_settings` is cleanly skippable.
- `scripts/little_loops/init/core.py` — no change expected (`build_config`
  already supports `session_digest_enabled`); confirm `--yes` defaults
  unaffected.

### Tests
- `scripts/tests/test_init_tui.py` — mock new questionary prompts (curated
  selects, profile picker, scan/worktree/digest, settings-skip); assert each
  toggle produces the expected config keys and `--yes` config is unchanged.
- `scripts/tests/test_init_core.py` — new `detect_documents` test; confirm all
  9 templates still load with the new `_meta` block.

## Implementation Steps

1. Add `_meta.command_options` to the 8 project-type templates; leave
   `generic.json` without it.
2. Add `detect_documents()` to `detect.py` with a unit test.
3. Extend `_FEATURE_CHOICES` / `_FEATURE_LABELS` and `_build_final_config` for
   `github_sync` / `confidence_gate` / `tdd`.
4. Add curated command-menu rendering to Screen 1; design-token profile picker;
   Scan screen; worktree-copy checkbox; session-digest confirm; settings "skip".
5. Extend `_render_summary` for all new rows; reflow screen numbering.
6. Add TUI unit tests mocking every new prompt; assert config keys and `--yes`
   invariance.
7. Run regression + lint + mypy.

## Acceptance Criteria

- Running `ll-init` interactively can produce `sync`,
  `commands.confidence_gate`, `commands.tdd_mode`, `design_tokens.active`/`path`,
  `documents.categories`, `parallel.worktree_copy_files`, custom scan
  `focus_dirs`/`exclude_patterns`, session-digest toggle, and settings-skip.
- Curated command menus appear for templates that define `_meta.command_options`,
  with a "Custom…" fallthrough; `generic.json` still uses free text.
- `detect_documents()` globs arch/product docs into a `categories` dict.
- `ll-init --yes` config is byte-unchanged from current behavior.
- For a Python project, the keys `ll-init` now writes are a superset of
  `/ll:init`'s interactive output for equivalent answers — no section
  unreachable.
- New unit tests pass; `ruff check scripts/` and
  `python -m mypy scripts/little_loops/init/` pass.

## Verification

1. `python -m pytest scripts/tests/test_init_tui.py scripts/tests/test_init_core.py -v`
2. `python -m pytest scripts/tests/test_init_core.py -k detect` (template
   integrity with new `_meta` block).
3. Manual smoke: `cd /tmp/ll-init-smoke && git init && ll-init -C .` — walk the
   wizard, exercise curated menus, profile pick, document auto-detect,
   settings-skip; inspect written `.ll/ll-config.json`.
4. Parity spot-check vs `/ll:init` interactive output for a Python project.
5. Regression: `python -m pytest scripts/tests/test_wiring_init_and_configure.py`
   and `ruff check scripts/ && python -m mypy scripts/little_loops/init/`.

## Impact

- **Priority**: P2 — hard prerequisite for ENH-1982 (skill deprecation); blocks
  it.
- **Effort**: Medium — concentrated in `tui.py` + `detect.py` + 8 template JSONs;
  no `writers.py`/`core.py` signature changes.
- **Risk**: Low-medium — `--yes` path is untouched; risk is isolated to new
  interactive prompts and template parsing.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-11 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-06-11T19:06:19 - `6629f98d-c43f-4ffa-bfee-4e29baead61f.jsonl`
- `/ll:capture-issue` - 2026-06-11T19:02:25Z - `6629f98d-c43f-4ffa-bfee-4e29baead61f.jsonl`
