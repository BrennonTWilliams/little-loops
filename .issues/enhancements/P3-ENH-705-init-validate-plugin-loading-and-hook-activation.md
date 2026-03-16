---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 78
---

# ENH-705: Init should validate hook script dependencies and version alignment

## Summary

Init should verify that hook runtime dependencies (`jq`, `python3`, `pyyaml`) are available, and that the installed `little_loops` pip package version matches the loaded plugin version. Missing dependencies cause silent hook failures; a mismatched pip/plugin version causes behavioral drift between hook scripts and CLI tools.

## Current Behavior

`/ll:init` successfully writes `.claude/ll-config.json` and reports success with no runtime dependency checks. If `jq` is missing from PATH, all hook scripts fail silently — PostToolUse, SessionStart, Stop, and PreCompact hooks produce no output and no error. If the user upgrades the Claude Code plugin without reinstalling the pip package (or vice versa), the hook scripts and CLI tools diverge in behavior with no warning at setup time.

## Expected Behavior

After writing the config, init should:
1. Check that `jq` is available in PATH (required by all hook scripts)
2. Check that `python3` is available (required by `session-start.sh`)
3. Check that `pyyaml` is installed (`python3 -c "import yaml"` — required by `session-start.sh` config merge)
4. Check that the `little-loops` pip package is installed (`importlib.metadata.version('little-loops')`)
5. If installed, verify the pip package version matches the plugin version — warn if they differ

All checks are non-blocking: display warnings and proceed.

## Motivation

Silent failure is confusing. A user who installs little-loops on a new machine and runs `/ll:init` reasonably expects hooks to work. When nothing happens at 80% context, they have no signal that `jq` is missing. Similarly, a user who upgrades only the Claude Code plugin has no indication that their `ll-*` CLI tools are out of sync. Surfacing these issues at init time is far better than leaving users to discover them empirically.

## Proposed Solution

Add a **Step 9.5** validation step in `skills/init/SKILL.md` (after Step 9: Update .gitignore, before Step 10: Update Allowed Tools), following the same non-blocking pattern as the existing Step 7.5 command availability check (`SKILL.md:212-243`):

1. Check `which jq` — warn if not found (required by all hooks)
2. Check `which python3` — warn if not found (required by `session-start.sh`)
3. Check `python3 -c "import yaml"` — warn if pyyaml not installed (required by `session-start.sh` config merge)
4. Check `python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))"` — warn if not installed; if installed, compare version to `PLUGIN_VERSION` comment embedded in the skill and warn if they differ
5. Do not block init — warn and continue

## Scope Boundaries

- **In scope**: Adding a post-write validation step to `skills/init/SKILL.md`
- **Out of scope**: Automatically installing missing dependencies, modifying system PATH

## Implementation Steps

1. **Add `<!-- PLUGIN_VERSION: 1.50.0 -->` comment** near the top of `skills/init/SKILL.md` (after the frontmatter/title block) — read by Step 9.5 as the authoritative plugin version for comparison; updated alongside the 4 existing version locations at release time

2. **Add Step 9.5 to `skills/init/SKILL.md`** (insert between Step 9 at ~line 323 and Step 10 at ~line 325):
   - Title: "### 9.5. Hook Dependency Validation"
   - Skip if `--dry-run` is set
   - Follow the structure of Step 7.5 (`SKILL.md:212-243`): non-blocking, warn-and-continue
   - Run four Bash checks; emit warnings for any failures; always proceed to Step 10

## Impact

- **Priority**: P3 - Quality-of-life improvement; silent failures are confusing but not blocking
- **Effort**: Small - Single validation step added to existing skill file
- **Risk**: Low - Warning-only, does not block init or change config behavior
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — add `PLUGIN_VERSION` comment and Step 9.5 hook dependency validation (insert between ~line 323 and ~line 325)

### Dependent Files (Callers/Importers)
- N/A — init skill is invoked directly by users, not imported

### Similar Patterns
- `skills/init/SKILL.md:212-243` — Step 7.5 command availability check: non-blocking, post-confirm, warn-and-continue pattern (direct structural analog)
- `hooks/scripts/session-start.sh` — uses `which jq` / `command -v` pattern for detecting missing dependencies before executing hook logic

### Dependency Check Summary

| Dep | Used By | Check Command | Install Hint |
|-----|---------|--------------|--------------|
| `jq` | ALL hooks | `which jq` | OS package manager |
| `python3` | session-start.sh | `which python3` | OS package manager |
| `pyyaml` | session-start.sh | `python3 -c "import yaml"` | `pip install pyyaml` |
| `little_loops` package | ll-* CLI tools | `importlib.metadata.version('little-loops')` | `pip install -e "./scripts"` |
| version alignment | (correctness) | compare metadata version to PLUGIN_VERSION | `pip install --upgrade` |

### Tests
- No existing test coverage for init skill validation logic
- `scripts/tests/test_hooks_integration.py` — hook integration tests (model for testing hook-dependent behavior)

### Documentation
- Warning is self-documenting in init output

### Configuration
- No config keys read or written
- Reads `PLUGIN_VERSION` comment embedded in `skills/init/SKILL.md`
- Reads pip package version via `importlib.metadata`

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `skills/init/SKILL.md` has no "Step 9.5" step. The referenced Step 7.5 pattern exists in the file. Hook scripts confirmed to require `jq` (all hooks) and `python3` + `pyyaml` (`session-start.sh`). Version is defined in 4 locations (plugin.json, pyproject.toml, `__init__.py`, CHANGELOG.md) with no cross-check at setup time.

## Labels

`enhancement`, `init`, `developer-experience`

## Session Log
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4922c4e9-2029-4f68-b0a3-04ae4dbcd620.jsonl`
- `/ll:format-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/515ca590-73cd-40a5-bdc2-fd93b84ad7b4.jsonl`
- `/ll:refine-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bbd0bb4e-1acc-4e46-9be4-546db972de6a.jsonl`

---

**Open** | Created: 2026-03-12 | Priority: P3
