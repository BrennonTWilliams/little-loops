---
id: ENH-2677
title: Consistent user-configurability across history.db issues
status: cancelled
priority: P3
type: ENH
discovered_date: 2026-07-18
discovered_by: ll-product-promotion
labels:
- history-db
- config
decision_needed: false
relates_to:
- ENH-2678
---

# ENH-2677: Consistent user-configurability across history.db issues

Origin: ll-product #ENH-011

## Summary

EPIC-1707 ("history.db as Agent Context Layer") is built across many issues touching history.db read/consume behavior. Today those issues use inconsistent config namespaces and some hardcode thresholds instead of exposing them via config. This issue standardizes on one convention: `history.*` config keys for the read/consume side, with a "config-or-default, never-raise" contract (the pattern already used by `AnalyticsCaptureConfig`/`analytics_capture` in `scripts/little_loops/config/core.py` and `config/features.py`).

## Problem

- **Missing primitive**: no `ll-config get <key>` CLI, no top-level `history` object in `config-schema.json`, no `HistoryConfig` dataclass, no `BRConfig.history` property. Markdown skills cannot read config directly — any consumer needing config-gating must self-gate through a Python CLI.
- **Namespace fragmentation**: read/consume tunables are split across `history.*` (e.g. `velocity_window`, `effort_fields`, `max_age_days`, `session_digest.*`, `planning_skills`), `analysis.evolution.*` (a done issue's threshold config), and `analytics.retention.*` (write/storage side) — three namespaces for what should be one read-side namespace.
- **Hardcoded thresholds** in some already-completed consumers (e.g. a `-0.2` correction-confidence penalty and a `>70%` dup-overlap threshold with no config exposure at all).

## Proposed convention

- `analytics.*` = capture/write side (what gets recorded into history.db): `enabled`, `capture.*`, `retention.*`.
- `history.*` = read/consume side (how recorded data is surfaced to agents): windows, fields, sections, which-skills, thresholds. Any threshold currently under `analysis.evolution.*` moves to `history.evolution.*`.
- Config is read in Python via `BRConfig` only, never in markdown skills — every consumer that needs to self-gate does so through a Python CLI entry point, following the `AnalyticsCaptureConfig` template (`features.py` dataclass + `core.py` property, lenient `from_dict` using `data.get(...)` with defaults).

## Proposed Implementation

1. Add a top-level `history` object to `config-schema.json` alongside the existing `analytics` object (which uses `additionalProperties: false`, so `history` should follow the same strict-schema convention).
2. Add a `HistoryConfig` dataclass to `scripts/little_loops/config/features.py`, modeled on `AnalyticsCaptureConfig` (`features.py:425`), with lenient `from_dict`.
3. Add a `BRConfig.history` property to `scripts/little_loops/config/core.py`, modeled on the `analytics_capture` property (`core.py:313`).
4. Migrate any issue/consumer currently using `analysis.evolution.*` thresholds to `history.evolution.*`.
5. For already-done consumers with hardcoded thresholds (correction-confidence penalty, dup-overlap threshold, correction-detection regex), expose them under `history.*` in a follow-up pass rather than leaving them fixed.
6. Audit open EPIC-1707 child issues for `history.*` namespace consistency going forward.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Major finding: most of the Proposed Implementation is already done.** A prior
issue (ENH-1913, referenced in code docstrings) already built the exact
convention this issue proposes:

- **Step 1** (top-level `history` object in `config-schema.json`) — **already done**.
  `scripts/little_loops/config-schema.json:1751-1890` — a `history` block exists,
  described as "Single namespace owner for all history.db consumer tunables
  (ENH-1913)", with `additionalProperties: false` at every nesting level
  (`session_digest`, `evolution`, `go_no_go`, `capture_issue`, `compaction`),
  matching the `analytics` block's convention (`config-schema.json:1672-1745`).
- **Step 2** (`HistoryConfig` dataclass) — **already done**.
  `scripts/little_loops/config/features.py:1076` — `HistoryConfig` (fields:
  `velocity_window`, `effort_fields`, `max_age_days`, `db_path`,
  `planning_skills`, plus nested `SessionDigestConfig`/`EvolutionConfig`/
  `GoNoGoConfig`/`CaptureIssueConfig`/`CompactionConfig`), with a lenient
  `from_dict()` following the exact `AnalyticsCaptureConfig` template
  (`features.py:562`, `data.get(key, default)` per field, never raises).
- **Step 3** (`BRConfig.history` property) — **already done**.
  `scripts/little_loops/config/core.py:250` constructs
  `self._history = HistoryConfig.from_dict(self._raw_config.get("history", {}))`;
  exposed via the `history` property at `core.py:362-365`, mirroring
  `analytics_capture` (`core.py:358-360`). Round-tripped in `to_dict()` at
  `core.py:729-757`.
- **Step 4** (migrate `analysis.evolution.*` → `history.evolution.*`) —
  **already done**. `EvolutionConfig` (`features.py:970`) already lives under
  `history.evolution.*`; no `analysis.*` references remain anywhere in
  `scripts/little_loops/**/*.py`.
- **Step 5** (expose hardcoded thresholds under `history.*`) — **partially done**:
  - `dup_overlap_threshold` (`CaptureIssueConfig`, `features.py:1000`, default
    `0.7`) is schema-exposed **and** live-wired: read at
    `scripts/little_loops/issue_discovery/search.py:245` as
    `config.history.capture_issue.dup_overlap_threshold`.
  - `correction_penalty` (`GoNoGoConfig`, `features.py:989`, default `-0.2`) is
    schema-exposed but **not consumed at runtime** — `skills/go-no-go/SKILL.md:145`
    only references it as the template variable
    `{{config.history.go_no_go.correction_penalty}}` in prose; no Python code
    path reads `.history.go_no_go.correction_penalty` to actually apply the
    penalty to a score.
  - The correction-detection regex (`_CORRECTION_RE`/`_PHRASE_RE`/`_REMEMBER_RE`
    in `scripts/little_loops/session_store.py:284-305`, consumed by
    `is_correction()` at `session_store.py:308` and called from
    `record_correction()` and `hooks/user_prompt_submit.py:80`) has **zero**
    config exposure under any namespace — only the `extra_patterns` parameter
    (fed from `analytics.capture.correction_patterns`,
    `AnalyticsCaptureConfig.correction_patterns` at `features.py:575`) allows
    *appending* patterns; the three built-in regexes are architecturally
    immutable constants.
- **Step 6** (audit open EPIC-1707 children for namespace consistency) — a
  process/triage task, not a code gap; not verifiable by static analysis.
- **`ll-config get <key>` CLI** — confirmed **missing**, as the issue states.
  `scripts/pyproject.toml`'s `[project.scripts]` has no `ll-config` entry point
  and no `main_config`-style function exists under `little_loops.cli`. The
  closest existing primitive is `BRConfig.resolve_variable(var_path: str)` at
  `scripts/little_loops/config/core.py:830-852` (walks a dot-path through
  `to_dict()`), currently only consumed internally by
  `scripts/little_loops/skill_expander.py` for template variable substitution
  — not exposed as a standalone CLI a skill could shell out to.

### Test patterns to follow for remaining work

- `scripts/tests/test_config.py:3230-3362` — `TestEvolutionConfig`,
  `TestGoNoGoConfig`, `TestCaptureIssueConfig`, `TestHistoryConfig` each use a
  3-test shape (`test_defaults`, `test_per_key_override`,
  `test_unknown_key_ignored`) — model any new `ll-config` CLI tests and the
  `correction_penalty` wiring test after this.
- `scripts/tests/test_config_schema.py:388-522` — schema-declaration tests
  (`test_analytics_in_schema`, `test_history_in_schema`, etc.) assert
  `type == "object"` and `additionalProperties is False` per block.

### Revised scope (decision needed)

Given the above, the issue's Proposed Implementation is mostly stale. Two ways
to proceed:

> **Selected:** Option A — already-implemented claims verified true and tested; no codebase precedent or benefit for keeping this ID open (EPIC-1707 is already closed and this issue isn't parent-linked to it).

**Option A**: Close ENH-2677 as substantially already implemented (schema,
dataclass, property, and namespace migration all landed under prior
ENH-1913/1907/1914 work), and open a narrower follow-up issue scoped to just
the two concrete remaining gaps: (1) wire `GoNoGoConfig.correction_penalty`
into the go-no-go skill's actual scoring path instead of leaving it as
documentation-only prose, and (2) build an `ll-config get <key>` CLI wrapping
`BRConfig.resolve_variable()` so markdown skills can read config without a
bespoke Python entry point per consumer.

**Option B**: Keep ENH-2677 open and rewrite its Proposed Implementation
section in place to strike the four already-done steps and retain only the
two remaining gaps plus the Step 6 audit task, preserving the original issue
ID for EPIC-1707 rollup tracking.

**Recommended**: Option A — the schema/dataclass/property work is complete and
independently tested (`test_config.py`, `test_config_schema.py`); leaving a
mostly-done issue open under its original broad framing risks confusing
future readers about what's actually outstanding. A fresh, narrowly-scoped
issue is cheaper to implement and verify than editing this one's now-stale
Proposed Implementation section.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-18.

**Selected**: Option A — close ENH-2677 as substantially already implemented, open a narrower follow-up

**Reasoning**: Two independent evidence-gathering passes confirmed all four "already done" claims (schema, dataclass, config property, namespace migration) are true and covered by 27 passing tests, and the two named remaining gaps (`correction_penalty` wiring, `ll-config get` CLI) are real. Option B's rationale (preserve the ID for EPIC-1707 rollup) does not hold: `ll-issues epic-progress` derives epic membership by walking `parent:` frontmatter fresh on every run (not by ID), ENH-2677 has no `parent:` field and isn't in EPIC-1707's `relates_to:` list, and EPIC-1707 is already `status: done` (closed 2026-06-12, before this issue was even created) — there is no active rollup to preserve. The repo's established precedent for "mostly-done issue, stale scope" is close+follow-up (`finalize_decomposed_parent`, commit `2146c493` closing ENH-2568 as superseded, EPIC-1707's own decomposed children ENH-1846/ENH-1847), not in-place rewrite.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 0/3 | 1/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- Option A: All four claimed-done items verified directly in code (`config-schema.json:1751-1890`, `features.py:1076`, `core.py:363-365`, zero `analysis.evolution` refs in `scripts/little_loops/**/*.py`); 27/27 relevant tests pass. Minor scope gap found: `skills/analyze-history/SKILL.md:143,158` still references stale `analysis.evolution.*` in prose and should be folded into the follow-up issue's scope.
- Option B: No codebase mechanism or precedent implements "rewrite in place, preserve ID, stay open"; epic rollup is `parent:`-derived per-run so ID preservation is moot; ENH-2677 isn't even epic-linked; EPIC-1707 is already closed.

## Execution Target

This issue was promoted from `ll-product` (planning/design hub) into `little-loops` for execution via `ll-auto`/`ll-parallel`.

## Status

**Cancelled: superseded-by-follow-up** | Created: 2026-07-18 | Priority: P3

Substantially already implemented under prior ENH-1913/1907/1914 work (schema,
`HistoryConfig` dataclass, `BRConfig.history` property, and the
`analysis.evolution.*` → `history.evolution.*` migration were all confirmed
done by `/ll:refine-issue`). Superseded by **ENH-2678**, scoped to the two
concrete remaining gaps: wiring `GoNoGoConfig.correction_penalty` into the
go-no-go skill's actual scoring path, and building an `ll-config get <key>`
CLI wrapping `BRConfig.resolve_variable()`. `/ll:wire-issue` was not run on
this issue since there is no implementation plan left to wire.

## Session Log
- `/ll:wire-issue` - 2026-07-18 - cancelled as superseded by ENH-2678, skipped wiring pass
- `/ll:decide-issue` - 2026-07-18T18:58:44 - `397fd40c-86e4-4952-8436-253025adf4c4.jsonl`
- `/ll:refine-issue` - 2026-07-18T18:45:26 - `9e72bd3b-c260-4f5e-86c6-545d78e8d8f0.jsonl`
