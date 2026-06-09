---
id: ENH-2040
title: "session_digest discoverability \u2014 flip global default on and wire into\
  \ init/configure"
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T03:43:41Z'
completed_at: '2026-06-09T13:37:42Z'
discovered_date: 2026-06-09
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- ENH-2028
- EPIC-1707
decision_needed: false
confidence_score: 94
outcome_confidence: 81
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2040: session_digest discoverability — flip global default on and wire into init/configure

## Summary

ENH-2028 (Option 2) fixed the dogfooding gap by enabling `session_digest` in this project's `.ll/ll-config.json`, but the global default remains `False` and there is no discovery path for users of other projects. This issue closes the discoverability gap by (1) flipping `SessionDigestConfig.enabled` to `True` as the global default (opt-out instead of opt-in) and (2) wiring a session_digest toggle prompt into `/ll:init` Phase 3 so users can make an informed choice at setup time.

## Motivation

The EPIC-1707 value proposition — "prior corrections, file edits, and tool-use patterns inform agent outputs without the user manually surfacing context" — only holds if users can actually discover the feature. With the global default off and no init prompt, the ambient session digest is effectively invisible: users who don't read `config-schema.json` or stumble on `/ll:configure history` never know it exists. FEAT-1743 established the pattern of wiring opt-in features into `/ll:init` for exactly this reason (learning-tests). This issue applies that pattern to session_digest.

## Current Behavior

- `SessionDigestConfig.enabled: bool = False` at `scripts/little_loops/config/features.py:661`.
- `session_start.py:170` gates the digest on `feature_enabled(merged_config, "history.session_digest.enabled")`, which returns `False` on missing keys regardless of the dataclass default — so the digest never fires on a fresh install even if the dataclass were changed alone.
- `/ll:init` (`skills/init/SKILL.md`) has no session_digest question — zero onboarding moment.
- `/ll:configure` already has a session_digest question at `skills/configure/areas.md:1312–1319`, but `configure` is a secondary surface reached only by users who already know the feature exists.

## Expected Behavior

### Global default flip

`SessionDigestConfig.enabled` defaults to `True` with `char_cap: 800` (conservative). Projects that want silence set `history.session_digest.enabled: false`.

`feature_enabled()` gate in `session_start.py:170` correctly reads the merged config default so that the digest fires on installs with no `history:` block.

### Init wizard addition (Phase 3)

```
? Enable ambient session digest? (Injects a capped history block at session start so 
  skills see recent corrections and file edits automatically.)
  > Yes — enable (800-char cap, 7-day window)  [default]
    No — disable (you can enable later with /ll:configure)
```

On **Yes** (or no answer — default): writes the block below to `.ll/ll-config.json` if not already present:
```json
"history": {
  "session_digest": {
    "enabled": true,
    "days": 7,
    "char_cap": 800
  }
}
```

On **No**: writes `"history": { "session_digest": { "enabled": false } }` so the opt-out is explicit and visible.

## Scope Boundaries

- **In scope**: Flip `SessionDigestConfig.enabled` default to `True` in `features.py:661`.
- **In scope**: Fix the `feature_enabled()` gate in `session_start.py:170` so it reads the merged config correctly when no `history:` block is present (the decoupling described in ENH-2028 decision rationale).
- **In scope**: Add a session_digest prompt to `/ll:init` Phase 3 (`skills/init/SKILL.md`), following the FEAT-1743 pattern.
- **In scope**: Update `config-schema.json` `history.session_digest.enabled` default annotation to `true`.
- **In scope**: Update tests in `scripts/tests/test_hook_session_start.py` (assert digest fires with no config) and `scripts/tests/test_config.py` (`TestSessionDigestConfig` near line 2751).
- **In scope**: Add CHANGELOG entry (behavior change — sessions that previously injected nothing will now inject a capped digest block; opt-out via `history.session_digest.enabled: false`).
- **Out of scope**: Changing digest content format or algorithm (ENH-1907).
- **Out of scope**: Modifying `/ll:configure` — the question already exists at `areas.md:1312`; no changes needed there.
- **Out of scope**: Changing `char_cap` algorithm or stale-filtering decay logic.

## Implementation Steps

1. **`scripts/little_loops/config/features.py:661`** — change `enabled: bool = False` to `enabled: bool = True`.
2. **`scripts/little_loops/config/features.py` `from_dict`** — verify `SessionDigestConfig.from_dict` defaults `enabled` to `True` when key is absent (check `data.get("enabled", True)`).
3. **`scripts/little_loops/hooks/session_start.py:170`** — audit the `feature_enabled()` call; if it short-circuits on missing keys before reading the dataclass default, replace with a direct attribute read (`merged_config.history.session_digest.enabled`) so the dataclass default is respected.
4. **`config-schema.json`** — update `history.session_digest.enabled` `"default": false` → `"default": true` and description to note opt-out behavior.
5. **`skills/init/SKILL.md`** — add session_digest prompt block to Phase 3, modeled on FEAT-1743's learning_tests block. Default answer = Yes.
6. **`scripts/tests/test_hook_session_start.py`** — update/add assertions that digest fires when config has no `history:` block and `SessionDigestConfig()` default is used.
7. **`scripts/tests/test_config.py`** — update `TestSessionDigestConfig` (near line 2751) to assert `SessionDigestConfig().enabled is True`.
8. **`CHANGELOG.md`** — add behavior-change entry: "Sessions on fresh installs now inject a capped ambient digest block (opt-out: `history.session_digest.enabled: false`)."

## Integration Map

### Files to Modify

- `scripts/little_loops/config/features.py` — `SessionDigestConfig.enabled` default (line 661) and `from_dict` default (verify `get("enabled", True)`)
- `scripts/little_loops/hooks/session_start.py` — gate expression at line 170
- `config-schema.json` — `history.session_digest.enabled` default annotation
- `skills/init/SKILL.md` — Phase 3 session_digest prompt block
- `CHANGELOG.md` — behavior-change migration note

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/session_start.py:170` — primary behavioral consumer; reads `history.session_digest.enabled` via `feature_enabled()`

### Similar Patterns

- `FEAT-1743` (done) — exact same shape: added `learning_tests.enabled` master flag and wired `/ll:init` Phase 3 prompt; diff that commit for the `/ll:init` edit pattern

### Tests

- `scripts/tests/test_hook_session_start.py` — assert digest fires with default `SessionDigestConfig()` (no project config)
- `scripts/tests/test_config.py` — `TestSessionDigestConfig` near line 2751: assert `.enabled` defaults to `True`

### Documentation

- `docs/reference/API.md` — update `SessionDigestConfig` default annotation for `enabled`

### Configuration

- `config-schema.json` — `history.session_digest.enabled` default value and description

## API / Interface Changes

- `SessionDigestConfig.enabled` default flips from `False` → `True`.
- `config-schema.json` default annotation updated.
- `/ll:init` gains a new Phase 3 question (additive, no existing answer changed).
- No CLI surface changes.

## Tests

- `scripts/tests/test_hook_session_start.py` — digest fires when no `history:` block is present in project config.
- `scripts/tests/test_config.py` — `SessionDigestConfig().enabled is True`.

## Impact

- **Priority**: P3 — Feature is usable but invisible; no user is blocked, but EPIC-1707's value proposition is undermined.
- **Effort**: Small-Medium — Three-point change (default flip + gate fix + init prompt) plus test/doc updates. Gate fix requires understanding the `feature_enabled()` decoupling from ENH-2028 decision rationale.
- **Risk**: Low-Medium — Global behavior change: every fresh install now injects a capped digest block at session start. The `char_cap: 800` limit is conservative, and opt-out is one config line. Users with automation that parses session output could be surprised.
- **Breaking Change**: Yes — observable behavior change. CHANGELOG entry required.

## Labels

`history`, `session-digest`, `config-defaults`, `dx`, `discoverability`, `init-wizard`

## Resolution

### Changes Made
- `scripts/little_loops/config/features.py` — `SessionDigestConfig.enabled` default flipped `False` → `True`; `char_cap` default updated `1200` → `800`; `from_dict` fallbacks updated to match
- `scripts/little_loops/hooks/session_start.py` — Gate replaced from `feature_enabled()` dict-walk to direct `SessionDigestConfig.enabled` attribute read so the dataclass default is respected when no `history:` block is present; unused `feature_enabled` import removed
- `config-schema.json` — `history.session_digest.enabled` default updated `false` → `true`; `char_cap` default updated `1200` → `800`; description notes opt-out behavior
- `skills/init/interactive.md` — Added Round 9.5 (Session Digest) between Round 9 and Round 10; `TOTAL` updated `10` → `11`
- `skills/init/SKILL.md` — Step 8 item 3 updated to include `history`/`session_digest` section; wizard description updated `9–10` → `10–11` rounds
- `scripts/tests/test_config.py` — Updated 3 test assertions for the new `enabled=True`, `char_cap=800` defaults
- `scripts/tests/test_hook_session_start.py` — Added `test_no_history_block_defaults_digest_on`
- `scripts/tests/test_wiring_init_and_configure.py` — Updated TOTAL/rounds anchors; added ENH-2040 wiring entries
- `CHANGELOG.md` — Added behavior-change entry for v1.120.0

## Session Log
- `/ll:manage-issue` - 2026-06-09T13:37:42Z - `fcb1b09c-f851-43f1-855e-3e9b29ba291d.jsonl`
- `/ll:ready-issue` - 2026-06-09T13:14:10 - `0b5a59fa-7cd3-45b2-b534-8436abcb7b56.jsonl`
- `/ll:capture-issue` - 2026-06-09T03:43:41Z - `43c168ba-0429-4c11-a637-5180d3e5a1ea.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `1924d461-8caf-443b-8d45-a63f048e04fa.jsonl`

---

**Open** | Created: 2026-06-09 | Priority: P3
