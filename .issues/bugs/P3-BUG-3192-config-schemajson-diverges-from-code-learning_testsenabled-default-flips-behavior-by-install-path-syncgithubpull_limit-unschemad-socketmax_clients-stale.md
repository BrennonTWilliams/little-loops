---
id: BUG-3192
type: BUG
title: 'config-schema.json diverges from code: learning_tests.enabled default flips
  behavior by install path, sync.github.pull_limit unschema''d, socket.max_clients
  stale'
priority: P3
status: open
testable: true
decision_needed: false
discovered_by: doc-audit-triage
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:50Z'
supersedes: []
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3192: config-schema.json diverges from code in four places

## Summary

Split out of BUG-3191 (`/ll:audit-docs` readme-scope sweep, 2026-08-15). Three findings
originally filed there were framed as documentation nits under "Risk: None — doc-only
change". They are not doc issues: in each case `scripts/little_loops/config-schema.json`
disagrees with the Python source, and in one case that disagreement changes runtime
behavior depending on how a project was initialized.

A **fourth** divergence (`analytics.enabled`, finding 4 below) was found during review by
running the generalized sweep this issue requires. It is folded in here: it is the same
install-path behavior split as finding 1, and the parity test this issue adds fails on its
first run unless it is resolved in the same pass.

BUG-3191 retains only the genuinely doc-only findings. This issue owns the schema fixes.

> **Note for anyone running `format-check` on this issue.** It reports
> `mislocated_symbol_ref` on `enabled` and `to_dict`. Both are BUG-3194 Finding 1 false
> positives — `enabled` is index pollution from keyword arguments, and `to_dict` is the
> `_MAX_ATTRIBUTION_DISTANCE` prose-adjacency class (this issue necessarily names
> `config/core.py:902` and `init/cli.py:590` in the same breath). Expected; do not "fix"
> them by removing the citations.

## Current Behavior

### 1. `learning_tests.enabled` — behavioral divergence, not cosmetic (primary)

- `config-schema.json` declares `"default": true`.
- `LearningTestsConfig.enabled` (`scripts/little_loops/config/features.py:498`) defaults
  to `False`.

These are not two views of one value — both are live, on different paths:

- `ll-init` writes the key explicitly, sourced from the schema:
  `scripts/little_loops/init/core.py:190` calls
  `schema_default("learning_tests.enabled")` → writes `true` into the new
  `.ll/ll-config.json`.
- A project whose config omits the key (hand-written config, older config predating the
  key, partial config) falls through to the dataclass → `False`.

Net effect: the Learning Test Registry is **on** for `ll-init`-generated projects and
**off** for projects without the key, with no signal to the user that the two differ.
`docs/reference/CONFIGURATION.md:897,909-921` documents the default as `false`, which is
correct against the dataclass and wrong against `ll-init`.

### 2. `sync.github.pull_limit` — real, documented, and unschema'd

- Read by code: `scripts/little_loops/sync.py:557,565,577-580` (bounds the `gh issue
  list` fetch and warns on truncation, naming the key in the warning text).
- Documented: `docs/reference/CONFIGURATION.md:720`.
- Absent from `config-schema.json`'s `sync.github.properties`, which declares
  `additionalProperties: false`. Present keys: `repo`, `label_mapping`,
  `priority_labels`, `sync_completed`, `state_file`, `pull_template`.

Blast radius is narrower than it first appears: little-loops does **not** runtime-validate
`ll-config.json` against this schema. The schema is consumed as the `$schema` pointer for
editor validation and by `schema_default()`/`schema_enum()` lookups in
`little_loops/init/core.py`. So the symptom is a spurious editor warning on a legitimate
key, not a hard config rejection. Still wrong, and it makes the key look unsupported to
anyone reading the schema as the source of truth.

### 3. `events.socket.max_clients` — stale schema default

- `config-schema.json` declares `"default": 8`.
- Code default is `32`; `docs/reference/CONFIGURATION.md:1466` documents `32` and is
  correct. The schema is the stale artifact here.

### 4. `analytics.enabled` — three literals, three values (found during review)

Surfaced by running the generalized sweep this issue's Acceptance Criteria require, against
a clean project. `analytics.enabled` has **no dataclass at all** — unlike findings 1-3 there
is no `AnalyticsConfig`; the key's fallback is an inline literal, and there are two of them
disagreeing with the schema and with each other:

| Site | Value |
|---|---|
| `config-schema.json` `analytics.enabled` | `true` |
| `BRConfig.to_dict()` (`config/core.py:902`) | `False` |
| `ll-init` reconfigure path (`init/cli.py:590`) | `True` |

`ll-init`'s fresh path is schema-sourced (`init/core.py:194` →
`schema_default("analytics.enabled")`), so it agrees with the schema.

**This is not finding 1's behavior split.** Nothing gates on `analytics.enabled` at
runtime: the capture hooks all key on `analytics.capture.*` via
`AnalyticsCaptureConfig.from_dict()` (`hooks/__init__.py:105`,
`hooks/user_prompt_submit.py:123`, `hooks/post_tool_use.py:231`,
`session_store/writers.py:207,240,274`) and never read `enabled`. So the user-visible
effect today is confined to what `ll-config` displays and what a reconfigure round-trip
seeds — not whether analytics runs.

It is folded in here for a mechanical reason rather than a severity one: the parity test
required below **fails on this key the moment it is written**, so this fix cannot land
without resolving it. Resolve it as `false` at both the schema and `init/cli.py:590`,
matching `to_dict()` and finding 1's dataclass-wins direction — no silent behavior change
for any project, and making analytics on-by-default is a product decision belonging in its
own issue.

Note the `to_dict()`-vs-`init/cli.py` disagreement is a genuine bug independent of the
schema, and is the *only* finding here where two Python literals disagree with each other.

## Steps to Reproduce

All three divergences are observable without writing anything:

```bash
python - <<'PY'
import json, pathlib
from little_loops.config.features import (
    LearningTestsConfig, GitHubSyncConfig, SocketEventsConfig,
)
s = json.loads(pathlib.Path('scripts/little_loops/config-schema.json').read_text())

lt = s['properties']['learning_tests']['properties']['enabled'].get('default')
print(f"learning_tests.enabled  schema={lt}  dataclass={LearningTestsConfig().enabled}")

gh = s['properties']['sync']['properties']['github']
print(f"sync.github.pull_limit  in schema={'pull_limit' in gh['properties']}"
      f"  additionalProperties={gh.get('additionalProperties')}"
      f"  dataclass={GitHubSyncConfig().pull_limit}")

mc = s['properties']['events']['properties']['socket']['properties']['max_clients'].get('default')
print(f"events.socket.max_clients  schema={mc}  dataclass={SocketEventsConfig().max_clients}")
PY
```

Observed:

```
learning_tests.enabled  schema=True  dataclass=False
sync.github.pull_limit  in schema=False  additionalProperties=False  dataclass=500
events.socket.max_clients  schema=8  dataclass=32
```

Finding 4 has no dataclass, so it needs a different probe — compare the schema against the
two inline literals directly:

**These probes must run against a config-less directory, not the repo root.** This repo's
own `.ll/ll-config.json` sets both `analytics.enabled` and `learning_tests.enabled` to
`true`, so `BRConfig(Path('.'))` here returns the *configured* value and the divergence is
invisible. Verified 2026-08-15: at the repo root `to_dict()['analytics']['enabled']` is
`True`, not `False`. Use a temp dir:

```bash
python -c "from little_loops.init.core import schema_default; print('schema:', schema_default('analytics.enabled'))"
# schema: True

python -c "
import tempfile
from pathlib import Path
from little_loops.config import BRConfig
print('to_dict:', BRConfig(Path(tempfile.mkdtemp())).to_dict()['analytics']['enabled'])"
# to_dict: False   (config/core.py:902 — the inline fallback, no config file present)

# and init/cli.py:590's reconfigure fallback, read directly:
grep -n 'analytics_enabled.*get("enabled"' scripts/little_loops/init/cli.py
# 590:  ... .get("enabled", True)
```

For the install-path split specifically, compare a generated config against a hand-written
one:

```bash
python -c "from little_loops.init.core import schema_default; print(schema_default('learning_tests.enabled'))"
# True  — what ll-init writes into a new .ll/ll-config.json

python -c "from little_loops.config.features import LearningTestsConfig; print(LearningTestsConfig().enabled)"
# False — what a config omitting the key resolves to at runtime
```

This config-masking hazard is not confined to the repro — it is the primary failure mode
of Guard 1 below, which will pass green against the repo root while catching nothing.

## Expected Behavior

- One default per config key, agreed between `config-schema.json` and the corresponding
  dataclass, so that `ll-init`-generated and key-omitting projects behave identically.
- `sync.github.pull_limit` declared in the schema with its code default, so
  `additionalProperties: false` stops rejecting a supported key.
- `events.socket.max_clients` schema default corrected to `32`.
- `analytics.enabled` reads `false` at all three sites (schema, `config/core.py:902`,
  `init/cli.py:590`).

## Program Design

The "learning_tests.enabled" fix requires a product decision, not just an edit — pick the
intended default and make both sides agree:

- **Schema wins (`true`)**: change `LearningTestsConfig.enabled` to `True`. Silently
  enables LT surfaces (discoverability hook, gate-loop hints) for existing projects that
  omit the key — a behavior change on upgrade for those projects.
- **Dataclass wins (`false`)**: change the schema default to `false`. `ll-init` then
  writes `false`, making LT opt-in. Matches what CONFIGURATION.md already documents.

Recommend **dataclass wins**: it is the documented behavior, it is opt-in rather than
opt-out for a feature that adds hook surface, and it changes nothing for existing
projects. Under this option CONFIGURATION.md needs no edit.

### Decision (resolved 2026-08-15)

**Dataclass wins — the schema default flips to `false`.** `LearningTestsConfig.enabled`
is unchanged; `config-schema.json`'s `learning_tests.enabled` default becomes `false`.

Rationale, and what was weighed against it:

- Dataclass-wins agrees with all **eight** existing doc sites already documenting `false`
  (`docs/reference/CONFIGURATION.md:897,909-921`, five statements in
  `docs/guides/BUILTIN_HOOKS_GUIDE.md:96,124,227,256,470`, `skills/configure/show-output.md:208`,
  `skills/scope-epic/SKILL.md:162,164`). Schema-wins makes all eight stale in one pass.
- Schema-wins would silently enable Learning Test hook surface on upgrade for every
  project whose config omits the key — a behavior change nobody opted into, on the exact
  install path this bug exists to reconcile.
- The one real argument for schema-wins is product-level: `ll-init` seeds `true` today, so
  dataclass-wins turns the Learning Test Registry off for all *future* projects. That is
  accepted here. Making LT on-by-default is a deliberate product change that should be
  filed on its own, with the doc sweep attached — not smuggled in through a schema-parity
  fix.
- A third option was considered and **rejected**: keep both values, redefining the schema
  `default` as "what `ll-init` seeds" rather than "what the code assumes when the key is
  absent", with an allowlist entry exempting this key from the parity test. Rejected
  because that ambiguity is precisely what produced this bug; encoding it as intent makes
  the next instance harder to catch, and it defeats the generalized parity sweep this
  issue requires.

Consequences for the rest of this issue: no documentation edits are needed for the
`learning_tests` half, and the four tests enumerated in Acceptance Criteria
(`test_config_schema.py:269`, `test_init_core.py:3444-3457`, `test_wheel_smoke.py:178-190`,
plus the socket assertion at `test_config_schema.py:762`) flip to `False`/`32` rather than
being deleted.

**The generalized parity test is required, not optional.** An earlier draft framed it as
"consider generalizing" — but this class of drift produced two of the original three
findings, and a key-by-key test only pins the keys we happen to have noticed. It is also
the sweep that found finding 4 during review, which is the concrete argument for it.

#### Two guards are needed, not one — and neither is the existing sweep

An earlier draft proposed reusing
`TestBuildConfigSchemaParity::test_emitted_defaults_match_schema` by tightening its
`KeyError` swallow into an allowlist. **That does not work, and the stated rationale for it
was wrong.** Two corrections, both verified:

- The test lives at `scripts/tests/test_init_core.py:763-801`, **not**
  `test_config_schema.py:763-801`. The two files coincide at those line numbers, which is
  how the mis-citation survived; `test_config_schema.py:763` is mid-socket-assertion.
- It walks **`build_config()` output**, not dataclasses. `build_config` emits
  `config["sync"] = {"enabled": True}` (`init/core.py:286`) with **no `github` subtree at
  all**, so `sync.github.pull_limit` was never in its walk. The `KeyError` swallow is not
  why that key slipped through, and tightening it produces an init-literal-vs-schema guard,
  which is what that test already is — not the schema-vs-code guard this issue needs.

The two guards to write, both new, in `scripts/tests/test_config_schema.py`:

1. **Value parity.** Walk `BRConfig(<clean project>).to_dict()` and diff every leaf against
   `schema_default(path)`, skipping the template-derived sections
   (`$schema`, `project`, `issues`, `scan`) the existing init-side test already excludes.

   **"Clean project" means `tmp_path` with no `.ll/ll-config.json` — this is load-bearing,
   not a detail.** `BRConfig` merges the on-disk config over the dataclass defaults, and
   this repo's own config sets `analytics.enabled` and `learning_tests.enabled` to `true`.
   A guard written against the repo root therefore sees both keys agreeing with the schema,
   reports zero mismatches, and ships as a permanent no-op that would not have caught any
   of the three findings it exists to catch. Verified 2026-08-15. Use `tmp_path` and assert
   the guard actually fails when a schema default is perturbed.

   Measured against `main` on 2026-08-15 from a config-less temp dir, this reports exactly
   the three value divergences this issue fixes and nothing else:

   ```
   MISMATCHES 3
     learning_tests.enabled:    to_dict=False schema=True
     analytics.enabled:         to_dict=False schema=True
     events.socket.max_clients: to_dict=32    schema=8
   ```

   Paths with no schema `default` must go to an explicit enumerated allowlist rather than
   a silent `KeyError` skip. Measured, that allowlist is seven entries:
   `commands.pre_implement`, `commands.post_implement`, `orchestration.host_cli` (declares
   an `enum`, no `default`), and the four `sync.github.label_mapping.*` leaves.

2. **Declared-ness.** Value parity alone still misses `sync.github.pull_limit` —
   `to_dict()` omits it (verified: `to_dict()["sync"]["github"]` has `repo`,
   `label_mapping`, `priority_labels`, `sync_completed`, `state_file`, `pull_template`, and
   no `pull_limit`). A key that no serializer emits cannot be caught by any output-walking
   sweep.

   **Revised approach (2026-08-15 review): fix `to_dict()` first, then keep guard 2
   narrow.** An earlier draft specified guard 2 as "iterate `dataclasses.fields()` over the
   config dataclasses and assert each field has a corresponding schema property". Measured,
   that is 59 config dataclasses / 236 fields across `config/features.py`,
   `config/automation.py`, and `config/core.py` — and **there is no dataclass→schema-path
   registry anywhere in the tree**. Written as specified, guard 2 requires a hand-maintained
   59-entry mapping whose own drift is unguarded: a new config dataclass omitted from the
   map is silently exempt. That is the same defect class this issue exists to fix, one
   level up.

   Cheaper and strictly better-covering:

   - **Make `to_dict()` emit `sync.github.pull_limit`.** The omission is a defect on its own
     terms (`TestToDictSchemaParity` checks only top-level key presence, so nothing caught
     it), and `pull_limit` is a real, documented, code-read key. Once emitted, **guard 1
     catches finding 2** with no second sweep — the key appears as a leaf, `schema_default`
     raises, and the explicit allowlist forces a decision.
   - **Guard 2 shrinks to a completeness assertion**: every config dataclass appears in the
     dataclass→section map, so a newly added dataclass cannot silently escape guard 1's
     walk. That is a one-line-per-dataclass map with a test that fails when it goes stale —
     bounded work, and it guards the guard.

   This inverts the earlier priority: fixing `to_dict()` was previously declared out of
   scope with guard 2 as "the one that must exist". It is the reverse — the `to_dict()` fix
   is small, is independently correct, and subsumes most of guard 2's value.

**Fold in the sibling `API.md` divergence.** `docs/reference/API.md:10025` documents
`UnixSocketTransport`'s constructor signature as `max_clients: int = 8`; the actual default
at `scripts/little_loops/transport.py:137` is `32`. This is the same 8-vs-32 stale value as
finding 3, one layer up (a documented Python constructor default rather than a schema
literal), and it is a one-line doc edit in the same review pass. Fix it here rather than
leaving it as a dangling "consider filing separately" — a separate P4 issue for a one-line
doc correction costs more to track than to fix.

**Precision on the span.** An earlier draft cited `API.md:10017-10025` as one range. Only
**line 10025** (the `#### Constructor` signature block) is wrong. Line 10017 is a usage
example that passes `max_clients=8` explicitly — valid code, not a default claim. Leave it,
or update it for consistency, but do not treat it as part of the defect.

### Codebase Research Findings — Types and Call Path

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Types
- No new type — `GitHubSyncConfig.pull_limit: int = 500` (`scripts/little_loops/config/features.py:968`) and its `from_dict()` read `data.get("pull_limit", 500)` (line 983) already exist. Only the schema property is missing; the dataclass side of this key is already correct.

### Signatures
- `schema_default(dotted_path: str) -> Any` — dotted-path walk over `config-schema.json`'s `properties` tree, raising `KeyError` if the path or its `"default"` key is absent; fail-loud, defined at `scripts/little_loops/init/core.py:39`, documented at `init/core.py:44-46`.
- `schema_enum(dotted_path: str) -> list[str]` — same dotted-path walk, returns `"enum"` instead of `"default"`, raising `KeyError` under the same conditions; defined at `scripts/little_loops/init/core.py:61`, documented at `init/core.py:64-65`.

### Call Path
`ll-init` → `build_config()` (`init/core.py:190`) → `schema_default("learning_tests.enabled")` → `config-schema.json` → written verbatim into the new project's `.ll/ll-config.json`.
Separately: any `ll-*` command → `BRConfig.__init__` (`config/core.py`) → `LearningTestsConfig`/`SyncConfig.from_dict(raw.get(..., {}))` → the dataclass literal default when the on-disk key is omitted. This second path never reads `config-schema.json` — it is the source of the "flips behavior by install path" divergence.

### Decision Rules
N/A — no new decision logic. This is a value-parity fix between an existing schema literal and an existing dataclass literal, not a new gap kind, gate, or threshold.

## Acceptance Criteria

- [ ] `schema_default("learning_tests.enabled")` and `LearningTestsConfig.enabled` return
      the same value.
- [ ] `sync.github.pull_limit` is declared in `config-schema.json` with a `type`,
      `default` matching code (`500`), a `description`, and `minimum: 1` per the
      limit-property convention.
- [ ] `events.socket.max_clients` schema default is `32`.
- [ ] `analytics.enabled` reads `false` at all three sites — `config-schema.json`, the
      serializer fallback at `config/core.py:902`, and the reconfigure fallback at
      `init/cli.py:590`.
- [ ] **Guard 1 (value parity)** — a new sweep in `scripts/tests/test_config_schema.py`
      walks `BRConfig(<clean project>).to_dict()` and fails if any leaf differs from
      `schema_default(path)`. Paths with no declared schema `default` are skipped only via
      an **explicit enumerated allowlist** (measured: the seven paths named in Program
      Design), never a silent `KeyError` catch.
- [ ] **Guard 1 uses `tmp_path`, not the repo root**, and is proven non-vacuous: perturb a
      schema default in the test and assert the guard fails. Against the repo root it
      passes green while catching nothing, because this project's own `.ll/ll-config.json`
      sets both divergent keys to `true`.
- [ ] **`BRConfig.to_dict()` emits `sync.github.pull_limit`**, so guard 1 covers finding 2.
      A key no serializer emits is invisible to any output-walking sweep.
- [ ] **Guard 2 (completeness)** — a test asserting every config dataclass is present in
      the dataclass→schema-section map guard 1 walks, so a newly added dataclass cannot
      silently escape coverage. Scoped deliberately: the earlier "iterate
      `dataclasses.fields()` over all config dataclasses" formulation is 59 dataclasses /
      236 fields with no existing path registry (see Program Design).
- [ ] Neither guard is implemented by editing
      `test_init_core.py::TestBuildConfigSchemaParity::test_emitted_defaults_match_schema`
      — that test compares `build_config()` literals against the schema, a different
      relation, and is out of scope here.
- [ ] The three tests that currently pin the divergent values are updated, not just left
      to fail: `test_config_schema.py::test_learning_tests_in_schema:269` (`default is
      True`), the socket assertion at `:762` (`== 8`), and — easy to miss because it runs
      in a subprocess against a wheel install — `test_wheel_smoke.py:178-190`. Plus
      `test_init_core.py:3444-3457`, whose docstring asserts "bundled schema default is
      True" and must be reworded, not only re-valued.
- [ ] `docs/reference/API.md:10025` documents `UnixSocketTransport`'s `max_clients`
      default as `32`, matching `transport.py:137`. (Line 10017 is an example passing `8`
      explicitly — not part of the defect.)
- [ ] `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Codebase Research Findings — Integration Map

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/config-schema.json` — three edits: "learning_tests.enabled" default (lines 1148-1152), add a `pull_limit` property under `sync.github.properties` (lines 1301-1362, blocked today by `additionalProperties: false` at line 1358), `events.socket.max_clients` default (lines 1583-1587)
- `scripts/little_loops/config/features.py` — only touched if the "schema wins" option is chosen: `LearningTestsConfig.enabled` (line 498) and its `from_dict()` read (line 520) would flip to `True`
- `scripts/tests/test_config_schema.py` — `test_learning_tests_in_schema` (~lines 247-289) asserts `lt_props["enabled"].get("default") is True` at line 269, and the socket test (~lines 735-797) asserts `socket_props["max_clients"]["default"] == 8` at line 762 — both currently pin the divergent (wrong) values and will not catch this fix unless updated. No existing test covers `sync.github.pull_limit`.
- `docs/reference/API.md:10025` — folded in from the sibling finding below: `UnixSocketTransport`'s documented constructor default `max_clients: int = 8` corrected to `32` to match `scripts/little_loops/transport.py:137`. One-line doc edit, same 8-vs-32 value as finding 3. Line 10017 is a usage example passing `8` explicitly and is not part of the defect.
- `scripts/little_loops/init/cli.py:590` — finding 4: the reconfigure path's `analytics_enabled` fallback is `True`, disagreeing with `config/core.py:902`'s `False`. Flips to `False`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/core.py:190` — `schema_default("learning_tests.enabled")` writes the schema's literal into new `.ll/ll-config.json` files. `schema_default()`/`schema_enum()` are defined at `init/core.py:39-77` (dotted-path walk over `config-schema.json`'s `properties` tree; raises `KeyError` if the path or its `default`/`enum` key is missing — fails loud rather than silently falling back).
- `scripts/little_loops/config/core.py:319` — `BRConfig` builds `SyncConfig.from_dict(raw.get("sync", {}))` independent of the schema file; the runtime fallback path for an omitted key never reads `config-schema.json`, only the dataclass literal.
- `scripts/little_loops/sync.py:557,565,577-580` — reads `pull_limit` off the loaded `GitHubSyncConfig`/raw dict; the truncation-warning text names the key.
- `scripts/little_loops/cli/config.py:83-99` — `_warn_if_unknown_section()` only unions top-level schema section names against `BRConfig.to_dict()`'s top-level keys, not nested dotted paths, so a missing `sync.github.pull_limit` entry produces no warning through this path either.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/learning_tests_gate.py:9,24,49-60` — `_load_lt_config()` builds `LearningTestsConfig` from raw project config, falling back to `LearningTestsConfig()`'s dataclass default (not the schema) on any read miss; its own module docstring at line 9 already documents "default False", consistent with the recommended dataclass-wins option.
- `scripts/little_loops/learning_tests/release_gate.py:17,23-33` — same `_load_lt_config()` pattern, same dataclass-default fallback.
- `scripts/little_loops/hooks/install_learning_gate.py:49,95` — same `_load_lt_config()` pattern, same dataclass-default fallback, gates on `lt_config.enabled` at line 95.

### Conventions in Force
- Every schema leaf property declares `type` + `description` + `default` together (key order varies) — evidence: `sync.github.*` block (`config-schema.json:1316-1359`), `events.socket.max_clients` (`config-schema.json:1583-1587`).
- Integer "limit"-named properties conventionally add a `minimum` bound, typically `1` — evidence: `mcp.*.max_results` (`config-schema.json:641-644`, `default: 500, minimum: 1`).
- Nested objects each declare their own `additionalProperties: false` (`sync.github` block, `config-schema.json:1301-1362`) — this is why `pull_limit` reads as unschema'd to editors today; no runtime `jsonschema`/`Draft7Validator` call against this file exists anywhere in `scripts/`, so the practical effect is a spurious editor warning, not a hard rejection.
- `test_config_schema.py` tests load the schema fresh per test via `json.loads(_load_schema_text())` and assert directly on the parsed dict — no shared fixture, no schema-walking helper.
- `test_skill_budget_in_schema` (`test_config_schema.py:1085-1107`) is the only existing test comparing a schema default against a live Python constant (`little_loops.doc_counts._DEFAULT_BUDGET_TOKENS`) instead of a hardcoded literal — the closest existing precedent for the schema-vs-dataclass parity test this issue's AC asks for. No generic/parametrized dotted-path-walking test exists anywhere in `scripts/tests/`.
- `TestToDictSchemaParity` (`test_config_schema.py:1127-1174`) generically compares schema section keys against `BRConfig(...).to_dict()` keys, but only at the top level and only for key presence, not nested default values.

### Tests
- `scripts/tests/test_config_schema.py` — `test_learning_tests_in_schema` and the socket `max_clients` assertion currently pin the divergent schema values (see Files to Modify above).
- No test currently exists for `sync.github.pull_limit`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_core.py:3444-3457` (`test_schema_default_returns_real_default`) — hard-pins `schema_default("learning_tests.enabled") is True` with a docstring literally asserting "bundled schema default is True". **Must update** to `False` under the recommended (dataclass-wins) option, or this test fails.
- `scripts/tests/test_wheel_smoke.py:178-190` (`test_schema_loads_in_wheel_install`) — same hard-pinned `is True` assertion inside a subprocess-invoked wheel-install check. Same update required.
- `scripts/tests/test_init_core.py::TestBuildConfigSchemaParity::test_emitted_defaults_match_schema` (763-801) — **corrected location** (an earlier pass cited `test_config_schema.py:763-801`; the two files coincide at those line numbers). Walks `build_config()` output and diffs every leaf against `schema_default(path)`, silently skipping any path raising `KeyError`. **It will never see `sync.github.pull_limit`**: `build_config` emits `config["sync"] = {"enabled": True}` (`init/core.py:286`) with no `github` subtree, so adding the schema property gives this sweep no new coverage. An earlier pass claimed the opposite; see Program Design § "Two guards are needed".
- `scripts/tests/test_config_schema.py::test_skill_budget_in_schema` (1085-1107) — closest existing precedent for "import the live dataclass default, assert schema `default` equals it" (imports `_DEFAULT_BUDGET_TOKENS` directly rather than walking `build_config()`); model the issue's requested parametrized dotted-path test on this pattern.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:96,124,227,256,470` — five separate statements that "learning_tests.enabled" defaults to `false`, consistent with the recommended (dataclass-wins) option and requiring **no edit** under it. Enumerated here because if "schema wins" (`true`) were chosen instead, all five become stale in addition to `docs/reference/CONFIGURATION.md` — this is the full blast radius of that alternative.
- `skills/configure/show-output.md:208` — inline template comment `(default: false)` next to the `{{config.learning_tests.enabled}}` display line. Same no-edit-under-recommended-option / stale-under-schema-wins status as above.
- `skills/scope-epic/SKILL.md:162,164` — states `config.learning_tests.enabled` is `false` "(the default)" and branches epic-scaffolding logic on it. Same status.
- `docs/reference/API.md:10017-10025` — **folded into this issue's scope** (see Program Design and Acceptance Criteria). `UnixSocketTransport`'s documented constructor default is `max_clients: int = 8`, but the actual default in `scripts/little_loops/transport.py:137` is `32` — the same 8-vs-32 divergence as this issue's `events.socket.max_clients` schema finding, on a different symbol (a Python constructor default, not the config schema) and not fixed by editing `config-schema.json`. Originally flagged as out of scope; folded in because it is a one-line doc edit in the same review pass and cheaper to fix than to track separately.

## Impact

- **Priority**: P3 — the `learning_tests` divergence is a genuine behavior split across
  install paths, but the affected feature is non-destructive and the other two findings
  are low-severity schema hygiene.
- **Effort**: Small-to-Medium — four schema/literal edits, a one-key `to_dict()` addition,
      and two new regression guards. Guard 1 is cheap (measured: three mismatches, a
      seven-entry allowlist); guard 2 was rescoped during review from a 59-dataclass field
      sweep down to a map-completeness assertion, which is what keeps this out of "Medium".
      Four existing tests pin the divergent values and must be updated in the same pass.
- **Risk**: Low — a schema-only change is inert at runtime; the `learning_tests` half
  touches a real default and should land with the recommended (no-op for existing
  projects) option unless deliberately chosen otherwise.
- **Breaking Change**: No, under the recommended option.

## Root Cause

### Codebase Research Findings — Root Cause

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

- **File**: `scripts/little_loops/config-schema.json`
- **Anchors**: "learning_tests.enabled" (lines 1148-1152, `"default": true`); `sync.github.properties` (lines 1301-1362, `additionalProperties: false` at line 1358, no `pull_limit` entry); `events.socket.max_clients` (lines 1583-1587, `"default": 8`)
- **Cause (findings 1-3)**: these three schema literals were never kept in sync with the corresponding dataclass defaults in `scripts/little_loops/config/features.py` — `LearningTestsConfig.enabled = False` (line 498), `GitHubSyncConfig.pull_limit: int = 500` (line 968, already present as a dataclass field — only the schema property is missing), `SocketEventsConfig.max_clients: int = 32` (line 1056). No code path cross-checks schema defaults against dataclass defaults. The existing regression tests in `scripts/tests/test_config_schema.py` currently assert *against* the schema's divergent values (`test_learning_tests_in_schema:269` asserts `default is True`; the socket test at `:762` asserts `default == 8`), so today they guard the divergence rather than catch it.
- **Cause (finding 4)**: different mechanism — `analytics.enabled` has no dataclass, so its
  fallback is an inline literal duplicated at two unrelated call sites
  (`config/core.py:902` → `False`, `init/cli.py:590` → `True`) with the schema as a third
  source. Nothing reads the key at runtime, so the disagreement never produced a visible
  failure and nothing forced the three to converge.

## Status

**Open** | Created: 2026-08-15 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-08-16T00:17:01 - `64e9e21e-d2d6-44cd-97cd-d980a3cc037d.jsonl`
- `/ll:confidence-check` - 2026-08-15T20:01:25 - `4eb27027-e6df-4ea9-a6cc-2ca5e6e40c15.jsonl`
- `/ll:wire-issue` - 2026-08-15T18:50:54 - `fbae9292-fc5e-470b-b261-173e14415c63.jsonl`
- `/ll:refine-issue` - 2026-08-15T18:41:16 - `d0d59699-3101-4268-a597-0b2238075aec.jsonl`
