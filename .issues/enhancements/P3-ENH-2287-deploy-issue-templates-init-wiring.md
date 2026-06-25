---
id: ENH-2287
type: ENH
priority: P3
status: open
parent: ENH-2272
relates_to:
- ENH-2285
- FEAT-2274
captured_at: '2026-06-25T00:00:00Z'
discovered_date: 2026-06-25
discovered_by: issue-size-review
---

# ENH-2287: deploy_issue_templates() + full init wiring

## Summary

Add `deploy_issue_templates(ll_dir, templates_dir, dry_run=False)` to `init/writers.py`
and wire it into `_run_yes()`, `_apply_config()` (TUI), and `init/__init__.py` exports.
Add the `issues.deploy_templates` property to `config-schema.json`. Can run in parallel
with ENH-2286; both depend on ENH-2285.

## Parent Issue

Decomposed from ENH-2272: ll-issues sections accessor + project-local template deploy

## Proposed Solution

### `init/writers.py` — `deploy_issue_templates()`

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

Copies only `*-sections.json` files (not project-type JSONs or design-tokens). Uses
`glob("*-sections.json")` iteration instead of `shutil.copytree` to avoid pulling in
future files inadvertently.

### `init/cli.py` — wire into `_run_yes()` (lines 309–316)

```python
if config.get("issues", {}).get("deploy_templates"):
    deploy_issue_templates(ll_dir, templates_dir)
```

Add after `deploy_design_tokens` call (line 313), mirroring the `deploy_design_tokens`
precedent — add to `_run_yes()` only, NOT to `apply_plan()`. Document this asymmetry
in the commit message. Also check `_apply_headless()` (imports `deploy_goals` at line
143) to determine if it also needs the call.

### `init/tui.py` — wire into `_apply_config()` (lines 842–849)

Add after `deploy_design_tokens` call (line 846), before `make_learning_tests_dir`
(line 849), gated by `config.get("issues", {}).get("deploy_templates")`. Add
`deploy_issue_templates` to the inline import block (lines 821–834).

### `init/__init__.py` — exports

Add `deploy_issue_templates` to:
- `from little_loops.init.writers import (...)` block
- `__all__` list (alongside `deploy_goals`, `deploy_design_tokens`)

### `config-schema.json` — schema property

Add as sibling of `templates_dir` (before the `"additionalProperties": false` at line 251):
```json
"deploy_templates": {
  "type": "boolean",
  "default": false,
  "description": "Copy bundled *-sections.json templates into .ll/templates/ on ll-init"
}
```

## Files to Modify/Create

- `scripts/little_loops/init/writers.py` — `deploy_issue_templates()` function
- `scripts/little_loops/init/cli.py` — wire into `_run_yes()` (and check `_apply_headless()`)
- `scripts/little_loops/init/tui.py` — wire into `_apply_config()` + inline import
- `scripts/little_loops/init/__init__.py` — add to imports + `__all__`
- `config-schema.json` — add `deploy_templates` property under `issues`
- `scripts/tests/test_deploy_issue_templates.py` (new) — `TestDeployIssueTemplates`:
  `test_deploys_sections`, `test_skips_if_already_exists`, `test_dry_run`,
  `test_skips_if_no_section_files` (mirror `TestDeployGoals` at lines 814–847)
- `scripts/tests/test_init_core.py` — add `TestDeployIssueTemplates` class and
  `test_yes_deploys_issue_templates_when_enabled` integration test (mirror
  `test_yes_deploys_design_tokens_when_enabled` at lines 1353–1375: patch `build_config`
  to inject `issues.deploy_templates: true`, assert `.ll/templates/` exists after
  `main_init(["--yes", ...])`)
- `scripts/tests/test_config_schema.py` — add `test_issues_deploy_templates_in_schema`
  sentinel following `test_issues_auto_commit_in_schema` pattern
- `scripts/tests/test_init_tui.py` — add `test_deploy_issue_templates_via_tui` following
  `test_design_tokens_selected_deploys_profiles` pattern (lines 214–223)

## Acceptance Criteria

- `deploy_issue_templates(ll_dir, src)` copies only `*-sections.json` files to `ll_dir/templates/`
- Returns `False` (skips) when `ll_dir/templates/` already exists (skip-if-exists)
- `dry_run=True` prints `[write] .ll/templates/ (issue section templates)` and returns `True`
- `ll-init --yes` with `issues.deploy_templates: true` in config creates `.ll/templates/`
- Config `issues.deploy_templates` validates against schema without error
- All new and modified tests pass

## Implementation Steps

1. Add `deploy_issue_templates()` to `init/writers.py` (import `shutil` if needed)
2. Update `init/__init__.py` — add to imports + `__all__`
3. Wire into `init/cli.py` `_run_yes()` and check `_apply_headless()`
4. Wire into `init/tui.py` `_apply_config()` + inline import block
5. Add `deploy_templates` to `config-schema.json` (before line 251)
6. Create `scripts/tests/test_deploy_issue_templates.py`
7. Add `TestDeployIssueTemplates` to `test_init_core.py`
8. Add `test_issues_deploy_templates_in_schema` to `test_config_schema.py`
9. Add `test_deploy_issue_templates_via_tui` to `test_init_tui.py`
10. Run `python -m pytest scripts/tests/test_deploy_issue_templates.py scripts/tests/test_init_core.py scripts/tests/test_config_schema.py scripts/tests/test_init_tui.py -v`

## Dependencies

- ENH-2285 must ship first (provides `resolve_templates_dir` — used indirectly by `deploy_issue_templates` to locate the source bundle via `get_bundled_templates_dir()`)
- Can run in parallel with ENH-2286 (no shared files)

## Session Log
- `/ll:issue-size-review` - 2026-06-25T00:00:00Z - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
