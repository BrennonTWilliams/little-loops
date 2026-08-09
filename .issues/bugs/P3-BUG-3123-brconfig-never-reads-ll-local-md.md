---
id: BUG-3123
title: BRConfig never reads .ll/ll.local.md overrides
type: BUG
priority: P3
status: open
captured_at: '2026-08-08T21:48:47Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- config
relates_to:
- ENH-3113
verify_verdict: NON_VALID
size: Very Large
confidence_score: 95
outcome_confidence: 68
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
decision_needed: false
---

# BUG-3123: BRConfig never reads `.ll/ll.local.md` overrides

## Summary

`.ll/ll.local.md` overrides (e.g. `project.test_cmd`, `scan.focus_dirs`) are
only ever merged inside the SessionStart hook process. `BRConfig`, which every
`ll-*` CLI command constructs directly, never reads the file — so an override
declared in `ll.local.md` silently does not apply to actual command execution,
in the main tree as well as in a worktree.

## Current Behavior

`SessionStart` (`scripts/little_loops/hooks/session_start.py:136-147`) is the
only code that parses `.ll/ll.local.md`'s YAML frontmatter and merges it via
`deep_merge()` (`config/core.py:57-84`) on top of the base config. That merged
result (`merged_config`) is used only for two things inside that single hook
invocation: the hook's own internal `HistoryConfig`/feature-validation logic,
and the JSON printed to session-start stdout for host-CLI context display
(`session_start.py:239-246`). It is never written back to disk and never read
by anything else.

`BRConfig._load_config()` (`scripts/little_loops/config/core.py:229-240`)
loads only `resolve_config_path()`'s result (`.ll/ll-config.json` or a
root-level `ll-config.json`) — it has no knowledge of `.ll/ll.local.md` at
all. Every `ll-*` CLI entry point that constructs a `BRConfig` therefore reads
the un-overridden base config, regardless of what `ll.local.md` declares.

## Expected Behavior

An override declared in `.ll/ll.local.md` (e.g. `project.test_cmd`) is
honored by any code path that resolves config through `BRConfig`, not just by
the SessionStart hook's own internal logic and printed context.

## Motivation

`.ll/ll.local.md` exists specifically to hold per-machine settings that
shouldn't be committed (see `.claude/CLAUDE.md` § Local Settings Override,
which documents overriding `project.test_cmd` as the canonical example). If
`BRConfig` never actually applies that override, the documented feature is
silently a no-op for anything except the SessionStart hook's own narrow
internal use — a project can set `test_cmd` in `ll.local.md` and have every
`ll-*` command keep using the base value with no error or warning.

Discovered while running `/ll:confidence-check` on ENH-3113 (worktree
`ll.local.md` copy mechanics), which deliberately scopes this out —
EPIC-3111's stated scope is worktree copy semantics only, not `BRConfig`'s
override-resolution mechanism, so this is filed separately rather than folded
into that issue.

## Root Cause

`BRConfig._load_config()` (`scripts/little_loops/config/core.py:229-240`) was
never extended to read `.ll/ll.local.md`; only `hooks/session_start.py` was
given that logic, and its merge result is process-local (printed/consumed
in-hook, never persisted).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- `BRConfig.__init__()` (`scripts/little_loops/config/core.py:215`): resolves `project_root`, calls `load_env_fallback()` (a `.env` fallback, unrelated to `ll.local.md`), then `self._raw_config = self._load_config()` (line 226), then `self._parse_config()` (line 227) turns the raw dict into ~25 typed dataclass sections. There is no splice point between `_load_config()` returning and `_parse_config()` consuming — a `.ll/ll.local.md` merge would need to happen inside `_load_config()` itself, after the `json.load(f)` call at line ~236-238.
- `BRConfig._load_config()` (`scripts/little_loops/config/core.py:229-240`) body: calls `resolve_config_path(self.project_root)` then `json.load()`s that single file. Nothing in this method or its callee `resolve_config_path`/`_config_candidates` (lines 87-145) reads the local-override file today. A text search of `config/core.py` for any mention of the local-override filename turned up zero hits. The frontmatter parser and merge helper the fix needs (covered under Program Design below) live outside this file.
- `deep_merge()` (`config/core.py:57-84`) semantics: nested dicts merge recursively; all other types (str/int/bool/list) **replace**, arrays do not append; an explicit `None` in override **removes** the key (`result.pop(key, None)`); returns a new dict without mutating either input. Its own docstring notes this differs from `little_loops.fsm.fragments._deep_merge`, which does not treat `None` as a removal sentinel — two independently-declared deep-merge functions exist in this codebase for different subsystems.
- SessionStart hook's merge (`hooks/session_start.py`, `handle()` lines 86-147): reads `base_config` via its own independent `json.loads()` (not via a `BRConfig` instance — the hook never constructs one), then if `.ll/ll.local.md` exists, parses it with `_parse_frontmatter()` (line 62-83, full `yaml.safe_load`) and computes `merged_config = deep_merge(base_config, local_overrides)`. `merged_config` is used only for: (a) the hook's own `stdout_payload` (lines 238-256), (b) `HistoryConfig.from_dict(merged_config.get("history", {}))` (line 226), (c) `_validate_features(merged_config)` warnings (line 271) — all scoped to that single `handle()` invocation. Confirmed no other module imports `_parse_frontmatter` from `session_start.py` or feeds `ll.local.md`-sourced data into `deep_merge` anywhere else in the codebase.
- No caching layer exists around `BRConfig` construction: grep across `scripts/little_loops/**` for `@lru_cache`/`@cache`/module-level singletons wrapping `BRConfig(...)` found none — 36+ call sites (`cli/config.py:70`, `cli/parallel.py`, `cli/loop/__init__.py`, `cli/issues/__init__.py`, `fsm/executor.py`, `fsm/persistence.py`, `codequery/codegraph.py`, `learning_tests/gate.py`, `worktree_utils.py`, `parallel/orchestrator.py`, `parallel/priority_queue.py`, and others) each construct a fresh `BRConfig(project_root)` and re-run `_load_config()` from scratch. This resolves the Proposed Solution's staleness question: config is always read fresh on construction (no caching to worry about), it just never reads `ll.local.md` regardless of freshness — so read-once-at-construction is not just "likely sufficient," it is already how every other part of `_load_config()` behaves.

## Proposed Solution

Give `BRConfig._load_config()` a read path for `.ll/ll.local.md`, reusing the
existing `_parse_frontmatter()` (`session_start.py`) and `deep_merge()`
(`config/core.py:57-84`) helpers rather than duplicating the parsing logic.
Candidate approaches to weigh during implementation:

### Option A: Extract `_parse_frontmatter()` into `config/core.py`

> **Selected:** Option A — mechanical extraction of a dependency-free pure function, matching the established `deep_merge`/`resolve_config_path` promotion precedent already in this file.

Extract `_parse_frontmatter()` out of `hooks/session_start.py` into
`config/core.py` (or a shared module both import), then have
`BRConfig._load_config()` apply the same `deep_merge()` step the hook
already performs.

### Option B: Dedicated shared helper `BRConfig` calls into

Have `BRConfig` call into a shared `resolve_effective_config()` helper that
both the hook and `BRConfig` use, so the two consumers can't drift again.

Either approach should decide: is `ll.local.md` read once at `BRConfig`
construction time, or does staleness matter (e.g. `ll-issues decisions sync`
rewriting `## Active Rules` mid-run)? Given `BRConfig` instances are typically
short-lived (one per CLI invocation), read-once-at-construction is likely
sufficient.

### Decision Rationale

**Selected: Option A — Extract `_parse_frontmatter()` into `config/core.py`**

`_parse_frontmatter()` (`hooks/session_start.py:62-83`) is a dependency-free
pure function (`content: str -> dict[str, Any]`, uses only `yaml.safe_load`
and string ops) with no session-specific coupling, so extracting it into
`config/core.py` alongside `deep_merge()` — which it is always used
together with — is a mechanical move with no adaptation cost. It also
directly repeats a promotion this codebase has already done twice
(`deep_merge()` and `resolve_config_path()` were both promoted from
hook-adjacent logic into `config/core.py`, with `hooks/session_start.py:41`
importing them back), and matches a broader one-directional convention where
10+ hook/CLI modules already import config-parsing primitives from
`config.core` and `config.core` never imports from `hooks/`. Option B would
introduce a novel `resolve_effective_config()` helper that mostly wraps two
already-existing pieces (`_parse_frontmatter`, `deep_merge`) split across a
new module, adding a naming/placement decision and a new test file for no
functional gain over Option A.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 2 |
| Simplicity | 3 | 2 |
| Testability | 3 | 2 |
| Risk | 3 | 2 |
| **Total** | **12/12** | **8/12** |

Key evidence: `config/core.py:57-84` (`deep_merge`) and `:121-145`
(`resolve_config_path`) are prior promotions of hook-adjacent logic into
`config/core.py`, with `hooks/session_start.py:41` importing both back —
direct precedent for Option A. `_parse_frontmatter()`
(`hooks/session_start.py:62-83`) has no hook-only dependencies, confirming
the extraction is mechanical. Option B's precedent (`env_file.py`) was new
logic filling a genuine gap; here the parse and merge pieces already exist,
so a new `resolve_effective_config()` module would be mostly glue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- The two candidate approaches above have disagreeing codebase precedent rather than one clearly-established convention:
  - Precedent for Option A (extract into `config/core.py`, hook imports back): `deep_merge()` and `resolve_config_path()` already live in `config/core.py` and `hooks/session_start.py:41` imports both back from there — `deep_merge`'s docstring documents this as a prior promotion of hook-adjacent logic into `core.py`.
  - Precedent for Option B-style (dedicated module, `BRConfig` calls into it): `env_file.py` is its own module, and `BRConfig.__init__` (`config/core.py:222-225`) only calls into it (`load_env_fallback()`) rather than inlining its logic — its docstring states this shape explicitly ("wired into `BRConfig.__init__` so every CLI entry point ... picks it up uniformly").
  - Both patterns currently coexist in this codebase; neither is the sole convention. No `resolve_effective_config()`-named helper exists anywhere today, so that name (Option B) would be novel rather than following an existing convention.
  - `little_loops/frontmatter.py::parse_frontmatter` is not a viable substitute for either option — it's a key:value string-only subset parser, while `.ll/ll.local.md` needs full nested-YAML parsing, per both that module's and `_parse_frontmatter()`'s own docstrings.
- On the staleness question raised above: no caching layer exists around `BRConfig` construction anywhere in the codebase (checked all 36+ construction call sites for `@lru_cache`/singletons — none found), so config is already read fresh on every construction. Read-once-at-construction is therefore not just "likely sufficient" — it's how the rest of `_load_config()` already behaves, with no existing staleness-handling pattern to match against either way.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

- Broader duplication precedent (pattern-finder pass): the "hook bypasses `BRConfig` with its own private loader" symptom already flagged for `hooks/post_tool_use.py:144` and `hooks/user_prompt_submit.py:98` is not a two-file anomaly — it is a six-file family, all importing `resolve_config_path` directly and duplicating the same `json.load()`/error-handling shape rather than routing through `BRConfig`: `hooks/post_tool_use.py:40` (`_load_config`), `hooks/user_prompt_submit.py:55` (`_load_config`, byte-identical body to the previous), `hooks/drift_check.py:97` (`_throttle_days`, inlines `resolve_config_path()` + `json.load()`), `hooks/pre_compact.py:35` (`_load_rubric_config`), `hooks/learning_tests_gate.py:49` (`_load_lt_config`), `hooks/install_learning_gate.py:50` (`_load_lt_config`, a separate duplicate of the previous). None of these six paths read `.ll/ll.local.md` either, so none would pick up the override even after this issue's fix lands — same symptom class, out of this issue's fix scope (which targets `BRConfig._load_config()` only). By contrast, `hooks/sweep_stale_refs.py:167` does construct a real `BRConfig(project_root=cwd)`, so hooks are not uniform on this.
- Test-shape precedent for "does BRConfig pick up an additional source": `scripts/tests/test_env_file.py:83-97` (`TestBRConfigWiring::test_brconfig_init_loads_project_env`) remains the only existing test with this exact shape (construct `BRConfig(tmp_path)` directly, assert a second-source value took effect) — no sibling example exists elsewhere in the suite. A related but distinct shape exists at `scripts/tests/test_config.py:1361-1605`, which tests multi-source config *selection* (which single candidate file `resolve_config_path()` picks, e.g. `.codex/ll-config.json` vs `.ll/ll-config.json` based on `LL_HOOK_HOST`) rather than *merging* two sources together — worth distinguishing if using it as a template, since it tests `resolve_config_path()` in isolation, not `BRConfig` construction end-to-end.
- No third frontmatter/YAML-merge utility found beyond the two already documented in this issue (`hooks/session_start.py:62-83` `_parse_frontmatter()` and `little_loops/frontmatter.py::parse_frontmatter`) — confirms the existing claim that `_parse_frontmatter()` is the only full nested-YAML parser matching `.ll/ll.local.md`'s shape.

### Types
- N/A — no new data shape is introduced; the fix reuses the existing `dict[str, Any]` config shape both `BRConfig._raw_config` and `deep_merge()` already operate on.

### Signatures
- `BRConfig._load_config(self) -> dict[str, Any]` — current body (`scripts/little_loops/config/core.py:229-240`) calls `resolve_config_path(self.project_root)` then `json.load()`s that one file; this is the method a `.ll/ll.local.md` merge step must extend, after the existing `json.load()` and before the `dict` is returned to `__init__`.
- `deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]` — already implemented at `scripts/little_loops/config/core.py:57-84` with the exact merge semantics needed (nested-dict recursive merge, scalar/array replace, `None`-removes-key); no new merge logic needs writing, only a new call site.
- `_parse_frontmatter(content: str) -> dict[str, Any]` — the only existing full-YAML (`yaml.safe_load`) frontmatter parser matching `.ll/ll.local.md`'s shape, defined at `scripts/little_loops/hooks/session_start.py:62-83`; not interchangeable with `little_loops.frontmatter.parse_frontmatter`, which is a key:value string-only subset parser.
- `BRConfig.__init__(self, project_root: Path) -> None` — unchanged signature at `scripts/little_loops/config/core.py:215-227`; calls `_load_config()` at line 226, so any override merge lands transparently for all 36+ existing construction call sites with no signature change required.

### Call Path
`BRConfig(project_root)` -> `BRConfig.__init__` -> `BRConfig._load_config()` -> `resolve_config_path(project_root)` + `json.load(config_path)` -> **[new: read `.ll/ll.local.md` if present, parse via `_parse_frontmatter()` (extracted or reused), `deep_merge(base_dict, local_overrides)`]** -> returns merged `dict[str, Any]` -> `BRConfig._parse_config()` (unchanged, consumes the returned dict into typed sections)

Parallel existing path (must keep working unchanged): `hooks/session_start.py handle()` -> independent `json.loads()` of base config -> `_parse_frontmatter()` -> `deep_merge()` -> `merged_config` (hook-local, feeds `stdout_payload`/`HistoryConfig`/`_validate_features` only)

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold is introduced. This is a wiring fix that gives `BRConfig` a second config source using an already-implemented, already-tested merge function (`deep_merge`); it introduces no new classification or decision logic.

## Implementation Steps

1. Decide where the shared parse/merge logic lives (extract from
   `session_start.py` vs. new shared helper) so the hook and `BRConfig` share
   one implementation instead of drifting.
2. Wire `BRConfig._load_config()` to apply the override after loading the
   base config.
3. Confirm the SessionStart hook keeps working unchanged (it should now be
   able to delegate to the shared helper instead of its own inline parse).
4. Test: with a `.ll/ll.local.md` overriding `project.test_cmd`, assert a
   freshly constructed `BRConfig` returns the overridden value.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Model the new `BRConfig` + `ll.local.md` test after
  `test_env_file.py::TestBRConfigWiring::test_brconfig_init_loads_project_env`
  (`scripts/tests/test_env_file.py:83-97`), combined with the
  `_write_base()`/`_write_local()` staging helpers from
  `test_hook_session_start.py:113-119`.
- After landing the fix, spot-check `scripts/tests/test_config_cli.py:151`,
  `scripts/tests/test_prose_dep_sweep_gate.py:24`, and
  `scripts/tests/test_symbol_cli_claim_sweep.py:22` — these construct
  `BRConfig` against a real (non-temp) directory and are the only suite
  members that could be affected by a contributor's own local
  `.ll/ll.local.md`.
- Optionally add a one-line scope-broadening note to
  `docs/guides/BUILTIN_HOOKS_GUIDE.md` (§ SessionStart) once `BRConfig`
  applies the override universally, not just the hook.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/core.py` — `BRConfig._load_config()`
- `scripts/little_loops/hooks/session_start.py` — reuse point for the shared
  parse/merge logic

### Similar Patterns
- `hooks/session_start.py:136-147` — the existing (process-local) parse +
  `deep_merge()` logic to reuse/extract
- `scripts/little_loops/env_file.py` + `BRConfig.__init__`
  (`config/core.py:222-225`, `load_env_fallback(self.project_root)`) — the
  codebase's existing "dedicated module, `BRConfig` calls into it" precedent
  (Option B style); its test file's `TestBRConfigWiring` class
  (`scripts/tests/test_env_file.py:83-97`,
  `test_brconfig_init_loads_project_env`) is the closest existing template
  for the new wiring-level test this issue's Step 4 calls for. [Agent 3
  finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/sweep_stale_refs.py:167` — constructs
  `BRConfig(project_root=cwd)` for issue scanning; will start picking up
  `.ll/ll.local.md` overrides once this fix lands [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` (§ SessionStart, lines 135-150, 439)
  — currently describes the `.ll/ll.local.md` override merge as scoped to
  the SessionStart hook's own context injection; remains factually accurate
  after this fix but understates the new scope (now applied universally via
  `BRConfig`, not just by the hook) — candidate for a one-line addition
  noting every `ll-*` CLI command now also honors the override [Agent 2
  finding]

### Tests
- `scripts/tests/test_config.py` — new coverage for `BRConfig` + local
  override
- `scripts/tests/test_hook_session_start.py::TestSessionStartLocalOverrides`
  — existing coverage for the hook's own merge path, must keep passing

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_cli.py:151` — `test_every_to_dict_key_is_a_known_root`
  constructs `BRConfig(Path.cwd()).to_dict()` against the real process cwd
  (not an isolated temp dir), the one non-fixture-isolated `BRConfig`
  construction in the suite. Passes today (this checkout has no
  `.ll/ll.local.md`), but any contributor with a local override touching an
  unrecognized key could see this test's behavior shift once `BRConfig`
  merges it in — a fixture-isolation gap to be aware of, not a guaranteed
  break [Agent 3 finding]
- `scripts/tests/test_prose_dep_sweep_gate.py:24` and
  `scripts/tests/test_symbol_cli_claim_sweep.py:22` — both construct
  `BRConfig(_REPO_ROOT)` against this repo's real root rather than a temp
  dir; same real-cwd fixture-isolation category as
  `test_config_cli.py:151` above [Agent 1 / Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

### Additional Dependent Files (Callers/Importers) — code-graph confirmed
- **Correction (`/ll:verify-issues`, 2026-08-08):** `scripts/little_loops/hooks/post_tool_use.py:144` and `scripts/little_loops/hooks/user_prompt_submit.py:98` do **not** construct a `BRConfig`. Each calls its own private `_load_config(cwd)` helper (`post_tool_use.py:40`, `user_prompt_submit.py:55`) that calls `resolve_config_path()` + `json.load()` directly, bypassing `BRConfig` entirely. Both are therefore **out of scope** for this fix — they will keep silently ignoring `.ll/ll.local.md` after `BRConfig._load_config()` is patched, same symptom class as the other four hooks listed under Program Design § Codebase Research Findings (`drift_check.py`, `pre_compact.py`, `learning_tests_gate.py`, `install_learning_gate.py`).
- `scripts/little_loops/config/core.py:226` — `BRConfig.__init__` itself calls `_load_config()`, the method this fix modifies
- `scripts/little_loops/config/core.py:236` — `_load_config()`'s only callee today is `resolve_config_path()`; a merge step must be added after its `json.load()` result, not inside `resolve_config_path()`

### Conventions in Force
- Hook-adjacent logic has already been promoted into `config/core.py` once before: `deep_merge()` and `resolve_config_path()` both live in `config/core.py` (not under `hooks/`), and `hooks/session_start.py:41` imports them back (`from little_loops.config.core import deep_merge, resolve_config_path`) — `deep_merge`'s own docstring calls this a port of hook-adjacent bash logic. This is direct precedent for the issue's Option A (extract `_parse_frontmatter()` the same way). Evidence: `config/core.py:57-84`, `config/core.py:121-145`, `hooks/session_start.py:41`.
- A second, disagreeing precedent also exists for "additional config source read during `BRConfig` construction": `env_file.py` is its own dedicated module (not folded into `config/core.py`), and `BRConfig.__init__` (`config/core.py:222-225`) merely imports and calls into it (`load_env_fallback(self.project_root)`) — its docstring states this shape explicitly: "Wired into `BRConfig.__init__` so every CLI entry point ... picks it up uniformly." This is precedent for the issue's Option B style (a separate shared helper `BRConfig` calls into, logic not inlined into `core.py`). Evidence: `env_file.py` (whole file), `config/core.py:222-225`.
- These two precedents disagree on placement (inline-in-`core.py` vs. dedicated-module-called-from-`core.py`) and both currently coexist in this codebase — this is a genuine open convention question for whoever implements the fix, not a resolved one.
- `little_loops/frontmatter.py::parse_frontmatter` (lines 255-291) is the codebase's one general-purpose shared frontmatter parser, but its own docstring disclaims substitutability for this issue's needs: it's a key:value **subset** parser (`yaml.BaseLoader`, resolves every scalar to a string), while `.ll/ll.local.md` needs full nested-YAML parsing (`yaml.safe_load`) — the same distinction `session_start.py:62-69`'s `_parse_frontmatter()` docstring already makes. Reusing `frontmatter.py` instead of extracting `_parse_frontmatter()` is not a viable third option.
- No `resolve_effective_config()`-named (or `effective_config`-named) helper exists anywhere in `scripts/little_loops/` today — the issue's Option B name would be novel to this codebase, not an existing convention being followed.

### Tests — existing coverage, exact locations
- `scripts/tests/test_config.py::TestBRConfig` (class starts line 680): `test_load_config_from_file` (683), `test_load_config_without_file` (698), `test_project_name_defaults_to_directory_name` (708), `test_get_issue_dir` (717), `test_load_config_invalid_json_raises` (1272), `test_load_config_empty_file_raises` (1284) — black-box tests via `BRConfig(temp_project_dir)` construction, using the `temp_project_dir` fixture (`conftest.py:240-247`) and `sample_config` fixture (`conftest.py:300-351`). None of these stage a `.ll/ll.local.md` file (confirmed by grep — zero matches for `ll\.local|local_override|LOCAL_OVERRIDE` in `test_config.py`), consistent with `_load_config()` having no such code path today.
- `scripts/tests/test_config.py` `deep_merge` test group (from line 3317): scalar override (3321), key addition (3328), nested-dict merge (3335), array replace (3345), `None`-removes-key (3352), `None`-on-absent-key no-op (3359), dict-over-scalar replace (3366), non-mutation of inputs (3373) — this coverage of `deep_merge()`'s contract already exists and does not need duplicating; a new `BRConfig` + local-override test only needs to assert the merge happened, not re-verify merge semantics.
- `scripts/tests/test_hook_session_start.py::TestSessionStartLocalOverrides` (class starts line 112): `_write_base()`/`_write_local()` helpers (113, 117) stage `.ll/ll-config.json`/`.ll/ll.local.md`; `test_local_overrides_deep_merge` (121), `test_local_null_removes_key` (133), `test_local_array_replaces` (142), `test_empty_frontmatter_does_not_emit_overrides_line` (151). Uses a local `in_tmp` fixture that `monkeypatch.chdir`s into `tmp_path`, because `handle()` reads `Path.cwd()` internally rather than taking an explicit `project_root` argument — unlike `BRConfig`, which takes `project_root` directly (so a new `BRConfig` test does not need the chdir fixture, per `test_config.py`'s existing convention of passing `temp_project_dir` straight to the constructor).

## Verification Notes

_Added by `/ll:verify-issues` — 2026-08-08:_

Core claim re-verified and accurate: `BRConfig._load_config()`
(`scripts/little_loops/config/core.py:229-240`) still only calls
`resolve_config_path()` + `json.load()`, with no `.ll/ll.local.md` read path.
All cited line numbers for `config/core.py` and `hooks/session_start.py`
(deep_merge, `_parse_frontmatter`, `merged_config` usage) match current code
exactly, as do the referenced test locations in `test_config.py`,
`test_hook_session_start.py`, and `test_env_file.py`.

One inaccuracy in "Additional Dependent Files — code-graph confirmed":
`scripts/little_loops/hooks/post_tool_use.py:144` and
`scripts/little_loops/hooks/user_prompt_submit.py:98` do **not** construct a
`BRConfig`. Both call a local `_load_config(cwd)` helper (defined in each
file) that calls `resolve_config_path()` + `json.load()` directly, bypassing
`BRConfig` entirely — same symptom (no `ll.local.md` override), different
and separate code path that this issue's proposed fix (wiring the override
into `BRConfig._load_config()`) will **not** address for these two hooks.
`scripts/little_loops/hooks/sweep_stale_refs.py:167` remains an accurate
`BRConfig`-constructing dependent. Recommend correcting or removing the two
inaccurate bullets, and optionally noting the separate `_load_config()`
duplication in `post_tool_use.py`/`user_prompt_submit.py` as out of scope or
a follow-up.

Decisions log checked (`.ll/decisions.d/` present) — no active required
rules found; no `DECISIONS_VIOLATION`.

**Verdict: NEEDS_UPDATE**

## Impact

- **Priority**: P3 — real but narrow; most projects don't heavily override
  config, and the failure mode (falls back to base config) is silent rather
  than destructive
- **Effort**: Medium — touches the shared config-loading core used by every
  `ll-*` invocation, not a single call site
- **Risk**: Low-Medium — behavior change is additive (previously-ignored
  overrides now apply), but `BRConfig._load_config()` is on the hot path for
  every CLI command
- **Breaking Change**: No — but any project whose `ll.local.md` currently sets
  an override that was silently ignored will see a behavior change once this
  ships

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 87/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 61/100 → MODERATE

### Concerns
- The shared-logic placement decision (extract `_parse_frontmatter()` into `config/core.py` vs. a dedicated module `BRConfig` calls into) is left open with disagreeing precedent — pick one before starting rather than during, to avoid churn.
- `BRConfig._load_config()` runs on every `ll-*` invocation; this is a hot-path, high-fan-in change (36+ construction call sites). Low behavioral risk (additive), but worth a focused review pass given the surface.
- Six other hook files (`post_tool_use.py`, `user_prompt_submit.py`, `drift_check.py`, `pre_compact.py`, `learning_tests_gate.py`, `install_learning_gate.py`) bypass `BRConfig` entirely with their own private loaders and will **not** pick up this fix — already correctly scoped out, but worth confirming that stays out of scope during implementation.

### Outcome Risk Factors
- Wide blast radius across 36+ `BRConfig` construction sites (broad enumeration across many sites) — mitigate with the fixture-isolation spot-checks already called out in the Wiring Phase (`test_config_cli.py:151`, `test_prose_dep_sweep_gate.py:24`, `test_symbol_cli_claim_sweep.py:22`) before merging.
- Unresolved placement decision could cause a mid-implementation restructure if the wrong option is picked first — resolve it as step 1, not as an afterthought.

## Session Log
- `/ll:confidence-check` - 2026-08-09T02:01:26 - `f1785c27-b4f6-4573-8ba2-1d0ff00ab817.jsonl`
- `/ll:decide-issue` - 2026-08-09T01:58:12 - `840d159c-6706-4ca5-b9a4-0207d99c09e6.jsonl`
- `/ll:confidence-check` - 2026-08-09T01:48:26 - `e99fadf0-4a73-439a-8b6e-81b9493d2612.jsonl`
- `/ll:refine-issue` - 2026-08-09T01:36:13 - `9f4add69-c20c-4e14-b64b-e236e6709d09.jsonl`
- `/ll:verify-issues` - 2026-08-09T01:32:37 - `4c1a0ff4-9eed-42d1-b58f-7e33f9ed46d5.jsonl`
- `/ll:wire-issue` - 2026-08-09T01:30:20 - `a82c515c-11f6-4fe3-8daf-17998535585d.jsonl`
- `/ll:refine-issue` - 2026-08-09T01:20:30 - `b89152fd-e021-4e4a-82d7-aab9fcc70ffc.jsonl`
- `/ll:capture-issue` - 2026-08-08T21:49:28 - `d7b6c474-eeb6-4901-9ffd-be8f7cc9a06c.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P3
