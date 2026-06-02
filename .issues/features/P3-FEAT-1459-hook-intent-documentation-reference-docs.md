---
id: FEAT-1459
type: FEAT
priority: P3
status: done
parent: FEAT-1453
discovered_date: 2026-05-12
completed_at: 2026-05-12T05:16:27Z
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1459: Hook-Intent Documentation — Reference Doc Enrichment

## Summary

Enrich existing reference documentation to cover the hook-intent abstraction layer: update `hooks-reference.md`, expand `EVENT-SCHEMA.md`, add API.md module and Extension API entries, update CONFIGURATION.md entry-points note, and patch TROUBLESHOOTING.md and TESTING.md where still accurate.

## Parent Issue

Decomposed from FEAT-1453: Hook-Intent Abstraction Layer — Documentation

## Depends On

- FEAT-1448 (LLHookEvent / LLHookResult types exist)
- FEAT-1450 (adapters exist)
- FEAT-1452 (LLHookIntentExtension Protocol)
- FEAT-1458 (authoring guide exists — hooks-reference.md will link to it)

## Scope

Covers FEAT-1453 Implementation Steps 3–9.

### Step 3 — `docs/claude-code/hooks-reference.md`

Add an "Intent model & adapters (little-loops)" section near the top:
- Briefly summarize the intent abstraction (LLHookEvent in, LLHookResult out)
- Link to the new `write-a-hook.md` authoring guide and to `docs/reference/EVENT-SCHEMA.md` hook intents section

### Step 4 — `docs/reference/EVENT-SCHEMA.md`

Replace the short `### Hook intents — sibling type` blockquote (~line 37-39) with a full subsection:
- `LLHookEvent` field table: `host`, `intent`, `timestamp`/`ts`, `payload`, `session_id`, `cwd`
- `LLHookResult` field table: `exit_code`, `feedback`, `decision`, `data`, `stdout`
- Wire-format example JSON (round-trip serialization note: `to_dict()` uses `ts`; `from_dict()` accepts both `ts` and `timestamp`)
- Per-intent payload notes: `pre_compact`, `session_start`
- Cross-link with `LLEvent`

Source of truth: `scripts/little_loops/hooks/types.py`

### Steps 5–6 — `docs/reference/API.md`

- **Module Overview table** (around lines 36-40): insert row `| little_loops.hooks | Hook intent dispatcher and host-agnostic handlers |` near the `events`/`extension` rows; use row neighbors as anchor, not line numbers
- **Extension API section** (~lines 5809-6091): add three subsections matching the existing `LLExtension Protocol` / `InterceptorExtension` format (signature block, fields/methods table, behavior bullets, code example):
  - `### LLHookEvent`
  - `### LLHookResult`
  - `### LLHookIntentExtension` (currently only mentioned once at ~line 5945 inside `wire_extensions()` bullets)

### Step 7 — `docs/reference/CONFIGURATION.md`

In the `### extensions` section (lines 709-756), "Auto-discovery via entry points" subsection:
- Add a single-paragraph note clarifying that the same `little_loops.extensions` entry-point group also dispatches `LLHookIntentExtension` providers (per FEAT-1116 Decision 2; FEAT-1117 group-split is deferred)
- Source of truth for entry-point name: `scripts/pyproject.toml` `[project.entry-points."little_loops.extensions"]`

### Step 8 — `docs/development/TROUBLESHOOTING.md`

Verify lines 790-941: only update entries for scripts NOT yet migrated (`context-monitor.sh`, `user-prompt-check.sh`, `check-duplicate-issue-id.sh`) — ensure they still reference `hooks/scripts/`. Do NOT re-edit the already-correct adapter chmod block (precompact.sh, session-start.sh paths already updated).

### Step 9 — `docs/development/TESTING.md`

Augment lines 774-789 `hook_script` fixture example with a sibling adapter-fixture variant showing:
```python
subprocess.run(
    [sys.executable, "-m", "little_loops.hooks", "pre_compact"],
    input=json.dumps({...}),
    capture_output=True, text=True
)
```
Model on `scripts/tests/test_pre_compact.py` and `test_hook_session_start.py`.

## Acceptance Criteria

- `hooks-reference.md` has an "Intent model & adapters" section linking to `write-a-hook.md`
- `EVENT-SCHEMA.md` has full `LLHookEvent`/`LLHookResult` field tables with JSON example and per-intent payload notes; cross-linked with `LLEvent`
- `API.md` Module Overview table includes `little_loops.hooks` row
- `API.md` Extension API section has dedicated `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension` subsections
- `CONFIGURATION.md` `### extensions` section notes that the entry-point group also dispatches hook-intent providers
- `TROUBLESHOOTING.md` non-migrated script entries reference `hooks/scripts/` (no stale paths introduced)
- `TESTING.md` fixture section includes adapter-fixture variant

## Integration Map

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1459_doc_wiring.py` — **new test file** following `test_feat1457_doc_wiring.py` pattern; one class per target doc file, substring assertions for each acceptance criterion (e.g. `"### LLHookEvent" in API_DOC.read_text()`, `"write-a-hook.md" in HOOKS_REFERENCE.read_text()`, `"hooks/scripts/context-monitor.sh" in TROUBLESHOOTING.read_text()`)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/claude-code/write-a-hook.md` — "See also" callout at line 12 currently points to `scripts/little_loops/hooks/types.py` as the canonical field reference for `LLHookEvent`/`LLHookResult`; when Step 4 makes `EVENT-SCHEMA.md` the new canonical wire-format reference, add `EVENT-SCHEMA.md` as a cross-link in that callout (Agent 2 finding: existing inline field tables in `write-a-hook.md` become parallel definitions)

## Source References

- `scripts/little_loops/hooks/types.py` — `LLHookEvent` / `LLHookResult` wire format
- `scripts/little_loops/extension.py:104-111` — `LLHookIntentExtension` Protocol
- `scripts/little_loops/extension.py:269-273` — `wire_extensions()` integration
- `scripts/pyproject.toml` — entry-point group name source of truth
- `docs/ARCHITECTURE.md:472` — components table pattern for new API.md subsections
- `docs/reference/EVENT-SCHEMA.md:37-39` — existing cross-reference note to expand
- `docs/reference/API.md:5809` — `## little_loops.extension` section model for new `## little_loops.hooks`
- `docs/reference/CONFIGURATION.md:743-754` — entry-points authoring block to augment
- `scripts/tests/test_pre_compact.py`, `test_hook_session_start.py` — adapter test patterns for TESTING.md
- `scripts/tests/test_hooks_integration.py:17-20` — legacy `hook_script` fixture to augment

## Codebase Research Findings

_Added by `/ll:refine-issue` — concrete details ready to transcribe into the docs._

### LLHookEvent field table (source: `scripts/little_loops/hooks/types.py` in `LLHookEvent`)

| Field | Type | Default | Wire key (via `to_dict`) | Description |
|---|---|---|---|---|
| `host` | `str` | _(required)_ | `host` | Host agent identifier (e.g. `"claude-code"`, `"opencode"`). Adapters set this. |
| `intent` | `str` | `""` | `intent` | Hook intent name matching the handler module (e.g. `pre_compact`, `session_start`). |
| `timestamp` | `str` | `""` | `ts` | ISO 8601 UTC string. **Field name and wire key differ** — stored as `timestamp`, serialized as `ts`. |
| `payload` | `dict[str, Any]` | `{}` | `payload` | Host-supplied event data. Schema is intent-specific. |
| `session_id` | `str \| None` | `None` | `session_id` | Host session identifier. Omitted from wire dict when `None`. |
| `cwd` | `str \| None` | `None` | `cwd` | Working directory the host was operating in. Omitted from wire dict when `None`. |

**Round-trip note**: `to_dict()` emits the timestamp under the key `ts`; `from_dict()` accepts either `ts` or `timestamp` via `data.get("ts", data.get("timestamp", ""))`. A dict from `to_dict()` round-trips cleanly through `from_dict()`.

### LLHookResult field table (source: `scripts/little_loops/hooks/types.py` in `LLHookResult`)

| Field | Type | Default | Wire key | Description |
|---|---|---|---|---|
| `exit_code` | `int` | `0` | `exit_code` | Always emitted. `0` = pass; `2` = block and surface `feedback` to the model. Non-Claude hosts map to their own permit/deny semantics. |
| `feedback` | `str \| None` | `None` | `feedback` | Human-readable message. Claude Code writes this to stderr when `exit_code == 2`. Omitted from wire dict when `None`. |
| `decision` | `str \| None` | `None` | `decision` | Permission decision for permission-checking intents (`allow` / `deny` / `ask`). Omitted from wire dict when `None`. |
| `data` | `dict[str, Any]` | `{}` | `data` | Additional structured data returned to the host. Omitted from wire dict when empty. |
| `stdout` | `str \| None` | `None` | `stdout` | Raw payload written to the host's stdout (e.g. SessionStart's merged config JSON). Omitted from wire dict when `None`. |

### Per-intent payload contracts

- **`pre_compact`** (`scripts/little_loops/hooks/pre_compact.py` in `handle`): reads exactly one payload key — `transcript_path` (falls back to `""`). Ignores `host`, `session_id`, `cwd`, `timestamp`. Writes `.ll/ll-precompact-state.json`. Returns `LLHookResult(exit_code=2, feedback=_FEEDBACK)`.
- **`session_start`** (`scripts/little_loops/hooks/session_start.py` in `handle`): reads **no** payload keys — first line is `del event`. Operates via `Path.cwd()`. Returns `LLHookResult(exit_code=0, feedback=<stderr-lines>, stdout=<config-json-or-None>)`.

### LLHookIntentExtension Protocol (source: `scripts/little_loops/extension.py` in `LLHookIntentExtension`)

```python
@runtime_checkable
class LLHookIntentExtension(Protocol):
    def provided_hook_intents(self) -> dict[str, Callable[[LLHookEvent], LLHookResult]]: ...
```

- `@runtime_checkable` — `isinstance()` works.
- `wire_extensions()` detects providers via `hasattr(ext, "provided_hook_intents")` (same pattern as `ActionProviderExtension`, `EvaluatorProviderExtension`, `InterceptorExtension`).
- Merges into module-level `_HOOK_INTENT_REGISTRY` in `little_loops.hooks` via `_register_hook_intents()`; raises `ValueError` on duplicate intent name across extensions.
- Built-in intents (`pre_compact`, `session_start`) shadow extension-registered intents on collision (see `_dispatch_table()` in `scripts/little_loops/hooks/__init__.py`: `return {**_HOOK_INTENT_REGISTRY, **built_ins}`).

### Entry-point group reality check (source: `scripts/pyproject.toml`)

- The group is `little_loops.extensions` (single shared group, also exported as `ENTRY_POINT_GROUP` in `scripts/little_loops/extension.py`).
- No entry points are currently registered — the section is comment-only. This matches FEAT-1116 Decision 2 (single shared group); FEAT-1117 group-split is deferred.
- CONFIGURATION.md augmentation should reuse the existing `little_loops.extensions` group name, not introduce `little_loops.hook_intents`.

### Dispatcher CLI surface (source: `scripts/little_loops/hooks/__init__.py` in `main_hooks`)

`python -m little_loops.hooks <intent>` flow:
1. Reads stdin as JSON (skips if TTY).
2. Builds `LLHookEvent(host=os.environ.get("LL_HOOK_HOST", "claude-code"), intent=<argv[1]>, payload=<parsed>, cwd=os.getcwd())`. **`timestamp` and `session_id` are not populated by the CLI** — they stay at dataclass defaults.
3. Calls handler; writes `result.stdout` to stdout if not None; prints `result.feedback` to stderr if truthy.
4. Returns `result.exit_code` via `raise SystemExit(...)` in `__main__.py`.

`LL_HOOK_HOST` env var: OpenCode adapter sets `LL_HOOK_HOST=opencode`; Claude Code adapters do not set it (defaults to `"claude-code"`).

Public surface — `__all__ = ["LLHookEvent", "LLHookResult", "main_hooks"]`. `_register_hook_intents` and `_dispatch_table` are private but `_register_hook_intents` is imported by name inside `wire_extensions()`.

### API.md pattern template (source: `docs/reference/API.md:5809-5950`, anchor `## little_loops.extension`)

Each Extension API entry follows this exact shape:

1. `### <Name>` heading
2. One-sentence prose description
3. Signature `python` code block (full Protocol/class declaration)
4. Behavior bullets / `**Parameters:**` / `**Returns:**` / `**Behavior:**` / `**Error handling:**` blocks as applicable
5. Usage `python` code block (concrete `import` + invocation example)

Subsections like `#### Constructor` and `#### Methods` (with pipe-table) are used when the type has callable surface (see `NoopLoggerExtension` at lines 5856-5881).

**Correction to issue Step 5–6**: `InterceptorExtension` does **not** have its own `###` subsection in API.md — it is only mentioned by name inside `wire_extensions()`'s **Behavior** bullets (line 5944). The model to follow is `### LLExtension Protocol` (lines 5829-5854) and `### NoopLoggerExtension` (lines 5856-5881), not "LLExtension Protocol / InterceptorExtension".

### Module Overview row format (source: `docs/reference/API.md:36-38`)

```
| `little_loops.hooks` | Host-agnostic hook intent dispatcher and built-in handlers |
```

Insert after `little_loops.events` and before `little_loops.extension` to keep alphabetical-ish neighbor grouping.

### EVENT-SCHEMA.md existing block to replace (source: `docs/reference/EVENT-SCHEMA.md:37-41`)

The blockquote at lines 37-41 is a single paragraph with embedded links to `types.py` and `hooks/__init__.py`. Replace the prose block (keeping the `### Hook intents — sibling type` heading) with full `LLHookEvent` / `LLHookResult` field tables (use the three-column `| Key | Type | Description |` format consistent with the file's existing wire-format table at lines 23-27), a wire-format JSON example, and the per-intent payload notes.

### CONFIGURATION.md augmentation locus (source: `docs/reference/CONFIGURATION.md:743-756`)

The "Auto-discovery via entry points" block already documents the `little_loops.extensions` group for `LLExtension` providers. Add a follow-on paragraph (after line 752, before line 754 cross-link to API.md) noting that the same group also dispatches `LLHookIntentExtension` providers and pointing at the new `### LLHookIntentExtension` API.md subsection.

### TROUBLESHOOTING.md script-path audit (source: `docs/development/TROUBLESHOOTING.md:790-1050`)

Non-migrated scripts still referenced under `hooks/scripts/` (correct — leave as-is):
- `hooks/scripts/context-monitor.sh` — appears in `### Hook not executing` (~line 792), `### Hook timeout errors` (~line 835), `### Context monitor not updating` (~line 923), `### Testing individual hooks` (~line 980), `### Common lock issues` (~line 1037)
- `hooks/scripts/check-duplicate-issue-id.sh` and `check-duplicate-issue-id-post.sh` — `### Duplicate issue ID not detected` (~line 895), `### Testing individual hooks`, `### Common lock issues`
- `hooks/scripts/user-prompt-check.sh` — `### User prompt optimization not working` (~line 955), `### Testing individual hooks`
- `hooks/scripts/scratch-pad-redirect.sh` — `### Hook not executing`

Already-migrated adapter paths (do **not** re-edit):
- `hooks/adapters/claude-code/precompact.sh`
- `hooks/adapters/claude-code/session-start.sh`
- `hooks/adapters/opencode/index.ts`

**Correction to issue Step 8**: TROUBLESHOOTING.md hook-related content extends to ~line 1050 (not 941). The verification scope should be lines ~790-1050; the `### Common lock issues` block at ~line 1037 also references `little_loops.hooks.pre_compact` and the non-migrated scripts.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Write `scripts/tests/test_feat1459_doc_wiring.py` — multi-class doc-wiring test file; use `test_feat1457_doc_wiring.py` as the direct template (same `PROJECT_ROOT / "docs" / ...` path pattern, same `.read_text()` assertion style). One class per doc file. Assertions should cover every acceptance criterion: `"Intent model" in hooks-reference.md`, `` "`ts`" in EVENT-SCHEMA.md ``, `"### LLHookEvent" in API.md`, `"### LLHookResult" in API.md`, `"### LLHookIntentExtension" in API.md`, `"little_loops.hooks" in API.md`, `"LLHookIntentExtension" in CONFIGURATION.md`, `"hooks/scripts/context-monitor.sh" in TROUBLESHOOTING.md`, `"subprocess.run" in TESTING.md`.
11. Update `docs/claude-code/write-a-hook.md` "See also" callout — add a cross-link to `EVENT-SCHEMA.md` (relative path: `../reference/EVENT-SCHEMA.md`) alongside the existing `types.py` source link, so the callout points users to the new canonical wire-format reference.

### TESTING.md adapter-fixture variant (source: `scripts/tests/test_hooks_integration.py:17-20` legacy fixture; `scripts/tests/test_pre_compact.py` + `test_hook_session_start.py` as patterns)

Legacy fixture to augment:
```python
@pytest.fixture
def hook_script(self) -> Path:
    """Path to context-monitor.sh."""
    return Path(__file__).parent.parent.parent / "hooks/scripts/context-monitor.sh"
```

Sibling adapter-fixture variant to render in TESTING.md (invokes the dispatcher CLI directly — no shell adapter needed; honors `LL_HOOK_HOST` to flip host identity):
```python
import json, subprocess, sys

def run_hook_intent(intent: str, payload: dict, host: str = "claude-code") -> subprocess.CompletedProcess:
    """Invoke a hook intent via the python -m little_loops.hooks dispatcher."""
    return subprocess.run(
        [sys.executable, "-m", "little_loops.hooks", intent],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "LL_HOOK_HOST": host},
    )

# Example call:
result = run_hook_intent("pre_compact", {"transcript_path": "/tmp/session.jsonl"})
assert result.returncode == 2  # pre_compact always blocks with feedback
```

Note: `test_pre_compact.py` and `test_hook_session_start.py` are unit tests that call `handle()` directly; `test_hooks_integration.py` is the place that exercises subprocess invocation patterns. TESTING.md should reference the unit-test files as "fast path" and the subprocess pattern (above) as "integration path".

### hooks-reference.md cross-link target (source: `docs/claude-code/write-a-hook.md:5`)

The authoring guide title is `# Write a little-loops hook`. From `docs/claude-code/hooks-reference.md` (same directory), use relative path `write-a-hook.md` with display text `Write a little-loops hook`. Existing cross-references already use this convention (`docs/claude-code/automate-workflows-with-hooks.md:644`).

## Resolution

Implemented across six reference docs plus a wiring-test pass:

- `docs/claude-code/hooks-reference.md` — new "Intent model & adapters (little-loops)" section near the top, linking to `write-a-hook.md` and `EVENT-SCHEMA.md`.
- `docs/reference/EVENT-SCHEMA.md` — `### Hook intents — sibling type` subsection now has full `LLHookEvent` and `LLHookResult` field tables, a wire-format JSON example, the `ts`/`timestamp` round-trip note, and per-intent payload notes for `pre_compact` and `session_start`.
- `docs/reference/API.md` — added `little_loops.hooks` row to the Module Overview, a new `## little_loops.hooks` section with `### LLHookEvent` / `### LLHookResult` / `### main_hooks` subsections, and a `### LLHookIntentExtension` subsection under `## little_loops.extension`.
- `docs/reference/CONFIGURATION.md` — `### extensions` entry-points block now documents that the same `little_loops.extensions` group also dispatches `LLHookIntentExtension` providers.
- `docs/development/TROUBLESHOOTING.md` — verified non-migrated script paths (`context-monitor.sh`, `user-prompt-check.sh`, `check-duplicate-issue-id.sh`) still reference `hooks/scripts/` correctly; no changes needed.
- `docs/development/TESTING.md` — new "Testing Hook Intents via the Dispatcher CLI" subsection with fast-path (direct handler call) and integration-path (`subprocess.run [-m little_loops.hooks]` fixture using `LL_HOOK_HOST`).
- `docs/claude-code/write-a-hook.md` — `See also` callout cross-links to `EVENT-SCHEMA.md` as the canonical wire-format reference alongside the existing `types.py` link.
- `scripts/tests/test_feat1459_doc_wiring.py` — 23-test wiring suite asserting every acceptance criterion as substring checks against the doc files (TDD red-then-green).

All 23 wiring tests pass. Pre-existing unrelated failures in `test_generate_schemas.py` and `test_update_skill.py` are out of scope.

## Session Log
- `/ll:manage-issue feature implement FEAT-1459` - 2026-05-12T05:16:27Z - `a2e9895d-1d2a-42d4-b0bf-56bb7f5ad16f.jsonl`
- `/ll:ready-issue` - 2026-05-12T05:08:10 - `b99e0889-c675-4bfc-9f42-688812025a20.jsonl`
- `/ll:confidence-check` - 2026-05-12T00:00:00Z - `bfd5b22f-5b5d-4e9f-840f-5f47586fbfd0.jsonl`
- `/ll:wire-issue` - 2026-05-12T05:02:01 - `60996da8-f8c0-446a-8c72-3e0170e3c5dc.jsonl`
- `/ll:refine-issue` - 2026-05-12T04:57:08 - `36688df2-2d3e-413f-8f0f-1691ef115fed.jsonl`
- `/ll:issue-size-review` - 2026-05-12T04:28:55 - `001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
