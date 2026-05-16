---
id: FEAT-1466
type: FEAT
priority: P3
status: done
parent: FEAT-1462
depends_on: FEAT-1464
decision_needed: true
discovered_date: 2026-05-15
discovered_by: issue-size-review
confidence_score: 85
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# FEAT-1466: OpenCodeRunner, PiRunner Stub, Docs Sweep, HOST_COMPATIBILITY.md Orchestration Row

## Summary

After FEAT-1464 lands, add `OpenCodeRunner` (OpenCode has a hook adapter since FEAT-769 but no orchestration story) and stub `PiRunner` (raises `HostNotConfigured` until FEAT-992 Pi plugin API research lands). Run the final grep sweep to confirm no hard-coded `"claude"` literals remain. Update all required documentation. Create the doc-wiring test file that enforces doc acceptance criteria. Can run in parallel with FEAT-1465.

## Parent Issue

Decomposed from FEAT-1462: Abstract Host CLI Invocation in Orchestration Layer

## Scope

Covers Implementation Steps 5, 6, 7, 8, and 15 from the parent issue.

**Explicitly out of scope**: CodexRunner (FEAT-1465), core scaffold and call site migrations (FEAT-1464).

## Acceptance Criteria

- [ ] `OpenCodeRunner` added to `host_runner.py`; implements all four factory methods (`build_streaming`, `build_blocking_json`, `build_version_check`, `build_detached`)
- [ ] `PiRunner` stub added; raises `HostNotConfigured("Pi orchestration not yet wired — see FEAT-992")` from all build methods
- [ ] `grep -rn '"claude"' scripts/little_loops/` returns no hard-coded binary literals (only comments/docs/test fixtures) — sweep confirms FEAT-1464's grep AC holds after this PR too
- [ ] `docs/ARCHITECTURE.md` updated: `host_runner` module added to the layering diagram alongside the hook-intent layer
- [ ] `docs/reference/API.md` updated: public API entries for `resolve_host()`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported`
- [ ] `docs/reference/HOST_COMPATIBILITY.md` updated: orchestration row added per-host (Claude Code ✓, Codex TBD per FEAT-1465, OpenCode ✓, Pi stub)
- [ ] `docs/development/TROUBLESHOOTING.md` updated: entry for `HostNotConfigured` with `LL_HOST_CLI` remediation hint
- [ ] `.claude/CLAUDE.md` updated: note about `host_runner` abstraction near "Automation: Scratch Pad" so contributors know not to add new `"claude"` literals
- [ ] `scripts/tests/test_feat1462_doc_wiring.py` created: asserts all five doc files contain required references (`API.md` has `host_runner`, `ARCHITECTURE.md` mentions `host_runner`, `HOST_COMPATIBILITY.md` has orchestration row, `TROUBLESHOOTING.md` has `HostNotConfigured`, `.claude/CLAUDE.md` references `LL_HOST_CLI` or `host_runner`)
- [ ] Tests for `OpenCodeRunner` added to `test_host_runner.py`
- [ ] `PiRunner` test verifies `HostNotConfigured` is raised with FEAT-992 pointer

## Proposed Solution

### OpenCodeRunner — implementation approach

Codebase research did NOT find any in-repo reference to OpenCode's headless CLI invocation form (no `thoughts/research/opencode-headless-invocation.md` analogous to the Codex research doc at `thoughts/research/codex-headless-invocation.md`). The OpenCode adapter at `hooks/adapters/opencode/index.ts` only handles **hook transport** (spawns `python -m little_loops.hooks <intent>` for `session.created` / `session.compacted`); it does NOT exercise any OpenCode CLI for orchestration. Because the implementer cannot stay in-repo to derive flag translations, there is a real fork:

**Option A — Full OpenCodeRunner (matches current AC)**

Research OpenCode's headless CLI externally (`opencode --help`, upstream docs) and implement all four `build_*` methods following the `CodexRunner` pattern at `scripts/little_loops/host_runner.py:268-416`. Capture the flag translation table in a new `thoughts/research/opencode-headless-invocation.md` (mirroring the Codex research doc) and add a snapshot argv-translation test in `scripts/tests/test_host_runner.py` mirroring `TestCodexRunner.test_codex_runner_flag_translation`. Register in `_HOST_RUNNER_REGISTRY` (host_runner.py:422) and add `("opencode", "opencode")` to `_PROBE_ORDER` (host_runner.py:433). Update `HOST_COMPATIBILITY.md`'s orchestration table (currently lines 55-74) to flip the OpenCode column from `✗[^orch]` to `✓`.

**Option B — Stub OpenCodeRunner (mirror PiRunner)**

> **Selected:** Option B — Stub OpenCodeRunner — no in-repo OpenCode CLI flag knowledge exists; stub mirrors PiRunner immediately, deferring external research to a follow-up FEAT (score: 10/12 vs Option A's 5/12).

If OpenCode headless invocation research is not in scope for this issue, implement `OpenCodeRunner` as a stub that raises `HostNotConfigured("OpenCode orchestration not yet wired — research OpenCode headless CLI. Set LL_HOST_CLI=claude-code to use Claude Code instead.")` from all four build methods, identical in shape to `PiRunner` below. This requires editing two acceptance criteria (AC1 weakens from "implements all four factory methods" to "registered as stub, raises HostNotConfigured") and `HOST_COMPATIBILITY.md` orchestration row would show OpenCode as stub (✗ with footnote pointing to follow-up issue). Defer Option A to a follow-up FEAT.

**Recommendation in research**: Option B is lower-risk and unblocks the docs sweep + grep AC; Option A is the originally-scoped path but introduces external-research dependency. Run `/ll:decide-issue` to pick.

### PiRunner stub

The probe wiring at `scripts/little_loops/host_runner.py:433-437` already includes `("pi", "pi")` in `_PROBE_ORDER`, but `_HOST_RUNNER_REGISTRY` (host_runner.py:422-425) has no `"pi"` entry — `resolve_host()` currently does `_HOST_RUNNER_REGISTRY.get("pi")` and silently skips. This issue adds the registry entry plus the stub class:

```python
class PiRunner:
    name = "pi"
    capabilities = HostCapabilities()  # all False — no orchestration yet

    def detect(self) -> bool:
        return shutil.which("pi") is not None

    def build_streaming(self, **kwargs) -> HostInvocation:
        raise HostNotConfigured(
            "Pi orchestration not yet wired — see FEAT-992. "
            "Set LL_HOST_CLI=claude-code to use Claude Code instead."
        )

    # same body for build_blocking_json, build_version_check, build_detached
```

Note: keyword-only params (`*`) on each method to satisfy the `HostRunner` Protocol's `@runtime_checkable` signature check (see `host_runner.py` Protocol definition).

### Grep sweep

```bash
grep -rn '"claude"' scripts/little_loops/
```

Expected legitimate hits (must remain): `ClaudeCodeRunner.name = "claude-code"`, `binary="claude"` inside `ClaudeCodeRunner.build_*` factory methods at `host_runner.py:156-265`, comments/docstrings, and the `_PROBE_ORDER` tuple `("claude-code", "claude")` at `host_runner.py:433`. Any other literal must be routed through `resolve_host()` or explicitly documented as intentional. Note: `scripts/little_loops/subprocess_utils.py` was migrated by FEAT-1468 (completed) — verify it now delegates rather than hard-codes.

### Doc wiring test pattern

Six existing files establish the convention (most recent: `scripts/tests/test_feat1459_doc_wiring.py`, `test_feat1457_doc_wiring.py`, `test_feat1447_doc_wiring.py`). Invariants to mirror:

- `PROJECT_ROOT = Path(__file__).parent.parent.parent` then per-doc `Path` constants at module level
- One `class Test<DocFile>Wiring` per doc file under test
- Assertion style: `content = SOME_PATH.read_text(); assert "token" in content, "descriptive message"` — substring match only, no regex
- Class-level docstring describes what the doc must contain; test-level docstrings are optional

Skeleton for FEAT-1462 doc-wiring (target test names from current AC line 38):

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
    def test_host_runner_module_listed(self) -> None:
        assert "host_runner" in API_DOC.read_text()
    # additional assertions for resolve_host, HostInvocation, HostNotConfigured, CapabilityNotSupported

class TestArchitectureMdWiring:
    def test_host_runner_in_layering(self) -> None:
        assert "host_runner" in ARCHITECTURE.read_text()

class TestHostCompatibilityWiring:
    def test_orchestration_row_present(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "Orchestration CLI" in content
        # per-host assertions (claude-code ✓, opencode, codex, pi)

class TestTroubleshootingWiring:
    def test_host_not_configured_entry(self) -> None:
        assert "HostNotConfigured" in TROUBLESHOOTING.read_text()

class TestClaudeMdWiring:
    def test_host_runner_note_present(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "host_runner" in content or "LL_HOST_CLI" in content
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current `host_runner.py` state (FEAT-1464 + FEAT-1465 landed):**
- `HostRunner` Protocol (`@runtime_checkable`) requires `name: str`, `detect()`, and four keyword-only `build_*` methods returning `HostInvocation`
- `HostInvocation` is a `@dataclass(frozen=True)` with `binary`, `args`, `env`, `capabilities` fields
- `HostCapabilities` is `@dataclass(frozen=True)` with four bool flags: `streaming`, `permission_skip`, `agent_select`, `tool_allowlist` (all default `False`)
- `_HOST_RUNNER_REGISTRY` (host_runner.py:422-425): currently `{"claude-code": ClaudeCodeRunner, "codex": CodexRunner}` — add `"opencode"` and `"pi"` keys
- `_PROBE_ORDER` (host_runner.py:433-437): currently `[("claude-code", "claude"), ("pi", "pi")]` with `codex` commented out — Option A would add `("opencode", "opencode")`; Pi stays as-is
- `_remediation_hint()` (host_runner.py:444) already names `opencode` and `pi` in the user-facing hint string
- Module-level `__all__` exports `CapabilityNotSupported`, `HostInvocation`, `HostNotConfigured`, `HostRunner`, `resolve_host`, `ClaudeCodeRunner`, `CodexRunner` — add new runners here

**Package re-exports** (`scripts/little_loops/__init__.py`): currently re-exports `CapabilityNotSupported`, `HostInvocation`, `HostNotConfigured`, `HostRunner` only — the concrete runner classes are NOT re-exported at package level (acceptable to follow this convention for `OpenCodeRunner`/`PiRunner`).

**Public API surface for AC5** (`docs/reference/API.md`): currently only a single module-overview row exists at line 35 (`| little_loops.host_runner | Host-agnostic CLI invocation layer ... |`). No dedicated `## little_loops.host_runner` section with class/method subsections exists yet. AC5 requires adding entries for `resolve_host()`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported` — this means **creating a new dedicated section**, not just amending line 35.

**ARCHITECTURE.md layering** (AC4): no explicit layering diagram for `host_runner` exists yet — only a file-tree comment at line 254 (`├── host_runner.py # Host CLI abstraction ...`). AC4 implies adding a new layering section alongside the hook-intent layer (likely near the existing hook-intent components discussion identified by `test_feat1457_doc_wiring.py` assertions).

**HOST_COMPATIBILITY.md** (AC6): orchestration table exists at lines 55-74 with three columns (Claude Code / OpenCode / Codex CLI). All non-Claude cells currently show `✗[^orch]`. The `[^orch]` footnote mentions only `ClaudeCodeRunner` by name — needs expansion. **No Pi column** exists yet; AC6 requires adding it. Tracking-issues section at lines 128-134 already lists FEAT-992 for Pi.

**Call sites that exercise `resolve_host()`** (must keep working after this PR — no behavior change expected):
- `scripts/little_loops/fsm/evaluators.py:609` — `build_blocking_json`
- `scripts/little_loops/fsm/handoff_handler.py:116` — `build_detached`
- `scripts/little_loops/parallel/worker_pool.py:576` — `build_blocking_json`
- `scripts/little_loops/cli/action.py:143` — `resolve_host()` in `cmd_capabilities()` (note: `cmd_invoke()` at lines 85 and 119 still calls `run_claude_command` directly and is NOT yet migrated — separate scope from FEAT-1466)

**Test patterns to mirror** (from `scripts/tests/test_host_runner.py`):
- `isolated_env` fixture (deletes `LL_HOST_CLI` and `LL_HOOK_HOST` from env)
- Registry-presence test: `assert "opencode" in hr._HOST_RUNNER_REGISTRY`
- Protocol-satisfaction test: `assert isinstance(PiRunner(), HostRunner)`
- env-var-resolve test: `resolve_host(env={"LL_HOST_CLI": "pi"})` returns `PiRunner` instance
- `HostNotConfigured` test pattern: `with pytest.raises(HostNotConfigured) as exc_info` then assert message contains `"FEAT-992"` for PiRunner

### Verification Pass — 2026-05-15

_Re-research confirmed earlier findings AND surfaced these additional points:_

- **No stub `HostRunner` precedent exists.** No runner currently raises `HostNotConfigured` from its `build_*` methods — only `resolve_host()` itself raises it. `PiRunner` (and `OpenCodeRunner` under Option B) will be the first stubs. Write from scratch following the `HostRunner` Protocol (host_runner.py:100-153); do not look for an existing analog.
- **`_PROBE_ORDER` already contains `("pi", "pi")` but `_HOST_RUNNER_REGISTRY` has no `"pi"` key** — `resolve_host()`'s `_HOST_RUNNER_REGISTRY.get("pi")` returns `None` and the probe silently skips. After this PR's registry entry, probing on a host that has `pi` on `$PATH` will start returning `PiRunner` and immediately raise `HostNotConfigured` from the first `build_*` call — confirm this behavior is desired (likely yes per AC2 phrasing).
- **`fsm/evaluators.py` has TWO hardcoded "claude" error strings, not one.** Beyond the `FileNotFoundError` branch at line 632, the non-zero-returncode branch at line 641 also reads `"Claude CLI error: {proc.stderr.strip()}"`. Both must be addressed (or both explicitly deferred) by the wiring-phase step 16 decision.
- **`cli/action.py` is only PARTIALLY migrated.** `cmd_capabilities()` at line 143 uses `resolve_host()`; `cmd_invoke()` at lines 85 and 119 still calls `run_claude_command(...)` directly — which itself uses the hardcoded `"claude"` literal at `subprocess_utils.py:261` (FEAT-1469's scope). FEAT-1466's `cmd_invoke()` reference should be understood as "downstream of FEAT-1469", not "already migrated".
- **`subprocess_utils.py:261` confirmed unmigrated.** `run_claude_command()` (function definition line 219) still has `cmd_args = ["claude", ...]`. The grep AC will not pass until FEAT-1469 lands. Consider listing FEAT-1469 in `depends_on` alongside FEAT-1464, OR explicitly scoping the grep AC to exclude `subprocess_utils.py` pending FEAT-1469.
- **API.md structural analog** for the new `## little_loops.host_runner` section: `little_loops.hooks` at API.md line 5582-5688 is the closest existing match (single non-subpackage module with multiple public classes, listed via `Public surface — __all__ = [...]`, `### ClassName` per class, `---` separator before the next module). Mirror that layout rather than the `little_loops.config` (line 65, deeply nested Constructor/Properties/Methods) or `little_loops.fsm` (line 3811, subpackage with Submodule Overview) shapes.
- **`HOST_COMPATIBILITY.md` `[^orch]` footnote already mentions `host_runner.py` and `ClaudeCodeRunner`** (HOST_COMPATIBILITY.md ~line 68-74) — expansion under AC6 should ADD `CodexRunner`, `OpenCodeRunner`, `PiRunner` to the existing sentence rather than rewriting it. The tracking-issues section at line 130 already references FEAT-992 for the Pi column.
- **Codex CodexRunner test class spans lines 163-282 (not 169-204 as referenced in Similar Patterns).** The argv snapshot test is at line 192-204; the full class with all 14 test methods continues through line 282. Mirror the full class scope for `TestOpenCodeRunner` (Option A); a minimal stub-class equivalent for `TestPiRunner` (registry presence, env-var resolve, all four build methods raise `HostNotConfigured` with FEAT-992 substring, protocol satisfaction).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-15.

**Selected**: Option B — Stub OpenCodeRunner (mirror PiRunner)

**Reasoning**: Option B wins on all three deciding dimensions — simplicity, testability, and risk. Zero in-repo OpenCode headless CLI knowledge exists (`thoughts/research/opencode-headless-invocation.md` does not exist; `hooks/adapters/opencode/index.ts` covers only hook transport, not orchestration invocation). Option A's argv-snapshot test cannot be written without external flag research, and adding `("opencode", "opencode")` to `_PROBE_ORDER` without gating (unlike the gated Codex entry at `host_runner.py:435`) introduces auto-probe risk. Option B reuses all existing infrastructure (`HostNotConfigured` at `host_runner.py:44`, `HostCapabilities()`, registry extension pattern) and needs only ~6 focused tests vs ~14 for Option A.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Full OpenCodeRunner | 2/3 | 1/3 | 1/3 | 1/3 | 5/12 |
| Option B — Stub OpenCodeRunner | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `CodexRunner` (`host_runner.py:268–416`) and `TestCodexRunner` (`test_host_runner.py:163–282`) are full templates, but no `thoughts/research/opencode-headless-invocation.md` exists; `hooks/adapters/opencode/index.ts` covers only hook transport, not orchestration invocation
- Option B: `HostNotConfigured` (`host_runner.py:44`), `HostCapabilities()`, registry/probe-order extension pattern, `isolated_env` fixture and `pytest.raises(HostNotConfigured)` in `test_host_runner.py` all directly reusable; PiRunner stub shape fully specified in the issue

## Files to Modify

- `scripts/little_loops/host_runner.py` — add `OpenCodeRunner`, `PiRunner` to registry
- `scripts/tests/test_host_runner.py` — add OpenCode and Pi tests
- `scripts/tests/test_feat1462_doc_wiring.py` — NEW: doc acceptance criteria enforcement
- `docs/ARCHITECTURE.md` — host_runner in layering diagram
- `docs/reference/API.md` — new public API entries
- `docs/reference/HOST_COMPATIBILITY.md` — orchestration row
- `docs/development/TROUBLESHOOTING.md` — HostNotConfigured entry
- `.claude/CLAUDE.md` — host_runner note near "Automation: Scratch Pad"

## Integration Map

### Files to Modify (with concrete anchors)

- `scripts/little_loops/host_runner.py`
  - Add `OpenCodeRunner` class (after `CodexRunner` ends ~line 416)
  - Add `PiRunner` class (after `OpenCodeRunner`)
  - Register both in `_HOST_RUNNER_REGISTRY` (line 422-425)
  - Option A only: add `("opencode", "opencode")` to `_PROBE_ORDER` (line 433-437)
  - Update `__all__` to export new runner classes
- `scripts/tests/test_host_runner.py` — add `TestOpenCodeRunner` and `TestPiRunner` classes mirroring `TestCodexRunner` (lines 169-204)
- `scripts/tests/test_feat1462_doc_wiring.py` — NEW file; pattern in `test_feat1459_doc_wiring.py:1-40`
- `docs/ARCHITECTURE.md` — file-tree entry at line 254 already mentions `host_runner.py`; AC4 requires adding new layering-diagram subsection
- `docs/reference/API.md` — module table row at line 35 exists; AC5 requires NEW dedicated `## little_loops.host_runner` section with subsections for `resolve_host`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported`
- `docs/reference/HOST_COMPATIBILITY.md` — table at lines 55-74; add Pi column, update OpenCode column per Option A/B, expand `[^orch]` footnote at line 68+
- `docs/development/TROUBLESHOOTING.md` — add new `HostNotConfigured` entry with `LL_HOST_CLI` remediation
- `.claude/CLAUDE.md` — add note near line 133 ("Automation: Scratch Pad" header)

### Dependent Files (Callers — must not regress)

- `scripts/little_loops/fsm/evaluators.py:609` — calls `resolve_host().build_blocking_json(prompt=..., model=...)` then augments args with `--json-schema`/`--no-session-persistence` at call site
- `scripts/little_loops/fsm/handoff_handler.py:116` — calls `resolve_host().build_detached(prompt=...)` then filters `--dangerously-skip-permissions` from args
- `scripts/little_loops/parallel/worker_pool.py:576` — calls `resolve_host().build_blocking_json(prompt="reply with just 'ok'")` then filters `--dangerously-skip-permissions`
- `scripts/little_loops/cli/action.py:143-149` — calls `resolve_host()` + `.detect()` + `.build_version_check()` in `cmd_capabilities()`

These call sites are host-agnostic — none assume `ClaudeCodeRunner` is the resolved runner. Adding new runners should not require changes here.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CONTRIBUTING.md` — file-tree inline comment at line 223 reads `"HostRunner Protocol + ClaudeCodeRunner + CodexRunner"`; will be stale after FEAT-1466 adds `OpenCodeRunner + PiRunner`; append new runner names to match

### Error Message Coupling

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/evaluators.py` — **two** hardcoded "Claude CLI" strings inside `evaluate_llm_structured()`:
  - Line 632 (inside the `except FileNotFoundError` block): `"claude CLI not found. Install from https://docs.anthropic.com/en/docs/claude-code"`
  - Line 641 (inside the non-zero `returncode` handler): `"Claude CLI error: {proc.stderr.strip()}"`

  Both will be misleading when the resolved runner is `OpenCodeRunner` or `PiRunner` (binary would be `opencode` or `pi`, not `claude`). Neither is test-asserted so they will not cause test failures, but they surface confusing messages to users. Decide: generalize both to reference `invocation.binary` instead of the literal `"claude"`/`"Claude"`, or explicitly mark as out-of-scope follow-up.

### Similar Patterns to Follow

- Full HostRunner implementation: `ClaudeCodeRunner` at `scripts/little_loops/host_runner.py:156-265`; `CodexRunner` at `host_runner.py:268-416`
- Stub-style HostNotConfigured raise: model PiRunner after the existing `HostNotConfigured` raise inside `resolve_host()` (host_runner.py around the registry lookup)
- Test class structure: `TestCodexRunner` in `scripts/tests/test_host_runner.py:160-220` (registry presence, probe gating, env-var resolution, argv snapshot, warning emission, protocol satisfaction)
- Argv snapshot pattern: `TestCodexRunner.test_codex_runner_flag_translation` at `test_host_runner.py:192-204`
- Doc-wiring test layout: `scripts/tests/test_feat1459_doc_wiring.py:1-40` (`PROJECT_ROOT` + per-doc `Path` constants + per-doc `TestXxxWiring` class + substring assertions)

### Configuration / Sentinels

- `LL_HOST_CLI` and `LL_HOOK_HOST` env vars are read in `host_runner.py:475` inside `resolve_host()`
- `OrchestrationConfig.host_cli` field in `scripts/little_loops/config/core.py` (configurable `auto` / `claude-code` / etc.) — documented but not yet wired into `resolve_host()` callers; out of scope for this issue
- `_remediation_hint()` at `host_runner.py:444` already names `opencode` and `pi` in user-facing error text

## Implementation Steps

1. **Decide on OpenCodeRunner approach** — run `/ll:decide-issue FEAT-1466` to pick Option A (full implementation + external OpenCode CLI research) or Option B (stub).
2. **(Option A only) Capture OpenCode headless CLI research** — create `thoughts/research/opencode-headless-invocation.md` documenting the flag translation table, mirroring `thoughts/research/codex-headless-invocation.md`.
3. **Add `OpenCodeRunner` to `scripts/little_loops/host_runner.py`** after `CodexRunner` (line 416). Follow `CodexRunner` pattern for Option A; follow PiRunner stub pattern for Option B.
4. **Add `PiRunner` stub** immediately after `OpenCodeRunner`. Raise `HostNotConfigured("Pi orchestration not yet wired — see FEAT-992. ...")` from all four `build_*` methods.
5. **Register both runners** in `_HOST_RUNNER_REGISTRY` (host_runner.py:422). Option A: add `("opencode", "opencode")` to `_PROBE_ORDER` (host_runner.py:433). Update `__all__`.
6. **Add tests** in `scripts/tests/test_host_runner.py`: `TestOpenCodeRunner` (registry presence, env-var resolve, argv snapshot for Option A or `HostNotConfigured` raise for Option B, protocol satisfaction) and `TestPiRunner` (registry presence, env-var resolve, `HostNotConfigured` raises with `"FEAT-992"` substring, protocol satisfaction).
7. **Run grep sweep**: `grep -rn '"claude"' scripts/little_loops/` — verify only legitimate hits remain (ClaudeCodeRunner internals, comments, `_PROBE_ORDER` tuple).
8. **Update `docs/ARCHITECTURE.md`** — add `host_runner` layering subsection (do NOT just rely on the file-tree comment at line 254).
9. **Update `docs/reference/API.md`** — add new dedicated `## little_loops.host_runner` section with subsections for `resolve_host`, `HostInvocation`, `HostNotConfigured`, `CapabilityNotSupported`.
10. **Update `docs/reference/HOST_COMPATIBILITY.md`** — extend table at lines 55-74: add Pi column, update OpenCode/Codex per current support state, expand `[^orch]` footnote to list all four runners.
11. **Update `docs/development/TROUBLESHOOTING.md`** — add `HostNotConfigured` entry with `LL_HOST_CLI` remediation hint.
12. **Update `.claude/CLAUDE.md`** — add a note near the "Automation: Scratch Pad" section (line 133+) telling contributors to route new host-CLI calls through `resolve_host()` rather than adding new `"claude"` literals.
13. **Create `scripts/tests/test_feat1462_doc_wiring.py`** following the `test_feat1459_doc_wiring.py` invariants. One `Test<Doc>Wiring` class per doc file; substring-match assertions only.
14. **Verify**: `python -m pytest scripts/tests/test_host_runner.py scripts/tests/test_feat1462_doc_wiring.py -v` and `python -m pytest scripts/tests/ -v` (full suite — confirm no call-site regression).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

15. Update `CONTRIBUTING.md` line 223 — file-tree comment names `ClaudeCodeRunner + CodexRunner` explicitly; append `+ OpenCodeRunner + PiRunner` to stay current
16. Decide on `evaluators.py` error message — `evaluate_llm_structured()` contains the hardcoded string `"claude CLI not found"` (~line 633); generalize to `f"{invocation.binary} CLI not found"` or document as explicit follow-up; do not silently leave a misleading user-facing message after non-Claude runners are registered

## Dependencies

- **FEAT-1464** must land first (provides `host_runner.py` scaffold and all call site migrations)
- Can run in parallel with **FEAT-1465**

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- **FEAT-1469 blocks AC3**: `subprocess_utils.py:261` still contains `"claude"` hardcoded; FEAT-1469 is open and not in `depends_on`. Either add it to `depends_on`, or narrow AC3's grep scope to exclude `subprocess_utils.py` pending FEAT-1469.
- **Step 16 evaluators.py judgment call**: "generalize `evaluate_llm_structured()`'s two hardcoded 'Claude CLI' strings to use `invocation.binary`, or mark as explicit follow-up" — decide before starting to avoid mid-implementation scope creep.

### Outcome Risk Factors
- **Open decision — Step 16 error message generalization**: `evaluators.py:632,641` still contains `"claude CLI not found"` / `"Claude CLI error"` verbatim; the issue says "decide" but leaves the call to implementation time. Resolve before implementing to prevent scope expansion mid-PR.
- **API.md section creation depth**: AC5 requires creating a new `## little_loops.host_runner` section (not just amending the row at line 35), mirroring `little_loops.hooks` section (~line 5582); non-trivial doc work that may require iteration.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-15
- **Reason**: Issue too large for single session (score: 11/11 — Very Large)

### Decomposed Into
- FEAT-1472: Host Runner Stubs — OpenCodeRunner + PiRunner + Tests
- FEAT-1473: Host Runner Docs Sweep + Doc-Wiring Test

## Session Log
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3404bce4-b1e1-4c4a-bdaf-327d629a43da.jsonl`
- `/ll:confidence-check` - 2026-05-15T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc13a20a-8690-49b7-beff-dc985d70eda3.jsonl`
- `/ll:decide-issue` - 2026-05-15T15:31:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e037612b-df0c-43c2-951a-3109467668e6.jsonl`
- `/ll:confidence-check` - 2026-05-15T15:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c07b83d1-d35c-4931-8888-e672f021a1d6.jsonl`
- `/ll:refine-issue` - 2026-05-15T15:23:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/272ded09-b9af-467d-b5fa-d9a2242a69f0.jsonl`
- `/ll:wire-issue` - 2026-05-15T15:16:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab38aeee-4797-4ba1-84e8-c0ec73147e0a.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74d0beba-44eb-4fd9-bfb9-4a9202d3f92d.jsonl`
- `/ll:refine-issue` - 2026-05-15T15:11:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/013359bb-2d12-4756-8ce9-b8b48e4cd6cf.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0a84cca-2574-4c32-8edd-684205b8feb0.jsonl`
