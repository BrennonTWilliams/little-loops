---
id: ENH-2434
title: ll-init defaults should be sourced from config-schema.json instead of hardcoded
  literals
type: enh
priority: P2
status: open
captured_at: '2026-07-02T01:05:48Z'
discovered_date: '2026-07-02'
discovered_by: capture-issue
decision_needed: false
labels:
- init
- config
- config-schema
relates_to:
- BUG-2321
- ENH-2298
- ENH-651
confidence_score: 100
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 23
score_ambiguity: 20
score_change_surface: 22
---

# ENH-2434: ll-init defaults should be sourced from config-schema.json instead of hardcoded literals

## Summary

`build_config()` in `scripts/little_loops/init/core.py` writes default values for
`.ll/ll-config.json` as hardcoded Python literals (e.g. `"days": 7`,
`"clear": True`, `"show_diagrams": "clean"`), while `config-schema.json`
independently declares a `default:` for the same keys (234 `default` entries
across the schema). The two are never reconciled programmatically, so nothing
prevents them from silently disagreeing.

This has already caused two closed bugs from the same root cause:
- **ENH-2298**: `core.py` wrote `history.session_digest.char_cap: 1200` while
  `config-schema.json` and `docs/reference/CONFIGURATION.md` said `800`.
- **BUG-2321**: `prompt_optimization` defaulted to enabled in the schema/docs,
  but `core.py` only wrote the block on opt-out, so a standard install shipped
  with no block and the feature was silently off.

Both were fixed as one-off value corrections. The underlying mechanism — two
independent sources of truth for the same default — is untouched, so the same
class of drift will recur for any of the other ~230 defaulted keys whenever one
side is edited without the other.

## Current Behavior

`build_config()` (`scripts/little_loops/init/core.py:44-151`) constructs the
generated config from inline literals and `choices.get(key, <hardcoded literal>)`
calls, e.g.:

```python
config["history"] = {
    "session_digest": {
        "enabled": session_digest_enabled,
        "days": 7,
    }
}
...
config["loops"] = {
    "run_defaults": {
        "clear": loop_clear,
        "show_diagrams": loop_show_diagrams,
    }
}
```

`config-schema.json` declares its own `default` for the same paths
(`history.session_digest.days`, `loops.run_defaults.clear`,
`loops.run_defaults.show_diagrams`, etc.), used only for runtime `jsonschema`
validation — `build_config()` never reads it. There is no test or lint that
fails when a literal in `core.py` diverges from the matching schema `default`.

## Expected Behavior

`build_config()` derives its baseline default values from `config-schema.json`
(e.g. via a small helper that walks `properties.*.default` for the keys it
emits), with `choices` overrides layered on top as they are today. A schema
default change automatically flows into newly generated configs, and adding a
guardrail (test or `ll-verify-*` CLI) that fails when a `core.py` literal
disagrees with the corresponding schema default closes off this class of bug
without requiring another one-off capture-issue per drifted key.

## Motivation

Two real, user-facing bugs (ENH-2298, BUG-2321) have already shipped from this
exact drift pattern, and `config-schema.json` documents ~230 other default
values `core.py` doesn't touch — any one of them can silently diverge the same
way, with no test catching it until a user notices the mismatch. Fixing the
mechanism once is cheaper than continuing to fix instances as they're
reported.

## Proposed Solution

1. Add a helper in `scripts/little_loops/init/core.py` (or a shared
   `config/schema_defaults.py`) that loads `config-schema.json` and extracts
   the `default` value at a given dotted path (e.g.
   `schema_default("history.session_digest.days")`).
2. Replace the hardcoded literals in `build_config()` (`char_cap`/`days: 7`,
   `loop_clear_default: True`, `loop_show_diagrams_default: "clean"`,
   `_DEFAULT_ANALYTICS_CAPTURE`, etc.) with calls to this helper, keeping
   `choices.get(...)` as the override layer.
3. Add a regression test (in `scripts/tests/test_init_core.py`) that asserts,
   for every key `build_config()` emits without a `choices` override, the
   emitted value equals `config-schema.json`'s declared default — so any future
   edit to one side without the other fails `python -m pytest scripts/tests/`.
4. Where `core.py` intentionally deviates from the schema default (if any
   legitimate cases exist), document the exception inline rather than leaving
   it as silent drift.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-02.

**Selected**: Option 2 — Align schema and `core.py` (schema-wins direction).

**Reasoning**: Three independent sources already agree on the schema-wins values: `config-schema.json` (`loops.run_defaults.clear: false` @ `:925`, `show_diagrams: null` @ `:931`, `analytics.enabled: false` @ `:1569`), the runtime `BRConfig` dataclass (`LoopRunDefaults.clear: bool = False`, `show_diagrams: str | None = None` in `scripts/little_loops/config/features.py:615-616`), and `docs/reference/CONFIGURATION.md:873-874` (`clear | boolean | false`, `show_diagrams | string|null | null`). Only `core.py` literals diverge. `deep_merge` (`scripts/little_loops/config/core.py:45-72`) lets `merge_with_existing` preserve existing user values on re-init, so schema-wins is a forward-only change — fresh inits emit schema-aligned values; existing configs keep their customizations. The codebase's documented "single source of truth" rule (`.ll/decisions.yaml:3355`) and ENH-2298's prior decision to align (rather than allow-list) the same drift class both favor this direction.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A: Allow-list | 1 | 2 | 2 | 1 | 6/12 |
| **B: Align schema-wins** | **3** | **2** | **3** | **1** | **9/12** |
| C: x-init-default | 1 | 0 | 1 | 0 | 2/12 |

**Key evidence**:
- **Option A (Allow-list)**: No existing allow-list utility for config defaults; contradicts the documented "single source of truth" rule and ENH-2298's prior "align all sources" decision; does not address the third drift source (`BRConfig` dataclass) which still disagrees with whichever side "wins"; 5 tests still need updating regardless. Reuse score 1/3 — only the `# --- <section> ---` banner comment style is reusable.
- **Option B (Align schema-wins)**: Three sources already agree; `deep_merge` handles migration safely; CLI readers in `scripts/little_loops/cli/loop/__init__.py:807-811` already handle `show_diagrams is None` cleanly; ENH-2243 conflict is documented and reopenable. Reuse score 1/3 — no existing `schema_default()` helper, but `feature_enabled()` (`features.py:14-35`) and `_scanner()` (`test_init_core.py:614-640`) provide the dotted-walk and report-all-disagreements shape.
- **Option C (x-init-default)**: No `x-` extensions anywhere in `config-schema.json`; no `jsonschema` runtime dependency; the schema has 234 `default:` entries that would each need editing; issue's scope boundaries explicitly exclude schema design changes; parity test would still fail on day one without one of options A/B/C. Reuse score 1/3 — structural-assertion test pattern generalizes, but no library support and no precedent.

**Implementation note**: The implementer should also (a) update the 5 tests that pin current literals in lockstep (`test_init_core.py:499-505`, `:522-542`, `test_init_e2e.py:66-67`, `test_loop_cli_defaults.py:58-74`), (b) update `scripts/little_loops/init/tui.py:633-634` to mirror schema-aligned defaults (or scope the parity test to `build_config()` with empty `choices`), and (c) document the ENH-2243 default change as an intentional departure — schema-wins reverts the recommendation that ENH-2243 made.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/core.py` — `build_config()`, replace hardcoded literals with schema-sourced defaults
- `config-schema.json` — no change expected, becomes the single source of truth

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/writers.py` — `merge_with_existing()` merges `build_config()` output; unaffected by this change but worth re-running its tests
- `scripts/little_loops/init/tui.py` (if present) — any TUI defaults mirroring `core.py` literals

### Similar Patterns
- Search for other modules hardcoding a value that also appears as a schema `default` (e.g. `history_reader.py:char_cap=1200` per ENH-2298) — candidates for the same helper

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (no removals; additive only):_

- **Verified anchors**: `scripts/little_loops/init/core.py:44-151` resolves to `build_config()`; `scripts/little_loops/init/core.py:13` resolves to `_DEFAULT_ANALYTICS_CAPTURE`; `scripts/tests/test_init_core.py:1368` test assertion still resolves; `scripts/little_loops/init/core.py:101` is the use-site for `_DEFAULT_ANALYTICS_CAPTURE` inside `build_config()` (analytics branch).
- **Sibling literal not in current Similar Patterns**: `scripts/little_loops/config/features.py:808` also defines `char_cap: int = 1200` — a third occurrence of the same hardcoded default that this issue's scope explicitly excludes ("separate follow-ups"). Recording here as additional evidence for the broader pattern; do NOT migrate in this issue's diff.
- **No existing schema-default helper**: `scripts/little_loops/init/core.py` is the only Python module under `scripts/` that consumes `config-schema.json` directly (search for `jsonschema` / `config-schema.json` returns a single hit). The proposed `schema_default(dotted_path)` helper is genuinely new — there is no existing pattern to reuse.
- **`merge_with_existing()` interaction**: `scripts/little_loops/init/writers.py:merge_with_existing()` operates on `build_config()`'s output via `strip_none_leaves()` (`core.py:21-41`, already in place per BUG-2311). Schema-sourcing the baseline is additive to that pipeline; the merge semantics do not change.
- **TUI parity check**: `scripts/little_loops/init/tui.py` exists. The parity test's parametrize should include both the headless `build_config()` path and any TUI emission path so a future drift in tui.py literals also fails CI (current scope keeps tui.py out of the diff but inside the test surface).
- **TUI mirrors `core.py` literals**: `scripts/little_loops/init/tui.py:634` declares `loop_show_diagrams_default: str | None = "clean"` and `:31` declares a `_DEFAULT_FEATURES` frozenset that mirrors the same literals. Both live alongside `build_config()` callers at `:637-639`. The parity test must include both code paths (per the analyzer's request) but migration can leave tui.py untouched per the issue's out-of-scope boundary — as long as a guardrail includes tui.py in the walker.
- **Six CLI readers touch the `show_diagrams` literal**: `scripts/little_loops/cli/loop/_helpers.py`, `cli/loop/info.py`, `cli/loop/diagram_modes.py`, `cli/loop/__init__.py`, `cli/loop/next_loop.py`, `cli/loop/lifecycle.py`. These are *readers* of `loops.run_defaults.show_diagrams`, not emitters — flag them so an implementer doesn't accidentally treat them as drift sources.
- **Other init module callers of `build_config`**: `scripts/little_loops/init/cli.py:225,387,453,461` (function-local imports). Worth re-running end-to-end tests after the refactor.
- **Existing test discipline that pins the literals**: `scripts/tests/test_init_core.py:499-505` (asserts `days == 7` and `"char_cap" not in sd`) and `:522-542` (asserts `clear is True` and `show_diagrams == "clean"`) are *the* tests that will fail if the parity test asserts schema=core.py. They confirm the design intent but lock in the current literal values — the parity test must align with them, OR they must be re-baselined (decision deferred; see Critical Finding below).
- **`pyproject.toml` and CLI registration**: `scripts/pyproject.toml:51-91` registers `ll-init` and the existing `ll-verify-*` CLIs. Any new `ll-verify-init-defaults` CLI would slot in here, and `scripts/little_loops/cli/__init__.py:81-83` is the corresponding `main_verify_*` re-export site. `scripts/little_loops/session_store.py:DEFAULT_DB_PATH` / `cli_event_context()` is the wrapping convention every `ll-verify-*` uses for telemetry.
- **Documentation drift surface**: `docs/reference/CONFIGURATION.md:565-566,603-604,874`; `docs/reference/CLI.md:45,2268`; `docs/reference/API.md:6659,6679,6692`; `docs/guides/HISTORY_SESSION_GUIDE.md:417-418`; `docs/guides/LOOPS_GUIDE.md:522`; `docs/guides/BUILTIN_HOOKS_GUIDE.md:138`. The issue already scopes doc sync as out-of-scope (`docs/reference/CONFIGURATION.md` spot-check only), but the implementer should be aware these are parallel sources of the same defaults and could drift again.

### Codebase Research Findings (locator critical-gaps pass)

_Added by `/ll:refine-issue` — based on locator agent. Two **LIVE** drifts exist right now between `core.py` literals and `config-schema.json` defaults that the proposed parity test would immediately catch as failures. The issue currently doesn't surface them:_

| `build_config()` key | `config-schema.json` default | `core.py` literal | Drift? |
|---------------------|------------------------------|-------------------|--------|
| `history.session_digest.enabled` | `true` (line 1669) | `choices.get("session_digest_enabled", True)` | no |
| `history.session_digest.days` | `7` (line 1674) | `"days": 7` (line 137) | no |
| `history.session_digest.char_cap` | `1200` (line 1679) | key never emitted (intentional — test asserts `"char_cap" not in sd`) | (skipped) |
| **`loops.run_defaults.clear`** | **`false` (line 925)** | `loop_clear = bool(choices.get("loop_clear_default", True))` (line 142) → **emits `True`** | **YES** |
| **`loops.run_defaults.show_diagrams`** | **`null` (line 931)** | `loop_show_diagrams = choices.get("loop_show_diagrams_default", "clean")` (line 143) → **emits `"clean"`** | **YES** |

The two live drifts are most plausibly **intentional**: the schema default is the *uninitialized* state ("what happens if `.ll/ll-config.json` is absent"), while the `core.py` literal is the *post-init* state ("what init writes into a fresh project"). Functionally these are two different semantics for the same key — they aren't a replay of ENH-2298 or BUG-2321.

**Required decision (record as a sub-task on this issue):** the parity test as written in the issue's Proposed Solution step 3 must either:
1. Treat these two keys as **explicit allow-list** with an inline `"deviates-by-design: schema default = uninitialized; init literal = post-init overwrite"` comment near each `build_config()` site, OR
2. Bring the schema and `core.py` into alignment (decide which is canonical, propagate to the other), OR
3. Add a third tier (`x-init-default` or `x-emit-default` JSON-schema field) to make the dual-default intent explicit — this falls under the issue's out-of-scope "Schema design changes" boundary so doing it requires decomposing the issue or filing a follow-up.

> **Selected:** Option 2 (Align schema-wins) — `config-schema.json`, the `BRConfig` runtime dataclass (`features.py:615-616`), and `docs/reference/CONFIGURATION.md:873-874` already agree; only `core.py` literals diverge, so schema-wins collapses to a single source of truth while `deep_merge` preserves existing user values on re-init.

Without picking one, the parity test will fail on day-one of implementation even when the refactor is otherwise correct. The two existing tests at `test_init_core.py:499-505` and `:522-542` will need updating in lockstep with whichever schema-vs-literal alignment is chosen (they currently lock in the literals, not the schema defaults).

### Codebase Research Findings (analyzer critical-additions pass)

_Added by `/ll:refine-issue` — based on analyzer agent. Adds a third drift the locator pass missed, plus structural facts about `_run_apply`, `BRConfig`, and `merge_with_existing` that change how the parity test can be written:_

- **Third live drift found: `analytics.enabled`** — `config-schema.json:1569` declares `analytics.enabled` `default: false` with description *"Default off; opt-in until the ctx-stats CLI ships"* (line 1570). `scripts/little_loops/init/core.py:100` emits `analytics.enabled = True`. The schema-default description frames `false` as the *intended* value; the init literal flips it to `True` for early-adopter projects. This is the strongest "schema-wins" candidate of the three drifts — the schema even documents *why* it's off. **The implementer should treat `analytics.enabled` as the third entry in the alignment decision alongside the two `loops.run_defaults.*` drifts above.**
- **`_run_apply()` does NOT call `build_config()`** — `scripts/little_loops/init/cli.py:520` reads `proposed_config` from the plan JSON verbatim. The plan is produced upstream by `_run_yes` or `_run_plan` (both go through `build_config()`), so apply inherits whatever drift handling happened at plan time. **Implication for parity test**: testing must occur at the `build_config()` level OR `main_init(["--yes","--dry-run","--root",...])` (which runs `build_config()` through `_run_yes`); testing the apply path alone would miss the drift entirely.
- **Three-source default problem** — the issue frames defaults as `config-schema.json` vs `core.py`, but there is a *third* source: `BRConfig` dataclass fields in `scripts/little_loops/config/core.py:154-786` and `scripts/little_loops/config/features.py:612-634`. `LoopRunDefaults.clear: bool = False` (`:615`) is the runtime Python dataclass default — *another* `false` value against which `core.py`'s `True` literal disagrees. The schema-winning alignment would resolve both at once (schema `false` ≡ `LoopRunDefaults` dataclass `False`); the schema-losing alignment would create a runtime/init mismatch that `BRConfig` then notices when loading the generated config.
- **`deep_merge` semantics constrain the parity test** — `scripts/little_loops/config/core.py:45-72` `deep_merge(base=existing, override=new)` (called from `writers.py:135`) lets existing values win on scalars. A re-init that produces a new schema-aligned literal will NOT overwrite a user's prior customized value. **Implication**: the parity test cannot use a round-trip approach (`generate → read back → compare`); it must compare `build_config()`'s direct dict output against `config-schema.json` defaults before any merge occurs.
- **Doc surface for `show_diagrams`**: `docs/reference/CONFIGURATION.md:874` documents `loops.run_defaults.show_diagrams: null` — agreeing with the schema and *disagreeing* with `core.py:147`'s `"clean"`. So the alignment direction "schema-wins" is *also* doc-winning. The other two drifts have doc evidence too (see `:566` for `char_cap: 1200`, which is schema-winning-by-coincidence because `core.py` simply doesn't write the key).
- **Existing test `test_init_core.py:522-542` `test_loops_run_defaults_keys` cannot be the only test enforcing the literal** — it is also asserted in `scripts/tests/integration/test_init_e2e.py:66-67` (`test_plan_apply_produces_same_artifacts_as_yes`) for the `--plan`/`apply` round-trip. Both must be updated in lockstep.
- **`.ll/decisions.yaml:3555-3564`** already records a related rule "*ll-init defaults should be sourced from config-schema.json instead of hardcoded literals*" referencing this issue (per the captured decision flow). The rule is captured but not yet enforced — this issue is its eventual enforcement site. `decisions.yaml:1487-1491` records another related sub-rule (`install_source` enum drift) for a *different* defaults class — confirming this issue is part of a wider family, not the only one.
- **The opt-out emission pattern** at `core.py:128-130` (`prompt_optimization`) is *itself* a documented drift per BUG-2321: the schema says enabled by default, but the code emits the block only when opted out, so a fresh init has the key absent. After the refactor, the helper should source the *default-true* value, but the *emission policy* (write block on absent vs. on opt-out) is a separate decision — keep the existing opt-out *structural* behavior even though the *value* comes from the schema.

### Tests
- `scripts/tests/test_init_core.py` — add the schema-parity regression test described above
- `scripts/tests/test_init_core.py:414` — `TestBuildConfig` class is the natural anchor for the new parametrized parity test (existing class exercises `build_config()` for ~190 lines and already imports `build_config`); an additional class such as `TestBuildConfigSchemaParity` would slot in just after the existing class

### Codebase Research Findings (pattern-finder pass)

_Added by `/ll:refine-issue` — based on pattern-finder agent (additive; do not remove existing content):_

- **Closest dotted-path resolver to model after**: `scripts/little_loops/config/features.py:14-35` `feature_enabled()` — splits on `.`, walks the dict, returns a sentinel on miss. The new `schema_default("a.b.c")` helper should follow this shape, with the schema dict as input and a `default`-aware return (sibling `feature_enabled_for()` at `:38-75` already takes a caller-supplied default). Two other dotted-walk helpers exist — `scripts/little_loops/config/core.py:760-782` `resolve_variable()` (returns `None` on miss) and `scripts/little_loops/fsm/interpolation.py:112-134` `_get_nested()` (raises on miss); neither fits "schema-default lookup" semantics as cleanly.
- **Schema file location**: `config-schema.json` lives at the project root (NOT under `scripts/little_loops/`), so any helper colocated under `init/` or `config/` must resolve via `Path(__file__).resolve().parents[N] / "config-schema.json"`. The existing test loader pattern is `scripts/tests/test_config_schema.py:1-9` (`PROJECT_ROOT = Path(__file__).parent.parent.parent; CONFIG_SCHEMA = PROJECT_ROOT / "config-schema.json"`).
- **Existing tests that *pin* the literals**: `scripts/tests/test_init_core.py:499-505` (`test_history_session_digest_defaults` — asserts `days == 7`) and `:522-542` (`test_loops_run_defaults_keys` — asserts `clear is True`, `show_diagrams == "clean"`) already lock in these exact values. The parity test must keep these assertions true, OR they must be loosened/kept in lockstep with whichever schema value the helper reads.
- **Walker pattern for "report all disagreements"**: `scripts/tests/test_init_core.py:614-640` `test_build_config_emits_no_null_leaves` includes a recursive `_scanner()` (`:624-639`) that collects every offending path rather than failing on the first mismatch. Use this shape for the new parity test so a future drift surfaces as a complete mismatch list, not "fix one and discover another".
- **`--dry-run` path equivalence**: `build_config()` returns the same dict unconditionally (terminal `return strip_none_leaves(config)` at `core.py:151`). The parity test only needs to exercise the helper once; both `main_init(...) --dry-run` (`:1268-1280`) and `main_init(...) --yes` paths share the same emission.
- **Deviation-marker convention**: The codebase has no precedent for `x-` JSON-schema extensions or `# intentional deviation` comments anywhere in `scripts/little_loops/` or `config-schema.json`. If a future `core.py` literal legitimately diverges from the schema default, the existing convention is an inline `# --- <section> ---` block comment above the divergence (see `core.py:128-130` for the prompt_optimization default-on pattern, or `:78-149` for the full section-banner style).
- **Optional CLI form**: If the parity check is promoted to a CLI rather than a pytest test, model it on `scripts/little_loops/cli/verify_design_tokens.py:141-194` (text + JSON reports, `_find_profiles_dir()` resolver for editable-vs-installed layouts) and register in `scripts/little_loops/cli/__init__.py:22-24`. The `ll-verify-*` family already includes `ll-verify-docs` (parity-with-codebase-counts), `ll-verify-package-data`, and `ll-verify-design-tokens` — `ll-verify-init-defaults` would fit naturally. **Decision deferred**: regression test vs. CLI is not yet chosen; default to the test form because it auto-runs under `python -m pytest scripts/tests/`.

### Documentation
- `docs/reference/CONFIGURATION.md` — spot-check for other doc/schema/init three-way mismatches while in this area

### Configuration
- `config-schema.json` — becomes authoritative; no schema changes required for this issue itself

### Wiring Findings (added by `/ll:wire-issue`)

_Additive findings from a 3-agent wiring pass (caller-tracer, side-effect-analyser, test-pattern-finder). No existing content removed._

#### Live Drifts Expanded: 3 → 5

The `refine-issue` locator and analyzer passes identified three live drifts
(`loops.run_defaults.clear`, `loops.run_defaults.show_diagrams`,
`analytics.enabled`). The wiring pass uncovered **two additional drifts** that
follow the same schema-wins direction:

| `build_config()` key | `config-schema.json` default | `core.py` literal | Drift? |
|---------------------|------------------------------|-------------------|--------|
| **`learning_tests.enabled`** | `false` (line 956) | `learning_tests_enabled = bool(choices.get("learning_tests_enabled", True))` → always emits `{"enabled": True}` (`core.py:93-94`) | **YES — NEW** |
| **`product.enabled`** | `false` (line 818) | `product_enabled = bool(choices.get("product_enabled", True))` → `if product_enabled: config["product"] = {"enabled": True}` (`core.py:111-114`) | **YES — NEW** |

Note: `learning_tests` has no matching `BRConfig` dataclass; reads via
`_raw_config.get` fallback chain elsewhere. `product`'s drift cascades into
`init/cli.py:_run_yes` line 402 — `if config.get("product", {}).get("enabled"):
deploy_goals(...)` — schema-wins would cause fresh inits to skip `deploy_goals`
unless the user explicitly opts in.

#### Fourth Drift Source: `_run_yes` Fallback Literals

`scripts/little_loops/init/cli.py:362-384` builds the `choices` dict from
`existing_config` with hardcoded `True`/`False` fallbacks that **parallel**
(but don't share with) `build_config()`:

| `cli.py` line | Choice key | Fallback literal | Schema default | Drift? |
|--------------|-----------|------------------|----------------|--------|
| 364 | `product_enabled` | `True` | `false` | **YES** |
| 365 | `analytics_enabled` | `True` | `false` | **YES** |
| 369 | `learning_tests_enabled` | `True` | `false` | **YES** |
| 367 | `context_monitor_enabled` | `True` | `true` | match |
| 372 | `decisions_enabled` | `False` | `false` | match |
| 373 | `scratch_pad_enabled` | `False` | `false` | match |
| 374 | `session_capture_enabled` | `False` | `false` | match |
| 377-379 | `session_digest_enabled` | `True` | `true` | match |
| 380-382 | `prompt_optimization_enabled` | `True` | `true` | match |

These are **outside the parity test's surface** (scoped to `build_config()`
with empty choices), so a future drift here wouldn't trip the proposed test.
Updating them to match schema-wins is a follow-up; flag for either inclusion
in this issue or a sibling.

#### Fifth Drift Source: Templates

All 8 project-type templates in `scripts/little_loops/templates/` declare
`"analytics": {"enabled": false}`, `"product": {"enabled": false}`, and
`"context_monitor": {"enabled": true}`. `build_config` does **not** consume
these template keys — it only reads `template.data["project"]`,
`template.data["issues"]`, `template.data["scan"]` (`core.py:79-90`). The
templates' defaults are silently overwritten by `core.py`'s literals today.
After schema-wins, all three sources (schema, `BRConfig` dataclass, templates)
agree on `false`/`true` for those keys.

Files:
- `scripts/little_loops/templates/python-generic.json:77-82`
- `scripts/little_loops/templates/typescript.json:75-80`
- `scripts/little_loops/templates/javascript.json:77-82`
- `scripts/little_loops/templates/java-gradle.json:72-77`
- `scripts/little_loops/templates/java-maven.json:70-75`
- `scripts/little_loops/templates/dotnet.json:73-78`
- `scripts/little_loops/templates/rust.json:69-74`
- `scripts/little_loops/templates/go.json:70-75`
- `scripts/little_loops/templates/generic.json:45-50`

The parity test must reconcile this rather than flagging it (templates already
agree with schema).

#### Test Files & Functions Missed

Beyond the `known_tests` list, the wiring pass identified these test files
exercising init/`build_config`/`merge_with_existing` paths and the specific
test functions pinning literal values:

**New test files** (not in `known_tests`):

- `scripts/tests/test_init_tui.py` (entire file) — drives `_build_final_config`
  and `run_tui`; `_wire_q` fixture directly references
  `loop_clear_default` and `loop_show_diagrams_default` (lines 111-125,
  152-260 HappyPath, 269-345 ConditionalParallel, 639-908 loop-defaults focused
  tests). All asserts must be re-baselined under schema-wins.
- `scripts/tests/test_deploy_issue_templates.py` — `from little_loops.init.writers
  import deploy_issue_templates` (line 9); sibling of `merge_with_existing`.
- `scripts/tests/test_config_schema.py:287-306` — `test_analytics_in_schema`
  asserts `enabled["default"] is False` at line 306; this is the **contract**
  the new parity test aligns `core.py` against.
- `scripts/tests/test_wiring_skills_and_commands.py` — wiring test asserting
  `ll-init` reachable from the plugin manifest; affected only if the
  registration site changes.

**Specific test functions in `test_init_core.py` pinning literals** (not all
were in the `known_tests` list):

| Line | Test function | Pin | Schema value |
|------|---------------|-----|--------------|
| 440 | `test_learning_tests_always_written` | `config["learning_tests"]["enabled"] is True` | `false` (NEW drift) |
| 447 | `test_analytics_always_written` | `config["analytics"]["enabled"] is True` | `false` |
| 454 | `test_product_enabled_by_default` | `config.get("product", {}).get("enabled") is True` | `false` (NEW drift) |
| 468 | `test_context_monitor_enabled_by_default` | `config.get("context_monitor", {}).get("enabled") is True` | `true` (match) |
| 478-483 | `test_analytics_disabled` | exercises disabled branch only | n/a |
| 1258-2058 | `test_yes_*` / `test_apply_*` / `test_plan_*` driver tests | all assert on `build_config` output via `main_init` | re-run under schema-wins |
| 1522 | (substring) | `"Unknown feature"` value-error | unaffected |
| 1533 | (substring) | `--yes` required for `--enable` | unaffected |

**Tests that do NOT break** (use **synthetic** configs, not
`build_config`-emitted):

- `scripts/tests/test_loop_cli_defaults.py:22-38` `test_clear_default_applied_from_config`
- `scripts/tests/test_loop_cli_defaults.py:58-74` `test_show_diagrams_default_applied_from_config`
- `scripts/tests/test_loop_cli_defaults.py:116-127` `test_invalid_show_diagrams_in_config_raises_value_error`
- `scripts/tests/test_loop_cli_defaults.py:164-205` `test_from_dict_clear_true` + `test_loops_config_includes_run_defaults`

These exercise the CLI consumer side via `_write_config(tmp_path, {...})` with
hand-built configs; they're independent of init's literal source and should
remain unchanged.

#### Re-export Sites

- `scripts/little_loops/init/__init__.py:31` — re-exports `build_config`;
  signature unchanged. No new export entry needed for `schema_default` if kept
  internal to `init/core.py`.
- `scripts/little_loops/cli/__init__.py:84` — `from little_loops.init.cli
  import main_init`; the bridge from `pyproject.toml`'s `ll-init` console
  script to `build_config()` callers. (`__all__` at line 102 lists it.)
- `skills/init/SKILL.md` — `/ll:init` skill is a redirect stub shelling out
  to `ll-init --yes`; the only user-facing command surface that drives
  `build_config()`.

#### Documentation Surface Missed

- `docs/guides/LOOPS_GUIDE.md:521-522` — example block **hardcodes**
  `"clear": true, "show_diagrams": "clean"` matching the drift. **Needs
  update under schema-wins** (will otherwise appear to contradict the
  now-correct defaults).
- `skills/configure/areas.md:1317-1319` — `history.session_digest` area
  references `{{config.history.session_digest.days}}` and
  `{{config.history.session_digest.char_cap}}`. No value change (char_cap
  remains un-emitted), but visible current-value rendering under schema-wins.
- `skills/configure/areas.md:1383-1469` — `loops.run_defaults` area;
  `current:` template tag would render `false`/`null` (not `True`/`"clean"`)
  for fresh inits — visible user-facing change.
- `skills/configure/show-output.md:258-273` — `## loops.run_defaults --show`
  displays `(default: false)` and `(default: null)` annotations. Under
  schema-wins, fresh-init output matches these annotations (today it doesn't).
- `docs/reference/CONFIGURATION.md:482-492` — `### analytics` says "Default
  is off". Under schema-wins, fresh inits will match this doc for the first
  time.
- `docs/guides/GETTING_STARTED.md:93` — feature name enumeration; unaffected
  (feature names don't change).
- `docs/development/TROUBLESHOOTING.md:1013-1018` — `prompt_optimization` JSON
  snippet, unaffected.

#### Configuration Surface (additional)

- `scripts/little_loops/init/core.py:SCHEMA_URL` (lines 9-11) — unchanged;
  the `$schema` URL written into every generated config.
- `scripts/little_loops/config/features.py` —
  `AnalyticsCaptureConfig` (526-554), `LoopRunDefaults` (611-634),
  `SessionDigestConfig` (802-819). `BRConfig` runtime dataclass defaults;
  already align with schema (per issue's "third source" framing).
- `scripts/little_loops/config/core.py:641` — analytics read fallback
  `_raw_config.get("analytics", {}).get("enabled", False)` — runtime side;
  aligns with schema. No change required.
- `.ll/decisions.yaml:3555-3579` — `ARCHITECTURE-085` rule and
  `ARCHITECTURE-086` schema-wins decision are already recorded; this issue
  is their eventual enforcement site. No `decisions.yaml` update required
  unless the rule text is amended.

#### Implementation Note (additional follow-ups beyond the 4-step solution)

The implementer should consider:

1. Acknowledge the 3→5 expansion in live drifts (add
   `learning_tests.enabled` and `product.enabled` to the parity test's
   parametrize list).
2. Decide whether to (a) include `_run_yes` fallback literal updates in this
   issue, or (b) file a sibling issue for them — they're outside the parity
   test's scope and represent a fourth parallel drift source.
3. Update `docs/guides/LOOPS_GUIDE.md:521-522` and the three
   `skills/configure/*` docs in lockstep with the schema-wins re-baseline
   (the docs currently reflect either side of the drift inconsistently).
4. The parity test should use the
   `scripts/tests/test_config_schema.py:8-9` loader pattern
   (`PROJECT_ROOT = Path(__file__).parent.parent.parent;
   CONFIG_SCHEMA = PROJECT_ROOT / "config-schema.json"`) — schema lives at
   project root, NOT under `scripts/little_loops/`.

## Scope Boundaries

- **In scope**:
  - Refactor `scripts/little_loops/init/core.py` `build_config()` to source its emitted defaults from `config-schema.json`
  - Add one helper (`schema_default(dotted_path)` or equivalent) in `init/core.py` or a new `config/schema_defaults.py`
  - Add a regression test in `scripts/tests/test_init_core.py` asserting parity between emitted values and schema `default`s
- **Out of scope**:
  - Other modules that hardcode values mirrored in the schema (e.g. `history_reader.py` per ENH-2298) — separate follow-ups; tracked via Similar Patterns but not modified here
  - TUI defaults mirroring `core.py` literals — separate concern unless parity test catches drift
  - Schema design changes (e.g. introducing `x-source` metadata or a default-emit manifest) — `config-schema.json` already carries `default:`; the fix consumes it as-is
  - Documentation sync tooling between `CONFIGURATION.md` and the schema — drift with docs is a separate class of bug; this issue closes the init↔schema leg

## Success Metrics

- **Drift bugs from init↔schema**: 2 closed in last ~6 months (ENH-2298, BUG-2321) → 0 new incidents citing `core.py` literal ≠ schema `default` after the parity test lands
- **Single source of truth**: 100% of values emitted by `build_config()` without a `choices` override derive from `config-schema.json` (verifiable via the new test across ~230 schema `default`s)
- **Coverage of parity test**: spans every dotted path under `properties.*` whose `default` is currently used by `build_config()`; expands automatically when `build_config()` starts emitting a new key (test should be regenerated from `properties.*.default`)

## Impact

- **Priority**: P2 - Structural fix for a drift pattern that has already produced two shipped bugs (ENH-2298, BUG-2321); low urgency on its own but prevents recurring, hard-to-notice defaults bugs
- **Effort**: Medium - requires a schema-path-lookup helper, refactoring `build_config()`'s literals, and a new parity test across ~230 schema defaults
- **Risk**: Low - `choices` overrides remain the same; only the fallback-literal source changes, and the new test catches any accidental default-value shift
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Documents `ll-init`, `config-schema.json`, and `.ll/ll-config.json` as core project configuration |

## Session Log
- `/ll:confidence-check` - 2026-07-02T02:42:35Z - `a9a9fc96-7f5d-4608-ba25-50ab2fbf9324.jsonl`
- `/ll:wire-issue` - 2026-07-02T01:56:52 - `ea47d6be-ecee-41c2-9918-0eee9aeca58a.jsonl`
- `/ll:decide-issue` - 2026-07-02T01:29:57 - `960b3ce5-4cee-422b-9b65-45f370408957.jsonl`
- `/ll:refine-issue` - 2026-07-02T01:24:54 - `27f08e41-8bd7-47f5-ae74-491580b8f097.jsonl`
- `/ll:refine-issue` - 2026-07-02T01:18:33 - `27f08e41-8bd7-47f5-ae74-491580b8f097.jsonl`
- `/ll:format-issue` - 2026-07-02T01:12:54 - `3201c5ec-2890-496b-95b4-787bfe0dedca.jsonl`
- `/ll:capture-issue` - 2026-07-02T01:05:48Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0793a24b-9f57-4b15-868c-e30290465fba.jsonl`

---

## Status

- **Current State**: Open
- **Blocking**: None
