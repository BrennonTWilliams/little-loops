---
id: ENH-2272
type: ENH
priority: P3
status: done
size: Very Large
captured_at: '2026-06-24T22:17:07Z'
discovered_date: 2026-06-24
discovered_by: capture-issue
parent: EPIC-2279
relates_to:
- BUG-2271
- BUG-2273
- FEAT-2274
confidence_score: 94
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 18
decision_needed: false
---

# ENH-2272: ll-issues sections accessor + project-local template deploy

## Summary

Six skill/command files instruct the LLM, in prose, to read
`templates/{type}-sections.json` "relative to the little-loops plugin
directory." In a target project (not the little-loops repo), the LLM has no
anchor for that path and falls back to a filesystem-wide `find /` — observed
taking ~1 minute on a single `/ll:format-issue` run. Add a dedicated
`ll-issues sections` accessor backed by a unified resolver, deploy default
section templates into the project via `ll-init`, and rewrite the six callsites
to call the CLI instead of searching the filesystem. This also makes
"bring your own templates" the default, editable path rather than a config knob.

## Motivation

- **Latency**: the "relative to the plugin directory" prose forces a
  filesystem walk; replacing it with one deterministic CLI call collapses ~60s
  to ~50ms.
- **Portability**: a CLI accessor works identically across hosts
  (claude-code / codex / opencode) and does not depend on the LLM knowing where
  the plugin lives or on `${CLAUDE_PLUGIN_ROOT}` being exported into the skill's
  bash context.
- **Customization as default**: deploying `*-sections.json` into `.ll/templates/`
  (skip-if-exists, like `deploy_goals` / `deploy_design_tokens`) lets users edit
  their own issue templates in-project with no `issues.templates_dir` config
  indirection, and survives plugin upgrade/uninstall.
- **Single source of resolution**: the precedence logic lives in one resolver
  instead of being re-encoded as prose/bash in every skill.

## Current Behavior

Callsites that tell the LLM to read the per-type section JSON relative to the
plugin directory:

- `skills/format-issue/SKILL.md` (Steps 3, 3.5 — lines ~196, ~221)
- `skills/format-issue/templates.md` (lines 7, 52, 54)
- `skills/capture-issue/SKILL.md` (line ~276)
- `skills/scope-epic/SKILL.md` (lines ~296, ~358)
- `commands/ready-issue.md` (line ~139)
- `commands/scan-codebase.md` (lines ~241, ~243)

`issues.templates_dir` already exists in config/schema (`config-schema.json:122`,
`config/features.py:200`) but defaults to `null` — and null is exactly the case
that triggers the filesystem search. There is no CLI to resolve the default
location, and no project-local copy.

## Expected Behavior

After the enhancement ships:
- `ll-issues sections <type>` resolves and prints the per-type section JSON in ~50ms (deterministic, no filesystem walk).
- `ll-issues sections <type> --path` prints only the absolute path to the resolved JSON file.
- All six callsites in skills/commands invoke `ll-issues sections` directly, removing the "relative to the plugin directory" prose and eliminating the ~60s `find /` fallback.
- The resolver works identically across claude-code, codex, and opencode hosts with no `CLAUDE_PLUGIN_ROOT` dependency.
- `ll-init` offers an opt-in step that copies bundled `*-sections.json` into `.ll/templates/` (skip-if-exists); when absent, the resolver falls through to the in-package bundle provided by FEAT-2274.

## Proposed Solution

### 1. Unified template resolver (precedence)

Introduce one resolver (shared with BUG-2271 / BUG-2273) used by the new CLI and
the existing Python loaders (`sync`, `issue_parser`). Under the **Both (wheel +
deploy)** decision (ARCHITECTURE-053), the in-package bundle (added by
FEAT-2274) is the primary source, so the resolver always succeeds with no
env-var dependency:

1. `config.issues.templates_dir` — explicit override (power users / shared dir)
2. `.ll/templates/` — deployed by `ll-init` (per-project customization)
3. in-package `Path(__file__).parent / "templates"` — bundled in the wheel by
   FEAT-2274 (works on every host, no `CLAUDE_PLUGIN_ROOT` needed)
4. `${CLAUDE_PLUGIN_ROOT}/templates` / `__file__`-to-repo-root — fallbacks
   (Claude plugin context / editable-dev)

### 2. `ll-issues sections` subcommand

```
ll-issues sections <bug|feat|enh|epic>   # print the resolved section JSON to stdout
ll-issues sections <type> --path         # print only the absolute path to the JSON file
```

Walks the precedence above and prints the JSON (or path). Mirrors the existing
`ll-issues path` pattern already used by `format-issue`. Registered in
`cli/issues/__init__.py` like the other subcommands.

### 3. `ll-init` deploy of default templates

Add an opt-in (default off) feature that copies the bundled `*-sections.json`
into `.ll/templates/` using skip-if-exists semantics, mirroring
`deploy_goals` / `deploy_design_tokens` in `init/writers.py`. Off-by-default
keeps projects that never customize templates clean; the resolver still works
via precedence steps 3–4 when no local copy exists.

### 4. Rewrite the six callsites

Replace "read `templates/{type}-sections.json` relative to the plugin
directory" with "run `ll-issues sections {type}`" (or
`ll-issues sections {type} --path` then Read, where the skill wants the file on
disk). Remove the "relative to the little-loops plugin directory" phrasing
entirely.

## API/Interface

New CLI surface on `ll-issues`:
- `ll-issues sections <type>` → stdout: section-definition JSON for `<type>`
- `ll-issues sections <type> --path` → stdout: absolute path to the JSON file
- Exit non-zero with a clear message if `<type>` is invalid or no templates dir
  resolves.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `sections` subcommand
  + dispatch.
- `scripts/little_loops/cli/issues/sections.py` (new) — `cmd_sections`.
- `scripts/little_loops/issue_template.py` — unified resolver consumed by the CLI
  and existing loaders (builds on BUG-2271).
- `scripts/little_loops/init/writers.py` — `deploy_issue_templates()` (skip-if-exists); also add `sections` to `_CLAUDE_MD_COMMANDS_BLOCK` (line ~83) so `ll-init`-generated CLAUDE.md blocks include the new subcommand.
- `scripts/little_loops/init/cli.py` — wire deploy into the init flow behind a
  feature flag.
- `scripts/little_loops/init/tui.py` — add `deploy_issue_templates()` call in `_apply_config()` (line ~847) alongside existing `deploy_goals` / `deploy_design_tokens` calls; add to inline import block. [Wiring]
- `scripts/little_loops/init/__init__.py` — add `deploy_issue_templates` to `from little_loops.init.writers import (...)` block and `__all__` list (alongside `deploy_goals`, `deploy_design_tokens`). [Wiring]
- `config-schema.json` / `config/features.py` — feature flag for the deploy (if
  gated).
- `skills/format-issue/SKILL.md`, `skills/format-issue/templates.md`,
  `skills/capture-issue/SKILL.md`, `skills/scope-epic/SKILL.md`,
  `commands/ready-issue.md`, `commands/scan-codebase.md` — swap prose for
  `ll-issues sections`.
- `docs/reference/CLI.md` / `docs/reference/API.md` — document the subcommand.

### Similar Patterns
- `ll-issues path` (`cli/issues/path_cmd.py`) — accessor pattern + skill usage in
  `format-issue`.
- `deploy_goals` / `deploy_design_tokens` (`init/writers.py:240`, `:264`) —
  skip-if-exists project deploy.
- `skill_expander._find_plugin_root()` — env-var-first resolution.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — imports `issue_template.py` resolver; must switch to the shared resolver when BUG-2271 lands.
- `scripts/little_loops/sync.py` — imports `load_issue_sections` at line 21; uses its own 2-tier config resolution at lines 697–700 (`config.issues.templates_dir` or `None`). When ENH-2272 lands, callers passing `None` can switch to `resolve_templates_dir(config)` to gain tiers 2–4; this migration is within BUG-2271 scope (existing-loader correctness), not ENH-2272's.
- Six skill/command files (listed in Files to Modify) — become callers of `ll-issues sections` after callsite rewrite.

### Tests
- New: `scripts/tests/test_ll_issues_sections.py` — JSON output, `--path`, invalid type, and each resolver precedence tier.
- New: `scripts/tests/test_deploy_issue_templates.py` — skip-if-exists semantics, dry-run, feature-flag gating.
- Update: tests covering `ll-init` flow to include the new deploy step.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_template.py` — existing `test_load_custom_dir` and `test_load_missing_file` may break if `load_issue_sections` second-parameter semantics change; add new parametrized tests for the 4-tier resolver precedence in `TestLoadIssueSections`. **Tier-ordering risk**: `test_uses_claude_plugin_root_when_set`, `test_falls_back_to_file_relative`, and `test_load_default_env_var_missing_templates_raises` assume the env-var tier has exclusive priority — if the new `.ll/templates/` tier is checked first and the test CWD has such a dir, these tests break. The resolver MUST check project-local tier only when a config `ll_dir` is explicitly passed (not from CWD), or the tests must explicitly suppress the local tier via monkeypatch.
- `scripts/tests/test_init_core.py` — add `TestDeployIssueTemplates` class (mirror `TestDeployGoals`: `test_deploys_sections`, `test_skips_if_already_exists`, `test_dry_run`, `test_skips_if_template_missing`); add `test_yes_deploys_issue_templates_when_enabled` integration test (follow `test_yes_deploys_design_tokens_when_enabled` pattern — patch `build_config` to inject `issues.deploy_templates: true`).
- `scripts/tests/test_config_schema.py` — add `test_issues_deploy_templates_in_schema` sentinel following `test_issues_auto_commit_in_schema` pattern.
- `scripts/tests/test_init_tui.py` — add `test_deploy_issue_templates_via_tui` following `test_design_tokens_selected_deploys_profiles` pattern (line 215), exercising the `deploy_issue_templates()` call in `_apply_config()` through the full TUI flow.

### Documentation
- `docs/reference/CLI.md` — document `ll-issues sections` subcommand.
- `docs/reference/API.md` — document the unified resolver (`issue_template.py`) and `deploy_issue_templates()`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — add `deploy_templates` row to the `### issues` config table (alongside `templates_dir`).
- `.claude/CLAUDE.md` — add `sections` to the parenthetical `ll-issues` subcommand list (line 233).
- `skills/configure/show-output.md` — the `## issues --show` section displays `templates_dir: {{config.issues.templates_dir}} (default: none)`; add a `deploy_templates: false` display row for the new config key.

### Configuration
- `config-schema.json` — feature flag property for `deploy_issue_templates` (if gated).
- `config/features.py` — register the feature flag constant.

### Packaging (see FEAT-2274)
- `scripts/pyproject.toml` packaging is changed by **FEAT-2274** (templates into
  the wheel), which makes resolver tier 3 always available. This ENH owns the
  accessor + `.ll/templates/` deploy (the "deploy" half of **Both**); FEAT-2274
  owns the "wheel" half.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Existing resolver state (`issue_template.py`):**
- `_default_templates_dir()` (line 15–17): resolves only via `Path(__file__).resolve().parent.parent.parent / "templates"` — no config.issues.templates_dir or `.ll/templates/` lookup. This is the function that must become the fallback tier.
- `load_issue_sections(issue_type, templates_dir=None)` (line 20–37): already accepts an optional `templates_dir` override, but callers must pass it explicitly — no auto-resolution from config.
- `sync.py:697–700`: already passes `config.issues.templates_dir` to `load_issue_sections` when set, but has only 2 tiers (explicit override or `__file__`-based default). The `.ll/templates/` tier is missing.
- **New function needed**: `resolve_templates_dir(config: BRConfig) -> Path` in `issue_template.py` that implements the 4-tier precedence and is consumed by both the new CLI and existing callers.

**Init gating pattern (`init/cli.py:289–293`):**
- `deploy_goals` is gated by `config.get("product", {}).get("enabled")` (not a feature constants file).
- `deploy_design_tokens` is gated by `config.get("design_tokens", {}).get("enabled")`.
- `deploy_issue_templates` should follow the same config-key gating pattern: `config.get("issues", {}).get("deploy_templates")`.
- `config-schema.json:122` already defines `issues.templates_dir`; add `"deploy_templates": {"type": "boolean", "default": false}` as a sibling property under `issues`.

**`init/__init__.py` exports:** `deploy_goals` (line 14) and `deploy_design_tokens` (line 15) are both exported; `deploy_issue_templates` must be added to the same import + `__all__` block (lines 13–22, 24–41).

**`deploy_goals()` signature to mirror (`init/writers.py:240–262`):**
```python
def deploy_issue_templates(ll_dir: Path, templates_dir: Path, dry_run: bool = False) -> bool:
    dest = ll_dir / "templates"
    if dest.exists():
        return False
    src = templates_dir  # bundle containing *-sections.json files
    if not src.exists():
        return False
    if dry_run:
        print(f"[write] {dest}/ (issue section templates)")
        return True
    ll_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("design-tokens", "*.md", "*.toml"))
    return True
```

**Exact callsite prose to replace:**
- `skills/format-issue/SKILL.md:196`: `"templates/{type}-sections.json" v2.0 (relative to the little-loops plugin directory)`
- `skills/format-issue/SKILL.md:221`: `"templates/{type}-sections.json" for the issue's type`
- `skills/format-issue/templates.md:7,52,54`: similar plugin-relative references
- `skills/capture-issue/SKILL.md:~276`: plugin-relative sections JSON reference
- `skills/scope-epic/SKILL.md:~296,~358`: plugin-relative sections JSON reference
- `commands/ready-issue.md:~139`: plugin-relative sections JSON reference
- `commands/scan-codebase.md:~241,~243`: plugin-relative sections JSON reference

**Registration pattern (`cli/issues/__init__.py`):** Each subcommand uses `subs.add_parser("sections", aliases=["sec"], help="...")` + `set_defaults(command="sections")` + `add_argument("type", ...)` + `add_argument("--path", action="store_true")`. Dispatch block at the end of `main_issues()` routes `command == "sections"` to `cmd_sections(config, args)`.

**Test patterns to follow:**
- For the new `test_ll_issues_sections.py`: mirror `test_issues_path.py` — use `patch.object(sys, "argv", ["ll-issues", "sections", "BUG", "--config", str(tmp_dir)])` + call `main_issues()` + `capsys.readouterr()`.
- For `test_deploy_issue_templates.py`: mirror `test_init_core.py:750–806` — create `tmp_path / "ll"` and `tmp_path / "templates"`, populate source files, call `deploy_issue_templates()`, assert destination state.
- For resolver precedence tests: extend `test_issue_template.py:TestLoadIssueSections` with the same parametrized approach, creating stub files in `tmp_path` for each tier.

**`_run_apply()` vs `_run_yes()` asymmetry in `init/cli.py` (confirmed by analysis):**
- `_run_yes()` (lines 298–305): calls both `deploy_goals` and `deploy_design_tokens` — note existing research said lines 289–293, but actual lines are 298–305.
- `_run_apply()` (lines 434–435): calls **only** `deploy_goals` — `deploy_design_tokens` is absent from this path.
- Implementer decision point: mirror the `deploy_design_tokens` precedent (add to `_run_yes()` only) or the `deploy_goals` precedent (add to both paths). Document the choice explicitly when implementing.

**`issue_parser.py:80` — `is_formatted()` explicit parameter:**
```python
def is_formatted(content: str, issue_type: str, templates_dir: Path | None = None) -> bool:
```
Receives `templates_dir` explicitly from its callers. When BUG-2271 lands and callers are migrated, callers passing `None` must be updated to pass `resolve_templates_dir(config)` so the new resolver tiers apply. Co-delivery sequencing with BUG-2271 must account for this interaction point.

**`main_issues()` deferred import location (confirmed):**
All subcommand module imports are deferred inside the `with cli_event_context(...)` block at lines 21–55, not at module level. The `from little_loops.cli.issues.sections import cmd_sections` import must be added inside this block, following the `from little_loops.cli.issues.path_cmd import cmd_path` pattern.

**`_default_templates_dir()` current tiers (line 16) — two tiers already exist:**
1. `CLAUDE_PLUGIN_ROOT` env var → `Path(env_root) / "templates"`
2. `Path(__file__).resolve().parent.parent.parent / "templates"` (3× `.parent` to repo root)

The new `resolve_templates_dir(config: BRConfig)` must demote these to tiers 3–4. Keep `_default_templates_dir()` as a private helper so existing callers that pass `None` to `load_issue_sections()` continue working until they are migrated. Ensure the new function's signature is distinct (takes `config: BRConfig`) to avoid silently shadowing the old private function.

_Added by `/ll:refine-issue` (2026-06-24 pass 3) — verified against current codebase:_

**BUG-2271 is done (status confirmed):** `_default_templates_dir()` now has 2 tiers as documented above. However, `resolve_templates_dir(config: BRConfig)` — the 4-tier function ENH-2272 adds — does NOT yet exist in `issue_template.py`. ENH-2272 can now proceed without waiting on BUG-2271.

**Callsite "plugin directory" prose — current exact state (4 of 6 need explicit replacement):**
- `skills/format-issue/SKILL.md:196` — `(relative to the little-loops plugin directory)` present ✓ replace
- `skills/format-issue/SKILL.md:221` — template reference without "plugin directory" phrase; still needs `ll-issues sections` substitution
- `skills/format-issue/templates.md:7` — `(relative to the little-loops plugin directory)` present ✓ replace
- `skills/format-issue/templates.md:52` — template reference without phrase; still needs substitution
- `skills/capture-issue/SKILL.md:276` — no "plugin directory" phrase; generic `templates/{type}-sections.json` reference; still needs `ll-issues sections` substitution
- `skills/scope-epic/SKILL.md:296,358` — no "plugin directory" phrase; generic template references; still need `ll-issues sections` substitution
- `commands/ready-issue.md:139` — `(relative to the little-loops plugin directory)` present ✓ replace
- `commands/scan-codebase.md:241` — `(relative to the little-loops plugin directory)` present ✓ replace

All 6 still require updates; 4 have the exact "plugin directory" phrase, 2 use generic path references.

**`init/tui.py:_apply_config()` exact line numbers:**
- `deploy_goals(ll_dir, templates_dir)` call is at **line 843**
- `deploy_design_tokens(ll_dir, templates_dir, active_profile=active_profile)` call is at **line 847**
- `deploy_issue_templates()` should be inserted after line 847, matching the pattern.
- Import block for `deploy_goals` and `deploy_design_tokens` is at lines 827–828 (inline import inside `_apply_config()`).

**`deploy_goals` uses `atomic_write()` (not `shutil.copy`):** For a single-file deploy, `writers.py:atomic_write()` is used (line 263). The proposed `deploy_issue_templates` correctly uses `shutil.copytree()` since it deploys a directory, not a single file — this is appropriate and differs from `deploy_goals` intentionally.

**Test files confirmed absent:** `scripts/tests/test_ll_issues_sections.py` and `scripts/tests/test_deploy_issue_templates.py` do not exist yet — both must be created as documented in the Tests section.

_Added by `/ll:refine-issue` (2026-06-25 pass 4) — corrected against current codebase:_

**`get_bundled_templates_dir()` already exists as a public function:**
`issue_template.py` exposes `get_bundled_templates_dir()` → `Path(__file__).resolve().parent / "templates"` (1× parent — in-package since BUG-2271). The old research note at lines above that described "3× `.parent` to repo root" is stale. The new `resolve_templates_dir(config)` should call `get_bundled_templates_dir()` as its tier-3 fallback rather than recomputing the path:
```python
def resolve_templates_dir(config: BRConfig) -> Path:
    # tier 1: explicit config override
    if explicit := (config.issues.templates_dir if hasattr(config, "issues") else None):
        return Path(explicit)
    # tier 2: per-project deployed copy
    if (ll_dir := Path(config.ll_dir if hasattr(config, "ll_dir") else ".ll") / "templates").exists():
        return ll_dir
    # tier 3: in-package bundle (always available; added by FEAT-2274 / present now)
    return get_bundled_templates_dir()
    # tier 4 (CLAUDE_PLUGIN_ROOT / repo root) is handled inside _default_templates_dir(); not needed here
```
This means `_default_templates_dir()` does NOT need to become a 4-tier function — ENH-2272 adds a separate `resolve_templates_dir(config)` that only callers with a config object use; `_default_templates_dir()` can remain as-is for legacy callers.

**Exact `_run_yes()` deploy call lines confirmed:**
- `deploy_goals(ll_dir, templates_dir)` → **line 310** (conditional on `config.get("product", {}).get("enabled")`)
- `deploy_design_tokens(ll_dir, templates_dir)` → **line 313** (conditional on `config.get("design_tokens", {}).get("enabled")`)
- `make_learning_tests_dir(ll_dir)` → **line 316** (conditional on `config.get("learning_tests", {}).get("enabled")`)
- `deploy_issue_templates` must be added at ~line 314 following the `deploy_design_tokens` pattern.

**Exact `_run_apply()` deploy call line confirmed:**
- `deploy_goals(ll_dir, templates_dir)` → **line 446** (conditional on same product gate)
- `deploy_design_tokens` is absent from `_run_apply()` — this asymmetry means the precedent is: add `deploy_issue_templates` to `_run_yes()` only (mirror `deploy_design_tokens`). Commit message must document this choice.

**`init/tui.py:_apply_config()` corrected line numbers:**
- Inline import block: **lines 821–834** (includes `deploy_design_tokens`, `deploy_goals`, `make_learning_tests_dir`, and others)
- `deploy_goals(ll_dir, templates_dir)` call: **line 842**
- `deploy_design_tokens(ll_dir, templates_dir, active_profile=active_profile)` call: **line 846**
- `make_learning_tests_dir(ll_dir)` call: **line 849**
- `deploy_issue_templates()` should be inserted between lines 846 and 849, gated by `config.get("issues", {}).get("deploy_templates")`.

**`init/__init__.py` exact import + `__all__` structure:**
```python
from little_loops.init.writers import (
    deploy_design_tokens,
    deploy_goals,
    install_codex_adapter,
    make_issue_dirs,
    make_learning_tests_dir,
    merge_settings,
    update_gitignore,
    write_config,
)
__all__ = [
    "InstallStatus", "TemplateMatch", "DepWarning", "build_config", "check_version",
    "deploy_design_tokens", "deploy_goals", "detect_installation", "detect_project_type",
    "fetch_latest_plugin", "fetch_latest_pypi", "install_codex_adapter",
    "make_issue_dirs", "make_learning_tests_dir", "merge_settings",
    "update_gitignore", "validate_deps", "write_config",
]
```
Add `deploy_issue_templates` to both the `from writers import (...)` block and `__all__` list.

**`config-schema.json` `issues` section has `"additionalProperties": false` at line 251:**
The new `"deploy_templates": {"type": "boolean", "default": false}` property MUST be added as a sibling of `templates_dir` (lines 122–126) before line 251, or any config file containing `issues.deploy_templates` will fail schema validation.

**Test class locations corrected:**
- `TestDeployGoals` in `test_init_core.py`: **lines 814–847** (not 750–806 as previous research stated)
- `TestDeployDesignTokens`: immediately follows at lines 855–887 (same 4-test shape: deploys, skips-if-exists, dry-run, skips-if-source-missing)
- `test_yes_deploys_design_tokens_when_enabled`: **lines 1353–1375** — exact integration test pattern; the `TestDeployIssueTemplates` integration test should follow this shape (patch `build_config` to inject `issues.deploy_templates: true`, then assert `.ll/templates/` directory exists after `main_init(["--yes", ...])`)
- `test_design_tokens_selected_deploys_profiles` in `test_init_tui.py`: **lines 214–223** — calls `_wire_q(mock_q, features=["design_tokens", ...])` then `run_tui(...)` and asserts the profiles dir; mirror with `features=["issues_deploy_templates"]` (or whatever checkbox label is used in the TUI) and assert `.ll/templates/` exists

**`deploy_issue_templates` copy filter — only `*-sections.json` files:**
The bundled `templates/` directory contains: `design-tokens/` subdir, project-type JSONs (`dotnet.json`, `go.json`, `java-gradle.json`, `java-maven.json`, `javascript.json`, `python-generic.json`, `rust.json`, `typescript.json`, `generic.json`), and `*-sections.json` files (bug, feat, enh, epic). The deploy function must copy ONLY the `*-sections.json` files — project-type JSONs are not user-editable per-project templates. Recommended approach: iterate `src.glob("*-sections.json")` and copy individual files rather than `shutil.copytree` with an ignore list (avoids the risk of inadvertently including future files):
```python
def deploy_issue_templates(ll_dir: Path, templates_dir: Path, dry_run: bool = False) -> bool:
    dest = ll_dir / "templates"
    if dest.exists():
        return False
    section_files = list(templates_dir.glob("*-sections.json"))
    if not section_files:
        print(f"Warning: no *-sections.json files found in {templates_dir}", file=sys.stderr)
        return False
    if dry_run:
        print(f"[write] {dest}/ (issue section templates)")
        return True
    dest.mkdir(parents=True, exist_ok=True)
    for f in section_files:
        shutil.copy2(f, dest / f.name)
    return True
```

_Added by `/ll:refine-issue` (2026-06-25 pass 5) — exact callsite text and cmd_sections structure confirmed:_

**FEAT-2274 partial path migration (already staged, not committed):** The `*-sections.json` files have already been moved from root `templates/` → `scripts/little_loops/templates/` by FEAT-2274 (visible as staged renames in `git status`). All six callsite files have been updated accordingly — they now reference `scripts/little_loops/templates/{type}-sections.json` rather than the old root-level path. **The prose-based lookup mechanism still exists in all 6 files** — ENH-2272 replaces this prose approach (whether the old path or new) with `ll-issues sections {type}`.

**Confirmed verbatim replacement targets (exact text from each file):**

| File | Line | Verbatim phrase to replace |
|------|------|----------------------------|
| `skills/format-issue/SKILL.md` | 196 | `scripts/little_loops/templates/{type}-sections.json` v2.0 (relative to the little-loops plugin directory) |
| `skills/format-issue/SKILL.md` | 221 | `the per-type template \`scripts/little_loops/templates/{type}-sections.json\` for the issue's type` |
| `skills/format-issue/templates.md` | 7 | `scripts/little_loops/templates/{type}-sections.json` (relative to the little-loops plugin directory) |
| `skills/format-issue/templates.md` | 52 | `the per-type template \`scripts/little_loops/templates/{type}-sections.json\` v2.0` |
| `skills/format-issue/templates.md` | 54 | `Read the per-type template file \`scripts/little_loops/templates/{type}-sections.json\`` |
| `skills/capture-issue/SKILL.md` | 276 | `Read the per-type template \`scripts/little_loops/templates/{type}-sections.json\`` |
| `skills/scope-epic/SKILL.md` | 296 | `Read \`scripts/little_loops/templates/epic-sections.json\` to get section definitions.` |
| `skills/scope-epic/SKILL.md` | 358 | `Read \`scripts/little_loops/templates/{type}-sections.json\` for the child's type.` |
| `commands/ready-issue.md` | 139 | `Read the per-type template \`scripts/little_loops/templates/{type}-sections.json\` v2.0 (relative to the little-loops plugin directory)` |
| `commands/scan-codebase.md` | 241 | `using the section structure from per-type template files (relative to the little-loops plugin directory)` |
| `commands/scan-codebase.md` | 243 | `Read the per-type template \`scripts/little_loops/templates/{type}-sections.json\`` |

**`cmd_sections` confirmed structure (from `path_cmd.py` pattern):**

```python
# cli/issues/sections.py
def cmd_sections(config: BRConfig, args: argparse.Namespace) -> int:
    issue_type = args.type.lower()
    if issue_type not in ("bug", "feat", "enh", "epic"):
        print(f"Error: invalid type '{args.type}' — must be bug, feat, enh, or epic", file=sys.stderr)
        return 1
    templates_dir = resolve_templates_dir(config)
    json_path = templates_dir / f"{issue_type}-sections.json"
    if not json_path.exists():
        print(f"Error: template not found: {json_path}", file=sys.stderr)
        return 1
    if getattr(args, "path", False):
        print(json_path)
        return 0
    print(json_path.read_text())
    return 0
```

Parser registration snippet (add after `path_p` block at line ~374 in `cli/issues/__init__.py`):
```python
sec_p = subs.add_parser("sections", aliases=["sec"], help="Print section template JSON for an issue type")
sec_p.set_defaults(command="sections")
sec_p.add_argument("type", help="Issue type: bug, feat, enh, or epic")
sec_p.add_argument("--path", action="store_true", help="Print path to template file instead of JSON content")
add_config_arg(sec_p)
```

Dispatch addition (after `if args.command == "path"` block at ~line 734; import is deferred inside `with cli_event_context(...)` block):
```python
if args.command == "sections":
    from little_loops.cli.issues.sections import cmd_sections
    return cmd_sections(config, args)
```

**File existence confirmed (all must be created from scratch):**
- `scripts/little_loops/cli/issues/sections.py` — does NOT exist
- `scripts/tests/test_ll_issues_sections.py` — does NOT exist
- `scripts/tests/test_deploy_issue_templates.py` — does NOT exist

**`_run_yes()` exact deploy block (lines 309–316) confirmed:**
```python
if config.get("product", {}).get("enabled"):
    deploy_goals(ll_dir, templates_dir)          # line 309–310
if config.get("design_tokens", {}).get("enabled"):
    deploy_design_tokens(ll_dir, templates_dir)  # line 312–313
if config.get("learning_tests", {}).get("enabled"):
    make_learning_tests_dir(ll_dir)              # line 315–316
# deploy_issue_templates goes here, gated by config.get("issues", {}).get("deploy_templates")
```

_Added by `/ll:refine-issue` (2026-06-25 pass 6) — verified against current codebase; corrects stale naming in prior passes:_

**`apply_plan()` is the correct function name (not `_run_apply()`):** All prior pass findings that reference `_run_apply()` in `init/cli.py` should read `apply_plan()`. The function containing the deploy call at line 446 is named `apply_plan()` (import at line 416), not `_run_apply()`. The asymmetry note from pass 4 stands: `apply_plan()` calls only `deploy_goals`, while `_run_yes()` calls both `deploy_goals` and `deploy_design_tokens`. Mirror `deploy_design_tokens` precedent: add `deploy_issue_templates` to `_run_yes()` only. Verify whether `_apply_headless()` (which imports `deploy_goals` at line 143) also needs the new deploy call — the analysis reveals a third entry point not previously documented; if `_apply_headless()` is the headless `--yes` path and `_run_yes()` is the interactive one, both may need the deploy. Check by grepping `def _apply_headless` and `def _run_yes` for their call contexts.

**Dispatch chain insertion point (confirmed exact):** The `sections` dispatch must be inserted before the final `return 1` in `main_issues()`. The current end of the dispatch chain is:
```python
if args.command == "finalize-decomposition":
    return cmd_finalize_decomposition(config, args)
return 1
```
Insert the `sections` dispatch block immediately before `return 1`:
```python
if args.command == "sections":
    from little_loops.cli.issues.sections import cmd_sections
    return cmd_sections(config, args)
return 1
```

**Pass 5 callsite table confirmed accurate:** All 11 verbatim replacement targets in the pass 5 table were verified against the current files. No text has changed since pass 5. All 6 callsite files still use `scripts/little_loops/templates/{type}-sections.json` path references.

**Pass 1–5 findings remain current:** All function names, signatures, and line numbers documented in earlier passes were re-verified and are accurate. No additional corrections required beyond the `apply_plan()` naming fix above.

## Implementation Steps

1. Land / reuse the unified resolver (BUG-2271) and extend precedence with
   config override + `.ll/templates/`.
2. Add `cli/issues/sections.py` + register subcommand; tests for JSON output,
   `--path`, invalid type, and each precedence tier.
3. Add `deploy_issue_templates()` + init wiring behind a feature flag; tests for
   skip-if-exists and dry-run.
4. Rewrite the six skill/command callsites; update CLI/API docs.
5. Verify `ll-verify-skills` / `ll-verify-skill-budget` still pass and run
   `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/init/tui.py` — add `deploy_issue_templates()` call in `_apply_config()` (line ~847) alongside `deploy_goals` / `deploy_design_tokens`; add to inline import block.
7. Update `scripts/little_loops/init/__init__.py` — add `deploy_issue_templates` to imports and `__all__`.
8. Update `scripts/tests/test_issue_template.py` — add 4-tier resolver precedence tests to `TestLoadIssueSections`; verify `test_load_custom_dir` / `test_load_missing_file` don't regress under any signature change.
9. Update `scripts/tests/test_init_core.py` — add `TestDeployIssueTemplates` class and `test_yes_deploys_issue_templates_when_enabled` integration test.
10. Update `scripts/tests/test_config_schema.py` — add `test_issues_deploy_templates_in_schema`.
11. Update `docs/reference/CONFIGURATION.md` — add `deploy_templates` row to the `### issues` config table.
12. Update `.claude/CLAUDE.md` — add `sections` to the `ll-issues` parenthetical subcommand list (line 233).

## Scope Boundaries

- Changing the content or format of the `*-sections.json` files themselves (only the access layer changes).
- Bundling templates into the wheel — owned by FEAT-2274.
- Fixing resolver correctness bugs in existing loaders — owned by BUG-2271 (`issue_parser`) and BUG-2273 (`ll-init`).
- Enabling `deploy_issue_templates` on-by-default (deliberately opt-in to keep projects that never customize templates clean).
- Migrating existing projects' custom `issues.templates_dir` paths or renaming config keys.
- Adding callsites beyond the six listed in Current Behavior.

## Impact

- **Priority**: P3 — meaningful per-invocation latency fix for several
  issue-pipeline skills + enables BYO templates; not blocking.
- **Effort**: Medium — new CLI subcommand + resolver + init deploy + 6 callsite
  edits + tests/docs.
- **Risk**: Low–Medium — additive CLI/feature; callsite edits are prose swaps;
  deploy is opt-in and non-destructive.
- **Breaking Change**: No.

## Related

- BUG-2271 — section-template resolver correctness (shared resolver).
- BUG-2273 — `ll-init` resolver correctness (shared resolver).
- FEAT-2274 — packages `templates/` into the wheel (the "wheel" half of **Both**);
  this ENH is the "deploy" half.
- BUG-938 — closed invalid; FEAT-2274 refines its rule (host-plugin assets out,
  package-data templates in).
- ENH-576 / ENH-491 / ENH-271 — prior work aligning and centralizing the
  per-type section JSON; this adds the access + deploy layer on top.

## Labels

`enhancement`, `templates`, `cli`, `ll-init`, `skills`, `performance`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-25_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 74/100 → CAUTION

### Outcome Risk Factors
- Wide change surface (~26 files) across CLI, init, skills, commands, tests, and docs — the 12-step plan is complete, but warrants a final `grep -r "plugin directory\|scripts/little_loops/templates" skills/ commands/` post-implementation to confirm no prose references remain
- FEAT-2274 still open — tier-3 bundle path works locally (`scripts/little_loops/templates/` staged), but pyproject.toml packaging not yet merged; implement `resolve_templates_dir()` using `get_bundled_templates_dir()` as tier-3, validate wheel packaging post-FEAT-2274 merge
- `_run_apply()` vs `_run_yes()` asymmetry — mirror `deploy_design_tokens` (`_run_yes()` only); document this precedent in the commit message (no blocking gap, implementer instruction only)

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-25
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-2285: Unified 4-tier template resolver in issue_template.py
- ENH-2286: ll-issues sections CLI subcommand
- ENH-2287: deploy_issue_templates() + full init wiring
- ENH-2288: Callsite rewrites (6 files) + docs updates

## Session Log
- `/ll:issue-size-review` - 2026-06-25T00:00:00Z - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
- `/ll:confidence-check` - 2026-06-25T16:00:00Z - `35673248-c074-4cec-bbe7-79fa8b2d18f6.jsonl`
- `/ll:refine-issue` - 2026-06-25T07:20:24 - `1ca16fef-a5e2-48b5-8b75-abcf46c496e5.jsonl`
- `/ll:confidence-check` - 2026-06-25T08:00:00Z - `5f0e8d2e-107a-4306-983f-dd49d06cf703.jsonl`
- `/ll:refine-issue` - 2026-06-25T07:09:59 - `93d8bdbd-9b51-40ae-bec7-7146cc267a60.jsonl`
- `/ll:confidence-check` - 2026-06-25T06:00:00Z - `93d8bdbd-9b51-40ae-bec7-7146cc267a60.jsonl`
- `/ll:refine-issue` - 2026-06-25T07:00:54 - `93d8bdbd-9b51-40ae-bec7-7146cc267a60.jsonl`
- `/ll:confidence-check` - 2026-06-25T00:00:00Z - `93d8bdbd-9b51-40ae-bec7-7146cc267a60.jsonl`
- `/ll:confidence-check` - 2026-06-24T00:00:00Z - `cad8a6a0-ea53-4a66-a1bc-b1dac77ffa38.jsonl`
- `/ll:refine-issue` - 2026-06-25T04:07:01 - `b128ec64-1e93-499b-9f80-d41e92fa74d3.jsonl`
- `/ll:confidence-check` - 2026-06-25T05:00:00Z - `9a49e22d-1a83-43d6-90bb-9066a033acd4.jsonl`
- `/ll:wire-issue` - 2026-06-25T03:45:08 - `96720814-9d39-475d-b533-70daac1152c4.jsonl`
- `/ll:refine-issue` - 2026-06-25T03:34:36 - `613142ac-86df-4bf4-8683-82620ab53b99.jsonl`
- `/ll:confidence-check` - 2026-06-24T23:45:00Z - `d0a0457b-8179-46d1-a61d-6ee6f3cc8921.jsonl`
- `/ll:wire-issue` - 2026-06-24T23:21:52 - `97498016-23cf-4c10-9b5b-f243fd01138b.jsonl`
- `/ll:refine-issue` - 2026-06-24T23:05:17 - `5b067ad3-2717-49a4-bf64-d61c0eab69cc.jsonl`
- `/ll:format-issue` - 2026-06-24T22:58:10 - `2559928a-8ef2-4ca3-879e-63d8f4134600.jsonl`
- `/ll:capture-issue` - 2026-06-24T22:17:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d34d610-c8b9-4a5e-82c8-191296760b6d.jsonl`
