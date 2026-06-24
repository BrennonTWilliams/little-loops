---
id: ENH-2272
type: ENH
priority: P3
status: open
captured_at: "2026-06-24T22:17:07Z"
discovered_date: 2026-06-24
discovered_by: capture-issue
relates_to: [BUG-2271, BUG-2273, FEAT-2274]
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
- `scripts/little_loops/init/writers.py` — `deploy_issue_templates()` (skip-if-exists).
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
- `scripts/little_loops/sync/` — any loader that reads per-type section JSON will consume the shared resolver.
- Six skill/command files (listed in Files to Modify) — become callers of `ll-issues sections` after callsite rewrite.

### Tests
- New: `scripts/tests/test_ll_issues_sections.py` — JSON output, `--path`, invalid type, and each resolver precedence tier.
- New: `scripts/tests/test_deploy_issue_templates.py` — skip-if-exists semantics, dry-run, feature-flag gating.
- Update: tests covering `ll-init` flow to include the new deploy step.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_template.py` — existing `test_load_custom_dir` and `test_load_missing_file` may break if `load_issue_sections` second-parameter semantics change; add new parametrized tests for the 4-tier resolver precedence in `TestLoadIssueSections`.
- `scripts/tests/test_init_core.py` — add `TestDeployIssueTemplates` class (mirror `TestDeployGoals`: `test_deploys_sections`, `test_skips_if_already_exists`, `test_dry_run`, `test_skips_if_template_missing`); add `test_yes_deploys_issue_templates_when_enabled` integration test.
- `scripts/tests/test_config_schema.py` — add `test_issues_deploy_templates_in_schema` sentinel following `test_issues_auto_commit_in_schema` pattern.

### Documentation
- `docs/reference/CLI.md` — document `ll-issues sections` subcommand.
- `docs/reference/API.md` — document the unified resolver (`issue_template.py`) and `deploy_issue_templates()`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — add `deploy_templates` row to the `### issues` config table (alongside `templates_dir`).
- `.claude/CLAUDE.md` — add `sections` to the parenthetical `ll-issues` subcommand list (line 233).

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

## Session Log
- `/ll:wire-issue` - 2026-06-24T23:21:52 - `97498016-23cf-4c10-9b5b-f243fd01138b.jsonl`
- `/ll:refine-issue` - 2026-06-24T23:05:17 - `5b067ad3-2717-49a4-bf64-d61c0eab69cc.jsonl`
- `/ll:format-issue` - 2026-06-24T22:58:10 - `2559928a-8ef2-4ca3-879e-63d8f4134600.jsonl`
- `/ll:capture-issue` - 2026-06-24T22:17:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d34d610-c8b9-4a5e-82c8-191296760b6d.jsonl`
