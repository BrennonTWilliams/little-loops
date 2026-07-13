---
id: ENH-2623
title: Configurable history.db_path and unified DB-path resolution
type: ENH
priority: P3
status: open
discovered_date: 2026-07-12
captured_at: '2026-07-12T00:00:00Z'
discovered_by: capture-issue
decision_needed: false
relates_to:
- ENH-2581
labels:
- enhancement
- history-db
- config
- captured
confidence_score: 100
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 24
score_ambiguity: 24
score_change_surface: 21
---

# ENH-2623: Configurable history.db_path and unified DB-path resolution

## Summary

Add a first-class `history.db_path` key to `.ll/ll-config.json` (and
`config-schema.json`) so a project can persistently relocate its session
database, and reconcile the two divergent DB-path resolution functions in
`session_store.py` behind a single precedence chain:

```
LL_HISTORY_DB (env, ephemeral override)
  → history.db_path (config, persistent project setting)
    → .ll/history.db (default)
```

Today the only way to point the store at a non-default location is the
`LL_HISTORY_DB` environment variable — there is no config key at all. The env
var is the right tool for ephemeral/bootstrap/test-isolation overrides, but it is
the *wrong* tool for a persistent per-project choice (can't be checked in, easy to
forget to export). This ENH keeps the env var as the top-precedence override and
adds the missing middle rung.

## Motivation

- **No persistent config option.** `.ll/ll-config.json` has no `history.db_path`
  key, so relocating the DB (e.g. onto a faster/larger volume, or a shared path)
  requires exporting an env var in every shell/hook/subprocess — brittle and
  invisible to teammates reading the config.
- **Two resolution functions disagree.** `resolve_history_db()`
  (session_store.py) applies `LL_HISTORY_DB` **unconditionally**, while
  `ensure_db()` applies it **only when the path argument equals
  `DEFAULT_DB_PATH`**. Any caller that passes an explicit path to one and relies
  on the other gets a different file. This is not hypothetical: the initial
  `recompress_raw_events()` implementation used `resolve_history_db(db)` and
  opened the env-var DB instead of the explicit `db` argument it was handed,
  which surfaced as a test failure and was worked around by switching to
  `ensure_db(db)`. The divergence is a latent footgun for every future caller.

## Current Behavior

- Env var `LL_HISTORY_DB` is the sole non-default mechanism.
- `resolve_history_db(path)`: returns `Path(env)` if `LL_HISTORY_DB` set, else
  `path or DEFAULT_DB_PATH`. Env always wins, even over an explicit `path`.
- `ensure_db(path)`: only consults `LL_HISTORY_DB` when `path == DEFAULT_DB_PATH`;
  an explicit non-default `path` is used verbatim.
- `connect()` delegates to `ensure_db()`, so most read/write paths follow the
  "env-only-for-default" rule, but `resolve_history_db()` callers follow the
  "env-always" rule.
- No config schema entry references a DB path.

## Expected Behavior

- A single resolution helper implements the precedence chain above and is used by
  `ensure_db()`, `connect()`, and everywhere `resolve_history_db()` is currently
  called. `resolve_history_db()` either becomes that helper or delegates to it.
- `history.db_path` (string, optional; relative paths resolved against project
  root) is read from `.ll/ll-config.json` when the env var is absent.
- `LL_HISTORY_DB` continues to override config and default — no behavior change
  for tests, `ll-parallel`/`ll-auto` workers, or ephemeral redirects.
- Bootstrap safety preserved: a missing/malformed config must fall back to the
  default without raising in the early hook paths (`SessionStart`,
  `UserPromptSubmit`).

## Proposed Solution

1. Add `history.db_path` to `config-schema.json` (nullable string, documented as
   "override the default `.ll/history.db` location; the `LL_HISTORY_DB` env var
   takes precedence").
2. Introduce one resolver (extend `resolve_history_db()` to accept an optional
   already-loaded config, or add a thin `_resolve_db_path(path, config)` that it
   and `ensure_db()` both call). Config lookup must be best-effort and cheap, and
   must not run in the hottest bootstrap path if config isn't already available —
   fall through to default on any load error.
3. Route `ensure_db()` and any remaining `resolve_history_db()` call sites through
   the single resolver so explicit-path vs default-path callers agree.
4. Keep the env var as the unconditional top-precedence override.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation (Option A: resolver stays in `session_store.py`, no signatures
change — so these are behavior-verification + doc/test edits, not call-site
migrations):_

5. Update the stale comment at `session_store.py:2702` (`ensure_db(db)` —
   "resolves env-override-for-default") to describe default-shaped classification.
6. Re-verify env/config routing for the newly-surfaced default-shaped call sites:
   `user_messages.py:841`, `pytest_history_plugin.py:130`, `history_reader.py:259`
   (no code change expected; guard-fixture regression check).
7. Add the `db_path` schema assertion to `test_config_schema.py::test_history_in_schema`
   and `db_path` cases to `test_config.py` (`TestHistoryConfig`,
   `TestBRConfigHistoryIntegration`), mirroring
   `test_host_runner.py::TestApplyHostCliFromConfig`.
8. Re-run `test_session_store.py::TestCliEventContext` and
   `test_hook_session_start.py::TestSessionStartDbMigration` after the
   `cli_event_context`/`skill_event_context` gate collapse; update assertions only
   if behavior actually shifts.
9. Documentation: add the `history.db_path` row to
   `docs/guides/HISTORY_SESSION_GUIDE.md`, a companion note at
   `docs/reference/HOST_COMPATIBILITY.md:288`, and update the env-only/fixed-default
   phrasing at `docs/reference/API.md:745,7214`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-12.

**Selected**: Option A — default-shaped vs deliberate-override classification.

**Reasoning**: Codebase evidence shows the "default-shaped but cwd-absolute" path
pattern (`<root> / ".ll" / "history.db"`) appears at ≥13 production call sites
across 8 files — not just `session_start.py:122` — so Option B's "fix the call
sites" directive touches far more surface than the issue text names, and several
of those sites (`post_tool_use.py`, `user_prompt_submit.py`, `user_messages.py:841`)
aren't even in the Integration Map. Option A confines the change to
`session_store.py`, preserving every existing call site's env/config routing and
collapsing the four strict-equality workaround sites (`ensure_db`,
`cli_event_context`, `skill_event_context`, `SQLiteTransport`) into one resolver.
The existing `_isolate_history_db` fixture and
`test_cli_event_context_explicit_path_not_redirected` already validate Option A's
contract, whereas Option B's `_guard_real_history_db` safety net only trips when a
test happens to exercise a missed hook path without `LL_HISTORY_DB` set — most set
it, so a missed site would silently "work by accident."

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (shape classification) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B (strict equality + call-site fixes) | 2/3 | 1/3 | 1/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: Unifies purely inside `session_store.py`; the four existing strict-`==`
  sites (`session_store.py:780,1001,1065,1442`) generalize behavior-preservingly to
  one resolver; residual risk is only the new/undertested "override path that looks
  default-shaped" case.
- Option B: Reuses the already-4x-duplicated `== DEFAULT_DB_PATH` idiom but requires
  touching/re-verifying ≥13 production sites across 8 files; `DEFAULT_DB_PATH` is a
  *relative* literal that never equals the absolute paths those sites construct, so
  the gate is a silent no-op for them today and easy to under-fix.

## Acceptance Criteria

- [ ] `config-schema.json` gains a validated `history.db_path` field; a config
      with it set is accepted by schema validation.
- [ ] With `LL_HISTORY_DB` unset and `history.db_path` set, `connect()` /
      `ensure_db()` open the configured path.
- [ ] With `LL_HISTORY_DB` set, it wins over both config and default.
- [ ] With neither set, the default `.ll/history.db` is used.
- [ ] `resolve_history_db()` and `ensure_db()` return the same path for the same
      inputs (regression test for the current divergence).
- [ ] Malformed/absent config falls back to default without raising.
- [ ] `python -m pytest scripts/tests/` passes (this suite is CI; see CLAUDE.md).

## Scope Boundaries

**In scope:** the `history.db_path` config key, the schema entry, and unifying the
two DB-path resolution functions behind one precedence chain.

**Out of scope:** separating `raw_events` into its own physical DB file, WAL
checkpoint tuning, and decoupling `busy_timeout` from hook timeouts (the other
history.db performance items surfaced alongside the compression work). Migrating
an existing DB when `history.db_path` changes is also out of scope — the setting
applies to which file is opened, not to relocating existing data.

## Impact

- Files: `scripts/little_loops/session_store.py` (resolver unification),
  `config-schema.json`, `.ll/ll-config.json` (optional documentation of the key),
  config loading in `little_loops/config/`, and tests under
  `scripts/tests/test_session_store.py` / config tests.
- Low change surface; risk is concentrated in getting the precedence and
  bootstrap fallback exactly right, since every session touches DB resolution.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis._

### Files to Modify

- `scripts/little_loops/session_store.py` — the two resolvers and their gate:
  - `DEFAULT_DB_PATH = Path(".ll/history.db")` (line 97).
  - `resolve_history_db(path)` (lines 100–105) — **env unconditional**; returns
    `Path(env)` before `path` is ever consulted.
  - `ensure_db(path)` (lines 765–807) — env **only when** `db_path ==
    DEFAULT_DB_PATH` (guard at lines 780–783); also owns legacy `session.db →
    history.db` migration, `parent.mkdir`, and `_apply_migrations`.
  - `connect(path)` (lines 810–819) — delegates path resolution to
    `ensure_db(path)`; inherits the "only-when-default" rule.
  - **Two in-module workaround sites** that hand-roll the same gate and must be
    routed through the unified resolver:
    `cli_event_context()` line 1001 and `skill_event_context()` line 1065, both:
    `resolve_history_db(db_path) if Path(db_path) == DEFAULT_DB_PATH else Path(db_path)`.
- `scripts/little_loops/config-schema.json` — `history` section at
  ~lines 1687–1821, `"additionalProperties": false` (line ~1821). Adding
  `db_path` **requires** a new `properties.db_path` entry or schema validation
  rejects it.
- `scripts/little_loops/config/features.py` — `HistoryConfig` dataclass
  (lines 981–1016) and its `from_dict()` (lines 1000–1016); add a
  `db_path: str | None = None` field + `data.get("db_path")` line if the resolver
  reads through the typed config (see decision below).

### Dependent Files (Callers of `resolve_history_db()`)

- `scripts/little_loops/cli/logs.py:1434` — `resolve_history_db()` (no arg).
- `scripts/little_loops/cli/logs.py:1651` — `resolve_history_db(cwd_path / ".ll" / "history.db")`.
- `scripts/little_loops/cli/history.py:245,262,299,316` — `resolve_history_db(project_root / DEFAULT_DB_PATH)`.
- `scripts/little_loops/cli/issues/set_status.py:77` — `resolve_history_db()` (no arg).
- `scripts/little_loops/hooks/post_commit.py:97` — `resolve_history_db()` (no arg; no divergence risk).
- `scripts/little_loops/hooks/session_start.py:122` — `ensure_db(resolve_history_db(cwd / ".ll" / "history.db"))`.
  **Note:** this passes a *cwd-absolute* `.ll/history.db`, which is **not**
  `== DEFAULT_DB_PATH` (a relative `Path`). The current env-unconditional
  `resolve_history_db` is what keeps this call test-isolated under
  `LL_HISTORY_DB`; any unified rule must preserve env/config routing for this
  "default-shaped but absolute" path (see decision below).

_Wiring pass added by `/ll:wire-issue`:_
These are additional `resolve_history_db()`/`ensure_db()` call sites the refine
pass did not list. Under Option A **their signatures do not change** — each passes
a default-shaped path, so all must keep resolving through the env→config→default
chain (verify each still lands in the per-test tmp DB, or `_guard_real_history_db`
in `conftest.py` will trip):
- `scripts/little_loops/user_messages.py:841` — `resolve_history_db(project_folder / ".ll" / "history.db")`; passes a cwd-absolute *default-shaped* path (same class as `session_start.py:122`). Called out in the Decision Rationale as not in the original map. [Agent 1/2 finding]
- `scripts/little_loops/pytest_history_plugin.py:130` — `resolve_history_db()` (no arg; test-suite DB routing — regressions here fail the pytest history plugin). [Agent 1/2 finding]
- `scripts/little_loops/history_reader.py:259` — `ensure_db(db_path)` (imports `ensure_db` + `DEFAULT_DB_PATH` at line 55). [Agent 1/2 finding]
- `scripts/little_loops/session_store.py:2702` — internal `ensure_db(db)` call whose comment ("resolves env-override-for-default and creates schema") **goes stale** once the resolver uses default-shaped classification instead of strict `==`; update the comment. [Agent 2 finding]

_Not wiring gaps (recorded to prevent re-triage):_ the ~30 modules importing
`DEFAULT_DB_PATH` and `cli_event_context`/`skill_event_context` (e.g. every
`cli/*.py` entrypoint) surfaced by the caller trace do **not** change under
Option A — no signature migration, so they inherit the unified behavior for free.

### Config-load pattern to reuse

- `scripts/little_loops/config/core.py:110–133` — `resolve_config_path(project_root)`
  returns the `ll-config.json` path or `None` (host-aware; pure lookup, no
  side effects). Bootstrap hooks already load config best-effort with it:
  `session_start.py:92–98` and `user_prompt_submit.py:_load_config()` (lines
  50–58) both do `resolve_config_path(cwd)` → `json.loads(...)` wrapped in
  `try/except (OSError, json.JSONDecodeError)` → `{}`/`None` fallback. The
  resolver's config lookup should mirror this best-effort shape so
  malformed/absent config never raises in the hot bootstrap path.
- **No import cycle:** `config/core.py` and `config/features.py` contain no
  import of `session_store`; `session_store.py` already imports
  `little_loops.config.features` lazily *inside* function bodies
  (`write_file_event` line 853, `record_correction` line 886). A local/deferred
  import of the config helper inside the resolver is the established, cycle-safe
  pattern.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` — the "## Configuration" table (lines ~484–505) enumerates every `history.*` key and is the canonical user-facing doc for the namespace; **add a `history.db_path` row** describing the override + `LL_HISTORY_DB` precedence. [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:288` — the `LL_HISTORY_DB` row currently documents the env override as the *only* relocation mechanism; add a companion note that `history.db_path` config is the persistent alternative it takes precedence over. [Agent 2 finding]
- `docs/reference/API.md:745,7214` — `cli_event_context()` docstring ("Honors `LL_HISTORY_DB` env var…", line 745) and the module-level "Unified SQLite session store for `.ll/history.db`" line (7214) both describe the resolution as env-only/fixed-default; update to reflect the config rung. [Agent 2 finding]
- `.claude/CLAUDE.md` — the `ll-session` bullet documents `.ll/history.db` as the default DB but no config key; optional per issue scope, but mention `history.db_path` for discoverability. [Agent 2 finding]
- `skills/improve-claude-md/SKILL.md:209` — inline `db = resolve_history_db()` usage example; signature unchanged so no edit required — verify surrounding prose doesn't describe env-only semantics. [Agent 2 finding, fyi]

### Configuration precedent to reuse

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/host_runner.py:1189–1214` (`apply_host_cli_from_config`) is the codebase's established "env var overrides config key" pattern (`LL_HOST_CLI` > `orchestration.host_cli` > probe) — mirror its best-effort, no-op-on-missing-config shape for the `history.db_path` config rung. [Agent 3 finding]

### Tests

- `scripts/tests/test_session_store.py` — `TestEnsureDb` (lines 65–241) covers
  bootstrap/migration; add the divergence-regression case here.
- `scripts/tests/test_config.py` — `HistoryConfig.from_dict()` coverage.
- `scripts/tests/test_config_schema.py` — schema-validation coverage for the new
  `history.db_path` key.
- `scripts/tests/conftest.py:546–560` (`_isolate_history_db`) sets
  `LL_HISTORY_DB` per-test and `_guard_real_history_db` (564–604) asserts no open
  hits the real DB — any resolver change must keep env-routing intact or the
  whole suite trips the guard.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store.py` — `TestCliEventContext` (lines 1660–1737), specifically `test_cli_event_context_explicit_path_not_redirected` (1721) and `test_cli_event_context_respects_LL_HISTORY_DB` (1707): these pin the *current* divergent `cli_event_context` behavior. When lines 1001/1065 collapse to a plain `resolve_history_db(db_path)`, **re-verify both still pass** under Option A (explicit non-default path returns verbatim ⇒ should stay green; default path still env-routes). Update if the collapse changes any assertion. [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — `test_history_in_schema` (starts line 380): structural test enumerating `history.*` keys + `additionalProperties is False`. **Add a parallel `db_path` assertion** (type/nullable/default) in the existing per-key style. Closest env-override-key precedent: `test_orchestration_host_cli_in_schema` (line 608). [Agent 3 finding]
- `scripts/tests/test_config.py` — `TestHistoryConfig` (line 3175) and `TestBRConfigHistoryIntegration` (line 3251): add `db_path` cases following `test_flat_key_override`/`test_unknown_key_ignored`; the `apply_host_cli_from_config` test set (`test_host_runner.py::TestApplyHostCliFromConfig`, lines 1123–1174) is the four-case env>config>none>malformed template to mirror. [Agent 3 finding]
- `scripts/tests/test_hook_session_start.py` — `TestSessionStartDbMigration::test_migrates_legacy_session_db` (line 96) exercises `ensure_db(resolve_history_db(...))` (the legacy `session.db → history.db` migration branch); **re-run after unification** to confirm the migration still fires when fed a resolver-resolved path. [Agent 3 finding]

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis._

### Decision: how the explicit `path` argument interacts with env/config

The AC "`resolve_history_db()` and `ensure_db()` return the same path for the
same inputs" forces one unified rule for the divergent case (explicit
non-default `path` **and** `LL_HISTORY_DB` set). Two viable rules exist, and the
`session_start.py:122` call site (a cwd-*absolute* `.ll/history.db`) makes a
naive `== DEFAULT_DB_PATH` equality check insufficient:

**Option A**: Resolver classifies the passed path as *default-shaped* (None, or a
`history.db` under a `.ll/` directory — matched by basename+parent, not strict
equality) vs a *deliberate override* (any other path). Default-shaped → apply the
`env → config db_path → default` chain; deliberate override → return it verbatim.
Preserves env routing for `session_start.py:122`'s absolute default path **and**
honors an explicit tmp/override path (fixing the original `recompress` footgun).

**Option B**: Keep `ensure_db`'s strict `Path(path) == DEFAULT_DB_PATH` gate as
the single rule and make `resolve_history_db` adopt it; then change
`session_start.py:122` (and any other caller passing a cwd-absolute default) to
pass `DEFAULT_DB_PATH`/no arg so env still routes. Simpler resolver, but requires
touching call sites and re-verifying each doesn't rely on the absolute form.

> **Selected:** Option A (default-shaped classification) — unifies purely inside `session_store.py`, preserves all existing call-site behavior (env/config routing for the cwd-absolute default path), and confines risk to a single module.

**Recommended**: Option A — it unifies purely inside `session_store.py`, matches
the tested-correct `recompress` outcome (explicit path honored over env), keeps
every existing call site's behavior (including `session_start.py:122` env
routing), and lets the two in-module workaround sites (`cli_event_context:1001`,
`skill_event_context:1065`) collapse to a plain `resolve_history_db(db_path)`
call. Config `db_path` slots into the middle rung of the same chain.

### Guardrails for implementation

- Config `db_path` lookup must be best-effort (try/except → fall through to
  default), and relative paths resolve against project root per Expected
  Behavior. Reuse the `resolve_config_path` + guarded `json.loads` pattern above.
- `additionalProperties: false` on the `history` schema block means the schema
  entry is **mandatory**, not optional — omitting it makes any config setting
  `history.db_path` fail validation.
- Regression test must assert `resolve_history_db(p) == ensure_db(p)` for the
  matrix {default path, explicit non-default path} × {env set, env unset}.

## Sources

- Discovered during ENH follow-up to the `raw_events` payload-compression work
  (added `ll-session recompress`), where `resolve_history_db()` vs `ensure_db()`
  divergence caused a wrong-DB bug in `recompress_raw_events()`.
- `scripts/little_loops/session_store.py`: `resolve_history_db()`, `ensure_db()`,
  `connect()`.

## Status

open — captured 2026-07-12.


## Session Log
- `/ll:wire-issue` - 2026-07-13T04:57:09 - `2f51a319-6efc-4c4d-a6d6-6a058afd8d6d.jsonl`
- `/ll:decide-issue` - 2026-07-13T04:40:07 - `c34d2f4c-d3a4-4025-bc6a-2b899a5909ba.jsonl`
- `/ll:refine-issue` - 2026-07-13T04:35:08 - `753720b1-af3e-4b6a-8164-cfc206346927.jsonl`
