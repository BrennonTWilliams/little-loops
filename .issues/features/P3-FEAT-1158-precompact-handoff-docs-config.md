---
id: FEAT-1158
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
discovered_by: issue-size-review
completed_at: 2026-06-17 17:16:17+00:00
blocked_by:
- FEAT-1112
- FEAT-1156
parent: FEAT-1113
decision_needed: false
relates_to:
- FEAT-1156
- FEAT-1157
confidence_score: 100
outcome_confidence: 72
score_complexity: 19
score_test_coverage: 12
score_ambiguity: 23
score_change_surface: 18
implementation_order_risk: true
size: Very Large
---

# FEAT-1158: PreCompact Handoff Hook — Docs & Configuration

## Summary

Update all documentation, configuration schema, templates, and peripheral config files to reflect the new `precompact-handoff.sh` hook introduced by FEAT-1156.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Acceptance Criteria

- `docs/guides/SESSION_HANDOFF.md` describes automatic PreCompact trigger alongside manual `/ll:handoff`
- `docs/ARCHITECTURE.md:87-90` (`claude-code/` adapter listing) lists all 6 adapter files: `post-tool-use.sh`, `pre-tool-use.sh`, `precompact-handoff.sh`, `precompact.sh`, `session-end.sh`, `session-start.sh`
- `docs/ARCHITECTURE.md:1105-1132` (`### Context Monitor and Session Continuation` flowchart) shows PreCompact as a second handoff trigger path (not PostToolUse-only; currently shows only PostToolUse → handoff)
- `docs/development/TROUBLESHOOTING.md:849` chmod list (lines 844–854) includes `hooks/adapters/claude-code/precompact-handoff.sh` after the existing `precompact.sh` entry
- `docs/development/TROUBLESHOOTING.md:1058-1074` manual test invocation block has parallel entry for `pre_compact_handoff` (three variants: default, `LL_HOOK_HOST=opencode`, `LL_HOOK_HOST=codex`)
- `docs/development/TROUBLESHOOTING.md:1104` lock timeout list includes `little_loops.hooks.pre_compact_handoff` with its 3s advisory lock
- `skills/configure/areas.md:878` hook audit table has a row for `precompact-handoff.sh` (`[Plugin] PreCompact * adapters/claude-code/precompact-handoff.sh 5s`)
- No `config-schema.json` changes (always-on decision: no feature flag)
- No `templates/*.json` changes (always-on decision: no feature flag)
- No `docs/reference/CONFIGURATION.md` config-key changes needed (always-on decision)

## Implementation

### Decision: Always-On (Resolved)

`precompact_handoff` runs unconditionally — no config gate. See `## Decision Rationale` below for scoring and reasoning. Steps 7–9 (schema and template changes) are not needed.

### Documentation Updates

1. `docs/guides/SESSION_HANDOFF.md` — add section explaining PreCompact auto-trigger; clarify `/ll:handoff` is now a manual override for the richer version; update `## Integration` (lines ~490-506) to mention PreCompact hook alongside PostToolUse; add `.ll/ll-precompact-state.json` to `## Files` table (lines ~365-371)
2. `docs/ARCHITECTURE.md:87-90` — replace the 3-entry `claude-code/` block (lines 88-90: `precompact.sh`, `session-end.sh`, `session-start.sh`) with all 6 adapter files in alphabetical order; the tree currently omits `post-tool-use.sh`, `pre-tool-use.sh`, and `precompact-handoff.sh` — adding only `precompact-handoff.sh` would leave the tree incomplete with misleading appearance of completeness
3. `docs/ARCHITECTURE.md:1105-1132` — update `### Context Monitor and Session Continuation` flowchart to show two handoff trigger paths: PostToolUse (existing) + PreCompact (new); the flowchart currently shows only PostToolUse → handoff with no PreCompact path
4. `docs/development/TROUBLESHOOTING.md:849` — add `chmod +x hooks/adapters/claude-code/precompact-handoff.sh` after the existing `precompact.sh` entry at line 849 (within the chmod block at lines 844-854)
5. `docs/development/TROUBLESHOOTING.md:1074` — add manual invocation block for `pre_compact_handoff` after the existing `pre_compact` block at lines 1058-1073; include three variants (default, `LL_HOOK_HOST=opencode`, `LL_HOOK_HOST=codex`) matching the `pre_compact` pattern
6. `docs/development/TROUBLESHOOTING.md:1104` — add `little_loops.hooks.pre_compact_handoff: 3s lock timeout (Python handler invoked via hooks/adapters/claude-code/precompact-handoff.sh)` to the lock timeout list after the existing `pre_compact` entry at line 1104

### Configuration (if opt-in) — NOT APPLICABLE

~~7. `config-schema.json` — new top-level section `precompact_handoff`~~
~~8. `templates/generic.json` + 8 other templates — add `"precompact_handoff": {"enabled": true}`~~
~~9. `docs/reference/CONFIGURATION.md` — document the new config key~~

_Steps 7–9 are superseded by the always-on decision. `pre_compact_handoff.py` has no `_load_config()` call, no `feature_enabled()` guard, and no `config-schema.json` entry — same pattern as `pre_compact.py`. No schema or template changes needed._

### Skill Config Audit Display

10. `skills/configure/areas.md:878` — add row after the existing `precompact.sh` entry (line 878): `[Plugin]   PreCompact        *              adapters/claude-code/precompact-handoff.sh       5s    [exists/MISSING]` (5s timeout per `hooks/hooks.json` PreCompact block; use same column spacing as adjacent rows)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` — (a) "Lifecycle at a Glance" table: add second `PreCompact` row after line 67 (`| **PreCompact** | precompact-handoff | Writes session continuation prompt before compaction | — | on |`); (b) `## PreCompact` section (lines 286-294): add parallel block describing `precompact-handoff.sh` → `little_loops.hooks.pre_compact_handoff.handle`, outputs `.ll/ll-continue-prompt.md`, reads `.ll/ll-precompact-state.json` for idempotency guard, 3s advisory lock; (c) "A Session from Hook's Perspective" narrative (lines 71-94): add second PreCompact step showing two-phase behavior (state snapshot via `precompact.sh` first, continuation prompt via `precompact-handoff.sh` second)
12. Update `docs/claude-code/write-a-hook.md:180` — add `precompact-handoff.sh` to the `Adapter files:` inline list (currently: `precompact.sh`, `post-tool-use.sh`, `session-end.sh`, `session-start.sh`; add `precompact-handoff.sh` after `precompact.sh`)
13. Update `commands/handoff.md:239-244` — extend `## Integration` section; add bullet: `- PreCompact hook writes `.ll/ll-continue-prompt.md` automatically before context compaction (passive path); /ll:handoff is the active/richer manual override`
14. Update `scripts/tests/test_wiring_guides_and_meta.py` — add to `DOC_STRINGS_PRESENT` list: `("docs/ARCHITECTURE.md", "precompact-handoff.sh", "FEAT-1158")`, `("docs/development/TROUBLESHOOTING.md", "precompact-handoff.sh", "FEAT-1158")`, `("docs/guides/SESSION_HANDOFF.md", "precompact-handoff.sh", "FEAT-1158")`; follow the tuple format `(doc_path, expected_string, issue_id)` used by existing entries (see lines 37-41)
15. Update `scripts/tests/test_wiring_init_and_configure.py` — add to `DOC_STRINGS_PRESENT` list: `("skills/configure/areas.md", "precompact-handoff.sh", "FEAT-1158")`; follow existing entries at lines 133-134: `("skills/configure/areas.md", "adapters/claude-code/precompact.sh", "FEAT-1457")`
16. Update `docs/reference/API.md` — (a) add `precompact-handoff.sh` to adapter file list in `main_hooks` "Adapter integration" note alongside `precompact.sh`, `post-tool-use.sh`, `session-end.sh`, `session-start.sh`; (b) add `pre_compact_handoff` to `LLHookIntentExtension` "Behavior" built-in shadow list (~line 7218) alongside `pre_compact`, `session_start`, `session_end`, `user_prompt_submit`, `post_tool_use`, `pre_tool_use`
17. Update `docs/reference/EVENT-SCHEMA.md` — add per-intent payload note for `pre_compact_handoff` in "Per-intent payload notes" section following the pattern of the `pre_compact` entry: outputs `.ll/ll-continue-prompt.md`; reads `.ll/ll-precompact-state.json` as idempotency guard; exit 2 on success, 0 on skip

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-16.

**Selected**: Always-on

**Reasoning**: The existing `pre_compact.py` handler — the direct predecessor to FEAT-1158's additions — runs unconditionally with no config gate and has no entry in `config-schema.json`. Eight of twelve hooks in this codebase follow the always-on pattern; only hooks with meaningful per-call cost or disruptive side effects (analytics, scratch_pad) use a config gate. Choosing always-on avoids adding config-reading to `pre_compact.py` (which currently has none), skips updating 9 template files, and aligns with the preference stated in the issue.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Always-on | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Opt-in | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- **Always-on**: `pre_compact.py` has no `_load_config()` call, no `feature_enabled()` guard, and no `config-schema.json` entry; 8 of 12 hooks run unconditionally; issue flags always-on as "preferred".
- **Opt-in**: Requires adding config-reading to `pre_compact.py` (absent today), touching all 9 template files, and a new schema section — convention exists but direct predecessor contradicts it.

## Files to Modify

- `docs/guides/SESSION_HANDOFF.md` — add PreCompact trigger section; update Integration (~492-507) and Files table (~366-372)
- `docs/ARCHITECTURE.md` (lines 86-91: add adapter entry; lines 1105-1132: update Context Monitor flowchart)
- `docs/development/TROUBLESHOOTING.md` (line 849: chmod entry; lines 1058-1074: add manual invocation block; line 1104: add lock timeout entry)
- `skills/configure/areas.md` (line 878: add hook audit table row)
- ~~`config-schema.json`~~ — not needed (always-on)
- ~~`templates/*.json`~~ — not needed (always-on)
- ~~`docs/reference/CONFIGURATION.md`~~ — no config keys to document (always-on)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — update "Lifecycle at a Glance" table (line 67), "PreCompact" section (lines 286-295), and session narrative (lines 71-94) to include `precompact-handoff.sh` as a second PreCompact entry alongside `precompact.sh`
- `docs/claude-code/write-a-hook.md` — add `precompact-handoff.sh` to `Adapter files:` inline list (line 180) which lists Claude Code adapter scripts
- `commands/handoff.md` — update `## Integration` section (lines 239-244) to mention PreCompact trigger path alongside the existing PostToolUse context monitor description
- `docs/reference/API.md` — add `precompact-handoff.sh` to `main_hooks` "Adapter integration" adapter file list; add `pre_compact_handoff` to `LLHookIntentExtension` "Behavior" built-in shadow list (~line 7218)
- `docs/reference/EVENT-SCHEMA.md` — add per-intent payload note for `pre_compact_handoff` in "Per-intent payload notes" section

## References

- Depends on: FEAT-1156 (hook must exist before docs can be accurate)
- Tests: FEAT-1157

## Integration Map

### Confirmed Pre-Existing Implementation (FEAT-1156 Complete)

_Re-verified by `/ll:refine-issue` on 2026-06-17 — all four artifacts confirmed present:_
- `hooks/adapters/claude-code/precompact-handoff.sh` — **EXISTS**; 3-line bash shim that pipes stdin to `python -m little_loops.hooks pre_compact_handoff`; no `LL_HOOK_HOST` export (defaults to `"claude-code"`)
- `hooks/hooks.json:176-198` — **REGISTERED**; `PreCompact` array contains both `precompact.sh` (entry 1) and `precompact-handoff.sh` (entry 2), timeout 5s, feedback `"Writing session handoff..."`
- `scripts/little_loops/hooks/pre_compact_handoff.py` — **EXISTS**; `handle()` reads `.ll/ll-precompact-state.json` for idempotency guard, writes `.ll/ll-continue-prompt.md` atomically with 3s advisory lock, returns `exit_code=2` on success, `exit_code=0` on idempotency skip
- `scripts/little_loops/hooks/__init__.py:17,52,78,87` — **DISPATCHED**; `pre_compact_handoff` is in `_dispatch_table()` mapping to `pre_compact_handoff.handle`; module docstring and `_USAGE` string enumerate it

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/hooks.json` — registers `precompact-handoff.sh` in the `PreCompact` array; owned by FEAT-1156 but must exist before FEAT-1158 docs can be accurate
- `scripts/little_loops/hooks/__init__.py` — module docstring and `_USAGE` string enumerate dispatched intents; owned by FEAT-1156 (adds `pre_compact_handoff` to intent list)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `context_monitor` description (line ~427) implies context_monitor is the sole automatic handoff path; add a clarifying cross-reference to SESSION_HANDOFF.md for the PreCompact trigger path [Agent 2 finding — low-force coupling]
- `docs/reference/API.md` — built-ins list in two locations omits `pre_compact_handoff`: (a) `main_hooks` "Adapter integration" adapter file list; (b) `LLHookIntentExtension` "Behavior" built-in shadow list (~line 7218) [second wiring pass]
- `docs/reference/EVENT-SCHEMA.md` — "Per-intent payload notes" section has no entry for `pre_compact_handoff` intent [second wiring pass]
- `commands/resume.md` — "Integration" section at end of file names only `/ll:handoff` as prompt source; does not mention PreCompact hook (though "If Nothing Found" block at line 132 already does) [advisory]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py` — add `DOC_STRINGS_PRESENT` entries: `("docs/guides/SESSION_HANDOFF.md", "precompact-handoff.sh", "FEAT-1158")` (currently zero wiring test coverage for this file); add presence guards for `"precompact-handoff.sh"` in `docs/ARCHITECTURE.md` and `docs/development/TROUBLESHOOTING.md` after FEAT-1158 edits are applied; follow tuple format at lines 37-41
- `scripts/tests/test_wiring_init_and_configure.py` — add `DOC_STRINGS_PRESENT` entry `("skills/configure/areas.md", "precompact-handoff.sh", "FEAT-1158")` to gate the new hook audit table row; add after existing lines 133-134 (`precompact.sh` entry for FEAT-1457)
- Extend step 14 (`scripts/tests/test_wiring_guides_and_meta.py`) with 2 additional tuples for new doc files: `("docs/reference/API.md", "precompact-handoff.sh", "FEAT-1158")` and `("docs/reference/EVENT-SCHEMA.md", "pre_compact_handoff", "FEAT-1158")`; bump header count from 173 → 175 [second wiring pass]
- `scripts/tests/test_wiring_skills_and_commands.py` — optional gap: `("commands/handoff.md", "precompact-handoff.sh", "FEAT-1158")` to gate step 13 insertion; not in original issue spec [optional]

### Codebase Research Findings

_Re-verified by `/ll:refine-issue` (full-rewrite pass, 2026-06-17) — all confirmed against current HEAD via codebase-analyzer + codebase-locator:_

**Pre-existing implementation artifacts (FEAT-1156) — all confirmed:**
- `hooks/adapters/claude-code/precompact-handoff.sh` — EXISTS; 3-line bash shim piping stdin to `python -m little_loops.hooks pre_compact_handoff`
- `hooks/hooks.json:176-198` — REGISTERED; PreCompact array contains both `precompact.sh` and `precompact-handoff.sh`; timeout 5s; statusMessage `"Writing session handoff..."`
- `scripts/little_loops/hooks/pre_compact_handoff.py:181` — exit_code=2 on success; exit_code=0 on idempotency skip (line 61) or any exception (line 179)
- `scripts/little_loops/hooks/__init__.py:17,79,87` — dispatch entry `"pre_compact_handoff": pre_compact_handoff.handle` at line 87; module docstring at line 17; lazy import at line 79

**All 15 target sections verified MISSING precompact-handoff.sh (codebase-analyzer, 2026-06-17):**
- `docs/ARCHITECTURE.md:87-90` — adapter tree: `precompact.sh` (88), `session-end.sh` (89), `session-start.sh` (90); no `post-tool-use.sh` or `precompact-handoff.sh` in the tree
- `docs/ARCHITECTURE.md:1101-1132` — `### Context Monitor and Session Continuation`; Mermaid flowchart at 1105-1132 shows PostToolUse → handoff only; closing ` ``` ` at line 1132; no PreCompact subgraph
- `docs/ARCHITECTURE.md:1231` — forward reference to `precompact-handoff.sh` present (session-capture consumer note); not a target — avoid clobbering
- `docs/development/TROUBLESHOOTING.md:843-855` — chmod block; `precompact.sh` at 849, `session-end.sh` at 850, `session-start.sh` at 851; no `precompact-handoff.sh`
- `docs/development/TROUBLESHOOTING.md:1058-1074` — `pre_compact` invocation block; three variants end at line 1073; closing ` ``` ` at line 1074 (insert before this line)
- `docs/development/TROUBLESHOOTING.md:1100-1104` — lock timeout list; `little_loops.hooks.pre_compact` at line 1104; line 1105 starts `3. Monitor lock files`
- `docs/guides/SESSION_HANDOFF.md:365-371` — Files table: `.ll/ll-continue-prompt.md` (369), `.ll/ll-context-state.json` (370), `.ll/ll-session-state.json` (371); no `.ll/ll-precompact-state.json`
- `docs/guides/SESSION_HANDOFF.md:490-495` — `## Integration` / `### With Other Hooks`; PostToolUse (494) and Stop (495) only; no PreCompact entry
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:51-67` — table ends at 67: `| **PreCompact** | precompact | Snapshots task state before compaction | exit 2 | on |`; no `precompact-handoff` row
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:71-94` — session narrative; PostToolUse block ends at 89; "Session ends" at 91; no PreCompact step between them
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:286-296` — `## PreCompact` section at 286-294; `---` separator at 296; describes only `precompact.sh → pre_compact.handle`
- `docs/claude-code/write-a-hook.md:180` — Adapter files list: `precompact.sh`, `post-tool-use.sh`, `session-end.sh`, `session-start.sh`; `precompact-handoff.sh` absent
- `commands/handoff.md:239-244` — `## Integration` section; PostToolUse context monitor mentioned; no PreCompact trigger path
- `skills/configure/areas.md:878` — one PreCompact row: `[Plugin]   PreCompact   *   adapters/claude-code/precompact.sh   5s   [exists/MISSING]`

**Exact text to insert at each change site:**

_Step 2 — `docs/ARCHITECTURE.md:87-90` (adapter listing — replace entire `claude-code/` block with all 6 adapter files):_
```
│   │   ├── claude-code/
│   │   │   ├── post-tool-use.sh
│   │   │   ├── pre-tool-use.sh
│   │   │   ├── precompact-handoff.sh
│   │   │   ├── precompact.sh
│   │   │   ├── session-end.sh
│   │   │   └── session-start.sh
```

_Step 3 — `docs/ARCHITECTURE.md:1105-1132` (flowchart — replace entire Mermaid block with):_
```mermaid
flowchart TB
    subgraph Hook["PostToolUse Hook"]
        ESTIMATE[Estimate context usage]
        CHECK[Check threshold]
    end

    subgraph Handoff["Active Handoff Path"]
        TRIGGER[Trigger /ll:handoff]
        WRITE[Write continuation prompt]
        SIGNAL[Output CONTEXT_HANDOFF signal]
    end

    subgraph CLI["CLI Detection"]
        DETECT[Detect handoff signal]
        READ[Read continuation prompt]
        SPAWN[Spawn fresh session]
    end

    subgraph PassivePath["Passive Handoff Path (PreCompact)"]
        PC_WRITE[precompact-handoff.sh writes continuation prompt]
        COMPACT[Claude Code compacts context]
        RESUME[/ll:resume re-injects context in current session]
    end

    ESTIMATE --> CHECK
    CHECK -->|>= 80%| TRIGGER
    TRIGGER --> WRITE
    WRITE --> SIGNAL
    SIGNAL --> DETECT
    DETECT --> READ
    READ --> SPAWN
    SPAWN -->|Resume work| ESTIMATE
    PC_WRITE --> COMPACT
    COMPACT --> RESUME
    RESUME -->|Work continues| ESTIMATE
```

_Step 4 — `docs/development/TROUBLESHOOTING.md:849` (chmod block — insert after `precompact.sh` chmod line):_
```
   chmod +x hooks/adapters/claude-code/precompact-handoff.sh
```

_Step 5 — `docs/development/TROUBLESHOOTING.md:1073` (manual invocation — insert after last `pre_compact` variant, before closing ` ``` ` at line 1074):_
```

# Test precompact-handoff handler (writes .ll/ll-continue-prompt.md; reads .ll/ll-precompact-state.json as idempotency guard)
echo '{
  "transcript_path": "/tmp/test.jsonl"
}' | python -m little_loops.hooks pre_compact_handoff

# Same handler from the OpenCode adapter's perspective: set LL_HOOK_HOST to
# reproduce the host identifier the OpenCode plugin injects.
echo '{
  "transcript_path": "/tmp/test.jsonl"
}' | LL_HOOK_HOST=opencode python -m little_loops.hooks pre_compact_handoff

# Same handler from the Codex CLI adapter's perspective: set LL_HOOK_HOST=codex.
# This also flips resolve_config_path() to probe .codex/ll-config.json first.
echo '{
  "transcript_path": "/tmp/test.jsonl"
}' | LL_HOOK_HOST=codex python -m little_loops.hooks pre_compact_handoff
```

_Step 6 — `docs/development/TROUBLESHOOTING.md:1104` (lock timeout — insert after `little_loops.hooks.pre_compact` entry at line 1104):_
```
   - little_loops.hooks.pre_compact_handoff: 3s lock timeout (Python handler invoked via hooks/adapters/claude-code/precompact-handoff.sh; writes .ll/ll-continue-prompt.md atomically after reading .ll/ll-precompact-state.json idempotency guard)
```

_Step 1 — `docs/guides/SESSION_HANDOFF.md:371` (Files table — insert after `.ll/ll-session-state.json` row):_
```
| `.ll/ll-precompact-state.json` | Idempotency guard written by `precompact.sh`; read by `precompact-handoff.sh` to prevent duplicate continuation-prompt writes |
```

_Step 1 — `docs/guides/SESSION_HANDOFF.md:495` (With Other Hooks — append after Stop hook bullet):_
```
- **PreCompact hook** (`precompact-handoff.sh`): Writes `.ll/ll-continue-prompt.md` passively before context compaction; use `/ll:resume` after compaction to re-inject the continuation prompt — passive counterpart to the active `/ll:handoff` command
```

_Step 11a — `docs/guides/BUILTIN_HOOKS_GUIDE.md:67` (Lifecycle table — insert after `precompact` row at line 67):_
```
| **PreCompact** | precompact-handoff | Writes session continuation prompt before compaction (passive path for `/ll:resume`) | — | on |
```

_Step 11c — `docs/guides/BUILTIN_HOOKS_GUIDE.md:89` (session narrative — insert after PostToolUse block, before `Session ends` at line 91):_
```

Context window fills up (Claude Code fires PreCompact before compacting)
  → PreCompact (precompact.sh): snapshots task state to .ll/ll-precompact-state.json
  → PreCompact (precompact-handoff.sh): reads state snapshot for idempotency, writes .ll/ll-continue-prompt.md; use /ll:resume after compaction to pick up work
```

_Step 11b — `docs/guides/BUILTIN_HOOKS_GUIDE.md:294` (PreCompact section — insert before `---` separator at line 296):_
```

**Hook:** `precompact-handoff.sh` → `little_loops.hooks.pre_compact_handoff.handle`

Fires as a second PreCompact handler, after `precompact.sh`. Reads `.ll/ll-precompact-state.json` as an idempotency guard (skips if no state snapshot was written by `precompact.sh`), then writes `.ll/ll-continue-prompt.md` atomically with a 3s advisory lock, returning **exit 2**:

> `[ll] Session continuation prompt written to .ll/ll-continue-prompt.md`

Use `/ll:resume` after compaction to re-inject the continuation prompt. Always on; passive counterpart to the active `/ll:handoff` command. See [Session Handoff](SESSION_HANDOFF.md).
```

_Step 12 — `docs/claude-code/write-a-hook.md:180` (Adapter files list — add `precompact-handoff.sh` after `precompact.sh`):_
```
Adapter files: `precompact.sh`, `precompact-handoff.sh`, `post-tool-use.sh`, `session-end.sh`, `session-start.sh`.
```

_Step 13 — `commands/handoff.md:239-244` (Integration section — append bullet; exact text per wiring pass):_
```
- PreCompact hook writes `.ll/ll-continue-prompt.md` automatically before context compaction (passive path); `/ll:handoff` is the active/richer manual override
```

_Step 10 — `skills/configure/areas.md:878` (hook audit table — insert after `precompact.sh` row):_
```
  [Plugin]   PreCompact        *              adapters/claude-code/precompact-handoff.sh  5s    [exists/MISSING]
```

**Test file entries to add (Steps 14-15):**

`scripts/tests/test_wiring_guides_and_meta.py` — insert 5 entries before closing `]` at line 203:
```python
    (
        "docs/ARCHITECTURE.md",
        "precompact-handoff.sh",
        "FEAT-1158",
    ),
    (
        "docs/development/TROUBLESHOOTING.md",
        "precompact-handoff.sh",
        "FEAT-1158",
    ),
    (
        "docs/guides/SESSION_HANDOFF.md",
        "precompact-handoff.sh",
        "FEAT-1158",
    ),
    (
        "docs/guides/BUILTIN_HOOKS_GUIDE.md",
        "precompact-handoff.sh",
        "FEAT-1158",
    ),
    (
        "docs/claude-code/write-a-hook.md",
        "precompact-handoff.sh",
        "FEAT-1158",
    ),
```

`scripts/tests/test_wiring_init_and_configure.py` — insert 1 entry after line 134 (`"hooks/adapters/"` entry):
```python
    ("skills/configure/areas.md", "adapters/claude-code/precompact-handoff.sh", "FEAT-1158"),
```

**Test coverage gap confirmed (both files at 0 FEAT-1158 entries as of 2026-06-17):**
- `scripts/tests/test_wiring_guides_and_meta.py` — 168-entry `DOC_STRINGS_PRESENT` list (lines 20-203); multi-line tuple format at lines 37-41; header count comment at line 19 must be bumped to 173
- `scripts/tests/test_wiring_init_and_configure.py` — 148-entry list (lines 20-177); single-line format at lines 133-134; header count comment must be bumped to 149

## Verification Notes

**Verdict**: VALID — Re-verified 2026-06-17

- All 15 documentation change sites confirmed still missing `precompact-handoff.sh` references ✓
- `ARCHITECTURE.md:86-90` adapter listing absent; `ARCHITECTURE.md:1105-1132` flowchart PostToolUse-only ✓
- `TROUBLESHOOTING.md:849` chmod block absent; lines 1058-1074 no `pre_compact_handoff` invocation block; line 1104 lock list absent ✓
- `SESSION_HANDOFF.md:365-371` Files table absent; lines 490-495 With Other Hooks absent ✓
- All implementation artifacts from FEAT-1156 confirmed present: `precompact-handoff.sh`, `pre_compact_handoff.py`, `hooks.json` registration ✓
- Both blockers (FEAT-1112, FEAT-1156) are now `done` — blockers cleared; issue `deferred` status may warrant re-evaluation

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-17 (re-check #8; both blockers confirmed done; Go/No-Go errors corrected by refine-issue; scores unchanged)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **Low test-coverage baseline** — 7 of 9+ change sites are documentation files with no automated unit tests; wiring test entries (steps 14–15) are the only doc-accuracy guard and are co-deliverables; implement tests first so each subsequent doc change is immediately gated by an automated presence check

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-06-17_ — **NO-GO (REFINE)**

**Deciding Factor**: The verbatim insert text for Step 3 (Mermaid diagram in `docs/ARCHITECTURE.md:1105-1132`) contains an architectural error — `PC_WRITE --> |/ll:resume| SPAWN` routes to the CLI Detection `SPAWN` node (representing `ll-auto`/`ll-parallel` fresh session spawning), but `/ll:resume` re-injects context in the current session. This is worse than the current omission and must be corrected before implementation.

### Key Arguments For
- Live, always-on hook (`precompact-handoff.sh`) has zero documentation coverage across 7 files; `BUILTIN_HOOKS_GUIDE.md:286-294` describes only `precompact.sh`, actively misleading readers about the dual-hook PreCompact behavior; both blockers confirmed done, competing issues deferred
- 13 of 15 change sites are pure additive insertions with no accuracy concerns; implementation plan is fully pre-computed with verbatim insert text at every site

### Key Arguments Against
- Step 3 Mermaid diagram replacement (`docs/ARCHITECTURE.md:1105-1132`) contains a confirmed architectural error: `PC_WRITE --> |/ll:resume| SPAWN` implies `/ll:resume` spawns a fresh session — `commands/resume.md` has zero references to "spawn" or "fresh session"; `/ll:resume` re-injects context in the current session
- `docs/ARCHITECTURE.md` adapter tree already lists only 3 of 6 adapter files; adding `precompact-handoff.sh` without adding `post-tool-use.sh` and `pre-tool-use.sh` leaves the tree still wrong with misleading appearance of completeness

### Rationale
The hook is live and undocumented across 15 verified locations, making implementation genuinely valuable. However, the proposed Mermaid flowchart replacement contains a confirmed architectural error and the adapter tree issue perpetuates an existing incompleteness gap. Both are refinable: correct the Mermaid diagram so `PC_WRITE` connects to a `/ll:resume`-in-session node (not the CLI spawn node), and expand the adapter tree scope to include `post-tool-use.sh` and `pre-tool-use.sh` alongside `precompact-handoff.sh`.

_Addressed by `/ll:refine-issue` on 2026-06-17:_
- **Step 2 fix**: Changed from single-line insert to full `claude-code/` block replacement with all 6 adapter files (`post-tool-use.sh`, `pre-tool-use.sh`, `precompact-handoff.sh`, `precompact.sh`, `session-end.sh`, `session-start.sh`) in alphabetical order. Confirmed via `ls hooks/adapters/claude-code/`.
- **Step 3 fix**: Replaced `PC_WRITE --> |/ll:resume| SPAWN` with a two-path diagram showing PreCompact as a separate "Passive Handoff Path" where `COMPACT → RESUME[/ll:resume re-injects context in current session]`. Confirmed: `commands/resume.md` contains zero references to "spawn" or "fresh session"; `/ll:resume` reads `.ll/ll-continue-prompt.md` and re-executes next steps in the current session turn.

## Session Log
- `/ll:ready-issue` - 2026-06-17T17:10:01 - `c71593f1-0d96-4ecc-b662-2a55426c32c3.jsonl`
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `bd900763-0b23-45ee-b17a-764082740a6e.jsonl`
- `/ll:wire-issue` - 2026-06-17T16:56:31 - `a27a16e0-4a9b-43f7-be41-8839fae042a6.jsonl`
- `/ll:refine-issue` - 2026-06-17T16:44:53 - `2654b6c8-3d42-4077-91e4-bc9e69441c9e.jsonl`
- `/ll:refine-issue` - 2026-06-17T16:32:52 - `b2ca9ab9-ae9a-445a-8889-96331c7bfcd4.jsonl`
- `/ll:go-no-go` - 2026-06-17T11:00:00Z - `3e014459-c03a-4d48-a488-7848dee02558.jsonl`
- `/ll:verify-issues` - 2026-06-17T15:48:21 - `3e014459-c03a-4d48-a488-7848dee02558.jsonl`
- `/ll:confidence-check` - 2026-06-17T15:30:00Z - `f7d8c3bf-5136-4a23-ab1a-2b6d85d3aff6.jsonl`
- `/ll:refine-issue` - 2026-06-17T15:07:05 - `956c3e6d-f1f2-45c5-b7a6-785dcd1a682f.jsonl`
- `/ll:confidence-check` - 2026-06-17T15:00:00Z - `ac6fa737-a322-42b5-8d7b-33d161c20fdb.jsonl`
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `e513b41c-6b52-45a2-9337-b97860e849e8.jsonl`
- `/ll:refine-issue` - 2026-06-17T14:10:33 - `0f016880-85bc-4bbe-99f8-02033fade9fb.jsonl`
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `b4e83fa1-ac6c-4881-a0f6-8e9ac33e4b65.jsonl`
- `/ll:refine-issue` - 2026-06-17T14:00:27 - `294a6e40-540e-468e-a590-e2a3425e134e.jsonl`
- `/ll:confidence-check` - 2026-06-17T14:00:00Z - `1e6e4626-ba64-460b-8cd7-3b31a567a30d.jsonl`
- `/ll:refine-issue` - 2026-06-17T13:51:12 - `f0515ea5-8fa5-41f9-b3b7-5de2abfc30fd.jsonl`
- `/ll:confidence-check` - 2026-06-17T00:00:00Z - `c5589c32-7fd0-47d2-befa-c0ce7b8d1ef4.jsonl`
- `/ll:wire-issue` - 2026-06-17T00:11:38 - `8d5b5e3d-ed9e-4e99-9628-47990c24c94a.jsonl`
- `/ll:decide-issue` - 2026-06-17T00:02:06 - `97cf2d3f-bfd7-4961-913e-a7776646b3aa.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `582fb982-6866-45ba-b90e-d2cfdc139ff2.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue edits `docs/ARCHITECTURE.md`, `docs/guides/SESSION_HANDOFF.md`, and `skills/configure/areas.md` for the precompact handoff feature. These same files are also modified by the session-start inject doc family: FEAT-1317 (`docs/ARCHITECTURE.md`), FEAT-1318 (`docs/guides/SESSION_HANDOFF.md`), FEAT-1319 (`skills/configure/areas.md`). No ordering dependency exists between these two doc families. If worked concurrently, coordinate to avoid git merge conflicts in these three shared files.

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-1262 (Session Event Capture Hook) also modifies `docs/ARCHITECTURE.md` (PostToolUse hook flow section) and `config-schema.json` (adds `session_capture` property). This issue touches `docs/ARCHITECTURE.md` at lines 85–98 and 888–955 and may touch `config-schema.json` if opt-in is chosen. No ordering dependency exists between FEAT-1158 and FEAT-1262. If worked concurrently, coordinate edits to these two shared files to avoid merge conflicts.
