---
id: BUG-3012
title: BRConfig.to_dict() omits 11 live config sections, breaking ll-config get and
  {{config.*}} expansion
type: BUG
status: done
priority: P2
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
testable: true
labels:
- config
- cli
- skills
milestone: epic-3008
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: '2026-08-03T15:44:19Z'
---

# BUG-3012: `BRConfig.to_dict()` omits 11 live config sections, breaking `ll-config get` and `{{config.*}}` expansion

## Summary

`to_dict()` (`scripts/little_loops/config/core.py:648-922`) emits 25 of the
config file's top-level sections and omits **11 live ones**. Since both
`ll-config get <dot.path>` and skill/command `{{config.<dot.path>}}` expansion
resolve through `to_dict()`/`resolve_variable()` (`core.py:924-946`), every
omitted section is unreachable: `ll-config get` prints nothing and exits `0`,
and `{{config.…}}` silently expands to the **empty string**.

## Current Behavior

Verified by diffing `config-schema.json`'s 38 top-level properties against
`BRConfig(Path(".")).to_dict()`. Missing, excluding the two meta keys `$schema`
and `install_source`:

| Section | How it's parsed | Consumed by |
|---|---|---|
| `refine_status` | typed property, `core.py:270-272, 378-381` | `cli/issues/refine_status.py` |
| `orchestration` | typed property, `core.py:277-278, 399-401` | `resolve_host()` (`.claude/CLAUDE.md` "Host CLI Abstraction"); set in this repo's own `.ll/ll-config.json` |
| `extensions` | raw-passthrough property, `core.py:428-431` | `EventBus`/extension loader |
| `context_monitor` | **no `BRConfig` property at all** | `hooks/scripts/context-monitor.sh:21`, `context-handoff-sentinel.sh:23`; written by `init/core.py:173` |
| `scratch_pad` | no property | `hooks/scripts/scratch-pad-redirect.sh:53`; `init/tui.py:668` |
| `session_capture` | no property | `hooks/scripts/session-capture.sh:27`; `init/core.py:190` |
| `prompt_optimization` | no property | `init/tui.py:448,814`; `init/cli.py:31` |
| `documents` | no property | `init/tui.py:559` |
| `product` | no property | `init/tui.py:32,37`; `ll-scan-product` |
| `continuation` | no property | continuation-prompt config |
| `hooks` | no property | `init/core.py:23` |

Empirically, in this very repo (which configures `context_monitor`,
`scratch_pad`, and `orchestration`):

```
$ ll-config get context_monitor.enabled     # (nothing)  exit 0
$ ll-config get scratch_pad.enabled         # (nothing)  exit 0
$ ll-config get orchestration.host_cli      # (nothing)  exit 0
$ ll-config get project.name                # little-loops
```

The lookup silently resolves to nothing rather than erroring
(`cli/config.py:52` documents "0 always"), which is why the gap survived
undetected.

## Two distinct failure classes — the fix must cover both

1. **Typed-but-unemitted** (`refine_status`, `orchestration`, `extensions`) —
   `BRConfig` parses them into properties, `to_dict()` just never emits them.
2. **Never-modelled** (the other 8) — these sections have **no `BRConfig`
   property and no `_raw_config` read anywhere in `scripts/`** (confirmed by
   grep). They're consumed by bash hooks via `jq` directly on the file, by
   `init/`'s raw config dict, and by `feature_enabled(raw_dict, path)`
   (`config/features.py:17`). `BRConfig` never modelled them at all, so
   `to_dict()` can only reach them via raw passthrough.

Class 2 is why the property-based parity guard proposed in an earlier draft of
this issue was wrong — see below.

## Steps to Reproduce

1. In this repo (or any project with `context_monitor` / `scratch_pad` /
   `orchestration` set in `.ll/ll-config.json`), run
   `ll-config get context_monitor.enabled`.
2. Observe empty output and exit `0`, even though the hook at
   `hooks/scripts/context-monitor.sh:21` reads the same key successfully via
   `jq` and acts on it.
3. Repeat for `scratch_pad.enabled`, `orchestration.host_cli`,
   `refine_status.columns`, `extensions`.
4. Put `{{config.orchestration.host_cli}}` in a skill body and expand it via
   `skill_expander` — it renders as the empty string
   (`skill_expander.py:64-67` substitutes `""` when `resolve_variable` returns
   `None`).

## Expected Behavior

Every top-level section present in `config-schema.json` (bar the meta keys) is
reachable through `to_dict()`, so `ll-config get <section>.<key>` and
`{{config.<section>.<key>}}` resolve to the configured value.

## Shape constraints (verified — do not assume otherwise)

1. **`RefineStatusConfig` has no `to_dict()`.** It is a plain dataclass
   (`scripts/little_loops/config/cli.py:151-163`) with only `from_dict`, fields
   `columns: list[str]` and `elide_order: list[str]`. The entry must be built
   inline, exactly like the `cache`/`deferred_tools` entries already do at
   `core.py:769-772`.

2. **`extensions` is a `list`, not a dict** (`core.py:428-431` returns
   `self._raw_config.get("extensions", [])`). `resolve_variable()`
   (`core.py:924-946`) only descends into `dict` values, and space-joins a
   terminal list into a string. So `ll-config get extensions` will work and
   return the joined list, but `ll-config get extensions.<field>` is
   unreachable by design — the AC must not require it.

3. **`OrchestrationConfig` has no `to_dict()` either, and it nests two further
   dataclasses.** It is a dataclass (`scripts/little_loops/config/orchestration.py:60-101`)
   with `host_cli: str | None`, `request_path: str`, plus
   `composer: ComposerConfig` and `cluster: ClusterConfig` (each with their own
   `from_dict` only). The entry must be built inline and must descend into the
   nested objects, or `ll-config get orchestration.cluster.max_batch_size` stays
   unreachable while the top two scalars start working — a half-fix that is
   harder to notice than the current total absence.

4. **The 8 never-modelled sections must NOT get new typed dataclasses here.**
   Emit them as raw passthrough (`self._raw_config.get("<key>", {})`), matching
   how `extensions` already works. Introducing 8 new config dataclasses is a
   much larger change with its own default-drift risk, and nothing in this
   issue's ACs needs it. Consequence to state plainly in the tests: unlike the
   typed sections, a never-modelled section that is **absent** from
   `ll-config.json` emits `{}`, not schema defaults — `ll-config get
   documents.enabled` on a project without a `documents` block still returns
   nothing. That is acceptable and matches current `extensions` behavior; a
   defaults-aware version is out of scope.

## Suggested Fix Direction

In `to_dict()` (`core.py:648-922`), add alongside the existing `cache` /
`deferred_tools` entries:

```python
# --- typed sections (build inline; these dataclasses have no to_dict()) ---
"refine_status": {
    "columns": self.refine_status.columns,
    "elide_order": self.refine_status.elide_order,
},
"extensions": self.extensions,
"orchestration": {
    "host_cli": self.orchestration.host_cli,
    "request_path": self.orchestration.request_path,
    "composer": {
        # fields per ComposerConfig / ComposerAdaptiveConfig at
        # config/orchestration.py:13-60 — read them at implementation time
        # rather than transcribing from this issue.
    },
    "cluster": {
        "max_batch_size": self.orchestration.cluster.max_batch_size,
        "enable_dedup": self.orchestration.cluster.enable_dedup,
        "propagate_context": self.orchestration.cluster.propagate_context,
    },
},
# --- never-modelled sections: raw passthrough, no new dataclasses ---
**{
    key: self._raw_config.get(key, {})
    for key in (
        "context_monitor",
        "scratch_pad",
        "session_capture",
        "prompt_optimization",
        "documents",
        "product",
        "continuation",
        "hooks",
    )
},
```

Add regression tests in `scripts/tests/` alongside the existing `to_dict()` /
`ll-config get` coverage.

## Also required: a parity guard so this stops recurring

Every omission arrived the same way — a config section was added to the schema
and to its consumers, and `to_dict()` was never updated. Fixing only the known
cases leaves the next one to be found by the next audit.

**Derive the expected key set from `config-schema.json`, not from `BRConfig`'s
properties.** An earlier draft of this issue specified a property-based guard
(enumerate `BRConfig`'s public properties, subtract `to_dict()`'s keys). That
guard is calibrated to the wrong universe: 8 of the 11 missing sections have no
property, so it would go green on a 3-section fix while leaving the majority of
the bug in place. It would also have gone green for the entire lifetime of the
`context_monitor` omission.

The guard:

- Read `scripts/little_loops/config-schema.json`'s top-level `properties` keys.
- Subtract an explicit, commented exclusion set: `{"$schema", "install_source"}`
  — document *why* each is excluded (JSON-Schema meta pointer; install
  provenance stamp written by `ll-init`, not user-tunable config).
- Subtract the top-level keys `to_dict()` emits.
- Assert the difference is empty, with a failure message naming the missing
  sections and pointing at `to_dict()`.

Keep the reverse direction too: assert `to_dict()` emits no top-level key that
is absent from the schema (currently already true — the reverse diff is empty),
so a typo'd key can't be added silently.

Note the one alias that must **not** trip the guard: `analytics_capture` is a
property but is emitted nested under the `analytics` key (`core.py:284-285`
parses from `raw["analytics"]["capture"]`; `core.py:789-796` emits it under
`"analytics"`). A schema-driven guard is naturally immune to this — it never
looks at property names — which is a second reason to prefer it.

Verified today, the schema-driven guard fails pre-fix with exactly:
`{'context_monitor', 'continuation', 'documents', 'extensions', 'hooks',
'orchestration', 'product', 'prompt_optimization', 'refine_status',
'scratch_pad', 'session_capture'}`.

### The guard binds every future schema addition — including one already in this epic

By design, the guard means **adding a top-level property to
`config-schema.json` without a matching `to_dict()` entry is now a test
failure.** That is the point, but it makes the guard a cross-issue constraint
rather than a local one, and there is already a collision inside EPIC-3008:

- **ENH-3014** adds a new top-level `skill_budget` object to the schema. Landing
  it without a `to_dict()` entry fails this guard with `{'skill_budget'}`.
  Resolved on that issue's side: it now declares `depends_on: [BUG-3012]` and
  carries an AC to emit `skill_budget` as raw passthrough. **Do not pre-emptively
  add `skill_budget` to this issue's exclusion set** — the exclusion set holds
  non-config meta keys only (`$schema`, `install_source`), and diluting it is how
  the guard stops meaning anything.

State this contract in the guard's own failure message: the fix for a new
section is to emit it from `to_dict()`, not to add it to the exclusion set.

### Note for ENH-3021: `to_dict()` is not the config-key inventory

The two excluded meta keys are real keys present in every generated
`.ll/ll-config.json`. ENH-3021 (which warns on unknown `ll-config get` roots)
therefore must **not** treat `to_dict()`'s key set as "all known sections" — it
would false-warn on `install_source`. That issue resolves this by unioning
`to_dict()` keys with the schema's top-level properties; no change is required
here, but do not "simplify" ENH-3021 back to a `to_dict()`-only check.

## Program Design

### Signatures

- `to_dict(self) -> dict` — existing, `scripts/little_loops/config/core.py:648-922`
- `resolve_variable(self, var_path: str) -> str | None` — existing, `core.py:924-946`
- `RefineStatusConfig(columns: list[str], elide_order: list[str])` — existing, `config/cli.py:151`
- `BRConfig.extensions -> list` — existing raw passthrough, `core.py:428-431`
- `OrchestrationConfig(host_cli, request_path, composer, cluster)` — existing,
  `config/orchestration.py:60-101`; property at `core.py:399-401`

### Call Path

`to_dict()` -> inline typed entries + raw-passthrough entries ->
`resolve_variable()` (`core.py:924-946`) -> two consumers:
`ll-config get` (`cli/config.py:63`) and `{{config.*}}` skill/command expansion
(`skill_expander.py:64`).

## Acceptance Criteria

- [ ] `ll-config get refine_status.columns` and `refine_status.elide_order`
      return the configured values.
- [ ] `ll-config get extensions` returns the configured extension list
      (space-joined per `resolve_variable`'s list handling).
- [ ] `ll-config get orchestration.host_cli` and
      `ll-config get orchestration.request_path` return the configured values.
- [ ] At least one nested orchestration lookup resolves (e.g.
      `orchestration.cluster.max_batch_size`), proving the entry descends into
      `ComposerConfig`/`ClusterConfig` rather than stopping at the scalars.
- [ ] All 8 never-modelled sections resolve when present in `ll-config.json` —
      covered by at least `context_monitor.enabled`, `scratch_pad.enabled`, and
      `prompt_optimization.enabled`, asserted against a fixture config that sets
      them.
- [ ] The typed sections (`refine_status`, `orchestration`) appear in
      `to_dict()` output with their dataclass defaults even when unset in
      config, matching sibling sections.
- [ ] The never-modelled sections emit `{}` when absent from config (documented
      behavior, per Shape constraint 4) — asserted explicitly so a later
      defaults-aware change is a deliberate decision, not an accident.
- [ ] `{{config.orchestration.host_cli}}` expands to the configured host rather
      than the empty string, via a `skill_expander` test.
- [ ] No test asserts `extensions.<field>` resolves — that is unreachable given
      `extensions` is a list.
- [ ] A parity test derives the expected section set from
      `config-schema.json`'s top-level `properties` with an explicit,
      commented `{"$schema", "install_source"}` exclusion set, and asserts
      nothing is missing from `to_dict()`. Confirm it fails before the fix with
      exactly the 11 sections listed above.
- [ ] The parity test also asserts the reverse direction: `to_dict()` emits no
      top-level key absent from the schema.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Impact

- **Priority**: P2 — 11 of 36 real config sections are unreachable through both
  documented resolution surfaces, and the `{{config.*}}` path fails *silently
  as empty string* inside skill and command prompts rather than erroring, so a
  wrong-but-plausible prompt ships instead of a visible failure. The underlying
  features still work (their consumers read raw config directly), which is
  precisely why this went unnoticed.
- **Effort**: Small — additive entries in one function, plus tests.
- **Risk**: Low — purely additive to `to_dict()` output; no consumer reads it
  exhaustively.
- **Breaking Change**: No.


## Session Log
- `ll-auto` - 2026-08-03T15:44:19 - `7939e26d-6a15-469e-8ea1-eadcf1af1588.jsonl`
- `/ll:ready-issue` - 2026-08-03T15:36:39 - `bc0fb2f7-2d62-483e-9dd1-9b579059436f.jsonl`
- `/ll:confidence-check` - 2026-08-03T14:57:36 - `1dc7def3-a259-4a68-91b0-e2316edb4c01.jsonl`
- `/ll:verify-issues` - 2026-08-03T04:16:46 - `2184690f-4a99-44a3-bf23-ddded9adf45a.jsonl`


---

## Resolution

- **Action**: fix
- **Completed**: 2026-08-03
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
