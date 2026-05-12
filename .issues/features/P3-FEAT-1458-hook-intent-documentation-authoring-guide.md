---
id: FEAT-1458
type: FEAT
priority: P3
status: done
parent: FEAT-1453
discovered_date: 2026-05-12
discovered_by: issue-size-review
completed_at: 2026-05-12T04:51:06Z
confidence_score: 95
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
testable: false
---

# FEAT-1458: Hook-Intent Documentation — Authoring Guide

## Summary

Create the new `docs/claude-code/write-a-hook.md` authoring guide for the hook-intent abstraction layer, add the adapter flow diagram to `automate-workflows-with-hooks.md`, and add a doc-wiring test class to verify the guide exists and references the key types.

## Parent Issue

Decomposed from FEAT-1453: Hook-Intent Abstraction Layer — Documentation

## Depends On

- FEAT-1448 (LLHookEvent / LLHookResult types exist)
- FEAT-1450 (SessionStart and PreCompact adapters exist — enough system to document)
- FEAT-1452 (LLHookIntentExtension Protocol documented)

## Scope

Covers FEAT-1453 Implementation Steps 1, 2, and 15.

### New Docs

- `docs/claude-code/write-a-hook.md` — "How to write a little-loops hook" guide:
  - Intent model overview (`LLHookEvent` in, `LLHookResult` out); link to `scripts/little_loops/hooks/types.py`
  - Handler signature: `handle(event: LLHookEvent) -> LLHookResult`
  - When to write a core handler vs. register via `LLHookIntentExtension.provided_hook_intents()`
  - Step-by-step registration via `little_loops.extensions` entry point (toml fence, auto-discovery)
  - Adapter flow: Claude Code shell vs. OpenCode TS — how the host event reaches Python
  - Testing pattern: `subprocess.run([sys.executable, "-m", "little_loops.hooks", "<intent>"], input=json.dumps(payload), ...)`
  - Minimal worked example: a custom intent end-to-end
  - Reference `ll-create-extension` for the scaffolding step (bidirectional link with `docs/reference/CLI.md`)
  - Model structure after `docs/guides/LOOPS_GUIDE.md`

- `docs/claude-code/automate-workflows-with-hooks.md` — append a mermaid `flowchart LR` block showing:
  host event → adapter (bash/TS) → `python -m little_loops.hooks <intent>` → `main_hooks()` → handler → `LLHookResult` → adapter → host response
  Model on the `flowchart LR` style at `docs/ARCHITECTURE.md:870-878`; embed the same diagram (or link it) into the new authoring guide.

### Tests

- `scripts/tests/test_feat1457_doc_wiring.py` — add `TestWriteAHookWiring` class:
  - Assert file exists at `docs/claude-code/write-a-hook.md`
  - Assert content mentions `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension`, `provided_hook_intents`
  - Follow existing class pattern: module-level `Path` constant + `"TOKEN" in content` assertions

## Acceptance Criteria

- `docs/claude-code/write-a-hook.md` exists and covers intent model, handler signature, registration, adapter flow, testing pattern, and a worked example
- Mermaid adapter flow diagram present in `automate-workflows-with-hooks.md`
- `TestWriteAHookWiring` passes in `test_feat1457_doc_wiring.py`
- New guide cross-references `ll-create-extension`

## Source References

- `scripts/little_loops/hooks/types.py` — `LLHookEvent` / `LLHookResult` dataclasses (wire format source of truth)
- `scripts/little_loops/hooks/__init__.py` — `main_hooks()`, `_dispatch_table()`, `_HOOK_INTENT_REGISTRY`
- `scripts/little_loops/extension.py:104-111` — `LLHookIntentExtension` Protocol
- `hooks/adapters/claude-code/precompact.sh`, `session-start.sh` — Claude Code bash shims
- `hooks/adapters/opencode/index.ts` — OpenCode TS plugin; `spawnIntent()` event→intent mapping
- `hooks/adapters/opencode/README.md` — existing adapter flow model
- `docs/guides/LOOPS_GUIDE.md` — structural model for authoring guides
- `docs/reference/CLI.md:1310-1388` — `ll-create-extension` section (add cross-link here)
- `scripts/tests/test_pre_compact.py`, `test_hook_session_start.py` — Python handler test patterns
- `scripts/tests/test_feat1457_doc_wiring.py` — existing doc-wiring test pattern to follow

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Wire types** (`scripts/little_loops/hooks/types.py`):
- `LLHookEvent` fields: `host: str` (positional), `intent: str = ""`, `timestamp: str = ""`, `payload: dict[str, Any] = {}`, `session_id: str | None = None`, `cwd: str | None = None`.
- `to_dict()` serializes `timestamp` under wire key `"ts"`; `from_dict()` accepts both `"ts"` and `"timestamp"`. `None`/empty optional fields are omitted from the dict.
- `LLHookResult` fields: `exit_code: int = 0`, `feedback: str | None = None`, `decision: str | None = None`, `data: dict[str, Any] = {}`, `stdout: str | None = None`.
- Exit code semantics: `0` = pass; `2` = block + inject `feedback` to stderr (Claude Code surfaces this in context); other = error. `main_hooks` writes `result.stdout` to stdout and `result.feedback` to stderr before returning `result.exit_code`.

**CLI dispatcher** (`scripts/little_loops/hooks/__init__.py`):
- Invocation form: `python -m little_loops.hooks <intent>` (via `scripts/little_loops/hooks/__main__.py` → `raise SystemExit(main_hooks())`).
- `main_hooks()`: reads `sys.argv[1]` as intent name, reads stdin (when `not sys.stdin.isatty()`), parses JSON (non-dict → `{}`), constructs `LLHookEvent(host=os.environ.get("LL_HOOK_HOST", "claude-code"), intent=<arg>, payload=<parsed>, cwd=os.getcwd())`, dispatches.
- Unknown intent → prints `"Unknown intent: <name>. Available: ..."` to stderr, returns exit code `1`.
- `_dispatch_table()` returns `{**_HOOK_INTENT_REGISTRY, **built_ins}` — built-ins shadow extension intents on collision.
- `_register_hook_intents()` populates `_HOOK_INTENT_REGISTRY`, raising `ValueError` on duplicate names.

**Extension Protocol** (`scripts/little_loops/extension.py:103-111`):
```python
@runtime_checkable
class LLHookIntentExtension(Protocol):
    def provided_hook_intents(self) -> dict[str, Callable[[LLHookEvent], LLHookResult]]: ...
```
Wired in `wire_extensions()` (lines 269–273): for each extension with `provided_hook_intents`, calls `_register_hook_intents(ext.provided_hook_intents())`.

**Entry-point group**: `little_loops.extensions` (constant `ENTRY_POINT_GROUP` in `extension.py`). Auto-discovery uses `importlib.metadata.entry_points(group="little_loops.extensions")` in `ExtensionLoader.from_entry_points()`; each entry-point class is instantiated with `cls()` (no-args). Registration toml fence in an extension package's `pyproject.toml`:
```toml
[project.entry-points."little_loops.extensions"]
my_ext = "my_package:MyExtension"
```

**Adapter contracts**:
- Claude Code bash (`hooks/adapters/claude-code/{precompact,session-start}.sh`):
  ```bash
  INPUT=$(cat)
  echo "$INPUT" | python -m little_loops.hooks <intent>
  exit $?
  ```
  Does NOT set `LL_HOOK_HOST` — Python dispatcher defaults to `"claude-code"`. Registered in `hooks/hooks.json` as `"bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/<intent>.sh"`.
- OpenCode TS (`hooks/adapters/opencode/index.ts` → `spawnIntent()`): uses `Bun.spawn(["python", "-m", "little_loops.hooks", intent], { cwd, env: { ...process.env, LL_HOOK_HOST: "opencode" }, stdin/stdout/stderr: "pipe" })`, writes `JSON.stringify(payload ?? {})` to stdin, awaits stdout/stderr/exit. Event mapping: `session.created → session_start`, `session.compacted → pre_compact`.

**Doc-wiring test pattern** (`scripts/tests/test_feat1457_doc_wiring.py`):
- Module docstring naming the issue and the surfaces being verified.
- `from __future__ import annotations` + `from pathlib import Path`.
- `PROJECT_ROOT = Path(__file__).parent.parent.parent` (tests/ → scripts/ → repo root).
- Module-level path constants (e.g., `WRITE_A_HOOK = PROJECT_ROOT / "docs" / "claude-code" / "write-a-hook.md"`).
- One `class Test<Scope>Wiring:` per surface, plain pytest class (no `unittest.TestCase`), one-sentence class docstring with "must" language.
- Per-test pattern: `def test_<thing>(self) -> None:` → `content = CONSTANT.read_text()` → `assert "TOKEN" in content, "<reason restating requirement>"`.
- File existence: `assert PATH.exists(), "<reason naming the path>"`.

**Mermaid `flowchart LR` convention** (`docs/ARCHITECTURE.md:628-658`, `:870-879`, `:1044-1053`):
- ALL_CAPS short node IDs, `[Label Text]` rectangle shape, multi-line labels via `<br/>`, `-->` solid edges, `-.->` dashed/optional, `subgraph Name["Display Name"] ... end` for groups, blank lines between logical groups inside the diagram. Always `flowchart LR`, never `graph`.

**docs/claude-code/ style** (`docs/claude-code/automate-workflows-with-hooks.md:1-18`, `docs/claude-code/create-plugin.md`):
- Leading docs-index blockquote + subtitle blockquote before `# Title`.
- `<Tip>...</Tip>` MDX callout after opening paragraph, linking to companion reference doc.
- `<Steps><Step title="...">` for procedural walkthroughs; `<Tabs><Tab title="...">` for variants.
- Sub-sections under `## What you can automate`-style H2 use ready-to-paste code blocks.
- Sibling pattern under `docs/guides/LOOPS_GUIDE.md` is plain Markdown (ToC, Quick Start, How It Works, Walkthrough, Built-ins, Troubleshooting, Further Reading) — `write-a-hook.md` lives in `docs/claude-code/` so it should match that family's MDX-flavored conventions, not LOOPS_GUIDE's pure-Markdown style.

**CLI cross-link convention** (`docs/reference/CLI.md:1492-1495`, `docs/reference/CONFIGURATION.md:754-756`):
- Inbound to CLI.md: `` [`ll-create-extension`](CLI.md#ll-create-extension) `` (relative path, backtick-wrapped tool name, lowercase hyphenated anchor matching the tool name).
- Outbound from CLI.md: `> **Note:** See [Section Title](../guides/PATH.md#anchor)` inline + a "See Also" bullet list near the bottom of CLI.md.
- Bidirectional: add the new guide to CLI.md's See Also block in addition to adding the CLI.md link from `write-a-hook.md`.

**Sibling doc-wiring test files** (use as additional structural references): `test_feat1447_doc_wiring.py`, `test_feat1287_doc_wiring.py`, `test_feat1172_doc_wiring.py`, `test_feat1407_doc_wiring.py`.

**Handler test patterns** (for documenting the recommended testing approach):
- `scripts/tests/test_pre_compact.py:1-50` — pure-function unit test: `_event(**payload)` factory, `monkeypatch.chdir(tmp_path)`, `LLHookResult` field assertions.
- `scripts/tests/test_hook_session_start.py:1-32` — same shape with an `@pytest.fixture in_tmp` cwd helper.
- `scripts/tests/test_hooks_integration.py` — subprocess round-trip: `subprocess.run([sys.executable, "-m", "little_loops.hooks", "<intent>"], input=json.dumps(payload), capture_output=True, text=True, timeout=10, cwd=str(tmp_path))`. The new guide should document this subprocess pattern (issue already calls for it) AND point at `test_pre_compact.py` as the pure-function alternative.
- `scripts/tests/test_hook_intents.py::TestHooksMainModule` — `LL_HOOK_HOST` env var propagation tested via `monkeypatch.setenv` + in-process `main_hooks()`, not subprocess.

## Integration Map

### Files to Create
- `docs/claude-code/write-a-hook.md` — new authoring guide. Style/structure: match `docs/claude-code/automate-workflows-with-hooks.md` (subtitle blockquote, `<Tip>` callout, `<Steps>/<Step>` walkthrough), not pure-Markdown `LOOPS_GUIDE.md`. Sections (suggested): docs-index blockquote → `# Write a little-loops hook` + subtitle → `<Tip>` linking to companion reference (FEAT-1459 deliverable) → "The intent model" (LLHookEvent in, LLHookResult out) → "Handler signature" (`handle(event: LLHookEvent) -> LLHookResult`) → "Core handler vs. extension intent" (decision criteria) → `<Steps>` walkthrough: scaffold via `ll-create-extension`, implement `handle`, register via `provided_hook_intents()` + entry-point toml, test via subprocess → "Adapter flow" (mermaid `flowchart LR` diagram, embedded inline or via include) → "Testing pattern" (subprocess + pure-function variants with code blocks modeled on `test_pre_compact.py` and `test_hooks_integration.py`) → "Worked example" (a minimal custom intent end-to-end) → "Limitations and troubleshooting" → "Learn more" (links).

### Files to Modify
- `docs/claude-code/automate-workflows-with-hooks.md` — append a `flowchart LR` mermaid block showing: `Host[Host event] --> Adapter[Adapter<br/>bash or TS] --> Subproc["python -m little_loops.hooks &lt;intent&gt;"] --> Main[main_hooks dispatch] --> Handler[handle&#40;event&#41;] --> Result[LLHookResult] --> AdapterBack[Adapter] --> HostBack[Host response]`. Match `docs/ARCHITECTURE.md:870-879` convention (ALL_CAPS IDs, `[Label]` rectangles, `<br/>` multi-line labels). Cross-link to `write-a-hook.md` for the full authoring walkthrough.
- `docs/reference/CLI.md` — under `ll-create-extension` section (lines 1305–1389), add a "See also" pointer to `docs/claude-code/write-a-hook.md`; also append `write-a-hook.md` to the bottom-of-file See Also block (around line 1492).
- `scripts/tests/test_feat1457_doc_wiring.py` — append `TestWriteAHookWiring` class. Add a module-level `WRITE_A_HOOK = PROJECT_ROOT / "docs" / "claude-code" / "write-a-hook.md"` constant. Class methods:
  1. `test_guide_file_exists` — `assert WRITE_A_HOOK.exists()`
  2. `test_guide_mentions_llhookevent` — `assert "LLHookEvent" in content`
  3. `test_guide_mentions_llhookresult` — `assert "LLHookResult" in content`
  4. `test_guide_mentions_llhookintentextension` — `assert "LLHookIntentExtension" in content`
  5. `test_guide_mentions_provided_hook_intents` — `assert "provided_hook_intents" in content`
  6. `test_guide_cross_references_ll_create_extension` — `assert "ll-create-extension" in content`

  Alternative: create a sibling `scripts/tests/test_feat1458_doc_wiring.py` for clearer per-issue traceability (consistent with `test_feat1447_doc_wiring.py`, `test_feat1407_doc_wiring.py`, etc.). The issue currently directs the additions into the existing `test_feat1457_doc_wiring.py` file; if implementer prefers per-issue files, that is an acceptable variation — flag in PR.

### Dependent Files (Callers/Importers)
- `docs/claude-code/automate-workflows-with-hooks.md` — needs the adapter-flow mermaid block (item above) and a "See also" link to the new guide.
- `docs/reference/CLI.md:1305-1389` — `ll-create-extension` section gains bidirectional link to the new guide.
- `docs/reference/CLI.md:1492-1495` — See Also block gains an entry for `write-a-hook.md`.
- `CONTRIBUTING.md`, `skills/workflow-automation-proposer/SKILL.md`, `skills/configure/areas.md`, `skills/audit-claude-config/SKILL.md`, `skills/init/SKILL.md` — already mention `LLHookIntentExtension` (FEAT-1457); none require changes here, but FEAT-1460 will add a navigation link from at least one of them.
- `docs/ARCHITECTURE.md` — no change required for FEAT-1458; the existing `flowchart LR` blocks at lines 628–658, 870–879, 1044–1053 are *referenced as style models*, not modified.

_Wiring pass added by `/ll:wire-issue`:_
- **CLI.md overlap with FEAT-1460**: `docs/reference/CLI.md` `ll-create-extension` cross-link is claimed by both FEAT-1458 (Step 5) and FEAT-1460 Step 14. FEAT-1458 should implement both CLI.md see-also blocks (the section link and the bottom See Also entry); FEAT-1460 Step 14 should then verify the link exists rather than repeat the edit.
- `docs/index.md` — no `docs/claude-code/` entries currently exist; `write-a-hook.md` will need an entry here. This is owned by FEAT-1460 Step 13 — do not implement in FEAT-1458; coordinate ordering so FEAT-1458 ships first.
- `mkdocs.yml` — `docs/claude-code/` is not present in the `nav:` block; `write-a-hook.md` will be invisible in the published site nav without a nav entry. This is owned by FEAT-1460 Step 12 — do not implement in FEAT-1458; FEAT-1460 depends on this file existing first.

### Similar Patterns (model after)
- Authoring guide structure: `docs/claude-code/automate-workflows-with-hooks.md`, `docs/claude-code/create-plugin.md`.
- Mermaid `flowchart LR`: `docs/ARCHITECTURE.md:870-879` (Sequential Merging — closest in node-count to the adapter flow).
- Doc-wiring test classes: `scripts/tests/test_feat1457_doc_wiring.py::TestContributingWiring`, `::TestCliDocWiring`; existence assertion at `test_feat1447_doc_wiring.py::TestVerifyIssueLoopSkillExists`.
- Subprocess test invocation (to demonstrate in the guide's testing section): `scripts/tests/test_hooks_integration.py` (subprocess) and `scripts/tests/test_pre_compact.py` / `test_hook_session_start.py` (pure-function).
- Adapter contract terminology (subprocess contract table, host identification): `hooks/adapters/opencode/README.md:1-8, 37-69`.

### Tests
- New: `TestWriteAHookWiring` class in `scripts/tests/test_feat1457_doc_wiring.py` (or new `test_feat1458_doc_wiring.py`).
- No new handler/integration tests required — this issue is documentation-only; the system being documented is already covered by `test_pre_compact.py`, `test_hook_session_start.py`, `test_hook_intents.py`, `test_hooks_integration.py`, `test_extension.py`.
- Verify: `python -m pytest scripts/tests/test_feat1457_doc_wiring.py -v`.

_Wiring pass added by `/ll:wire-issue`:_
- **Test gap — diagram addition**: No existing test covers `docs/claude-code/automate-workflows-with-hooks.md` content. After the mermaid block is appended (Step 4), add a `TestAutomateHooksWiring` class (or a `test_automate_hooks_has_adapter_diagram` method) asserting `"flowchart LR" in content` — confirms the diagram was actually written. Add to `test_feat1457_doc_wiring.py` alongside `TestWriteAHookWiring`. Also add a module-level constant: `AUTOMATE_HOOKS = PROJECT_ROOT / "docs" / "claude-code" / "automate-workflows-with-hooks.md"`.

### Documentation
- Target: `docs/claude-code/write-a-hook.md` (new).
- Modified: `docs/claude-code/automate-workflows-with-hooks.md`, `docs/reference/CLI.md`.

### Configuration
- None. No `.ll/ll-config.json`, `hooks/hooks.json`, or `pyproject.toml` changes required for FEAT-1458.

## Implementation Steps

1. **Read the style models.** Open `docs/claude-code/automate-workflows-with-hooks.md` (full file) and `docs/claude-code/create-plugin.md` for header conventions, `<Tip>` / `<Steps>` / `<Tabs>` MDX usage, and section ordering. Open `docs/ARCHITECTURE.md:870-879` for the mermaid `flowchart LR` model.

2. **Pull the live API surface.** Read `scripts/little_loops/hooks/types.py` (verify `LLHookEvent` / `LLHookResult` field names and the `ts` wire alias), `scripts/little_loops/hooks/__init__.py` (`main_hooks`, `_dispatch_table`, `_HOOK_INTENT_REGISTRY`, `_register_hook_intents`), and `scripts/little_loops/extension.py:103-111` (the Protocol signature). Verbatim-quote the dataclass field lists and the Protocol method into the guide so it stays the source of truth for the wire format until FEAT-1459 ships dedicated reference docs.

3. **Draft `docs/claude-code/write-a-hook.md`** in sections (use `<Steps>` for the registration walkthrough):
   - Opening: docs-index blockquote + `# Write a little-loops hook` + one-paragraph subtitle blockquote + `<Tip>` linking to the FEAT-1459 reference (or temporarily to `scripts/little_loops/hooks/types.py` if FEAT-1459 not yet merged).
   - "The intent model": LLHookEvent in, LLHookResult out; show the dataclass field tables; explain exit-code semantics (`0` pass, `2` block+inject feedback to stderr, other = error).
   - "Handler signature": `def handle(event: LLHookEvent) -> LLHookResult:` with a 5-line example body.
   - "Core handler vs. extension intent": decision criteria — core handlers (in `scripts/little_loops/hooks/*.py`, dispatch-table built-ins) are appropriate for hooks shipped with little-loops itself; extension intents (`provided_hook_intents()`) are appropriate for third-party packages and out-of-tree workflows. Built-ins shadow extension intents on name collision (per `_dispatch_table()` merge order).
   - "Step-by-step: register a new intent" (`<Steps>` block):
     1. Scaffold with `ll-create-extension` (link to `docs/reference/CLI.md#ll-create-extension`).
     2. Implement `handle(event: LLHookEvent) -> LLHookResult` in your extension module.
     3. Implement `provided_hook_intents()` on your extension class, returning `{"<intent_name>": handle}`.
     4. Add the toml fence to your `pyproject.toml`:
        ```toml
        [project.entry-points."little_loops.extensions"]
        my_ext = "my_package:MyExtension"
        ```
     5. `pip install -e .` to register; verify with `python -m little_loops.hooks <intent_name>` (unknown intent → exit `1` with stderr list).
   - "Adapter flow": embed the new `flowchart LR` mermaid block (host event → adapter → subprocess → main_hooks → handler → result → adapter → host response) and link to `hooks/adapters/opencode/README.md` for the subprocess contract.
   - "Testing pattern": two code blocks.
     - **Pure-function** modeled on `test_pre_compact.py:28-50`: `_event(**payload)` factory + `monkeypatch.chdir(tmp_path)` + direct `handle()` call + `LLHookResult` field assertions.
     - **Subprocess round-trip** modeled on `test_hooks_integration.py`: `subprocess.run([sys.executable, "-m", "little_loops.hooks", "<intent>"], input=json.dumps(payload), capture_output=True, text=True, timeout=10, cwd=str(tmp_path))`.
   - "Worked example": pick a tiny custom intent (e.g., `count_files`) and walk it end-to-end — module file, `handle`, `provided_hook_intents`, toml fence, one subprocess test.
   - "Limitations and troubleshooting": unknown-intent exit `1`; built-in shadowing; `LL_HOOK_HOST` defaults (`claude-code` from bash adapter, explicit `opencode` from TS); hot-path note from FEAT-1116 Decision 3 if relevant.
   - "Learn more": link to CLI.md (`ll-create-extension`), `docs/claude-code/automate-workflows-with-hooks.md`, `hooks/adapters/opencode/README.md`, FEAT-1459 reference doc when available.

4. **Append the mermaid diagram to `docs/claude-code/automate-workflows-with-hooks.md`** under a new H2/H3 (e.g., `## Adapter flow` or inside the existing "How hooks work" section). Match the ARCHITECTURE.md node/arrow conventions. Add a "See also" sentence pointing to `write-a-hook.md`.

5. **Add bidirectional CLI cross-links.** In `docs/reference/CLI.md`'s `ll-create-extension` section (lines 1305–1389), add `> **See also:** [Write a little-loops hook](../claude-code/write-a-hook.md) — full authoring walkthrough.` In CLI.md's bottom See Also block (~line 1492), append `- [write-a-hook.md](../claude-code/write-a-hook.md) — hook authoring guide`.

6. **Add the wiring test.** Edit `scripts/tests/test_feat1457_doc_wiring.py`:
   - Add `WRITE_A_HOOK = PROJECT_ROOT / "docs" / "claude-code" / "write-a-hook.md"` to the module-level constants.
   - Append the `TestWriteAHookWiring` class with the 6 test methods listed in the Integration Map. Match the existing class docstring style ("must" language) and `assert "TOKEN" in content, "<reason>"` pattern.
   - (Optional variant: create `scripts/tests/test_feat1458_doc_wiring.py` instead, replicating the module-level boilerplate from `test_feat1457_doc_wiring.py:1-15`.)

7. **Verify.** Run:
   ```bash
   python -m pytest scripts/tests/test_feat1457_doc_wiring.py -v
   ll-check-links docs/claude-code/write-a-hook.md docs/claude-code/automate-workflows-with-hooks.md docs/reference/CLI.md
   ll-verify-docs
   ```
   All `TestWriteAHookWiring` cases pass; no broken links introduced; doc count audits clean.

8. **Verify mermaid renders** by previewing `automate-workflows-with-hooks.md` (or use `mcp__plugin_claude-mermaid_mermaid__mermaid_preview` on the diagram block) — confirms node IDs/labels are syntactically valid before commit.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Coordinate CLI.md cross-link with FEAT-1460** — Implement both CLI.md see-also blocks in Step 5 as written; flag for FEAT-1460 implementer that Step 14 should verify (not re-apply) this change to avoid a double-edit conflict.
10. **Add `TestAutomateHooksWiring` class** — In `scripts/tests/test_feat1457_doc_wiring.py`, after `TestWriteAHookWiring`, add a `TestAutomateHooksWiring` class with `test_automate_hooks_has_adapter_diagram` asserting `"flowchart LR" in AUTOMATE_HOOKS.read_text()`. Also add `AUTOMATE_HOOKS = PROJECT_ROOT / "docs" / "claude-code" / "automate-workflows-with-hooks.md"` to the module-level constants. This is the only test gate for the Step 4 diagram addition.
11. **Note — nav and index are FEAT-1460's scope** — Do not implement `mkdocs.yml` nav or `docs/index.md` entry in FEAT-1458; FEAT-1460 Steps 12–13 own those. FEAT-1458 must land before FEAT-1460 so the nav entries can reference the actual file.

## Resolution

Implemented FEAT-1458 — Hook-Intent Documentation Authoring Guide.

**Files created:**
- `docs/claude-code/write-a-hook.md` — authoring guide for host-agnostic hook intents. Covers the `LLHookEvent` / `LLHookResult` wire format, handler signature, core-vs-extension decision criteria, a 5-step `<Steps>` registration walkthrough using `ll-create-extension` + `provided_hook_intents()`, the adapter flow diagram, pure-function + subprocess testing patterns, a worked `count_files` example, and a limitations/troubleshooting section. Style follows the MDX-flavored sibling at `docs/claude-code/automate-workflows-with-hooks.md`.

**Files modified:**
- `docs/claude-code/automate-workflows-with-hooks.md` — appended an "Adapter flow for little-loops hooks" section with a `flowchart LR` mermaid block (host event → adapter → `python -m little_loops.hooks <intent>` → `main_hooks` dispatch → `handle(event)` → `LLHookResult` → adapter → host response) following the ARCHITECTURE.md node/arrow conventions. Cross-links to the authoring guide from both the new section and the Learn more list.
- `docs/reference/CLI.md` — added bidirectional cross-links to the authoring guide: an inline `> **See also:**` note inside the `ll-create-extension` section and a `write-a-hook.md` entry in the bottom-of-file See Also block (per the wiring-pass note about FEAT-1460 Step 14, FEAT-1460 should verify these links rather than re-apply them).
- `scripts/tests/test_feat1457_doc_wiring.py` — added module-level `WRITE_A_HOOK` and `AUTOMATE_HOOKS` path constants and two new test classes: `TestWriteAHookWiring` (6 methods: file exists; mentions `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension`, `provided_hook_intents`, `ll-create-extension`) and `TestAutomateHooksWiring` (2 methods: contains `flowchart LR`; links to `write-a-hook.md`).

**Verification:**
- `python -m pytest scripts/tests/test_feat1457_doc_wiring.py -v` — 27 passed (8 new).
- `ll-check-links` on the modified docs reported no new broken links (pre-existing example.com placeholder URLs in unrelated files).
- `ll-verify-docs` reported only the pre-existing `skills` count mismatch in CONTRIBUTING.md.
- Full pytest run: 7 pre-existing failures in `test_generate_schemas.py` and `test_update_skill.py` (schema regeneration / marketplace version sync — both unrelated to documentation).

**Out of scope (owned by FEAT-1460 per wiring-pass note):**
- `mkdocs.yml` nav entry for `docs/claude-code/` (Step 12).
- `docs/index.md` entry for `write-a-hook.md` (Step 13).
- FEAT-1460 Step 14 (CLI.md cross-link) is now a verification step, not an edit.

## Session Log
- `/ll:manage-issue` - 2026-05-12T04:51:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42a87158-4715-487e-9607-65a4368e7b76.jsonl`
- `/ll:ready-issue` - 2026-05-12T04:44:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cacd405-07ec-45fd-9483-f49ad9cf7343.jsonl`
- `/ll:wire-issue` - 2026-05-12T04:40:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6631d514-aa18-41b4-a905-645bdb8bf3fe.jsonl`
- `/ll:refine-issue` - 2026-05-12T04:35:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94a3b45b-9842-4161-a6eb-d42432c12d64.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c649d9b-2581-4606-bbef-f8600ec424d0.jsonl`
- `/ll:issue-size-review` - 2026-05-12T04:28:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
