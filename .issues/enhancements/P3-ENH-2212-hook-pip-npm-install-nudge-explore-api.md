---
id: ENH-2212
title: Hook on pip/npm install to nudge explore-api for new dependencies
type: enhancement
priority: P3
status: done
parent: EPIC-2207
relates_to:
- ENH-2209
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T03:27:26Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 22
implementation_order_risk: true
decision_needed: false
---

# ENH-2212: Hook on pip/npm install to nudge explore-api for new dependencies

## Summary

When an agent or user runs `pip install <pkg>` or `npm install <pkg>`, nothing currently triggers a learning test check. Add a `PostToolUse` hook on Bash that detects install commands, extracts the package name, queries the registry, and nudges `/ll:explore-api` if no proven record exists. This is the highest-leverage injection point: the exact moment a new external dependency enters the project.

## Current Behavior

Currently, there is no hook or automated process that detects when a new Python or Node.js dependency is installed via `pip install`, `npm install`, or related package manager commands. When an agent or user installs a new package, the learning test registry is never consulted at that moment. This creates a gap where code may be written against unproven API surfaces without prior exploration via `/ll:explore-api`.

The existing `PostToolUse` wildcard hook in `hooks/hooks.json` (`"matcher": "*"`) fires for all Bash tool calls via `hooks/adapters/claude-code/post-tool-use.sh`, routing to `post_tool_use.handle()` in `scripts/little_loops/hooks/post_tool_use.py`. That handler does analytics writes and auto-commit checks but never consults the learning test registry.

## Expected Behavior

When a `Bash` tool call contains a `pip install`, `pip3 install`, `uv add`, `poetry add`, `npm install`, `yarn add`, or `pnpm add` command, a `PostToolUse` hook should:

1. Detect the install command and extract the package name.
2. Normalize the package name (strip version specifiers and extras).
3. Query the learning test registry via `check_learning_test(pkg)`.
4. Check staleness via `is_record_stale(record, lt_config.stale_after_days)`.
5. Emit a nudge message referencing `/ll:explore-api` if no proven record exists or the record is stale.
6. Emit nothing (silent pass) if a proven record already exists and is fresh.

All behavior is gated behind `learning_tests.enabled` in config.

## Motivation

Install-time is cheap. Proof-later is expensive. A nudge at install time — before any code is written against the new package — costs nothing and prevents the entire pattern of writing code against unknown API surfaces.

## Scope Boundaries

- **In scope**: Detecting `pip install <pkg>`, `pip3 install <pkg>`, `uv add <pkg>`, `poetry add <pkg>`, `npm install <pkg>`, `yarn add <pkg>`, `pnpm add <pkg>`; extracting and normalizing package names; querying learning test registry; emitting nudge messages
- **Out of scope**: Blocking installs (nudge only, not a gate); `pip install -r requirements.txt` (too noisy, no single package name); transitive dependencies (only the explicitly installed package); existing or previously-installed dependencies (only new install invocations); configuration of `learning_tests.enabled` (already exists)

## Proposed Solution

### Option A: Delegate from existing `post_tool_use.handle()` (follows pre_tool_use pattern)

> **Selected:** Option A — Delegate from existing post_tool_use.handle() — zero double-execution overhead; mirrors pre_tool_use delegation pattern exactly; fewest files changed

Add a delegation call inside `post_tool_use.handle()` in `scripts/little_loops/hooks/post_tool_use.py` when `tool_name == "Bash"`, mirroring how `pre_tool_use.handle()` delegates to `learning_tests_gate.gate()`. No new hook entry in `hooks/hooks.json` is needed — the existing `"*"` PostToolUse matcher already fires for Bash.

**Changes:**
- `scripts/little_loops/hooks/install_learning_gate.py` — new module with `gate(event)` function
- `scripts/little_loops/hooks/post_tool_use.py:handle()` — add `if tool_name == "Bash": install_learning_gate.gate(event)` call
- `scripts/little_loops/learning_tests/gate.py` — add `format_nudge_message(pkg, stale)` shared formatter
- No changes to `hooks/hooks.json` or `hooks/__init__.py`

**Tradeoff**: Simpler (no new intent/adapter), consistent with how pre_tool_use delegates, but install-gate logic is hidden inside a handler that callers expect to handle analytics only.

### Option B: Separate hook entry with new intent and adapter script

Add a dedicated `"Bash"` matcher entry to the `PostToolUse` array in `hooks/hooks.json`, with its own shell adapter `hooks/adapters/claude-code/install-gate.sh` invoking a new intent (`post_install_gate`), and register `install_learning_gate.handle` in `_dispatch_table()`.

**Changes:**
- `hooks/hooks.json` — new `{"matcher": "Bash", "hooks": [...]}` entry in `"PostToolUse"` array
- `hooks/adapters/claude-code/install-gate.sh` — new 3-line adapter (pattern: `hooks/adapters/claude-code/post-tool-use.sh`)
- `scripts/little_loops/hooks/install_learning_gate.py` — new module with `handle(event)` function
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` — add `"post_install_gate": install_learning_gate.handle`
- `scripts/little_loops/learning_tests/gate.py` — add `format_nudge_message()` shared formatter

**Tradeoff**: More surgical (Bash-only hook, clear intent boundary), but both the existing `"*"` entry and the new `"Bash"` entry would fire on Bash tool calls (double execution overhead on every Bash call — analytics + install check would be separate Python process invocations).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-18.

**Selected**: Option A — Delegate from existing `post_tool_use.handle()`

**Reasoning**: Option B's `"Bash"` PostToolUse matcher entry fires alongside both existing `"*"` catch-alls (no deduplication mechanism in hooks.json), adding a fourth Python process invocation to every Bash tool call regardless of whether it is an install command — an unacceptable overhead for a nudge-only feature. Option A reuses the established `pre_tool_use.handle() → learning_tests_gate.gate()` delegation pattern, adds no hooks.json change, and places the install-gate logic inside a handler that already has two independent conditional blocks (analytics and auto-commit), making a third block structurally consistent.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (delegate) | 2/3 | 3/3 | 2/3 | 2/3 | 9/12 |
| Option B (new intent) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: `pre_tool_use.handle()` → `learning_tests_gate.gate()` delegation at `scripts/little_loops/hooks/pre_tool_use.py:28` is the direct template; `post_tool_use.handle()` already has analytics + auto-commit as independent conditional blocks at lines 151–202.
- Option B: `hooks/hooks.json` PostToolUse has no exclusion/deduplication mechanism — three entries (`"*"` analytics, `"*"` context-monitor, new `"Bash"`) all fire on every Bash call. `"Bash"` PostToolUse matcher has zero precedent in the current file.

## Implementation Steps

1. **Add shared nudge formatter** — Add `format_nudge_message(pkg: str, stale: bool = False) -> str` to `scripts/little_loops/learning_tests/gate.py`. Format: `[ll: new dependency] No learning test for "<pkg>". Consider: /ll:explore-api "<pkg>"`. This function must be usable by both this hook and ENH-2209's auto-population logic.

2. **Create `install_learning_gate.py`** — New file at `scripts/little_loops/hooks/install_learning_gate.py` with:
   - `_INSTALL_RE: re.Pattern` — regex matching `pip[3]? install`, `uv add`, `poetry add`, `npm install`, `yarn add`, `pnpm add` followed by non-flag package name
   - `_normalize_pkg(raw: str) -> str | None` — strips version specifiers (`>=`, `==`, `~=`), extras (`[...]`), returns `None` for `-r` / `--requirement` / empty strings
   - `gate(event: LLHookEvent) -> LLHookResult` — config-load → parse command → normalize → `check_learning_test()` + `is_record_stale()` → return feedback or no-op
   - Config loading: follow `_load_lt_config(cwd)` pattern from `scripts/little_loops/hooks/learning_tests_gate.py` using `LearningTestsConfig.from_dict()` from `scripts/little_loops/config/features.py`

3. **Wire into `post_tool_use.handle()` (Option A)** or **register new intent (Option B)**:
   - Option A: In `scripts/little_loops/hooks/post_tool_use.py:handle()`, after the analytics block, add: `if tool_name == "Bash": result = install_learning_gate.gate(event); return result` (guarded so it still returns `LLHookResult(exit_code=0)` on all non-Bash paths)
   - Option B: Add to `hooks/hooks.json` `PostToolUse` array; create `hooks/adapters/claude-code/install-gate.sh` following the 3-line pattern in `hooks/adapters/claude-code/post-tool-use.sh`; add `"post_install_gate": install_learning_gate.handle` in `scripts/little_loops/hooks/__init__.py:_dispatch_table()`

4. **Write tests** — Create `scripts/tests/test_install_learning_gate.py` using:
   - `_event()` factory pattern from `scripts/tests/test_learning_tests_discoverability.py:_event()` (adapt for `tool_name="Bash"`, `tool_input={"command": cmd}`)
   - `_write_config()` helper to set `learning_tests.enabled`
   - `_write_record()` helper from `test_learning_tests_discoverability.py` to create proven/stale records
   - `clear_session_cache` fixture from `test_learning_tests_discoverability.py` (clears `_SESSION_CACHE` between tests)
   - Five acceptance-signal test cases from the Acceptance Signals section

5. **Verify** — Run `python -m pytest scripts/tests/test_install_learning_gate.py -v`

## Integration Map

### Files to Modify

- `scripts/little_loops/learning_tests/gate.py` — Add `format_nudge_message(pkg, stale=False)` shared formatter (required for ENH-2209 consistency)
- `scripts/little_loops/hooks/post_tool_use.py` — (Option A) Add delegation to `install_learning_gate.gate(event)` in `handle()` when `tool_name == "Bash"`
- `hooks/hooks.json` — (Option B only) Add `{"matcher": "Bash", ...}` entry to `PostToolUse` array
- `scripts/little_loops/hooks/__init__.py` — (Option B only) Add `"post_install_gate": install_learning_gate.handle` to `_dispatch_table()`

### New Files

- `scripts/little_loops/hooks/install_learning_gate.py` — New hook handler with regex parsing, normalization, and registry query
- `hooks/adapters/claude-code/install-gate.sh` — (Option B only) New 3-line shell adapter (identical pattern to `hooks/adapters/claude-code/post-tool-use.sh`)
- `scripts/tests/test_install_learning_gate.py` — New test file

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/post_tool_use.py:handle()` — will import and call `install_learning_gate.gate(event)` (Option A)
- `scripts/little_loops/hooks/learning_tests_gate.py:gate()` — will import `format_nudge_message` from `scripts/little_loops/learning_tests/gate.py` (both issues use the same formatter)
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` — (Option B) registers the new intent

### Similar Patterns

- `scripts/little_loops/hooks/learning_tests_gate.py:gate()` — **direct model** for the new `install_learning_gate.gate()`: config load → extract packages from content → `check_learning_test()` + `is_record_stale()` → feedback
- `scripts/little_loops/hooks/pre_tool_use.py:handle()` — delegation pattern to `learning_tests_gate.gate()` (mirrors the Option A wiring approach)
- `scripts/little_loops/hooks/post_tool_use.py:_extract_file_path()` — already reads `tool_input.get("command") or ""` for `tool_name == "Bash"`, establishes access pattern
- `hooks/adapters/claude-code/post-tool-use.sh` — 3-line adapter pattern for Option B

### Tests

- `scripts/tests/test_install_learning_gate.py` — NEW (co-deliverable)
- `scripts/tests/test_learning_tests_discoverability.py` — source of `_event()`, `_write_config()`, `_write_record()`, `clear_session_cache` helpers to copy/adapt
- `scripts/tests/test_hook_post_tool_use.py` — (Option A) may need updates if `handle()` is modified
- `scripts/tests/test_hook_intents.py:TestHooksMainModule.test_dispatch_post_tool_use_happy_path` — subprocess integration test pattern

### Documentation

- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — add entry for the new install-nudge hook behavior
- `docs/guides/LEARNING_TESTS_GUIDE.md` — document install-time nudge trigger

### Configuration

- `.ll/ll-config.json` — `learning_tests.enabled` gate (existing config key); `learning_tests.stale_after_days` (used by `is_record_stale()`)
- No new config keys required

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2211 (debt marker) was cancelled per EPIC-2207 scoping review. This hook is now the sole PostToolUse detection path for unproven packages — no session-scoped cache coordination with a sibling hook is needed.

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2208 (stale-aware gate). The implementation must use the standalone `is_record_stale(record, stale_after_days)` helper that ENH-2208 exposes in `scripts/little_loops/learning_tests/gate.py`, rather than calling `check_learning_test()` directly. `check_learning_test()` returns registry status without date arithmetic — a date-old proven record would return "proven" and the nudge would be silently skipped. The correct call sequence is: (1) call `check_learning_test(pkg)` to get the record; (2) call `is_record_stale(record, lt_config.stale_after_days)` to determine effective staleness; (3) emit the nudge if no record exists or `is_record_stale` returns True. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2209 (refine-issue/wire-issue auto-population) both produce a proven/unproven summary message. Without a shared format, users see inconsistent phrasing depending on whether they encounter an unproven package via an install hook or via refine-issue. The nudge message format must be defined once in the shared gate utility (`scripts/little_loops/learning_tests/gate.py`) and used by both issues. See [[ENH-2209]].

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Hook payload access for Bash tool calls:**
- `tool_input["command"]` is the full shell command string passed by Claude Code for Bash tool calls
- Existing access pattern (already in codebase): `tool_input.get("command") or ""` in `post_tool_use.py:_extract_file_path()`
- Claude Code PostToolUse JSON shape: `{"tool_name": "Bash", "tool_input": {"command": "..."}, "tool_response": {...}, "session_id": "..."}`

**Dispatch table — how to add a new intent (Option B):**
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` builds a `dict[str, Callable[[LLHookEvent], LLHookResult]]`
- New intent: add `"post_install_gate": install_learning_gate.handle` alongside existing entries (`post_tool_use`, `pre_tool_use`, etc.)
- Shell adapter must call `python -m little_loops.hooks post_install_gate` (the intent name passed as `sys.argv[1]`)

**No existing install-command regex in codebase:**
- `scripts/little_loops/hooks/post_tool_use.py:_BASH_PATH_RE` matches file paths in Bash commands — unrelated
- Package normalization for pip (`>=`, `==`, `[extras]`) is not yet implemented anywhere
- JS package normalization (strip scope path: `@scope/pkg/subpath` → `@scope/pkg`) exists in `learning_tests_gate.py:_extract_packages()`

**Session-level cache:**
- `scripts/little_loops/hooks/learning_tests_gate.py:_SESSION_CACHE: dict[str, bool]` — module-level dict; `True` = proven/fresh, `False` = missing/stale
- Copy this pattern to `install_learning_gate.py` to avoid redundant registry reads on repeated installs
- Test fixture pattern: `clear_session_cache` autouse fixture in `test_learning_tests_discoverability.py` clears `_SESSION_CACHE` between tests

**Config loading typed pattern (prefer this over raw dict):**
```python
# from learning_tests_gate.py:_load_lt_config()
from little_loops.config.core import resolve_config_path
from little_loops.config.features import LearningTestsConfig

def _load_lt_config(cwd: Path) -> LearningTestsConfig:
    config_path = resolve_config_path(cwd)
    if config_path is None:
        return LearningTestsConfig()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LearningTestsConfig()
    return LearningTestsConfig.from_dict(data.get("learning_tests", {}))
```

**`LLHookResult` feedback semantics for PostToolUse:**
- `exit_code=0, feedback="..."` → feedback written to stderr, tool call allowed (warn mode, appropriate for nudge)
- `exit_code=2, feedback="..."` → blocks and injects feedback (not appropriate for install nudge — nudge only, no blocking)

**`check_learning_test()` import path:**
```python
from little_loops.learning_tests import check_learning_test  # returns LearnTestRecord | None
from little_loops.learning_tests.gate import is_record_stale  # returns bool
```

**Existing nudge message format in `learning_tests_gate.py`** (proof-first hint):
```
[ll: proof-first hint] No learning-test record found for "pkg". You're about to write integration code based on training-data assumptions. Consider: ll-loop run proof-first-task ...
```
The install-gate nudge format (per issue spec): `[ll: new dependency] No learning test for "<pkg>". Consider: /ll:explore-api "<pkg>"`
Both formats must use the shared `format_nudge_message()` in `scripts/little_loops/learning_tests/gate.py`.

### Codebase Research Findings (full-rewrite pass — 2026-06-18)

_Added by `/ll:refine-issue` — based on codebase analysis:_

**ENH-2208 is completed — no prerequisite blocks this issue:**
- `is_record_stale(record, stale_after_days)` is live at `scripts/little_loops/learning_tests/gate.py:17`
- `format_nudge_message()` does NOT yet exist in that file — confirmed gap; only `is_record_stale()` is there

**`check_learning_test()` `base_dir` parameter — must pass explicitly:**
```python
from little_loops.learning_tests import check_learning_test
record = check_learning_test(pkg, base_dir=cwd / ".ll" / "learning-tests")
```
`base_dir` is `Path | None` and defaults to `Path.cwd() / ".ll/learning-tests"` if `None`. Since the hook process CWD may differ from the project root (Claude Code can invoke hooks from any directory), always pass `base_dir=cwd / ".ll" / "learning-tests"` explicitly — `cwd` from `event.cwd` is the project root.

**`post_tool_use.handle()` exact insertion point (Option A):**
The new Bash gate block goes **between line 202 (auto-commit) and line 204 (unconditional return)**:
```python
# line 201: if config is not None and tool_name in {"Write", "Edit"} and raw_path:
# line 202:     _maybe_auto_commit(config, cwd, raw_path, tool_name)
# NEW (~line 203):
if tool_name == "Bash":
    from little_loops.hooks import install_learning_gate
    return install_learning_gate.gate(event)
# line 204: return LLHookResult(exit_code=0)
```
Safe placement: auto-commit never fires for Bash (`tool_name in {"Write", "Edit"}` is always false). The lazy import (`from little_loops.hooks import install_learning_gate` inside the `if`) avoids top-level circular import surface — mirrors how `pre_tool_use.handle()` lazily imports `learning_tests_gate`.

**`_bash_event()` test construction — factory does NOT support Bash:**
The `_event()` factory in `test_learning_tests_discoverability.py` only builds `Write`/`Edit` payloads. For `install_learning_gate` tests, construct `LLHookEvent` directly:
```python
from little_loops.hooks.types import LLHookEvent

def _bash_event(cmd: str, cwd: str) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code",
        intent="post_tool_use",
        payload={"tool_name": "Bash", "tool_input": {"command": cmd}},
        cwd=cwd,
    )
```
Note: `intent="post_tool_use"` (not `"pre_tool_use"`) since this is the PostToolUse path.

**`clear_session_cache` fixture — import from the new module:**
For `test_install_learning_gate.py`, import `_SESSION_CACHE` from `install_learning_gate` (the new module), not from `learning_tests_gate`:
```python
from little_loops.hooks.install_learning_gate import _SESSION_CACHE

@pytest.fixture(autouse=True)
def clear_session_cache() -> Generator[None, None, None]:
    _SESSION_CACHE.clear()
    yield
    _SESSION_CACHE.clear()
```

**Stale nudge message format — not yet specified in issue body:**
`format_nudge_message(pkg, stale=True)` should mirror the stale annotation in `learning_tests_gate.py`. Suggested format:
- Fresh missing: `[ll: new dependency] No learning test for "<pkg>". Consider: /ll:explore-api "<pkg>"`
- Stale: `[ll: new dependency] Learning test for "<pkg>" is stale. Consider: /ll:explore-api "<pkg>"`

## Acceptance Signals

- `Bash("pip install httpx")` triggers a nudge: "No learning test for 'httpx'..."
- `Bash("pip install requests")` where `requests` has a proven record emits nothing
- `Bash("pip install -r requirements.txt")` is skipped (too noisy, no single package name)
- Version specifiers stripped: `pip install anthropic>=0.20` → checks `anthropic`
- Extras stripped: `pip install "anthropic[bedrock]"` → checks `anthropic`

## Impact

- **Priority**: P3 — High-leverage automation that catches missing learning tests at the earliest possible moment, blocking the costliest pattern before any code is written
- **Effort**: Medium — New hook handler with regex parsing and registry query; existing hook infrastructure can be reused
- **Risk**: Low — Fully gated behind `learning_tests.enabled` config flag; nudge only, no blocking behavior; silent pass for proven records
- **Breaking Change**: No — Adds optional nudge behavior; existing workflows and install commands unaffected

## Related Key Documentation

- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — built-in hook catalog
- `docs/guides/LEARNING_TESTS_GUIDE.md` — learning test registry usage

## Labels

`enhancement`, `hooks`, `learning-tests`, `captured`

## Status

**Open** | Created: 2026-06-18 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-18, updated 2026-06-18_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Tests are **co-deliverables** of this issue — write `test_install_learning_gate.py` alongside `install_learning_gate.py`, using the five acceptance signals as the spec (httpx nudge, requests silent pass, requirements.txt skip, version specifier strip, extras strip)
- The shared nudge format function belongs in `gate.py` — **implement first so** both the install hook and the PreToolUse gate can reference a common formatter; format string is already specified in the issue body

## Session Log
- `/ll:ready-issue` - 2026-06-19T03:13:26 - `84dd549f-3f27-4673-ad06-8be737793484.jsonl`
- `/ll:confidence-check` - 2026-06-18T23:55:00 - `99e321aa-8389-47b4-9453-ec006830044f.jsonl`
- `/ll:refine-issue` - 2026-06-19T03:06:32 - `26f76c56-7e1b-4482-842b-ac61ee4ca021.jsonl`
- `/ll:decide-issue` - 2026-06-19T02:54:09 - `b6e3e403-649c-406c-8c0b-5a3a981e82c5.jsonl`
- `/ll:refine-issue` - 2026-06-19T02:49:33 - `58f32f47-b086-43cd-b87f-f61b4fa4cfa6.jsonl`
- `/ll:refine-issue` - 2026-06-18T00:00:00Z - `unknown`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `9b3ef9f8-be05-473d-b249-2ce92bfb1e19.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:54 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T19:32:41 - `ef0b05a4-a7e0-47d6-afa2-5f2b99558da6.jsonl`
- `/ll:confidence-check` - 2026-06-18T23:30:00 - `017f1b69-a60e-405e-9d0e-e2ab0baacad9.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
