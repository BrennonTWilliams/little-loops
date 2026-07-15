---
id: BUG-2646
title: Extend decisions validation gates (PreToolUse, pre-commit, `ll-verify-decisions`)
  to the fragment path
type: BUG
status: done
priority: P2
parent: BUG-2642
discovered_date: '2026-07-15'
completed_at: '2026-07-15T15:31:31Z'
discovered_by: issue-size-review
confidence_score: 98
outcome_confidence: 83
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 20
---

# BUG-2646: Extend decisions validation gates to the fragment path

## Summary

Decomposed from BUG-2642 (Option A: append-only fragment files). Depends on
BUG-2644 (fragment storage layer) landing first. The three-tier decisions
validation gate (PreToolUse hook, pre-commit hook, `ll-verify-decisions`) is
keyed to the literal `.ll/decisions.yaml` path and a narrower exception
catch; once fragment writes exist under `.ll/decisions.d/`, they bypass
validation entirely unless each gate learns the new path and error type.
This is a genuinely separate subsystem (hooks + pre-commit config, not the
core read/write layer) and is independently testable, so it is split out
rather than folded into BUG-2644.

## Current Behavior

The three-tier decisions validation gate is keyed to the literal
`.ll/decisions.yaml` path:
- `ll-verify-decisions` (`verify_decisions.py:35,60`) validates only the flat
  file via `load_decisions()`, which **silently skips** malformed fragments
  (`decisions.py:40-59`) — so no exception escapes and the gate catches nothing
  for `.ll/decisions.d/*.json`.
- The PreToolUse shell hook (`check-decisions-yaml.sh:87`) only fires on
  Write/Edit to `.ll/decisions.yaml` exactly.
- The pre-commit hook (`.pre-commit-config.yaml:12`,
  `files: ^\.ll/decisions\.yaml$`) never matches fragment files.

Fragment writes under `.ll/decisions.d/` (introduced by BUG-2644) therefore
bypass all three validation tiers entirely.

## Expected Behavior

Each tier validates fragments as well as the flat file:
- `ll-verify-decisions` gains a **strict** fragment pass that iterates
  `.ll/decisions.d/*.json` (dir derived via `decisions._fragments_dir()`),
  parsing each strictly and returning exit 1 on the first malformed fragment —
  **not** routed through the swallowing `load_decisions()` path.
- The shell hook recognizes `.ll/decisions.d/*.json` and stages the candidate
  as a fragment.
- The pre-commit `files:` pattern matches fragment files.

## Impact

Corruption in fragment files (invalid JSON, missing `id`, unknown `type`) is
committable and mergeable without detection, silently defeating the governance
gate the three tiers exist to enforce. Since BUG-2644 has landed and
`.ll/decisions.d/` is live on disk, this gap is active now.

## Parent Issue

Decomposed from BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on
ARCHITECTURE-NNN id and block EPIC merges.

## Depends On

BUG-2644 must land first — these gates validate the fragment format that
BUG-2644 introduces.

## Scope

- `scripts/little_loops/cli/verify_decisions.py` — `_run()` (~line 60)
  currently catches only `(yaml.YAMLError, KeyError, ValueError)`; a
  directory-union reader over `.ll/decisions.d/*.json` must either normalize
  `json.JSONDecodeError` into a caught type or this except clause must
  broaden, or the three-tier gate silently stops catching malformed
  fragments. Also resolves `_DEFAULT_LOG_PATH` (~line 35) singularly — must
  validate the whole fragment directory.
- `hooks/scripts/check-decisions-yaml.sh` — path-match guard (~lines 80–89)
  only fires on Write/Edit to `.ll/decisions.yaml` exactly; add a second path
  pattern for `.ll/decisions.d/*.json` and a Write-only (no Edit diff)
  staging path for write-once fragments.
- `hooks/hooks.json` (~lines 57–61) — registers `check-decisions-yaml.sh` as
  the PreToolUse Write|Edit hook; widen the registration matcher to match the
  new path pattern.
- `.pre-commit-config.yaml` — `ll-verify-decisions` hook entry
  `files: ^\.ll/decisions\.yaml$` (~lines 8–12) won't match new fragment
  files; add `^\.ll/decisions\.d/.*\.json$` (or make the validator
  directory-aware) so fragments are validated pre-commit.

## Tests

- `scripts/tests/test_decisions_yaml_gate.py`,
  `scripts/tests/test_decisions_yaml_pre_commit_gate.py`,
  `scripts/tests/test_check_decisions_yaml_hook.py` — each currently keyed to
  the single-file `.ll/decisions.yaml` assumption; add cases for
  `.ll/decisions.d/*.json` writes (valid fragment passes, malformed fragment
  blocks).
- `scripts/tests/test_verify_decisions.py` — add a malformed-fragment case
  exercising the broadened/normalized exception handling in `_run()`.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:84` — exports `main_verify_decisions`
  in `__all__`; **no change needed** unless the entry-point signature changes
  (a new strict fragment pass should live inside `_run()`/`main_verify_decisions`,
  not alter its signature) [Agent 1 — FYI].
- `scripts/pyproject.toml:90` — `ll-verify-decisions` console-script maps to
  `little_loops.cli:main_verify_decisions`; **no change needed** (entry point
  is stable) [Agent 1 — FYI].
- `scripts/little_loops/decisions_sync.py` — imports `load_decisions()` and
  `_DEFAULT_LOG_PATH` from `decisions.py`; a **sibling consumer** of the same
  fragment-aware layer, **not** part of the validation gate. No change needed,
  but confirms `_DEFAULT_LOG_PATH`/fragment-dir derivation must stay backward
  compatible [Agent 1 — advisory].
- `scripts/little_loops/cli/issues/decisions.py` — the `ll-issues decisions`
  CRUD family calls `add_entry()`/`update_entry()` directly (the writers that
  emit fragments). Not a gate site; no change needed, but it is the *source*
  of the fragments the new strict pass will validate [Agent 2 — advisory].

### Scope boundary (docs/config → BUG-2647)

_Wiring pass added by `/ll:wire-issue`:_
Agent 2 surfaced documentation + config-schema + `.gitignore` couplings
(`docs/guides/DECISIONS_LOG_GUIDE.md` "three transport layers" section,
`docs/reference/CLI.md`, `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `CONTRIBUTING.md`,
`.claude/CLAUDE.md` CLI-tools line, `config-schema.json` `decisions.log_path`,
and the untracked `?? .ll/decisions.d/` in `.gitignore`). **These are owned by
sibling issue BUG-2647** (docs + config schema for fragment storage) — do NOT
duplicate them here. One cross-cutting caveat worth flagging in BUG-2647: the
pre-commit gate can only validate **staged/tracked** fragments, so whether
`.ll/decisions.d/*.json` is committed vs. gitignored materially affects whether
the pre-commit tier ever sees a fragment.

### Implementation contract (reuse, don't fork)

_Wiring pass added by `/ll:wire-issue`:_
- The new strict fragment pass in `verify_decisions.py` must derive the
  fragment directory via `decisions._fragments_dir(log_path)`
  (`log_path.with_suffix(".d")`, `decisions.py:30`) — **not** hardcode
  `.ll/decisions.d` — so a `config.decisions.log_path` override still resolves
  correctly (`_fragments_dir` is the shared derivation used by
  `load_decisions`/`save_decisions`/`add_entry`/`update_entry`) [Agent 2 §1].
- Reuse `decisions._entry_from_dict` for the strict per-fragment parse, but
  intentionally **do not** wrap it in `_load_fragments()`'s swallowing
  `except (json.JSONDecodeError, KeyError, ValueError, TypeError, OSError)`
  tuple — the whole point of the strict pass is to let those escape as exit 1
  [Agent 2 §1].

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (BUG-2644 fragment
storage has already landed; `.ll/decisions.d/` exists on disk):_

### ⚠ Critical correction to Scope bullet 1 (the validator gap)

The Scope premise — "broaden `_run()`'s `except (yaml.YAMLError, KeyError,
ValueError)` so it catches malformed fragments" — **will not work**.
`ll-verify-decisions` calls `load_decisions()`
(`scripts/little_loops/cli/verify_decisions.py:56,59`), and
`load_decisions()` **silently skips** malformed fragments rather than
raising:

- `scripts/little_loops/decisions.py:338` — `load_decisions` returns
  `legacy + _load_fragments(...)`.
- `scripts/little_loops/decisions.py:40-59` — `_load_fragments()` wraps each
  fragment parse in `except (json.JSONDecodeError, KeyError, ValueError,
  TypeError, OSError): continue` (line 58-59). Malformed fragments are
  swallowed by design (BUG-2644, docstring line 328-329: "malformed
  *fragments* are skipped").

So **no exception ever escapes `load_decisions()` for a bad fragment** — a
broadened `except` clause in `_run()` catches nothing. This is an MR-10-style
parse-swallow: the corruption class the gate is supposed to catch is
already suppressed upstream.

**Correct fix**: `verify_decisions.py` must gain a *strict* fragment pass
that does **not** go through `load_decisions()`. It should iterate
`.ll/decisions.d/*.json` and parse each fragment strictly
(`json.loads` + `_entry_from_dict`), returning exit 1 on the first
`json.JSONDecodeError` / `KeyError` / `ValueError` — mirroring the strict
handling `load_decisions()` still applies to the flat file. `_DEFAULT_LOG_PATH`
(`verify_decisions.py:35`) and `_resolve_log_path()` (line 38-46) resolve only
the flat file today; add a fragment-directory resolver (reuse
`decisions._fragments_dir()` at `decisions.py:30`).

### Correction to Scope bullet 3 (hooks.json)

`hooks/hooks.json:54` registers `check-decisions-yaml.sh` with a **tool-name**
matcher (`"matcher": "Write|Edit"`), **not** a path matcher. All path
filtering happens inside the shell script (`check-decisions-yaml.sh:87`). So
**no `hooks.json` change is needed** — the matcher already fires on every
Write/Edit. The path-widening work is entirely in the shell script (Scope
bullet 2).

### Scope bullet 2 (shell hook) — confirmed and detailed

- `hooks/scripts/check-decisions-yaml.sh:87-89` — the path guard accepts only
  `*/.ll/decisions.yaml` or the bare `.ll/decisions.yaml`; add a branch for
  `*/.ll/decisions.d/*.json` and `.ll/decisions.d/*.json`.
- Fragments are **write-once JSON** (`add_entry` →
  `atomic_write_json(frag_dir / f"{uuid.uuid4()}.json", ...)`,
  `decisions.py:374-375`). The hook's Edit-reconstruction branch
  (`check-decisions-yaml.sh:103-142`) is largely irrelevant for the append
  path — a fragment write is a `Write` of a full JSON doc, staged directly
  (lines 96-101). Note `update_entry()` (`decisions.py:383-407`) **does**
  rewrite an existing fragment via `atomic_write_json`, so Edit-style diffs
  against an existing fragment are possible but still land as Writes.
- The staged candidate is written to `$WORK_DIR/.ll/decisions.yaml`
  (line 94). For a fragment candidate it must instead be staged at
  `$WORK_DIR/.ll/decisions.d/<name>.json` so the (fragment-aware) validator
  invoked at line 176 sees it as a fragment, not a flat file.

### Scope bullet 4 (pre-commit) — confirmed

`.pre-commit-config.yaml:12` — `files: ^\.ll/decisions\.yaml$`. Add the
fragment pattern (single alternation): `files:
^\.ll/decisions(\.yaml|\.d/.*\.json)$`. `pass_filenames: false` (line 13)
means the validator is invoked path-agnostically, so it must self-discover
the fragment directory (see bullet 1 fix).

### Fragment format reference

Live example (`.ll/decisions.d/*.json`) is a single JSON object with `id`,
`type`, `timestamp`, `category`, `rationale`, `rule`, `scope`,
`alternatives_rejected`, `issue` — parsed by `_entry_from_dict`
(`decisions.py`, dispatch table line 309). A malformed fragment = invalid
JSON, or valid JSON missing `id` / with an unknown `type`.

### Tests — confirmed keying

- ⚠ **Correction (wiring pass):** the "3 hits each" claim below is wrong. A
  fresh grep confirms **all four** gate test files
  (`test_decisions_yaml_gate.py`, `test_verify_decisions.py`,
  `test_decisions_yaml_pre_commit_gate.py`, `test_check_decisions_yaml_hook.py`)
  have **0** references to `decisions.d`/`fragment` today [Agent 3]. **Every**
  fragment case in all four files is net-new; none is a partial extension.
- `test_decisions_yaml_gate.py`, `test_verify_decisions.py` — no fragment
  coverage yet; add a **malformed-fragment-blocks** case that proves the
  *strict* pass (Scope bullet 1), not the swallowing `load_decisions()` path.
- `test_decisions_yaml_pre_commit_gate.py`,
  `test_check_decisions_yaml_hook.py` — no fragment coverage yet; add
  valid-passes / malformed-blocks cases for `.ll/decisions.d/*.json`.

### Tests — models to follow & couplings to satisfy

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_decisions_fragments.py:78-85`
  (`TestDirectoryUnionRead::test_malformed_fragment_skipped`) — the **exact
  counterpoint** the strict pass must diverge from: it asserts a malformed
  fragment is *silently skipped* by `load_decisions()`. The new
  strict-fragment test must assert the opposite (non-zero exit) through
  `verify_decisions.py`. Reuse this file's `_write_fragment`/`_frag_dir`
  (`.with_suffix(".d")`) fixture shape [Agent 3].
- `scripts/tests/test_verify_decisions.py::TestMainVerifyDecisions` — model the
  new `TestMainVerifyDecisionsFragments` class on this: `patch("sys.argv", …)`,
  `_make_project(tmp_path)`, exit-code assertion paired with a `captured.err`
  substring check, plus a positive control (valid-fragment-passes) [Agent 3].
- `scripts/tests/test_decisions_yaml_gate.py::test_decisions_yaml_rejects_othe_203`
  — asserts `"decisions.yaml" in result.stderr.lower()`. A fragment-corruption
  error that names a `.json` fragment filename instead would **not** satisfy
  this substring; the new fragment case needs its own assertion (or the
  validator's error string must still mention `decisions.yaml`) [Agent 2 §4].
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py::_write_config`
  (lines 73-90) hardcodes the `files: ^\.ll/decisions\.yaml$` literal; once
  `.pre-commit-config.yaml`'s real regex is widened it becomes **stale
  relative to the real config** — update the fixture in lockstep. Mirror
  `_write_decisions` (lines 93-99) with a `_write_fragment` staging helper
  [Agent 2 §4 / Agent 3].
- `scripts/tests/test_check_decisions_yaml_hook.py` — mirror
  `_stage_clean_decisions`/`_invoke_hook` and the no-dependency path-guard test
  `test_hook_allows_non_target_path` (lines 249-270) with a
  `test_hook_recognizes_decisions_d_fragment_path` staging
  `.ll/decisions.d/<uuid>.json` [Agent 3].
- `test_decisions_fragments.py` will **not** break — `_fragments_dir`/
  `_load_fragments` are private and only reached indirectly; the strict pass is
  additive [Agent 3].

## Resolution

Extended all three decisions-validation tiers to the append-only fragment path
(`.ll/decisions.d/*.json`):

- **`ll-verify-decisions`** (`verify_decisions.py::_run`) gains a **strict**
  fragment pass after the flat-file `load_decisions()` check: it iterates
  `_fragments_dir(log_path)/*.json`, parsing each strictly via
  `_entry_from_dict` and returning exit 1 on the first `JSONDecodeError` /
  `KeyError` / `ValueError` — deliberately *not* routed through the swallowing
  `_load_fragments()` path that `load_decisions()` uses (the root-cause gap:
  malformed fragments were silently skipped).
- **Shell hook** (`check-decisions-yaml.sh`) recognizes fragment paths and
  stages a Write/Edit candidate under `$WORK_DIR/.ll/decisions.d/<name>.json`
  so the validator's fragment pass sees it as a fragment.
- **Pre-commit** `files:` pattern widened to
  `^\.ll/decisions(\.yaml|\.d/.*\.json)$`.
- `hooks.json` needed **no change** — its `Write|Edit` matcher is tool-name
  based; path filtering lives in the shell script.

Verified: full suite `14981 passed`, ruff + mypy clean.

## Status

**Done** | Created: 2026-07-15 | Completed: 2026-07-15 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-15T15:30:59 - `cf14e90b-d335-4198-933c-07300e5383ee.jsonl`
- `/ll:ready-issue` - 2026-07-15T15:19:11 - `3e704b5f-5224-43d4-b3c6-900efc27ebf4.jsonl`
- `/ll:wire-issue` - 2026-07-15T15:15:37 - `17469c20-89fd-4425-a82a-73a90dce3139.jsonl`
- `/ll:refine-issue` - 2026-07-15T15:09:24 - `71748b8a-0d20-481b-9f5a-9db58d73c12f.jsonl`
- `/ll:issue-size-review` - 2026-07-15T00:00:00 - `1e8c4ff4-aeb1-4a0e-ae31-59bf29c066dd.jsonl`
