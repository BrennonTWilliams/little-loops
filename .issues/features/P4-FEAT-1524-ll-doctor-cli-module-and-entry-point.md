---
id: FEAT-1524
type: FEAT
priority: P4
status: done
captured_at: '2026-05-16T00:00:00Z'
completed_at: '2026-05-16T17:49:05Z'
discovered_date: 2026-05-16
discovered_by: issue-size-review
parent: FEAT-1503
blocked_by: []
labels:
- host-compat
- preflight
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1524: ll-doctor — CLI module, entry point registration, and tests

## Summary

Author `scripts/little_loops/cli/doctor.py` implementing `main_doctor()`, register it as an entry point, and write full test coverage in `scripts/tests/test_cli_doctor.py`.

## Parent Issue

Decomposed from FEAT-1503: ll-doctor — CLI tool and ll-action capabilities update

## Scope

Covers implementation steps 1, 2, 5 from the parent issue.

**Depends on**: FEAT-1523 (CapabilityReport dataclass and `describe_capabilities()` protocol must land first)

## Current Behavior

No `ll-doctor` CLI tool exists; users have no unified way to check which host capabilities are available before running automation.

## Expected Behavior

`ll-doctor` resolves the active host (via `LL_HOST_CLI` / `orchestration.host_cli`) and prints a ✓/✗/○ status table covering host binary, version, invocation modes, and per-hook installation status. Exit code is `0` when all required capabilities are present; `1` when any critical capability is missing.

## Proposed Solution

### Step 1: Author `scripts/little_loops/cli/doctor.py`

Model on `cli/docs.py:main_verify_docs()`. The function:

1. Parses args (no positional args; `--json` flag optional for machine output).
2. Calls the host-resolution helper from FEAT-1523 to get the active runner.
3. Calls `runner.describe_capabilities()` → `CapabilityReport`.
4. Prints a ✓/✗/○ table using literal Unicode (the three-symbol mapping must be implemented directly in `doctor.py` — `doc_counts.py:format_result_text()` at line 163 only uses ✓ and ✗, not ○).
5. Returns `0` if no critical gaps, `1` otherwise.

```python
# scripts/little_loops/cli/doctor.py (sketch)
def main_doctor(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    configure_output()
    log = Logger(use_color=use_color_enabled())
    apply_host_cli_from_config(load_config())  # FEAT-1523 helper: seeds LL_HOST_CLI from orchestration.host_cli
    runner = resolve_host()                    # resolve_host() from host_runner.py (NOT resolve_host_runner())
    report = runner.describe_capabilities()
    _print_report(report, json_mode=args.json)
    return 0 if not any(c.status == "unsupported" for c in report.capabilities) else 1
```

`resolve_host(env=None)` (line 688 in `host_runner.py`) is the actual function — no `resolve_host_runner()` exists. FEAT-1523 delivers `apply_host_cli_from_config()` as a separate call that writes to `LL_HOST_CLI` before `resolve_host()` runs.

`--json` flag should be registered as `-j`/`--json` with `action="store_true"` following the `docs.py` pattern.

**Exact imports** (from `docs.py:8-9`):
```python
from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.logger import Logger
```

### Step 2: Register entry point in two places

- `scripts/pyproject.toml` `[project.scripts]` (lines 48-74): add `ll-doctor = "little_loops.cli:main_doctor"`
- `scripts/little_loops/cli/__init__.py` (lines 29-84): `from little_loops.cli.doctor import main_doctor` + add to `__all__` and module-docstring tool listing

Note: `main_gitignore` IS present in `__all__` (line 65) — the concern was unfounded. Ensure `main_doctor` is added to both the import block (around line 36) AND `__all__`. The file is exactly 84 lines with 24 entries in `__all__`; add the module-docstring bullet (lines 1–27) as well.

### Step 5: Write `scripts/tests/test_cli_doctor.py`

Follow `test_cli_docs.py` pattern. Tests use `patch("sys.argv", [...])` (not `monkeypatch.setattr`) and stack patches in a single `with (...):` block (Python 3.10+):

```python
class TestMainDoctor:
    def test_exit_zero_when_all_capabilities_present(self):
        mock_report = MagicMock()
        mock_report.has_critical_gap.return_value = False
        mock_runner = MagicMock()
        mock_runner.describe_capabilities.return_value = mock_report
        with (patch("sys.argv", ["ll-doctor"]),
              patch("little_loops.host_runner.resolve_host", return_value=mock_runner),
              patch("little_loops.cli.doctor.apply_host_cli_from_config"),  # FEAT-1523 helper
              patch("builtins.print")):
            assert main_doctor() == 0

    def test_exit_one_when_critical_capability_missing(self):
        # mock_report.has_critical_gap.return_value = True → assert result == 1
        ...

    def test_consistency_capability_not_supported_matches_report(self):
        # warnings.catch_warnings(record=True) → assert each CapabilityNotSupported
        # corresponds to unsupported entry in describe_capabilities()
        # CapabilityNotSupported is an importable UserWarning subclass in host_runner.py
        ...
```

For tests that need to control `resolve_host()` detection (e.g., simulating no binary found), use `monkeypatch.setenv("LL_HOST_CLI", "codex")` or `monkeypatch.delenv("LL_HOST_CLI", raising=False)` + `monkeypatch.setattr("little_loops.host_runner.shutil.which", lambda x: None)` — see `test_host_runner.py` for the `isolated_env` fixture pattern.

### Wiring Phase (added by `/ll:wire-issue`)

_Coordination touchpoints identified by wiring analysis:_

1. After implementing Step 5 (`test_cli_doctor.py`), verify `isolated_env` fixture is imported or replicated from `test_host_runner.py` for any tests that manipulate `LL_HOST_CLI` or probe `shutil.which`
2. Do NOT update doc surfaces (README, CLI.md, help.md, CLAUDE.md, areas.md, init/SKILL.md) — those belong to FEAT-1504; alert FEAT-1504 implementer that this issue has landed when done
3. The two count-asserting tests flagged in "Side Effects to Expect" will NOT break from this issue alone — they only break when FEAT-1504 updates the count strings
4. Update `CONTRIBUTING.md` — add `- doctor.py` to the `cli/` directory tree listing (around line 184) alongside `auto.py`, `docs.py`, etc.; this tree lists individual CLI files for developer orientation and is FEAT-1524 scope (not FEAT-1504)

## Acceptance Criteria

- [ ] `scripts/little_loops/cli/doctor.py` exists and implements `main_doctor()`
- [ ] `ll-doctor` resolves the active host via `LL_HOST_CLI` / `orchestration.host_cli` using the helper from FEAT-1523
- [ ] Output includes host binary name and resolved version
- [ ] Each invocation-mode capability is printed with ✓/✗/○ status and a short description
- [ ] Hook installation status is reported per hook intent (installed / registered-not-wired / deferred)
- [ ] Exit code 0 when all required capabilities are present; 1 when any critical capability is missing
- [ ] `ll-doctor` registered as an entry point in `scripts/pyproject.toml` and `scripts/little_loops/cli/__init__.py`
- [ ] `scripts/tests/test_cli_doctor.py` exists with full coverage of doctor.py behaviors
- [ ] All existing tests pass: `python -m pytest scripts/tests/ -v && ruff check scripts/ && python -m mypy scripts/little_loops/`

## Integration Map

### Files to Create

- `scripts/little_loops/cli/doctor.py`
- `scripts/tests/test_cli_doctor.py`

### Files to Modify

- `scripts/pyproject.toml` — add `ll-doctor` entry point in `[project.scripts]` (lines 48-74)
- `scripts/little_loops/cli/__init__.py` — import `main_doctor`, add to `__all__`, update module docstring tool listing (lines 29-84, file is exactly 84 lines total)
- `CONTRIBUTING.md` — add `doctor.py` to the `cli/` directory tree listing (~line 184); this tree enumerates individual CLI module files for developer orientation and is FEAT-1524 scope (not FEAT-1504 end-user doc surfaces) [Wiring pass added by `/ll:wire-issue`]

### Similar Patterns

- `scripts/little_loops/cli/docs.py:main_verify_docs()` — template for `main_doctor()` structure
- `scripts/little_loops/doc_counts.py:format_result_text()` (line 163, NOT under `cli/`) — pattern for ✓/✗ Unicode output (○ must be added in doctor.py)
- `scripts/tests/test_cli_docs.py` — template for `test_cli_doctor.py`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_docs.py` — primary template; follow `TestMainVerifyDocs` class structure: one class per entry point, `_make_*_result()` MagicMock helper, nested `with (patch("sys.argv", [...]), patch(...), patch("builtins.print")):` blocks, assert return value is int (0 or 1)
- `scripts/tests/test_host_runner.py` — source of `isolated_env` fixture (`monkeypatch.delenv("LL_HOST_CLI", raising=False)`) and `monkeypatch.setattr("little_loops.host_runner.shutil.which", lambda x: None)` pattern; use in tests that simulate missing host binary or force a specific host
- `scripts/tests/test_create_extension_wiring.py` — per CONTRIBUTING.md wiring pattern, a new `TestFeat1524LlDoctorWiring` class checking `"ll-doctor"` in `CLI_REFERENCE`, `HELP_MD`, and `CLAUDE_MD` is required; however those doc surfaces won't exist until FEAT-1504 lands — **this class belongs in FEAT-1504, not here**

### Documentation

_Wiring pass added by `/ll:wire-issue` — these files are FEAT-1504 scope, out of scope for FEAT-1524. Do NOT modify them here:_
- `.claude/CLAUDE.md` — "CLI Tools" section (lines 104–131) — add `ll-doctor` bullet
- `commands/help.md` — CLI TOOLS block (lines 239–264) — add `ll-doctor` one-liner
- `docs/reference/CLI.md` — add `### ll-doctor` section after `### ll-learning-tests` (flags: `--json`/`-j`, exit codes, examples)
- `docs/reference/API.md` — `## little_loops.cli` section — add `### main_doctor` subsection documenting `main_doctor() -> int`
- `README.md` line 46 — `"23 typed CLI tools"` → `"24 typed CLI tools"` (triggers `TestFeat1229LlActionWiring.test_readme_tool_count_is_20` and `TestFeat1045DocUpdates.test_readme_tool_count_is_20`)
- `README.md` line 164 — `"24 CLI tools"` → `"25 CLI tools"` (separate count string, not currently tested)
- `skills/configure/areas.md` — `"Authorize all 21"` → `"Authorize all 22"`; add `ll-doctor` to enumerated name list (triggers `TestConfigureAreasWiring` in both `test_create_extension_wiring.py` and `test_ll_logs_wiring.py`)
- `skills/init/SKILL.md` — three locations: add `"Bash(ll-doctor:*)"` to Step 10 permissions block; add `` - `ll-doctor` `` to both Step 11 CLAUDE.md boilerplate blocks (file-exists and no-file paths)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/__init__.py` is exactly 84 lines with 24 entries in `__all__` (lines 56–84); add `from little_loops.cli.doctor import main_doctor` after line 34 (`from little_loops.cli.docs import ...`), becoming line 35; add `main_doctor` to `__all__` between `main_deps` (line 62) and `main_generate_schemas` (line 63); add docstring bullet (lines 1–27)
- `scripts/pyproject.toml` `[project.scripts]` spans lines 48–74 with 25 entries; pattern is `ll-<name> = "little_loops.cli:main_<name>"` (note: `ll-workflows` is an exception using `little_loops.workflow_sequence:main` — `ll-doctor` follows the standard pattern)
- `scripts/little_loops/host_runner.py:resolve_host()` signature: `resolve_host(env: dict[str, str] | None = None) -> HostRunner` (line 688)
- `scripts/little_loops/cli/output.py:configure_output()` (line 49) — call before `use_color_enabled()` (line 92); both used in `docs.py:main_verify_docs()` (lines 78–79)
- `scripts/little_loops/logger.py:Logger.__init__()` (line 38) — params: `verbose=True`, `use_color=None`, `colors=None`; instantiate as `Logger(use_color=use_color_enabled())`
- `scripts/tests/test_host_runner.py` — uses `isolated_env` fixture (`monkeypatch.delenv("LL_HOST_CLI", raising=False)`) and `monkeypatch.setattr("little_loops.host_runner.shutil.which", ...)` for host binary probe control

### Codebase Research Findings (Second Pass — 2026-05-16)

_Added by `/ll:refine-issue` — verified against live code after FEAT-1523 landed:_

- **CRITICAL — sketch correction**: `CapabilityReport.has_critical_gap()` does **not** exist; the dataclass is a plain frozen value object with no methods. Exit-code logic must be inline: `return 0 if not any(c.status == "unsupported" for c in report.capabilities) else 1`
- **FEAT-1523 blocker is resolved** — `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities()`, and `apply_host_cli_from_config()` are all live in `host_runner.py`; `blocked_by: [FEAT-1523]` can be treated as satisfied
- `CapabilityEntry` fields: `name: str`, `status: Literal["full", "partial", "unsupported"]`, `note: str = ""`
- `HookEntry` fields: `name: str`, `status: Literal["installed", "registered", "deferred", "absent"]`, `note: str = ""`
- **`version` field is always `""`** — all four runners return an empty string from `describe_capabilities()`; call `runner.build_version_check()` separately if a real version string is needed, or display `"(unknown)"` as fallback
- **`hooks` list is always empty** — no runner currently populates `HookEntry` items; the "Hook installation status" acceptance criterion will produce an empty section until runners are updated
- `cli/__init__.py` is **84 lines**; insert `from little_loops.cli.doctor import main_doctor` after the `main_deps` import line; add `"main_doctor"` to `__all__` between `"main_deps"` and `"main_generate_schemas"`
- `pyproject.toml` `[project.scripts]` is not alphabetically sorted; insert `ll-doctor = "little_loops.cli:main_doctor"` after the `ll-deps` line
- `isolated_env` fixture (`test_host_runner.py` lines 38–43): clears both `LL_HOST_CLI` and `LL_HOOK_HOST` via `monkeypatch.delenv(..., raising=False)` — copy verbatim into `test_cli_doctor.py` if any tests manipulate env vars

### Side Effects to Expect

- `test_create_extension_wiring.py:TestFeat1229LlActionWiring.test_readme_tool_count_is_20` asserts `"23 typed CLI tools"` in README — will break when the FEAT-1496 doc pass adds `ll-doctor` to count surfaces. This is a FEAT-1496 concern, not FEAT-1524.
- `test_ll_logs_wiring.py:TestConfigureAreasWiring.test_authorize_all_count_is_17` asserts `"Authorize all 21"` — same dependency.

## Impact

- **Priority**: P4 — Quality-of-life preflight tool
- **Effort**: Small-Medium — New CLI module (~100 LOC) + test file; pattern established by `cli/docs.py`
- **Risk**: Low — Net-new tool, no downstream breakage

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-16_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- ~~**FEAT-1523 is a hard blocker (status: open)**~~ — **RESOLVED**: FEAT-1523 has landed; `CapabilityReport`, `describe_capabilities()`, and `apply_host_cli_from_config()` are all live in `host_runner.py`. Ready to implement.
- `_print_report()` internals: adapt the exit-code logic per second-pass research — `has_critical_gap()` doesn't exist; use `any(c.status == "unsupported" for c in report.capabilities)` instead (see Integration Map → Codebase Research Findings, Second Pass).

## Session Log
- `/ll:ready-issue` - 2026-05-16T17:40:37 - `b6c43e41-7c77-4927-964a-ec7ed9c2c3a4.jsonl`
- `/ll:wire-issue` - 2026-05-16T17:36:21 - `5a262d39-bb27-474d-8727-1698c67bde4a.jsonl`
- `/ll:refine-issue` - 2026-05-16T17:31:34 - `cc0d981c-725a-499a-92cc-8c1031ae6285.jsonl`
- `/ll:refine-issue` - 2026-05-16T16:39:44 - `b95dabac-b2c1-4fa3-838b-0f6d6e632c33.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `308e8709-77ed-477d-9ac7-496e083d3cb5.jsonl`
- `/ll:refine-issue` - 2026-05-16T16:26:40 - `a77d3232-c9c0-42ec-8932-e269a7236972.jsonl`
- `/ll:issue-size-review` - 2026-05-16T00:00:00Z - `e46d252d-d6ba-4cf5-9954-c3c6cea402e5.jsonl`
- `/ll:wire-issue` - 2026-05-16T17:00:00Z - `claude_current_session.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `7fed5baf-1ed9-4704-8717-3da01b034a44.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `28dfbccd-f4e2-4ad4-808a-ab9e4c0cde82.jsonl`

## Resolution

Implemented in full. Created `scripts/little_loops/cli/doctor.py` with `main_doctor()` following the `cli/docs.py` pattern. Registered the entry point in `pyproject.toml` and `cli/__init__.py`. Added `doctor.py` to the `cli/` listing in `CONTRIBUTING.md`. Wrote 13 tests in `scripts/tests/test_cli_doctor.py` covering exit codes, text/JSON output, status symbols, and hook sections. All 6736 tests pass; ruff and mypy clean.

---

**Done** | Created: 2026-05-16 | Priority: P4
