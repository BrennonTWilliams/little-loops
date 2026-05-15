---
id: FEAT-1473
type: FEAT
priority: P3
status: done
parent: FEAT-1466
depends_on: FEAT-1464
discovered_date: 2026-05-15
completed_at: 2026-05-15T16:17:24Z
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1473: Host Runner Docs Sweep + Doc-Wiring Test

## Summary

Update all required documentation for the `host_runner` abstraction introduced by FEAT-1464/1462, add a `Pi` column to `HOST_COMPATIBILITY.md`, update `CONTRIBUTING.md`, and create `scripts/tests/test_feat1462_doc_wiring.py` that enforces doc acceptance criteria via substring assertions. Best landed after FEAT-1472 so assertions reference concrete runner names.

## Parent Issue

Decomposed from FEAT-1466: OpenCodeRunner, PiRunner Stub, Docs Sweep, HOST_COMPATIBILITY.md Orchestration Row

## Scope

Covers Implementation Steps 8, 9, 10, 11, 12, 13, 14, and 15 from FEAT-1466.

**Explicitly out of scope**: Runner code implementation (FEAT-1472), CodexRunner (FEAT-1465), core scaffold (FEAT-1464).

## Acceptance Criteria

- [ ] `docs/ARCHITECTURE.md` updated: `host_runner` module added to the layering diagram (new subsection alongside hook-intent layer, NOT just the file-tree comment at line 254)
- [ ] `docs/reference/API.md` updated: new dedicated `## little_loops.host_runner` section with subsections for `resolve_host()`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` — mirror `little_loops.hooks` section layout (~line 5582)
- [ ] `docs/reference/HOST_COMPATIBILITY.md` updated: Pi column added to the orchestration table (lines 55–74); OpenCode column updated per Option B stub state; `[^orch]` footnote expanded to list all four runners (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`)
- [ ] `docs/development/TROUBLESHOOTING.md` updated: new entry for `HostNotConfigured` with `LL_HOST_CLI` remediation hint
- [ ] `.claude/CLAUDE.md` updated: note added near "Automation: Scratch Pad" section directing contributors to route new host-CLI calls through `resolve_host()` rather than adding new `"claude"` literals
- [ ] `CONTRIBUTING.md` line ~223 file-tree comment updated: `"HostRunner Protocol + ClaudeCodeRunner + CodexRunner"` → append `+ OpenCodeRunner + PiRunner`
- [ ] `scripts/tests/test_feat1462_doc_wiring.py` created: five `Test<Doc>Wiring` classes, one per doc file; substring-match assertions only; all tests pass
- [ ] `python -m pytest scripts/tests/test_feat1462_doc_wiring.py -v` passes

## Proposed Solution

### ARCHITECTURE.md update

The file-tree comment at line 254 already mentions `host_runner.py`. AC1 requires adding a NEW layering subsection explaining the module's role alongside the hook-intent layer. Locate the existing hook-intent components discussion and add a parallel `### Host Runner Layer` subsection.

### API.md new section

Mirror the `little_loops.hooks` section (~line 5582–5688):
- `Public surface — __all__ = [...]`
- `### resolve_host` — function signature + description
- `### HostInvocation` — dataclass fields (`binary`, `args`, `env`, `capabilities`)
- `### HostNotConfigured` — exception, `LL_HOST_CLI` remediation
- `### CapabilityNotSupported` — exception
- `---` separator before next module

Do NOT just amend the existing module-table row at line 35.

### HOST_COMPATIBILITY.md update

The orchestration table at lines 55–74 currently has three columns (Claude Code / OpenCode / Codex CLI). Add a **Pi** column:
- Claude Code: ✓ (`ClaudeCodeRunner`)
- OpenCode: stub (`OpenCodeRunner`, FEAT-1472)
- Codex: TBD (FEAT-1465)
- Pi: stub (`PiRunner`, FEAT-1472, research deferred to FEAT-992)

Expand the `[^orch]` footnote (currently ~line 68) which already mentions `ClaudeCodeRunner` — ADD `CodexRunner`, `OpenCodeRunner`, `PiRunner` to the sentence rather than rewriting it.

The tracking-issues section at line ~130 already references FEAT-992 for Pi.

### TROUBLESHOOTING.md entry

New entry template:
```markdown
### HostNotConfigured

**Symptom**: `HostNotConfigured: <host> orchestration not yet wired` when running `ll-auto`, `ll-parallel`, or `ll-sprint`.

**Cause**: The resolved host runner does not support CLI orchestration yet.

**Fix**: Set `LL_HOST_CLI=claude-code` in your environment to force Claude Code as the orchestration host, or install a supported host binary (`claude`).
```

### .claude/CLAUDE.md note

Near the "Automation: Scratch Pad" section (line ~133), add:

```markdown
### Host CLI Abstraction

All host CLI invocations must go through `resolve_host()` in `scripts/little_loops/host_runner.py`. Never add new `"claude"` literals to automation code — use `HostInvocation.binary` instead. Set `LL_HOST_CLI=<host>` to override host selection.
```

### CONTRIBUTING.md update

Locate file-tree comment at line ~223 that reads:
```
HostRunner Protocol + ClaudeCodeRunner + CodexRunner
```
Replace with:
```
HostRunner Protocol + ClaudeCodeRunner + CodexRunner + OpenCodeRunner + PiRunner
```

### Doc-wiring test

Follow `scripts/tests/test_feat1459_doc_wiring.py` invariants exactly:
- `PROJECT_ROOT = Path(__file__).parent.parent.parent` then per-doc `Path` constants at module level
- One `class Test<DocFile>Wiring` per doc file under test
- Assertion style: `content = SOME_PATH.read_text(); assert "token" in content, "descriptive message"`
- No regex, no imports beyond `pathlib.Path`

```python
# scripts/tests/test_feat1462_doc_wiring.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
API_DOC = PROJECT_ROOT / "docs" / "reference" / "API.md"
ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
HOST_COMPAT = PROJECT_ROOT / "docs" / "reference" / "HOST_COMPATIBILITY.md"
TROUBLESHOOTING = PROJECT_ROOT / "docs" / "development" / "TROUBLESHOOTING.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"


class TestApiMdWiring:
    """API.md must document the host_runner public surface."""

    def test_host_runner_module_listed(self) -> None:
        assert "host_runner" in API_DOC.read_text()

    def test_resolve_host_documented(self) -> None:
        assert "resolve_host" in API_DOC.read_text()

    def test_host_invocation_documented(self) -> None:
        assert "HostInvocation" in API_DOC.read_text()

    def test_host_not_configured_documented(self) -> None:
        assert "HostNotConfigured" in API_DOC.read_text()

    def test_capability_not_supported_documented(self) -> None:
        assert "CapabilityNotSupported" in API_DOC.read_text()


class TestArchitectureMdWiring:
    """ARCHITECTURE.md must include host_runner in the layering diagram."""

    def test_host_runner_in_layering(self) -> None:
        assert "host_runner" in ARCHITECTURE.read_text()


class TestHostCompatibilityWiring:
    """HOST_COMPATIBILITY.md must have an orchestration row with all four hosts."""

    def test_orchestration_row_present(self) -> None:
        assert "Orchestration" in HOST_COMPAT.read_text()

    def test_pi_column_present(self) -> None:
        assert "Pi" in HOST_COMPAT.read_text()


class TestTroubleshootingWiring:
    """TROUBLESHOOTING.md must have a HostNotConfigured entry."""

    def test_host_not_configured_entry(self) -> None:
        assert "HostNotConfigured" in TROUBLESHOOTING.read_text()

    def test_ll_host_cli_remediation(self) -> None:
        assert "LL_HOST_CLI" in TROUBLESHOOTING.read_text()


class TestClaudeMdWiring:
    """CLAUDE.md must reference host_runner or LL_HOST_CLI."""

    def test_host_runner_note_present(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "host_runner" in content or "LL_HOST_CLI" in content
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis on 2026-05-15:_

**All line-number claims in this issue are VERIFIED against the current tree:**
- `docs/ARCHITECTURE.md:254` — file-tree comment `├── host_runner.py       # Host CLI abstraction (HostRunner Protocol + ClaudeCodeRunner + CodexRunner)` exists.
- `docs/reference/API.md:5582–5688` — `## little_loops.hooks` section present with the exact structure described.
- `docs/reference/API.md:35` — module-table row for `little_loops.host_runner` already exists; do not duplicate.
- `docs/reference/HOST_COMPATIBILITY.md:55` — `## Orchestration CLI` heading; table starts at line 62; `[^orch]` footnote definition at line 70.
- `docs/reference/HOST_COMPATIBILITY.md:132–133` — FEAT-992 Pi-deferral note present.
- `.claude/CLAUDE.md:133` — `## Automation: Scratch Pad` heading present.
- `CONTRIBUTING.md:223` — file-tree comment matches claim verbatim.

**Actual `host_runner.py` `__all__` (scripts/little_loops/host_runner.py:32–43)** — the AC names only 4 of 10 exports:

```python
__all__ = [
    "CapabilityNotSupported",
    "ClaudeCodeRunner",
    "CodexRunner",
    "HostCapabilities",
    "HostInvocation",
    "HostNotConfigured",
    "HostRunner",
    "OpenCodeRunner",
    "PiRunner",
    "resolve_host",
]
```

The API.md section should additionally document `HostRunner` (Protocol) and `HostCapabilities` (dataclass) to mirror the full public surface — the four concrete runner classes (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`) can be listed in a single "Concrete runners" subsection. Out-of-scope for AC but recommended for completeness; the AC's four-name minimum still holds.

**Exact current `[^orch]` footnote text (docs/reference/HOST_COMPATIBILITY.md:70)** — needs editing in place, not rewriting:

> All six call sites now route through `scripts/little_loops/host_runner.py` (`HostRunner` Protocol + `ClaudeCodeRunner`). Wiring a non-Claude host means registering a new `HostRunner` implementation; the orchestration layer no longer hard-codes the `claude` binary or its argv.

Append `+ CodexRunner + OpenCodeRunner + PiRunner` to the parenthetical and leave the rest unchanged.

**API.md `little_loops.hooks` formatting convention** — bold-headed sub-sections, not `####` headings:

The hooks section uses `**Fields:**` and `**Behavior:**` bold labels under each `### Name` heading (not `#### Constructor` / `#### Methods` as `little_loops.events` and `little_loops.config` do). Follow the hooks style for `little_loops.host_runner` per AC. Section ordering within hooks is: input dataclass → output dataclass → entry-point function — the host_runner analogue is: `HostInvocation` → `HostCapabilities` → `HostRunner` (Protocol) → `resolve_host()` → exceptions (`HostNotConfigured`, `CapabilityNotSupported`).

**Section separator convention** — bare `---` on its own line with blank lines above/below, between every `## little_loops.*` section (verified at API.md lines 63, 311, 549, 5580, 5688).

**Test scaffold corrections** — the pattern file `scripts/tests/test_feat1459_doc_wiring.py` uses two conventions the scaffold in this issue omits:

1. `from __future__ import annotations` at the top (after the module docstring) — add this for consistency with all 26 existing `test_*_doc_wiring.py` files.
2. Module docstring naming the issue: `"""Tests for FEAT-1462: <description>. Verifies that <doc surfaces> cover <feature> per the acceptance criteria enumerated in FEAT-1462."""` — every existing doc-wiring test has this.
3. Bind `content = SOME_PATH.read_text()` to a local variable before asserting, even for single-assertion tests — every existing test does this consistently.

The scaffold's bare `assert "host_runner" in API_DOC.read_text()` style works but is inconsistent with the established pattern.

**Existing doc-wiring tests for reference** (26 in `scripts/tests/`): closest structural matches are `test_feat1459_doc_wiring.py` (5 doc files, multiple `Test<Doc>Wiring` classes — exact pattern this issue targets) and `test_feat1457_doc_wiring.py` (similar multi-doc structure with negative assertions and existence checks).

## Files to Modify

- `docs/ARCHITECTURE.md` — host_runner layering subsection (line 254 has the file-tree comment; AC1 requires a NEW layering subsection elsewhere)
- `docs/reference/API.md` — new `## little_loops.host_runner` section (insert between existing sections following separator convention; do NOT amend line 35 module-table row, which already exists)
- `docs/reference/HOST_COMPATIBILITY.md` — Pi column added to table (lines 62–68), OpenCode stub update, footnote text at line 70 expanded in place
- `docs/development/TROUBLESHOOTING.md` — `HostNotConfigured` entry
- `.claude/CLAUDE.md` — host_runner note near "Automation: Scratch Pad" (line 133)
- `CONTRIBUTING.md` — file-tree comment at line 223

## New Files

- `scripts/tests/test_feat1462_doc_wiring.py` — doc acceptance criteria enforcement

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

These files import `host_runner` symbols. FEAT-1473 changes are purely additive — these callers do not need modification, but are listed for implementer context:
- `scripts/little_loops/__init__.py` — re-exports only 4 of 10 `host_runner` symbols (`CapabilityNotSupported`, `HostInvocation`, `HostNotConfigured`, `HostRunner`); the API.md `## little_loops.host_runner` section must document `host_runner.__all__` (10 symbols, lines 32–43 of `host_runner.py`), NOT `little_loops.__all__` [Agent 1 finding]
- `scripts/little_loops/cli/action.py` — calls `resolve_host().detect()` in `cmd_capabilities()` [Agent 1 finding]
- `scripts/little_loops/fsm/evaluators.py` — calls `resolve_host()` for FSM structured evaluation [Agent 1 finding]
- `scripts/little_loops/fsm/handoff_handler.py` — calls `resolve_host().build_detached()` in `HandoffHandler.handle()` [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py` — calls `resolve_host()` for worker process spawning [Agent 1 finding]
- `docs/generalized-fsm-loop.md` — contains `from little_loops.host_runner import resolve_host` example; unaffected by doc changes [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**New test file (this issue):**
- `scripts/tests/test_feat1462_doc_wiring.py` — created by this issue; follow `test_feat1459_doc_wiring.py` exactly: module docstring naming FEAT-1462, `from __future__ import annotations` immediately after docstring, `from pathlib import Path` as the only import, and `content = PATH.read_text()` bound to a local variable before every assertion (even single-assertion tests)

**Existing tests to run after each doc change (verify no regressions):**
- `scripts/tests/test_feat1457_doc_wiring.py` — asserts on CONTRIBUTING.md (`LLHookIntentExtension`, `LLHookEvent`), CLAUDE.md (`scripts/little_loops/hooks/`, `adapters/`), TROUBLESHOOTING.md paths — safe if changes are additive [Agent 3 finding]
- `scripts/tests/test_feat1447_doc_wiring.py` — asserts on CONTRIBUTING.md (`30 skill definitions`) — safe if only line 223 is changed [Agent 3 finding]
- `scripts/tests/test_feat1287_doc_wiring.py` — asserts on CLAUDE.md (`(30 skills)`, `ll-learning-tests`) [Agent 3 finding]
- `scripts/tests/test_feat1407_doc_wiring.py` — asserts on CLAUDE.md (`EPIC`) [Agent 3 finding]
- `scripts/tests/test_feat1459_doc_wiring.py` — asserts on TROUBLESHOOTING.md hook script paths, API.md hooks section [Agent 3 finding]
- `scripts/tests/test_feat1172_doc_wiring.py` — asserts on API.md (`update_frontmatter`) [Agent 3 finding]
- `scripts/tests/test_host_runner.py` — behavioral tests for all runner classes; not affected by docs-only changes but confirm green [Agent 1 finding]
- `scripts/tests/test_extension.py` — smoke imports for `HostRunner`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` from `little_loops` [Agent 1 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

No changes needed — already up to date:
- `docs/reference/CONFIGURATION.md` — already fully documents `orchestration`, `LL_HOST_CLI`, `HostNotConfigured`, all four runner enum values (`claude-code`, `codex`, `opencode`, `pi`) [Agent 2 finding]
- `config-schema.json` — already has `orchestration.host_cli` with enum `["auto", "claude-code", "codex", "opencode", "pi"]` and default `"auto"` [Agent 2 finding]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. After each doc file update, run the overlapping doc-wiring regression suite: `python -m pytest scripts/tests/test_feat1457_doc_wiring.py scripts/tests/test_feat1447_doc_wiring.py scripts/tests/test_feat1287_doc_wiring.py scripts/tests/test_feat1407_doc_wiring.py scripts/tests/test_feat1459_doc_wiring.py scripts/tests/test_feat1172_doc_wiring.py -v`
2. When writing `test_feat1462_doc_wiring.py`: source the `__all__` list from `host_runner.__all__` (10 symbols at `scripts/little_loops/host_runner.py:32–43`), not from `little_loops.__init__.__all__` (only 4 symbols)
3. Final gate: `python -m pytest scripts/tests/test_feat1462_doc_wiring.py -v` passes with all assertions green

## Dependencies

- **FEAT-1464** must land first (provides the `host_runner.py` module being documented)
- **FEAT-1472** should land first (provides `OpenCodeRunner` and `PiRunner` so doc references are concrete), but can proceed in parallel
- Can run in parallel with **FEAT-1472**

## Resolution

Implemented 2026-05-15. All acceptance criteria met:

- `docs/ARCHITECTURE.md` — new `## Host Runner Layer` section added after Extension Architecture, alongside the hook-intent layer; documents the Protocol, value objects, exceptions, four concrete runners, and the `resolve_host()` discovery rule. File-tree comment at line 254 already in place.
- `docs/reference/API.md` — new `## little_loops.host_runner` section inserted between `## little_loops.hooks` and `## little_loops.transport`, mirroring the hooks-section layout (bold `**Fields:**` / `**Behavior:**` labels, dedicated subsections per export). Module-overview row at line 35 expanded to list all four runners.
- `docs/reference/HOST_COMPATIBILITY.md` — Pi column added to the orchestration table; OpenCode column updated to `stub`; Codex marked `gated`; `[^orch]` footnote expanded in place to name all four runners (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`) with the stub/gated semantics defined.
- `docs/development/TROUBLESHOOTING.md` — `### HostNotConfigured` entry added at the end of the Claude CLI Issues section, covering both `LL_HOST_CLI=claude-code` fallback and the stub-runner case.
- `.claude/CLAUDE.md` — new `## Host CLI Abstraction` section added before `## Automation: Scratch Pad`, directing contributors to route host-CLI calls through `resolve_host()` rather than adding new `"claude"` literals.
- `CONTRIBUTING.md` — file-tree comment at line 223 appended `+ OpenCodeRunner + PiRunner`.
- `scripts/tests/test_feat1462_doc_wiring.py` — 5 `Test<Doc>Wiring` classes, 12 assertions, following `test_feat1459_doc_wiring.py` invariants verbatim (`from __future__ import annotations`, `PROJECT_ROOT` constant, `content = PATH.read_text()` bound locally, substring-only assertions).

**Verification:**
- `python -m pytest scripts/tests/test_feat1462_doc_wiring.py -v` — 12 passed.
- Overlapping regression suite (FEAT-1457/1447/1287/1407/1459/1172 doc-wiring tests) — 102 total passed.
- Full `python -m pytest scripts/tests/` — 6575 passed; 5 pre-existing failures (README pillars, marketplace version sync — unrelated to this issue, also fail on `HEAD` pre-change).
- `ruff check` + `mypy` on the new test file — clean.

## Session Log
- `/ll:manage-issue` - 2026-05-15T16:17:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74989793-8902-46f0-8ede-54024c676c0d.jsonl`
- `/ll:ready-issue` - 2026-05-15T16:10:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/209f2886-399d-46b4-8ff2-ab8828434471.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c46e81e8-7919-42c6-9c3d-c06c3317134a.jsonl`
- `/ll:wire-issue` - 2026-05-15T16:06:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc0dd184-e030-4410-a4ee-0cb7dce96a23.jsonl`
- `/ll:refine-issue` - 2026-05-15T16:00:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9dd271a-e4aa-48c2-a86f-d0b6134ac1cb.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3404bce4-b1e1-4c4a-bdaf-327d629a43da.jsonl`
