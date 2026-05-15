---
id: FEAT-1473
type: FEAT
priority: P3
status: open
parent: FEAT-1466
depends_on: FEAT-1464
discovered_date: 2026-05-15
discovered_by: issue-size-review
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

## Files to Modify

- `docs/ARCHITECTURE.md` — host_runner layering subsection
- `docs/reference/API.md` — new `## little_loops.host_runner` section
- `docs/reference/HOST_COMPATIBILITY.md` — Pi column, OpenCode stub update, expanded footnote
- `docs/development/TROUBLESHOOTING.md` — `HostNotConfigured` entry
- `.claude/CLAUDE.md` — host_runner note near "Automation: Scratch Pad"
- `CONTRIBUTING.md` — file-tree comment at line ~223

## New Files

- `scripts/tests/test_feat1462_doc_wiring.py` — doc acceptance criteria enforcement

## Dependencies

- **FEAT-1464** must land first (provides the `host_runner.py` module being documented)
- **FEAT-1472** should land first (provides `OpenCodeRunner` and `PiRunner` so doc references are concrete), but can proceed in parallel
- Can run in parallel with **FEAT-1472**

## Session Log
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3404bce4-b1e1-4c4a-bdaf-327d629a43da.jsonl`
