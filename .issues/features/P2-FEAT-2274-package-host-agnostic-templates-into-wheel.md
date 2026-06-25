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
decision_needed: false
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

## Current Behavior

The `templates/` directory lives at the repo root, outside the packaged `little_loops/` Python tree. When installed via `pip install little-loops` (non-editable), the wheel does not include this directory. Host-specific resolvers (`_default_templates_dir()`, `_plugin_root()`, `_find_templates_dir()`) rely on `${CLAUDE_PLUGIN_ROOT}` or `__file__`-traversal heuristics that only work under Claude Code's plugin delivery model. Every non-Claude host (Codex, Gemini, omp) receives the wheel without templates, causing `ll-init`, `load_issue_sections()`, `detect_project_type()`, and `deploy_design_tokens()` to fail or silently error when `CLAUDE_PLUGIN_ROOT` is unset.

## Expected Behavior

The `templates/` directory — along with related host-agnostic assets under `hooks/prompts/`, `hooks/adapters/codex/`, and `assets/` — ships inside the wheel as `little_loops/templates/`. A plain `pip install little-loops` (non-editable, no `CLAUDE_PLUGIN_ROOT` set) provides all data the CLI code reads. All resolvers default to the in-package location (`Path(__file__).parent / "templates"`), with `.ll/templates/` (per-project customization) layered above it as an override.

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

> **Selected:** Option 1 — git mv templates → scripts/little_loops/templates/ — matches BUG-885 precedent exactly; zero pyproject.toml changes; single-tier resolver simplicity (score 9/12 vs 3/12 for force-include).

2. **Hatch `force-include`** mapping `../templates` → `little_loops/templates`.
   Keeps the repo-root layout but can behave inconsistently under editable
   installs; the resolver would need to try both locations.

Either way, update the shared resolver (BUG-2271 / ENH-2272) so the in-package
location is the primary bundled source, with `.ll/templates/` (customization) and
`config.issues.templates_dir` (override) layered above it.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-24.

**Selected**: Option 1 — git mv templates → scripts/little_loops/templates/

**Reasoning**: The BUG-885 precedent (moving `loops/` inside the package) is directly reusable here: `pyproject.toml`'s `include = ["little_loops/**"]` already covers all subdirectories, so the `git mv` requires zero build config changes. Option 2 (Hatch force-include) has zero precedent in this codebase, explicitly behaves inconsistently under editable installs, and would require adding a new third-tier resolver across four files from scratch.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 — git mv | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| Option 2 — force-include | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- **Option 1**: `get_builtin_loops_dir()` at `scripts/little_loops/cli/loop/_helpers.py:822` is the direct BUG-885 precedent; `pyproject.toml:114` (`include = ["little_loops/**"]`) already covers new subdirectories with zero changes; three resolver functions need mechanical hop-count updates.
- **Option 2**: No `force-include` stanza exists anywhere in this project; no dual-location resolver pattern exists in any module; the BUG-885 precedent explicitly used the git mv approach.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/logo.py` — `get_logo()` uses `parent.parent.parent / "assets"` traversal; FEAT-2274's git mv of `assets/ll-cli-logo.txt` makes this path stale (BUG-2276 owns the resolver fix; listed here as a breakage dependency) [Agent 1 finding]
- `scripts/little_loops/hooks/user_prompt_submit.py` — `_PROMPT_FILE` uses `parents[3] / "hooks" / "prompts"` traversal; FEAT-2274's git mv of `hooks/prompts/optimize-prompt-hook.md` makes this path stale (BUG-2275 owns the resolver fix; listed here as a breakage dependency) [Agent 2 finding]
- `scripts/little_loops/init/writers.py` — `install_codex_adapter()` constructs `plugin_root / "hooks" / "adapters" / "codex" / "hooks.json"`; path resolves correctly once `_plugin_root()` in `init/cli.py` is updated to resolve to `little_loops/` [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — directory tree (lines ~186–206) lists `templates/` subtree at repo root; Mermaid diagram has `TPL[templates/*.json]`; hooks tree lists `hooks/prompts/optimize-prompt-hook.md` and `hooks/adapters/codex/hooks.json` — all become stale after git mv [Agent 2 finding]
- `CONTRIBUTING.md` — line ~161 directory tree entry `├── templates/ # Project-type config templates` becomes stale after move [Agent 2 finding]
- `.claude/CLAUDE.md` — Key Directories section lists `templates/ # Project-type config templates` at repo root [Agent 2 finding]
- `docs/reference/OUTPUT_STYLING.md` — Logo section describes "Reads ASCII art from `assets/ll-cli-logo.txt`"; path changes to `scripts/little_loops/assets/ll-cli-logo.txt` after move [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — diagnostic step `ls -la hooks/prompts/optimize-prompt-hook.md` references old repo-root path; update to `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md` [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — `user_prompt_submit` section references `hooks/prompts/optimize-prompt-hook.md` by old path [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_design_tokens.py` — `TestIntegration._TEMPLATE_DIR` (line ~336) and `_make_config_from_template()` (line ~371) both compute `Path(__file__).parent.parent.parent / "templates" / "design-tokens"`; resolves to nonexistent path after git mv — update to `Path(__file__).parent.parent / "little_loops" / "templates" / "design-tokens"` [Agent 2/3 finding]
- `scripts/tests/test_codex_adapter.py` — module-level `ADAPTER_DIR = REPO_ROOT / "hooks" / "adapters" / "codex"` drives five test methods that check `hooks.json`; `hooks.json` moves to `scripts/little_loops/hooks/adapters/codex/hooks.json` — all five methods break [Agent 1/3 finding]
- `scripts/tests/test_hooks_integration.py` — `test_optimization_template_injected_when_claude_plugin_root_set` exercises bash shim for `optimize-prompt-hook.md`; investigate whether shim uses `SCRIPT_DIR/../prompts/` (safe) or `$CLAUDE_PLUGIN_ROOT/hooks/prompts/` (breaks after move) [Agent 3 finding]

### Skill / Command Instructions

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/areas.md` — contains `shutil.copytree('templates/design-tokens/profiles', ...)` Python snippet (CWD-relative path); update to `scripts/little_loops/templates/design-tokens/profiles` after git mv [Agent 2 finding]
- `skills/capture-issue/SKILL.md`, `skills/format-issue/SKILL.md`, `skills/format-issue/templates.md`, `skills/scope-epic/SKILL.md`, `commands/scan-codebase.md`, `commands/ready-issue.md` — reference `templates/{type}-sections.json` as a CWD-relative Read path; after git mv the repo root has no `templates/` — update references to `scripts/little_loops/templates/{type}-sections.json` [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Resolver inventory (FEAT-2274 owns items 1–3; companions own 4–6):**

| Resolver | File | Current `__file__` traversal | Post-move traversal |
|---|---|---|---|
| `_default_templates_dir()` | `scripts/little_loops/issue_template.py` | `.parent×3` → repo root | `.parent` → `little_loops/` |
| `_find_templates_dir()` | `scripts/little_loops/init/detect.py` | `.parent×4` → repo root | `.parent.parent` → `little_loops/` |
| `_plugin_root()` → `/ "templates"` | `scripts/little_loops/init/cli.py` | `.parent×4` → repo root | replace caller with shared helper |
| `_PROMPT_FILE` constant | `scripts/little_loops/hooks/user_prompt_submit.py` | `.parents[3]` → repo root | BUG-2275 owns resolver change |
| `get_logo()` | `scripts/little_loops/logo.py` | `.parent×3` → repo root | BUG-2276 owns resolver change |
| `install_codex_adapter()` | `scripts/little_loops/init/writers.py` | receives `plugin_root` parameter | fixed when BUG-2275 updates `_plugin_root()` caller |

**pyproject.toml — confirmed no change needed with Option 1 (git mv):**
`[tool.hatch.build.targets.wheel]` is `packages = ["little_loops"]` + `include = ["little_loops/**", "LICENSE"]`. Once `templates/` moves inside `little_loops/`, it is bundled automatically — identical mechanism to `little_loops/loops/**` (BUG-885 precedent confirmed). Option 2 (force-include) would require adding a `[tool.hatch.build.targets.wheel.force-include]` stanza.

**Loop YAML references — confirmed no updates needed:**
All `templates/` mentions in loop YAMLs are `.issues/templates/*` exclusion globs in `find` commands (project `.issues/` subtree — unrelated to the top-level `templates/` package directory). `scripts/little_loops/loops/README.md` references `lib/task-templates/` (loop-internal YAML fragments, already inside the package). The issue's current Integration Map mention of `little_loops/loops/*.yaml` needing updates is **incorrect** — no loop YAML edits required.

**Test files that need updating (not yet listed in this issue):**
- `scripts/tests/test_init_core.py` `templates_dir` fixture (lines 48–54): `_PROJECT_ROOT / "templates"` must point inside the package post-move, e.g. `Path(importlib.resources.files("little_loops")).joinpath("templates")` or `Path(little_loops.__file__).parent / "templates"`
- `scripts/tests/test_init_core.py:TestPluginRoot.test_falls_back_to_file_path` — asserts `.parent×4` expected path; must update to new traversal depth
- `scripts/tests/test_init_core.py:TestFindTemplatesDir.test_falls_back_to_file_path` — asserts `.parent×4`; update to `.parent.parent`
- `scripts/tests/test_issue_template.py:test_falls_back_to_file_relative` — exercises `_default_templates_dir()` traversal; must remain green after resolver update

**Shared helper (BUG-885 pattern):**
Introduce `get_bundled_templates_dir() -> Path` returning `Path(__file__).parent / "templates"` (where `__file__` is the helper's module, inside `little_loops/`). Mirrors `get_builtin_loops_dir()` at `scripts/little_loops/cli/loop/_helpers.py:822`. Suggested location: `scripts/little_loops/issue_template.py` (alongside `_default_templates_dir()`) or a new `scripts/little_loops/_package_data.py` shared by all three resolvers.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete per-step details:_

**Step 1 — git mv is the preferred mechanism:** `pyproject.toml` already covers `little_loops/**` with no config changes needed. Also move the other package-data files in the same commit:
- `git mv assets/ll-cli-logo.txt scripts/little_loops/assets/ll-cli-logo.txt`
- `git mv hooks/prompts/optimize-prompt-hook.md scripts/little_loops/hooks/prompts/optimize-prompt-hook.md`
- `git mv hooks/adapters/codex/hooks.json scripts/little_loops/hooks/adapters/codex/hooks.json`
(FEAT-2274 owns all four moves; BUG-2275 / BUG-2276 own the companion resolver changes for the last three.)

**Step 2 — exact resolver changes:**
- `issue_template.py:_default_templates_dir()`: `Path(__file__).resolve().parent.parent.parent / "templates"` → `Path(__file__).resolve().parent / "templates"` (templates become sibling directory inside `little_loops/`)
- `init/detect.py:_find_templates_dir()`: `Path(__file__).resolve().parent.parent.parent.parent / "templates"` → `Path(__file__).resolve().parent.parent / "templates"` (`detect.py` → `init/` → `little_loops/` → `templates/`)
- `init/cli.py:main_init()`: replace `plug_root / "templates"` with a direct call to the shared `get_bundled_templates_dir()` helper; keep `_plugin_root()` untouched (BUG-2275 will update it for the codex adapter path separately)

**Step 3 — test file updates required:**
- `test_init_core.py` `templates_dir` fixture: update `_PROJECT_ROOT / "templates"` to point inside the installed package
- `test_init_core.py:TestPluginRoot.test_falls_back_to_file_path` and `TestFindTemplatesDir.test_falls_back_to_file_path`: update expected traversal depths

**Step 4 — wheel smoke test command:**
```bash
python -m build scripts/ --wheel && unzip -l dist/little_loops-*.whl | grep -E "(templates|assets)/"
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_design_tokens.py` — fix `TestIntegration._TEMPLATE_DIR` and `_make_config_from_template()` hard-coded `parent×3 / "templates" / "design-tokens"` constants to new in-package path (`parent×2 / "little_loops" / "templates" / "design-tokens"`)
7. Update `scripts/tests/test_codex_adapter.py` — fix `ADAPTER_DIR = REPO_ROOT / "hooks" / "adapters" / "codex"` to resolve `hooks.json` from new `scripts/little_loops/hooks/adapters/codex/` location; all five JSON-reading test methods depend on it
8. Investigate `scripts/tests/test_hooks_integration.py:test_optimization_template_injected_when_claude_plugin_root_set` — confirm bash shim resolves `optimize-prompt-hook.md` via `SCRIPT_DIR/../prompts/` (safe) vs `$CLAUDE_PLUGIN_ROOT/hooks/prompts/` (breaks); fix if latter
9. Update documentation directory trees — `docs/ARCHITECTURE.md` (Mermaid diagram + directory tree), `CONTRIBUTING.md` (line ~161), `.claude/CLAUDE.md` (Key Directories); update `docs/reference/OUTPUT_STYLING.md` logo path prose; update `docs/development/TROUBLESHOOTING.md` diagnostic `ls` step; update `docs/guides/BUILTIN_HOOKS_GUIDE.md` prompt-file path reference
10. Update `skills/configure/areas.md` — fix `shutil.copytree('templates/design-tokens/profiles', ...)` snippet to `scripts/little_loops/templates/design-tokens/profiles`
11. Update skill/command instruction files with CWD-relative `templates/{type}-sections.json` paths — `skills/capture-issue/SKILL.md`, `skills/format-issue/SKILL.md`, `skills/format-issue/templates.md`, `skills/scope-epic/SKILL.md`, `commands/scan-codebase.md`, `commands/ready-issue.md`

## Use Case

A developer sets up little-loops on a Codex or Gemini host. They run `pip install little-loops` in a fresh virtual environment — no repo clone, no `CLAUDE_PLUGIN_ROOT` — and then execute `ll-init` in their project. They expect design tokens to deploy, project type to be detected, and issue-section templates to load. Currently this fails silently because the wheel ships without `templates/`. After this feature, the wheel is self-sufficient: `ll-init` completes successfully on every supported host through the one delivery mechanism they all share.

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

## Status

**Open** | Created: 2026-06-24 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-2274 owns the packaging `git mv` of `hooks/prompts/optimize-prompt-hook.md`, `hooks/adapters/codex/hooks.json`, and `assets/ll-cli-logo.txt` into the wheel (the "wheel" half of the Both decision). Related issues own complementary — non-overlapping — work: [BUG-2275] owns resolver changes + warning behavior + Bash script path update (`hooks/scripts/user-prompt-check.sh`) + template substitution decisions; [BUG-2276] owns the path fix in `logo.py:get_logo()` + test + doc update. Neither BUG-2275 nor BUG-2276 should perform the `git mv` independently.

## Session Log
- `/ll:wire-issue` - 2026-06-25T04:25:00 - `9a8ff45c-72c4-436a-a3dd-5e842eb87e61.jsonl`
- `/ll:decide-issue` - 2026-06-25T04:15:30 - `7d489730-0081-4f8f-9a5b-aac0cb779c57.jsonl`
- `/ll:refine-issue` - 2026-06-25T04:09:36 - `18bb767c-bb64-42b8-87dd-2614b8c50967.jsonl`
- `/ll:format-issue` - 2026-06-25T03:58:38 - `06ffb4c9-80f3-4642-b0d8-8f65d0237b1c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-25T01:15:24 - `4d9c6bcd-b580-4f4a-bc4f-3993c0160aa9.jsonl`
- `/ll:capture-issue` - 2026-06-24T22:29:39Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d34d610-c8b9-4a5e-82c8-191296760b6d.jsonl`
