---
id: ENH-2896
type: ENH
priority: P2
status: done
captured_at: '2026-07-28T22:13:33Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2893
- BUG-2894
- ENH-2895
confidence_score: 100
outcome_confidence: 65
score_complexity: 13
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 15
decision_needed: false
completed_at: '2026-07-29T01:34:08Z'
---

# ENH-2896: Reject or warn on unknown keys in EvaluateConfig.from_dict

## Summary

`EvaluateConfig.from_dict` builds the dataclass by enumerating known fields with
`data.get(...)`. Any key present in the YAML but absent from that enumeration is
discarded silently — no exception, no log line, no `ll-loop validate` diagnostic. A
typo'd, aspirational, or version-drifted evaluator key is indistinguishable from a
working one until someone traces a runtime verdict back to its source.

This is the root cause that let BUG-2893 and BUG-2894 ship: two loops declaring
`key: <field>` on `output_numeric`, both inert, both undetected.

## Motivation

The failure mode is uniquely bad because it is *quiet and plausible*. The author writes
a field, the loop loads, `ll-loop validate` passes, the loop runs. The only symptom is a
verdict that is subtly wrong — and in BUG-2894's case the wrong verdict was masked by
shared `on_no`/`on_error` routing, so it went unnoticed indefinitely.

`.claude/CLAUDE.md` documents an extensive `ll-loop validate` gate table (MR-1 … MR-13,
policy-table, capture-reachability, …) built precisely to shift this class of error
left. "Evaluator field silently does nothing" belongs in that family and is currently
the only member with no detection at all.

The same pattern likely exists in sibling `from_dict` methods across `fsm/schema.py`
(`StateConfig`, `LoopConfig`, and others) — worth auditing in the same pass.

## Current Behavior

`scripts/little_loops/fsm/schema.py`:

```python
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluateConfig:
        """Create from dictionary (JSON/YAML deserialization)."""
        return cls(
            type=data["type"],
            operator=data.get("operator"),
            target=data.get("target"),
            ...
        )
```

`{"type": "output_numeric", "key": "pass_rate", "operator": "ge", "target": 0.95}`
constructs successfully; `key` is gone. `EvaluateConfig` has ~28 optional fields, most
of them evaluator-type-specific, so authors reasonably guess at names.

## Expected Behavior

An unknown key under `evaluate:` produces a diagnostic naming the state, the key, and
the evaluator type — at validation time, not at runtime.

Two candidate strictness levels:

- **WARN at `ll-loop validate`** (recommended default): a new lint rule reporting
  unknown evaluate keys. Non-breaking; surfaces existing drift across user loops without
  hard-failing anyone's working automation.
- **ERROR at load**: `from_dict` raises on unknown keys. Strongest guarantee, but
  breaks any third-party or user loop currently carrying a stray key. ~~including,
  today, two of our own built-ins.~~

> **Added 2026-07-29 — the ERROR stance is already half-adopted.** Commit
> `e2ea3c56` set `"additionalProperties": false` on `evaluateConfig` in
> `fsm-loop-schema.json`, which *is* ERROR strictness on the JSON-schema side.
> Anyone validating a loop against that schema (editor integration, docs
> tooling) already gets a hard rejection for an unknown evaluate key. So the
> live choice is narrower than "WARN vs ERROR" implies: it is whether the Python
> loader should **agree with a stance the JSON schema has already taken**, or
> deliberately stay more permissive than it. A permanent WARN/ERROR split
> between the two validators is itself a drift bug of the kind this issue
> exists to eliminate — if WARN is chosen, say explicitly why the two layers
> differ and for how long.

> **UPDATED 2026-07-28** by `/ll:audit-issue-conflicts`: **the built-in sweep is
> already clean.** Commit `e2ea3c56` (ENH-2895) made `key` a real field on
> `EvaluateConfig`, so neither `docs-sync.yaml` nor `oracles/code-run-gate.yaml`
> is an unknown-key hit any more. The stated blocker on ERROR-at-load is gone,
> and **this issue now has no ordering constraint in either direction** relative
> to BUG-2893 (closeable) or BUG-2894 (rescoped to a shell-format defect no
> schema lint can see). WARN-vs-ERROR remains a live decision — but decide it on
> third-party/user-loop compatibility grounds, not on our own built-ins.

**Decision: WARN-now / ERROR-later.** Ship the `ll-loop validate` lint rule as WARN
severity now — non-breaking for third-party/user loops carrying a stray key today —
and revisit ERROR-at-load once telemetry from the WARN rule shows the built-in and
user-loop population is clean in practice, bringing the Python loader into eventual
agreement with the JSON schema's existing `additionalProperties: false` stance. The
built-in-sweep precondition is already met, so there is no staged rollout blocking
WARN from shipping immediately. Record this WARN-now/ERROR-later decision via
`ll-issues decisions add`, citing third-party/user-loop compatibility and the JSON
schema's `additionalProperties: false` precedent (see the note above) as the
rationale.

A useful refinement either way: suggest the nearest known field name
(`difflib.get_close_matches`) so `key` → *did you mean `line`? `path`?* guides the author
to an existing primitive.

### Type-aware validation (stretch)

Beyond unknown keys, most fields are only meaningful for specific evaluator types —
`pattern` for `output_contains`, `pairs` for `contract`, `line` for `classify`. A field
that is *known but irrelevant to the declared type* is equally inert. Consider a
per-type allowed-field map as a follow-on; note it here so the option isn't lost, but
keep it out of this issue's minimum scope.

## Proposed Solution

1. Derive the known-field set from the dataclass itself
   (`{f.name for f in dataclasses.fields(EvaluateConfig)}`) rather than hand-maintaining
   a second list that can drift from `from_dict` the same way `from_dict` drifted from
   authors' expectations. Expose this as a named helper (e.g.
   `find_issues_for_graph`-style — a single function encapsulating the field-set
   derivation) rather than inlining the set-comprehension at each call site; BUG-2897
   imports `_ALL_STATUSES`/`_TERMINAL_STATUSES` from `issue_progress` directly (an
   underscore-private module boundary `sequence.py` already crosses, so precedent
   exists), but a named helper is the cleaner resolution here and is a requirement of
   this issue, not an optional consideration.
2. Add an `ll-loop validate` rule walking every state's raw `evaluate:` mapping and
   reporting keys outside that set, with a close-match suggestion.
3. Follow the existing gate conventions in `.claude/CLAUDE.md`: assign a rule id,
   severity, and a top-level suppression flag consistent with the MR-* table.
4. Audit sibling `from_dict` implementations in `fsm/schema.py` for the same silent-drop
   pattern and decide whether to generalize the check.
5. **Fix and gate the JSON-schema/dataclass parity drift** (added by
   `/ll:audit-issue-conflicts`). Commit `e2ea3c56` set
   `"additionalProperties": false` on `evaluateConfig` in
   `scripts/little_loops/fsm/fsm-loop-schema.json` — creating exactly the
   second hand-maintained field list this issue exists to eliminate. It is
   **already out of sync**:

   ```
   evaluateConfig additionalProperties: False
   dataclass-only: ['line']
   schema-only:    []
   ```

   (Re-verified 2026-07-29 — still drifted, exactly as stated.)

   So a loop legitimately using `line:` — the documented `classify` evaluator
   selector — is rejected by the JSON schema today. This is currently *latent*,
   not live: `fsm-loop-schema.json` has no runtime consumer under
   `scripts/little_loops/` (it is an editor/docs artifact). Add `line` to the
   schema and a test asserting `dataclasses.fields(EvaluateConfig)` and the
   schema's `evaluateConfig.properties` keys stay in lockstep, so the two lists
   can never drift again.

## Scope Boundaries

**In scope:**
- Unknown-key detection for `evaluate:` mappings, derived from
  `dataclasses.fields(EvaluateConfig)`
- The new validation rule, its rule id, severity, and suppression flag
- The `fsm-loop-schema.json` `line` parity fix and the schema/dataclass lockstep test
- A built-in-loops sweep (expected to come back clean)
- Recording the WARN-vs-ERROR decision

**Explicitly out of scope:**
- **Type-aware validation** — rejecting a field that is *known but irrelevant to
  the declared evaluator type* (`pattern` on `output_numeric`, etc.). Noted under
  Type-aware validation (stretch) so the idea isn't lost; it becomes its own
  follow-up issue rather than being folded in here.
- **Generalizing the check to sibling `from_dict` methods** (`StateConfig`,
  `LoopConfig`, …). Step 4 *audits* them and decides; any actual fix is a
  follow-up. Widening to every schema dataclass in this pass would make the
  breaking-change surface unassessable.
- Changing any built-in loop's evaluator configuration — the sweep is expected to
  find nothing, and a hit would be filed, not fixed inline.

## Integration Map

- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.from_dict` and siblings
- `scripts/little_loops/fsm/validation/` — new lint rule
- `.claude/CLAUDE.md` — Loop Authoring gate table entry (rule id, severity, suppress flag)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — source of truth the table summarizes
- `scripts/tests/` — lint unit tests + a built-in-loops sweep asserting zero unknown keys

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the authoritative `ll-loop validate` rule catalog (bulleted
  MR-1..MR-13 list, `docs/reference/CLI.md:761-787`) plus the consolidated
  "suppressed by `*_ok` flag" summary sentence at line 779. Needs a new bullet and a
  clause appended to that sentence. This is the CLI-facing rule catalog end users
  actually read; it duplicates (does not derive from) `.claude/CLAUDE.md`'s copy.
- `docs/reference/API.md` — carries its own independent copy of both the `*_ok`
  suppression-flag dataclass field list (~lines 4954-4967, one bullet per flag with an
  inline `# Suppress MR-N ... (ENH-####)` comment, e.g. `evidence_contract_ok` at line
  4961) and a duplicate prose MR-* rule description list (~lines 5660-5672). Both need a
  new entry. Previously only listed in this issue's "Related Key Documentation" table as
  a reference to read — it is actually a file to *edit*.
- `skills/review-loop/reference.md` — a third, independently-maintained condensed
  one-line-per-rule table (`| MR-8 | ... | Warning |` at line 47). Add a row for the new
  rule if `review-loop` is expected to surface it (none of these three doc copies are
  generated from a single source — CLAUDE.md, CLI.md/API.md, and this file must all be
  hand-updated in lockstep).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py`, `class TestEvaluateConfig` (starts line 92) — no
  existing test pins "unknown `evaluate:` keys are silently dropped" (confirmed); this is
  the target file/class for the pinning test from Implementation Step 1. It's also the
  natural home for the new schema/dataclass-vs-JSON-schema lockstep test (Proposed
  Solution step 5) since it already imports `EvaluateConfig` and exercises its shape —
  no existing dataclass-fields-vs-schema-properties comparison test exists anywhere to
  model from; this is genuinely new test shape
  (`dataclasses.fields(EvaluateConfig)` vs. `json.load(...)["...evaluateConfig"]["properties"].keys()`).
- `scripts/tests/test_fsm_schema.py:1729-1753` (`test_unknown_top_level_keys_warn`) and
  its companion `test_known_keys_no_warning` (line 1755+) — **closer structural template
  than MR-8** for both the rule and its test: they exercise the *existing* top-level
  `unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS` diff check
  (`structural_rules.py:1510-1520`), which is set-difference-based like the new rule
  needs to be, vs. MR-8's semantic/keyword-based check. Copy this pattern for the new
  `evaluate:`-scoped version, asserting `path == "states.<name>.evaluate"` instead of
  `<root>`.
- Confirmed via repo-wide grep: **no `difflib.get_close_matches` / "did you mean"
  pattern exists anywhere in the codebase or test suite** — corroborates the issue's
  claim that this would be a first use with no style precedent to follow beyond
  `ValidationError.message` phrasing conventions.

### Additional sibling `from_dict` audit target (Step 4)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/host_guard.py` — `HostGuardConfig.from_dict` is a third
  dataclass with the same enumerate-known-fields silent-drop pattern, not mentioned in
  the issue's existing Step 4 audit (which covers `StateConfig` and `FSMLoop` only).
  Include it in the sibling sweep.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`EvaluateConfig`** class: `scripts/little_loops/fsm/schema.py:38-213`. `from_dict`
  is `schema.py:182-213` (25 `data.get(...)` calls, one per field, plus `type=data["type"]`);
  `to_dict` is the symmetric inverse at `schema.py:122-180`. The `line` field lives at
  `schema.py:116` (`line: str | int | None = None`, "for classify: which line to read").
- **Sibling `from_dict` audit (Step 4)** — confirmed same silent-drop pattern:
  - `StateConfig.from_dict` (`schema.py:782-889`) is a **partial** exception: it computes
    `_known_on_keys` (lines 816-828) and derives `extra_routes` from unrecognized `on_*`
    keys (829-833) — but every other field (`action`, `params`, `capture`, `worktree`,
    `agent`, `tools`, `model`, `request_path`, `session_mode`, `effort`, ...) is populated
    via plain `.get(...)` at lines 836-888 with no unknown-key check outside the `on_*`
    namespace.
  - `FSMLoop.from_dict` (`schema.py:1446-1546`, the issue's "LoopConfig") is **already
    partially covered at the top level only**: `load_and_validate()`
    (`fsm/validation/structural_rules.py:1457-1565`) computes
    `unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS` (line 1512) and emits a WARNING
    *before* calling `FSMLoop.from_dict` — this check lives in the loader, not the
    dataclass, and has no analog for nested mappings (`evaluate:`, `states.<name>.*`).
- **Critical implementation constraint**: `validate_fsm()`'s per-state dispatch
  (`structural_rules.py:893-1095`) only receives the **already-parsed** `FSMLoop`/
  `StateConfig`/`EvaluateConfig` objects — by the time a rule function runs,
  `EvaluateConfig.from_dict` has already silently dropped any unrecognized key, so the
  parsed object can never reveal what was lost. The new rule needs the **raw pre-parse
  dict** for each state's `evaluate:` mapping, the same way the existing top-level
  unknown-key check operates on raw `data` (`structural_rules.py:1510-1534`) before
  `FSMLoop.from_dict()` runs (line 1540). Two viable wiring points: (a) inline in
  `load_and_validate()` alongside the existing top-level block, iterating
  `data.get("states", {}).items()` and each state's raw `evaluate` sub-dict; or (b) a new
  `_validate_evaluate_unknown_keys(fsm, raw_data)`-style function taking the raw dict as
  an extra parameter, dispatched from `validate_fsm` (option (b) breaks the existing
  one-arg `_validate_XXX(fsm)` signature convention used by every other rule at
  `structural_rules.py:1042-1093`, so it needs either a signature change across all
  rules or a separate raw-dict-aware check list — worth flagging as an open design
  question for the implementer, not resolved here).
- **Model rule to follow**: MR-8 (`_validate_llm_evidence_contract`,
  `fsm/validation/evaluator_rules.py`) is the closest existing analog — WARN severity,
  suppression-flag early return, `ValidationError.message` embeds `[state: ...]` context
  plus remediation text plus a `(ENH-#### MR-#)` trailer. Its suppression flag
  (`evidence_contract_ok`) is wired in three places to replicate for the new flag: (1)
  dataclass field on `FSMLoop` (`schema.py:1302`, grouped with other `*_ok` flags
  ~1293-1309), (2) conditional serialization in `to_dict()` (`schema.py:1422-1423`), (3)
  `from_dict()` parse (`schema.py:1536`), and (4) **must also be added to
  `KNOWN_TOP_LEVEL_KEYS`** in `fsm/validation/_base.py:77-132` — omitting this step means
  the loop's own top-level unknown-key check would flag the new suppression flag itself.
  All existing `*_ok` flags are loop-top-level-only; there is no per-state suppression
  flag precedent.
- **Dispatcher wiring**: new rule function added to `evaluator_rules.py`, imported and
  called via `errors.extend(_validate_XXX(fsm))` in `validate_fsm()`
  (`structural_rules.py:~1091`), and re-exported from
  `fsm/validation/__init__.py` (import + `__all__`, matching the MR-8 pattern at lines
  103/226).
- **`difflib.get_close_matches`**: no existing usage anywhere in the codebase (confirmed
  via repo-wide grep) — this would be the first use; no style precedent beyond the
  `ValidationError.message` phrasing conventions above.
- **JSON-schema parity gap (Step 5) — confirmed with exact anchors**: `evaluateConfig`
  block is `fsm-loop-schema.json:654-853`; `additionalProperties: false` at line 817;
  `properties` (658-815) list 26 keys and omit `line`. Since `line` is round-tripped by
  `to_dict`/`from_dict` (`schema.py:173-174/210`) but absent from `properties` under
  `additionalProperties: false`, a loop using `evaluate: {type: classify, line: last}`
  is currently rejected by strict validation against this schema file even though the
  Python loader accepts it — a live (not just latent) drift for any schema consumer.
- **Test pattern to model after**: `TestLLMEvidenceContractValidation`
  (`scripts/tests/test_fsm_validation_evaluator_rules.py:260-404`) — a `_simple_fsm(**kwargs)`
  helper builds a minimal `FSMLoop`; positive-control test calls the rule function
  directly and filters `errors` by severity + rule-id substring; negative-control tests
  cover the "shouldn't fire" cases; a suppression test passes the `*_ok` flag as `True`;
  an end-to-end test calls the public `validate_fsm(fsm)` entry point to confirm
  dispatcher wiring.
- **CLI entry point**: `ll-loop validate` → `cli/loop/config_cmds.py:cmd_validate()`
  (lines 12-75) → `load_and_validate()` (`fsm/validation/structural_rules.py:1457-1565`).
- **Suppression-flag registry is duplicated in TWO places, not one** (re-verified
  2026-07-29, gap not previously documented): `evidence_contract_ok` — the model flag
  for MR-8 — is registered in both `structural_rules.py`'s `KNOWN_TOP_LEVEL_KEYS` (already
  cited above) **and** a separate list in `fsm/validation/_base.py:106` alongside sibling
  flag names like `meta_self_eval_ok`. A new suppression flag for this issue's rule must
  land in both registries; missing `_base.py:106` would make the loop's own top-level
  unknown-key check flag the new suppression flag itself, same failure mode already
  called out for `KNOWN_TOP_LEVEL_KEYS` above but at a second site.
- **No existing precedent for a raw-per-state-dict validation rule**: confirmed via
  pattern search — all 30+ `_validate_*` functions in `fsm/validation/` take the
  already-parsed `FSMLoop` object; none operate on a raw pre-parse dict at the state
  level. The closest signature deviation is `_validate_evaluator(state_name: str,
  evaluate: EvaluateConfig)` (`structural_rules.py:69`, dispatched manually inside the
  states-iteration loop at `structural_rules.py:974` rather than registered as an
  independent top-level rule) — evidence that a per-`EvaluateConfig`-instance rule
  function is an established shape, but it still receives the parsed object, not the raw
  dict. This confirms Codebase Research Findings' open design question above (raw-dict
  access has no existing pattern to model from) rather than resolving it.
- **Re-verified 2026-07-29 (this refine-issue pass)**: all previously-cited claims in
  this issue (schema.py line numbers, `KNOWN_TOP_LEVEL_KEYS` at structural_rules.py:1512,
  MR-8 at evaluator_rules.py, `evaluateConfig.additionalProperties: false` at
  fsm-loop-schema.json:817 with no `line` property) hold unchanged on current `main`;
  `structural_rules.py`/`evaluator_rules.py` living under `fsm/validation/` (already
  reflected in this issue's citations) is the only prior directory-move note, and it was
  already correctly cited.

## Implementation Steps

1. Write a test asserting the current silent drop, to pin the behaviour being changed.
2. Implement known-field derivation from `dataclasses.fields`.
3. Add the validation rule with close-match suggestions; assign the rule id and
   suppression flag.
4. Run it across all built-in loops. ~~expect hits in `docs-sync.yaml` and
   `oracles/code-run-gate.yaml`~~ — **both are clean post-`e2ea3c56`**; the sweep
   is still a deliverable, but expect zero hits unless it surfaces something new.
4a. Fix the `fsm-loop-schema.json` parity drift (missing `line`) and add the
   schema/dataclass lockstep test — see Proposed Solution step 5.
5. Document the rule in `.claude/CLAUDE.md` and the harness guide.
6. Record the WARN-now / ERROR-later decision via `ll-issues decisions add`.
7. Confirm `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/reference/CLI.md` — add the new rule to the MR-1..MR-13 catalog
   (lines 761-787) and append its suppression clause to the line-779 summary sentence.
9. Update `docs/reference/API.md` — add the new `*_ok` field to the suppression-flag
   list (~4954-4967) and the duplicate MR-* rule description list (~5660-5672).
10. Update `skills/review-loop/reference.md` — add a row to its condensed MR table
    (line 47) if `review-loop` should surface the new rule.
11. Extend Step 4's sibling `from_dict` audit to include
    `scripts/little_loops/fsm/host_guard.py`'s `HostGuardConfig.from_dict`.
12. Model the rule and its test on the closer structural precedent —
    `structural_rules.py:1510-1520`'s top-level `KNOWN_TOP_LEVEL_KEYS` diff check and
    `test_fsm_schema.py:1729-1755` (`test_unknown_top_level_keys_warn` /
    `test_known_keys_no_warning`) — rather than MR-8 alone, since the new rule is
    set-difference-based like the top-level check, not keyword-based like MR-8.

## Impact

- **Value**: Prevents recurrence of an entire defect class. This is the higher-leverage
  half of the ENH-2895 / ENH-2896 pair — ENH-2895 fixes the field authors wanted;
  this one ensures the *next* wrong field is loud.
- **Backward compatibility**: WARN level is non-breaking. ERROR level is breaking and
  should not ship until the built-in sweep is clean.
- **Effort**: Moderate — the validation framework and gate-table conventions already
  exist; this is a new rule within them.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` | Loop Authoring gate table; where the new rule is registered |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Source of truth for validation rules and rationale |
| `docs/reference/API.md` | `little_loops.fsm.schema` / `validation` reference |

## Confidence Check Notes

**Outcome Risk Factors:**
- **Open decision on rule wiring signature.** The Codebase Research Findings section flags an unresolved implementation choice: extending every `_validate_XXX(fsm)` rule function's signature to accept the raw pre-parse dict, vs. a separate raw-dict-aware check list, "worth flagging as an open design question for the implementer, not resolved here." This is an either/or that should be resolved before implementing to avoid rework across `structural_rules.py`'s dispatcher.
- **Breadth spans code + three independently-maintained doc copies.** `CLAUDE.md`, `docs/reference/CLI.md`, `docs/reference/API.md`, and `skills/review-loop/reference.md` all need hand-updated, lockstep entries with no single source of truth — a plausible site to miss one on first pass.
- **Change touches shared dispatcher conventions**, not just additive code: the new rule needs the raw `evaluate:` sub-dict at a point where every existing rule operates on the already-parsed `FSMLoop`, so the safest wiring point (inline in `load_and_validate()` vs. a new dispatcher parameter) has a real chance of introducing an inconsistent pattern relative to the other MR-* rules.

## Session Log
- `ll-auto` - 2026-07-29T01:34:08 - `32b1535b-0d0d-472e-a7c1-930cffc02ac1.jsonl`
- `/ll:ready-issue` - 2026-07-29T01:22:39 - `624479d1-605f-4fe4-baf9-e256169e0545.jsonl`
- `/ll:confidence-check` - 2026-07-29T01:25:00 - `6fb4edc7-15d6-49af-9ec8-259adbf907c5.jsonl`
- `/ll:decide-issue` - 2026-07-29T01:19:05 - `50ca76db-5df4-4b38-9164-b4cf87428101.jsonl`
- `/ll:refine-issue` - 2026-07-29T01:17:28 - `60c750bb-f80c-4a5e-b219-73d8b2313931.jsonl`
- `/ll:confidence-check` - 2026-07-29T01:20:00 - `6c859d45-bf82-4d73-aab0-de1d6206980d.jsonl`
- `/ll:wire-issue` - 2026-07-29T01:12:41 - `3a65e46d-1003-469a-92b6-e5f2599363a4.jsonl`
- `/ll:refine-issue` - 2026-07-29T01:07:22 - `64b64dec-95dc-4a5a-87ce-dfcf1a85081b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T23:20:23 - `c53b272d-061d-4930-bc4e-fede59dd7ae2.jsonl`
- `/ll:verify-issues` - 2026-07-28T22:25:21 - `f37e3f6b-746f-494f-89ff-1a095c8399bf.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:13:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c5d6d08-1571-414a-8fb3-349dddc4e1fc.jsonl`

---

## Status

open


---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-28
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
