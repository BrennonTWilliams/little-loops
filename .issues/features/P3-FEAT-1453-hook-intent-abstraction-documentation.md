---
id: FEAT-1453
type: FEAT
priority: P3
status: done
size: Very Large
parent: FEAT-1116
discovered_date: 2026-05-12
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 59
score_complexity: 13
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 18
completed_at: 2026-05-15T00:00:00Z
---

# FEAT-1453: Hook-Intent Abstraction Layer — Documentation

## Summary

Write all end-user and developer documentation for the hook-intent abstraction layer introduced by FEAT-1116. Covers the "How to write a little-loops hook" guide, reference doc updates, architecture updates, and TROUBLESHOOTING path fixes.

## Parent Issue

Decomposed from FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Depends On

- FEAT-1448 (types exist)
- FEAT-1450 (both SessionStart and PreCompact adapters exist — enough system to document)
- FEAT-1452 (Protocol documented alongside extension authoring docs)

## Scope

Covers FEAT-1116 Implementation Step 8 and all documentation coupling identified by the wiring pass.

### New Docs

- `docs/claude-code/` — new "How to write a little-loops hook" guide covering the intent model, `LLHookEvent`/`LLHookResult`, adapter flow, and how to register via `LLHookIntentExtension`
- `docs/claude-code/automate-workflows-with-hooks.md` — add adapter flow diagram

### Reference Doc Updates

- `docs/claude-code/hooks-reference.md` — add section on the intent model and adapters
- `docs/reference/EVENT-SCHEMA.md` — document `LLHookEvent` type (analogous to existing `LLEvent` documentation); cross-link between the two types
- `docs/reference/API.md:36-37` — add `little_loops.hooks` row to the Module Overview table; add `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension` to the Extension API section (lines 5163-5339)
- `docs/reference/CONFIGURATION.md:617` — add `little_loops.hook_intents` entry-point group description (or note that it uses the existing `little_loops.extensions` group per Decision 2)
- `docs/reference/CONFIGURATION.md:527` — update `### scratch_pad` section: `hooks/scripts/scratch-pad-redirect.sh` path becomes stale if/when it migrates to `hooks/adapters/claude-code/`

### Architecture Updates

- `docs/ARCHITECTURE.md:84-95` — add `hooks/adapters/` and `hooks/core/` to the directory tree
- `docs/ARCHITECTURE.md` Extension Architecture section (lines 454-512) — update to document `LLHookIntentExtension` alongside `LLExtension`, `InterceptorExtension`, `wire_extensions()`
- `docs/ARCHITECTURE.md:969` — update exact path reference if `hooks/scripts/issue-completion-log.sh` migrates

### Troubleshooting Updates

- `docs/development/TROUBLESHOOTING.md:750-941` — update `chmod +x` instructions and manual test invocations for `context-monitor.sh`, `user-prompt-check.sh`, `precompact-state.sh`, `check-duplicate-issue-id.sh` to reflect adapter paths under `hooks/adapters/claude-code/`

### Testing Docs

- `docs/development/TESTING.md:774-781` — update `hook_script: Path` fixture pattern to show both legacy shell and adapter fixture variants

## Acceptance Criteria

- "How to write a little-loops hook" guide exists under `docs/claude-code/`
- `hooks-reference.md` has an intent model section
- `EVENT-SCHEMA.md` documents `LLHookEvent` with cross-link to `LLEvent`
- `API.md` Module Overview table includes `little_loops.hooks`
- `ARCHITECTURE.md` directory tree includes `hooks/adapters/` and `hooks/core/`
- `TROUBLESHOOTING.md` paths updated for moved adapter scripts
- `TESTING.md` fixture pattern updated

## Codebase Research Findings

_Added by `/ll:refine-issue` — verifies the Scope claims against current source as of 2026-05-11._

### Already-Done Items (Scope can be narrowed)

- **`docs/ARCHITECTURE.md` directory tree (lines 80-104)** — already lists `hooks/adapters/`, `hooks/adapters/claude-code/`, `hooks/adapters/opencode/` with `precompact.sh`, `session-start.sh`, and `index.ts` entries. Legacy `hooks/scripts/precompact-state.sh` is annotated `# Legacy shell handler; replaced by adapters/claude-code/precompact.sh`. **No directory-tree edit needed.**
- **`docs/ARCHITECTURE.md` Extension Architecture (lines 472-516)** — `LLHookIntentExtension` row already present in the components table (line 487) with full description tying it to `_HOOK_INTENT_REGISTRY`. **No additional edit needed unless a dedicated subsection is desired.**
- **`docs/development/TROUBLESHOOTING.md` chmod block (lines 800-809)** — already includes `hooks/adapters/claude-code/precompact.sh` and `hooks/adapters/claude-code/session-start.sh` alongside legacy `hooks/scripts/` paths. Already notes that the OpenCode TS adapter does not need `chmod +x`. **No edit needed for migrated paths.**
- **`docs/reference/EVENT-SCHEMA.md`** — already contains a `### Hook intents — sibling type` cross-reference note (~line 37-39) linking to `scripts/little_loops/hooks/types.py` and `__init__.py`. **Cross-link exists; full schema documentation still missing.**

### Inaccurate Line References (correct before editing)

- **`docs/reference/API.md:36-37`** — Module Overview table actually spans lines 30-60. The `hooks` row should be inserted near existing `events`/`extension` rows (around line 36-40 is roughly correct, but use the row's neighbors as anchor, not the line number).
- **`docs/reference/API.md:5163-5339`** — Extension API section actually spans lines 5809-6091. `LLHookIntentExtension` is currently mentioned only once at line ~5945 inside the `wire_extensions()` Behavior bullets — no dedicated subsection exists yet.
- **`docs/reference/CONFIGURATION.md:617`** — this line is the `### cli` section header, NOT entry-point group documentation. The actual extensions entry-point doc is in the `### extensions` section, subsection "Auto-discovery via entry points" at lines 743-754. Per Decision 2 in FEAT-1116 (and FEAT-1117 being deferred), hook intents share the existing `little_loops.extensions` entry-point group — the doc update should clarify this in the existing extensions section rather than adding a new entry-point group section.
- **`docs/ARCHITECTURE.md:969`** — this line is inside a "heuristic estimates" tokens table (e.g., `| WebFetch | 1500 tokens |`), NOT a reference to `hooks/scripts/issue-completion-log.sh`. `issue-completion-log.sh` has NOT migrated to adapters; `hooks.json` still points to `hooks/scripts/issue-completion-log.sh`. **No path update needed at this line.**
- **`docs/reference/CONFIGURATION.md:527`** — `### scratch_pad` section reference to `hooks/scripts/scratch-pad-redirect.sh` is accurate today; that script has NOT been migrated. **Only update if/when migration happens.**

### Structural Reality

- **No `hooks/core/` directory exists.** Host-agnostic Python handlers live as peer modules inside `scripts/little_loops/hooks/` (`types.py`, `__init__.py`, `__main__.py`, `pre_compact.py`, `session_start.py`). CLAUDE.md describes a future `hooks/core/` layout that does not yet match reality. The "How to write a little-loops hook" guide and ARCHITECTURE updates should reference `scripts/little_loops/hooks/` as the handler location, NOT `hooks/core/`.
- **No standalone "How to write an extension" guide exists.** Closest models are: `docs/guides/LOOPS_GUIDE.md` (large authoring guide format), `docs/reference/CLI.md` `ll-create-extension` section (lines 1310-1388, scaffold + skeleton + workflow), and `docs/reference/CONFIGURATION.md` `### extensions` section (inline authoring snippet + entry-points block).

## Integration Map

### Source Files (authoritative references for documentation content)

- `scripts/little_loops/hooks/types.py` — `LLHookEvent` and `LLHookResult` dataclasses; the wire-format source of truth (note `to_dict()` uses `ts` key for timestamp; `from_dict()` accepts both `ts` and `timestamp`)
- `scripts/little_loops/hooks/__init__.py` — `main_hooks()` CLI dispatcher, `_dispatch_table()` (built-ins shadow extension handlers on name collision), `_HOOK_INTENT_REGISTRY`, `_register_hook_intents()`
- `scripts/little_loops/hooks/__main__.py` — `python -m little_loops.hooks <intent>` entry point
- `scripts/little_loops/hooks/pre_compact.py` — PreCompact handler (`handle()`); returns `LLHookResult(exit_code=2, feedback=...)` as normal success
- `scripts/little_loops/hooks/session_start.py` — SessionStart handler (`handle()`); returns merged config via `LLHookResult.stdout`
- `scripts/little_loops/extension.py:104-111` — `LLHookIntentExtension` Protocol (`@runtime_checkable`)
- `scripts/little_loops/extension.py:269-273` — `wire_extensions()` integration: `hasattr(ext, "provided_hook_intents")` then `_register_hook_intents(...)`
- `hooks/adapters/claude-code/precompact.sh` — Claude Code bash shim (pipes stdin to `python -m little_loops.hooks pre_compact`)
- `hooks/adapters/claude-code/session-start.sh` — Claude Code bash shim
- `hooks/adapters/opencode/index.ts` — OpenCode TS plugin; `spawnIntent()` translates `session.created → session_start`, `session.compacted → pre_compact`; sets `LL_HOOK_HOST=opencode`
- `hooks/adapters/opencode/README.md` — event→intent mapping table, subprocess contract, latency target (existing model for the adapter flow diagram)
- `hooks/hooks.json` — Claude Code hook wiring; shows which intents use adapters vs legacy `hooks/scripts/`

### Documentation Files to Update

- `docs/reference/API.md` (Module Overview ~line 36, Extension API section ~lines 5809-6091) — add `little_loops.hooks` module row; add `LLHookEvent`, `LLHookResult`, dedicated `LLHookIntentExtension` subsections
- `docs/reference/EVENT-SCHEMA.md` — expand `### Hook intents — sibling type` (~line 37-39) into a full `LLHookEvent`/`LLHookResult` schema section with field tables and per-intent payload examples; cross-link with `LLEvent`
- `docs/reference/CONFIGURATION.md` `### extensions` section (lines 709-756) — add a note that the same `little_loops.extensions` entry-point group also dispatches `LLHookIntentExtension` providers (per FEAT-1116 Decision 2; FEAT-1117 group-split is deferred)
- `docs/claude-code/hooks-reference.md` — add new "Intent model & adapters (little-loops)" section
- `docs/claude-code/automate-workflows-with-hooks.md` — add adapter flow diagram (mermaid `flowchart LR`, modeled on the `flowchart LR` style at `docs/ARCHITECTURE.md` line 870-878)
- `docs/development/TROUBLESHOOTING.md` (lines 790-941) — only update entries for scripts NOT yet migrated (`context-monitor.sh`, `user-prompt-check.sh`, `check-duplicate-issue-id.sh`); leave adapter paths as-is (already correct)
- `docs/development/TESTING.md` (lines 774-789) — add an adapter-path fixture variant alongside the existing `hook_script` shell fixture pattern; reference the adapter pattern from `scripts/tests/test_pre_compact.py` and `scripts/tests/test_hook_session_start.py` for the Python-handler test idiom
- `docs/reference/CLI.md` — `### ll-create-extension` section (lines 1310-1388) — add cross-link to new `write-a-hook.md` guide; new guide should reciprocally reference `ll-create-extension` for the scaffolding step [Wiring pass]
- `.claude/CLAUDE.md` — `## Key Directories` `hooks/` entry: correct `core/` line to reference `scripts/little_loops/hooks/` (not `hooks/core/`, which does not exist per Structural Reality finding above) [Wiring pass]
- `skills/workflow-automation-proposer/SKILL.md` — Step 7 "For hooks" block: `"Handlers live in host-agnostic core code under hooks/core/"` — replace `hooks/core/` with `scripts/little_loops/hooks/` [Wiring pass]
- `skills/audit-claude-config/SKILL.md` — Plugin Components bullet (line 41): replace `hooks/core/` with `scripts/little_loops/hooks/` [Wiring pass]

### Documentation Files to Create

- `docs/claude-code/write-a-hook.md` (or similar slug) — "How to write a little-loops hook" guide:
  - Intent model overview (`LLHookEvent` in, `LLHookResult` out)
  - When to write a core handler vs. when to register via `LLHookIntentExtension`
  - Step-by-step: implement `handle(event: LLHookEvent) -> LLHookResult`, expose via `provided_hook_intents()`, register via `little_loops.extensions` entry point
  - Adapter flow diagram (mermaid)
  - Testing pattern (Python `subprocess.run([sys.executable, "-m", "little_loops.hooks", "<intent>"], input=json.dumps(payload), ...)`)
  - Worked example: a minimal custom intent

### Reusable Patterns

- **Components table for Extension API** — `docs/ARCHITECTURE.md:472` (Extension Architecture section) — pattern for documenting `LLHookEvent`/`LLHookResult` alongside the existing `LLHookIntentExtension` row
- **Per-event field table** — `docs/reference/EVENT-SCHEMA.md` (e.g., `### loop_start`) — 3-column or 4-column table with `Field | Type | Required | Description`
- **Module section structure** — `docs/reference/API.md:5809` (`## little_loops.extension`) — model for new `## little_loops.hooks` section
- **Entry-points authoring block** — `docs/reference/CONFIGURATION.md:743-754` — toml fence + auto-discovery prose
- **Hook script TROUBLESHOOTING entry** — `docs/development/TROUBLESHOOTING.md:800-809` — chmod list + adapter exclusion note
- **Mermaid flow diagrams** — `docs/ARCHITECTURE.md` uses `flowchart LR`/`TB`, `sequenceDiagram`, `stateDiagram-v2`; no ASCII diagrams

### Test References (for documentation accuracy)

- `scripts/tests/test_hook_intents.py` — `LLHookEvent`/`LLHookResult` roundtrip serialization
- `scripts/tests/test_hook_session_start.py` — SessionStart handler test pattern
- `scripts/tests/test_pre_compact.py` — PreCompact handler test pattern
- `scripts/tests/test_opencode_adapter.py` — OpenCode adapter end-to-end test pattern
- `scripts/tests/test_extension.py` — `LLHookIntentExtension` Protocol check pattern
- `scripts/tests/test_hooks_integration.py:17-20` — existing `hook_script: Path` fixture (legacy shell pattern); model for new adapter fixture variant
- `scripts/tests/test_feat1457_doc_wiring.py` — pattern for asserting docs cross-reference hook intents (model for any doc-wiring assertions added by this issue)

### Navigation and Index Files

_Wiring pass added by `/ll:wire-issue`:_
- `mkdocs.yml` — `nav:` block has no `claude-code/` section; new `write-a-hook.md` (and existing `hooks-reference.md`, `automate-workflows-with-hooks.md`) will be invisible in the published site nav without a nav entry [Agent 2]
- `docs/index.md` — no entries exist for any `docs/claude-code/` file; `EVENT-SCHEMA.md` description ("All LLEvent types…") implies only `LLEvent` coverage and becomes stale after FEAT-1453 expands it to cover hook intent types [Agent 2]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1457_doc_wiring.py` — add `TestWriteAHookWiring` class: assert file exists at `docs/claude-code/write-a-hook.md` and content mentions `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension`, `provided_hook_intents`; use the same module-level `Path` constant + `"TOKEN" in content` pattern as existing classes [Agent 3]
- `scripts/tests/test_feat1457_doc_wiring.py::TestAuditClaudeConfigWiring.test_audit_scope_includes_core` — currently asserts `"hooks/core/"` is present in `audit-claude-config/SKILL.md`; if FEAT-1453 corrects that skill, update the assertion to `"scripts/little_loops/hooks/"` instead [Agent 3]
- `scripts/tests/test_hook_intents.py::TestLLHookResult` — `stdout` field has no `to_dict`/`from_dict`/roundtrip coverage despite being a first-class `LLHookResult` field that the docs will describe; add `test_stdout_field_defaults_to_none`, `test_to_dict_skips_stdout_when_none`, `test_to_dict_includes_stdout_when_set`, `test_roundtrip_with_stdout` using the same structure as existing `feedback`/`decision`/`data` tests [Agent 3]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — public package exports `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension`; confirms public API surface documented in the `API.md` update [Agent 1]
- `scripts/little_loops/cli/create_extension.py` — scaffold generator referencing `LLHookIntentExtension`; requires bidirectional cross-link between `docs/reference/CLI.md` `ll-create-extension` section and new `write-a-hook.md` guide [Agent 1]
- `scripts/pyproject.toml` — defines `[project.entry-points."little_loops.extensions"]` group; source of truth for the entry-point name used in the `CONFIGURATION.md` update [Agent 1]

## Proposed Solution

Document the hook-intent abstraction layer in two complementary tracks: a **user-facing authoring guide** (new `docs/claude-code/write-a-hook.md`) and **reference-doc enrichment** (API.md, EVENT-SCHEMA.md, CONFIGURATION.md). Use existing extension-authoring patterns (`docs/reference/CLI.md` `ll-create-extension`, `docs/reference/CONFIGURATION.md` `### extensions`, `docs/ARCHITECTURE.md` components table) as the model — do not invent new structural conventions.

Narrow the original Scope: drop the directory-tree, Extension Architecture components-table, TROUBLESHOOTING adapter-chmod, and ARCHITECTURE:969 items because they are already done or based on inaccurate line references. Treat the entry-point group note as a single-paragraph addition under the existing `### extensions` section (not a new section) since FEAT-1117 is deferred.

## Implementation Steps

1. **Author new guide** — create `docs/claude-code/write-a-hook.md` covering: intent model (link `scripts/little_loops/hooks/types.py`), handler signature (`handle(event: LLHookEvent) -> LLHookResult`), registration via `LLHookIntentExtension.provided_hook_intents()` + `little_loops.extensions` entry point, adapter flow (Claude Code shell vs. OpenCode TS), testing pattern, and a minimal worked example. Model after `docs/guides/LOOPS_GUIDE.md` structure.
2. **Add adapter flow diagram** — append a mermaid `flowchart LR` block to `docs/claude-code/automate-workflows-with-hooks.md` showing: host event → adapter (bash/TS) → `python -m little_loops.hooks <intent>` → `main_hooks()` → handler → `LLHookResult` → adapter → host response. Embed the same diagram (or link it) into the new authoring guide.
3. **Update `hooks-reference.md`** — add an "Intent model & adapters (little-loops)" section near the top, briefly summarizing the abstraction and linking to the new authoring guide + `docs/reference/EVENT-SCHEMA.md` hook intents section.
4. **Expand `EVENT-SCHEMA.md`** — replace the short `### Hook intents — sibling type` blockquote with a full subsection that includes: `LLHookEvent` field table (host, intent, timestamp/ts, payload, session_id, cwd), `LLHookResult` field table (exit_code, feedback, decision, data, stdout), wire-format example JSON, and per-intent payload notes (`pre_compact`, `session_start`). Cross-link with `LLEvent`.
5. **Update `API.md` Module Overview** — insert a `| `little_loops.hooks` | Hook intent dispatcher and host-agnostic handlers |` row near the existing `events`/`extension` rows (around line 36-40).
6. **Update `API.md` Extension API section** — add three subsections in `## little_loops.extension` (or a new `## little_loops.hooks` section, whichever is more discoverable): `### LLHookEvent`, `### LLHookResult`, `### LLHookIntentExtension`. Match the existing `LLExtension Protocol` / `InterceptorExtension` subsection format (signature block, fields/methods table, behavior bullets, code example).
7. **Update `CONFIGURATION.md` `### extensions`** — add a single-paragraph note to the "Auto-discovery via entry points" subsection clarifying that the same `little_loops.extensions` entry-point group also dispatches hook-intent providers (referencing FEAT-1117 as the deferred split).
8. **Update `TROUBLESHOOTING.md`** — verify the non-migrated script entries (`context-monitor.sh`, `user-prompt-check.sh`, `check-duplicate-issue-id.sh`) reference `hooks/scripts/`; only flag migration-blocked items here. Do NOT re-edit the already-correct adapter chmod block.
9. **Update `TESTING.md`** — augment the lines 774-789 `hook_script` fixture example with a sibling adapter-fixture variant showing `subprocess.run([sys.executable, "-m", "little_loops.hooks", "pre_compact"], input=json.dumps({...}), ...)`, modeled on `scripts/tests/test_pre_compact.py`.
10. **Verify with `ll-check-links` and `ll-verify-docs`** — run `python -m little_loops.cli.check_links` (or `ll-check-links`) over `docs/` to catch broken anchors; run `ll-verify-docs` to ensure documented counts still match. Run `python -m pytest scripts/tests/test_feat1457_doc_wiring.py -v` if it covers the new guide; otherwise consider adding an assertion that the new guide exists and references `LLHookEvent`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Fix `hooks/core/` references — in `.claude/CLAUDE.md` (`## Key Directories` `hooks/` entry), `skills/workflow-automation-proposer/SKILL.md` (Step 7 "For hooks"), and `skills/audit-claude-config/SKILL.md` (Plugin Components bullet): replace `hooks/core/` with `scripts/little_loops/hooks/` to match the actual filesystem layout; also update `test_feat1457_doc_wiring.py::TestAuditClaudeConfigWiring.test_audit_scope_includes_core` to assert `"scripts/little_loops/hooks/"` instead of `"hooks/core/"`
12. Add `docs/claude-code/` nav section to `mkdocs.yml` — add nav entries for `write-a-hook.md` (and optionally `hooks-reference.md`, `automate-workflows-with-hooks.md`) so the new guide appears in the published site nav
13. Update `docs/index.md` — add entry for `docs/claude-code/write-a-hook.md`; broaden the `EVENT-SCHEMA.md` description line from "All LLEvent types…" to include hook intent types alongside `LLEvent`
14. Add bidirectional cross-link between `docs/reference/CLI.md` `### ll-create-extension` section and new `write-a-hook.md` — `CLI.md` links to the new guide; the guide references `ll-create-extension` for the scaffolding step
15. Add `TestWriteAHookWiring` class to `scripts/tests/test_feat1457_doc_wiring.py` — assert guide exists and mentions `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension`, `provided_hook_intents`; follow the existing class pattern (module-level `Path` constant + `"TOKEN" in content` assertions)
16. Add `stdout` field coverage to `scripts/tests/test_hook_intents.py::TestLLHookResult` — add `to_dict`/`from_dict`/roundtrip tests using the same structure as the existing `feedback`/`decision`/`data` tests

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Outcome Risk Factors
- **Wide file surface despite mechanical depth** — 16 distinct change sites across docs, skills, tests, and config. No single change is architecturally risky, but partial completion is the most common failure mode for this profile. Use the Implementation Steps list as the checklist.
- **Thin automated coverage over modified files** — doc-wiring tests (token-presence assertions) cover only the new `write-a-hook.md` guide; 13 of 16 modified files have no regression net. Rely on `ll-check-links`/`ll-verify-docs` in Step 10 as the completion gate.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-12
- **Reason**: Issue too large for single session — 16 implementation steps across 16+ files

### Decomposed Into
- FEAT-1458: Hook-Intent Documentation — Authoring Guide
- FEAT-1459: Hook-Intent Documentation — Reference Doc Enrichment
- FEAT-1460: Hook-Intent Documentation — Navigation, Wiring Fixes & Tests

## Session Log
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `d988513e-3479-406f-a1d0-1ef8c9b891d7.jsonl`
- `/ll:wire-issue` - 2026-05-12T04:24:02 - `d2bf320b-b12e-4a6d-b429-17b9901b45a0.jsonl`
- `/ll:refine-issue` - 2026-05-12T04:17:30 - `db8b45cd-427f-4cb7-8a63-6d5af9871153.jsonl`
- `/ll:issue-size-review` - 2026-05-12T00:20:02 - `5cb0dc9a-fd6f-4945-97b0-ad6acec56482.jsonl`
- `/ll:issue-size-review` - 2026-05-12T04:28:55 - `001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
