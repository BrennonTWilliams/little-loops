---
id: FEAT-2274
type: FEAT
priority: P2
status: open
captured_at: "2026-06-24T22:29:39Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2279
relates_to: [EPIC-2257, BUG-2271, BUG-2273, ENH-2272, BUG-2275, BUG-2276, ENH-2277, BUG-938, BUG-885]
decision_ref: ARCHITECTURE-053
labels: [feature, packaging, templates, host-compat, cross-host, install]
---

# FEAT-2274: Package host-agnostic templates into the wheel (cross-host delivery)

## Summary

The `templates/` directory lives at the repo root, **outside** the packaged
`little_loops/` tree, so the pip wheel does not contain it. Today it reaches
users only because Claude Code's `marketplace.json` (`"source": "./"`) pulls the
entire repo root — a **Claude-Code-specific** delivery path. Every other host on
the roadmap (Codex `~/.codex/skills/`, Gemini per EPIC-2178, oh-my-pi/omp per
EPIC-2258) installs via `pip install little-loops` and adapts skills into
host-specific locations; none of them deliver `templates/`, and none set
`${CLAUDE_PLUGIN_ROOT}`.

`templates/*` is **package data consumed by the package's own CLI code**
(`load_issue_sections()` in `sync.py`/`issue_parser.py`; `detect_project_type()`,
`deploy_goals()`, `deploy_design_tokens()` in `ll-init`), not a host-plugin
artifact. Data the wheel's code reads should ship in the wheel. Package the
host-agnostic `templates/` into the wheel so `ll-init`, section loading, and
design-token/goals deploy work identically on every host through the one
substrate they all share — the pip package. This is the structural enabler that
makes BUG-2271 / BUG-2273 / ENH-2272's resolvers robust without depending on
`${CLAUDE_PLUGIN_ROOT}`.

Ratified direction (this session): **Both** — package into the wheel as the
universal seed/fallback **and** keep the `.ll/templates/` project deploy
(ENH-2272) for per-project customization.

## Motivation

- **Cross-host correctness**: pip is the only delivery mechanism common to
  Codex / Gemini / omp; the wheel must be self-sufficient for the data its own
  code reads. Without this, `ll-init` and issue-section loading are broken for
  every non-Claude host (see BUG-2273, BUG-2271).
- **Resolver simplification**: once `templates/` is in-package,
  `Path(__file__).parent / "templates"` resolves in editable **and** non-editable
  installs, on every host, with no env-var dependency. The
  `${CLAUDE_PLUGIN_ROOT}` tier demotes from load-bearing to optional fallback.
- **Correct consume-side boundary**: distinguishes host-plugin assets
  (`skills/`, `commands/`, `agents/`, `hooks/` — adapted per host, correctly kept
  out of the wheel by BUG-938) from package-data templates the CLIs import.

## Scope

In scope — all host-agnostic package data consumed by CLI/hook code:

- `*-sections.json` (bug/feat/enh/epic) — `load_issue_sections()`
- project-type configs (`python-generic.json`, `typescript.json`, `go.json`,
  `rust.json`, `java-*.json`, `dotnet.json`, `javascript.json`, `generic.json`) —
  `detect_project_type()`
- `design-tokens/` — `deploy_design_tokens()`
- `ll-goals-template.md` — `deploy_goals()`
- `extension/` — `ll-create-extension` scaffolding
- `hooks/prompts/optimize-prompt-hook.md` — read by
  `hooks/user_prompt_submit.py` (**BUG-2275**)
- `hooks/adapters/codex/hooks.json` (and any other consumed adapter templates) —
  read by `init/writers.py:install_codex_adapter()` (**BUG-2275**)
- `assets/ll-cli-logo.txt` — read by `logo.py:get_logo()` (**BUG-2276**)

The unifying rule (ARCHITECTURE-053): *data the wheel's own code reads ships in
the wheel*, regardless of which repo-root dir it currently lives under. The
three additions above were missed in the initial scoping; they are the same
package-data class as `templates/`, just under `hooks/` and `assets/`.

Out of scope (host-plugin assets adapted per host; stay out of the wheel,
BUG-938 stance unchanged):
- `skills/`, `commands/`, `agents/`, `.claude-plugin/`
- host-plugin glue under `hooks/` that is *not* read by package code
  (e.g. `hooks/hooks.json`, host launcher/adapter shell scripts) — only the
  asset files package code imports move in.

## Proposed Solution

Two viable mechanisms — decide during implementation:

1. **`git mv templates → scripts/little_loops/templates/`** (preferred; the
   BUG-885 / BUG-938 precedent). Then `packages = ["little_loops"]` bundles it
   automatically, and every resolver becomes `Path(__file__).parent / "templates"`
   — robust for editable and non-editable installs alike. Requires updating the
   handful of repo-root `templates/` references (e.g. loop YAMLs under
   `little_loops/loops/`, `loops/README.md`) and the Claude-context
   `${CLAUDE_PLUGIN_ROOT}/templates` path to the new sub-path.
2. **Hatch `force-include`** mapping `../templates` → `little_loops/templates`.
   Keeps the repo-root layout but can behave inconsistently under editable
   installs; the resolver would need to try both locations.

Either way, update the shared resolver (BUG-2271 / ENH-2272) so the in-package
location is the primary bundled source, with `.ll/templates/` (customization) and
`config.issues.templates_dir` (override) layered above it.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_template.py` — `_default_templates_dir()` → in-package.
- `scripts/little_loops/init/cli.py` — `_plugin_root()` / `templates_dir` → in-package.
- `scripts/little_loops/init/detect.py` — `_find_templates_dir()` → in-package.
- `scripts/pyproject.toml` — `git mv` needs no change (covered by
  `packages = ["little_loops"]`); `force-include` needs a wheel-target stanza.
- Repo-root `templates/` references: `little_loops/loops/*.yaml`,
  `loops/README.md`, any Claude-context `${CLAUDE_PLUGIN_ROOT}/templates` path.

### Directories to Move (if mechanism 1)
- `templates/` → `scripts/little_loops/templates/`

### Similar Patterns
- BUG-885 — moved `loops/` into the package to fix the identical wheel-exclusion
  class; `cli/loop/_helpers.py:get_builtin_loops_dir()`.
- BUG-938 — set the host-plugin-vs-package-data line this issue refines.

### No Changes Needed
- `skills/` / `commands/` / `agents/` / `hooks/` packaging — stay plugin-delivered.

## Implementation Steps

1. Decide mechanism (git mv vs force-include); if git mv, move the tree.
2. Point all three resolvers at the in-package `templates/`; share one helper.
3. Update repo-root `templates/` references and the `${CLAUDE_PLUGIN_ROOT}`
   sub-path.
4. Build the wheel and assert `unzip -l dist/*.whl | grep templates/` shows the
   files; install non-editable in a clean venv and run `ll-init --yes` end-to-end
   (design tokens + goals deploy; correct project-type detection).
5. Run `python -m pytest scripts/tests/`; verify BUG-2271 / BUG-2273 reproduction
   steps now pass without `CLAUDE_PLUGIN_ROOT`.

## Acceptance Criteria

- `pip install little-loops` (non-editable) + `ll-init` in a target project, in a
  plain shell with `CLAUDE_PLUGIN_ROOT` unset, deploys design tokens + goals and
  detects project type correctly.
- `ll-issues sections <type>` and `load_issue_sections()` resolve with no env var
  set, on a non-editable install.
- `unzip -l` of the built wheel lists the `templates/` tree under `little_loops/`.
- Host-plugin assets (`skills/` etc.) remain absent from the wheel (BUG-938
  preserved).

## Impact

- **Priority**: P2 — unblocks correct onboarding for every non-Claude host on the
  generalization roadmap; without it BUG-2271 / BUG-2273 can only be partially fixed.
- **Effort**: Medium — mechanical move + reference updates + resolver + packaging
  verification.
- **Risk**: Medium — touches packaging and a repo-root directory move; editable
  installs and Claude plugin delivery must both keep working (verify both).
- **Breaking Change**: No (internal layout / packaging).

## Related

- EPIC-2257 — parent; cross-host shared infrastructure owner.
- BUG-2271 — section-template resolver; consumes the in-package location this adds.
- BUG-2273 — `ll-init` resolver; same.
- ENH-2272 — `ll-issues sections` accessor + `.ll/templates/` deploy (the "deploy"
  half of Both).
- BUG-938 — closed invalid; this refines its rule to "host-plugin assets stay out
  of the wheel; package-data templates go in."
- BUG-885 — precedent for moving package-consumed assets into the package.

## Labels

`feature`, `packaging`, `templates`, `host-compat`, `cross-host`, `install`

## Session Log
- `/ll:capture-issue` - 2026-06-24T22:29:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d34d610-c8b9-4a5e-82c8-191296760b6d.jsonl`
