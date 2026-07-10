---
id: ENH-2587
title: Guard .ll/decisions.yaml with a load-time validation check on commit/CI
type: ENH
status: open
priority: P2
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T21:08:10Z'
decision_needed: false
labels:
- decisions
- data-integrity
- tooling
- pre-commit
- ci
---

# ENH-2587: Guard `.ll/decisions.yaml` with a load-time validation check on commit/CI

## Summary

`.ll/decisions.yaml` can be — and in practice is — edited by hand / by an agent
rather than exclusively through `save_decisions()`. When that happens, PyYAML's
emitter (which escapes and quotes correctly) is bypassed, so a malformed scalar can
be committed and silently break every tool that later reads the file. This happened
with the `OTHE-203` entry (see the corruption fixed on 2026-07-10): a double-quoted
`rationale` contained an unescaped `` `""` ``, which is invalid inside a
double-quoted YAML scalar, so `yaml.safe_load` failed with
`ParserError: expected <block end>, but found '<scalar>'`. The broken file was
committed to `HEAD`, so nothing caught it until a reader crashed.

There is currently no automated check that `.ll/decisions.yaml` is loadable before
it lands in a commit.

## Motivation

- The file is the source of truth for team-enforced rules, decisions, exceptions,
  and coupling entries; a parse failure disables `load_decisions()` and everything
  built on it.
- Hand/agent edits bypass the serializer's escaping, so syntax corruption is a
  recurring failure mode, not a one-off.
- A parse failure has no localized blast radius — the whole file becomes unreadable
  from the first bad byte onward.

## Proposed Enhancement

Add a lightweight validation gate that runs `load_decisions()` (not just
`yaml.safe_load`) against `.ll/decisions.yaml` and fails non-zero on any error:

- A `pre-commit` hook scoped to `.ll/decisions.yaml` so corruption is caught before
  it is committed locally.
- The same check mirrored in CI so `--no-verify` and non-hook edit paths can't slip
  a broken file into the branch.

Validating through `load_decisions()` / `_entry_from_dict()` (rather than a bare
YAML parse) means the gate also catches schema-level problems — missing `id`,
unknown `type` — not merely syntax.

## Acceptance Criteria

- A committed check loads `.ll/decisions.yaml` via `load_decisions()` and exits
  non-zero on any parse or schema error, with a message pointing at the file.
- The check runs both as a `pre-commit` hook and in CI.
- A deliberately corrupted `decisions.yaml` (e.g. the `OTHE-203`
  unescaped-quote case) is rejected by the check; a valid file passes.
- The check is fast enough (single file load) to run on every commit without
  friction.

## Notes

- Related fixed corruption: `OTHE-203` rationale unescaped `` `""` `` in
  `.ll/decisions.yaml` (repaired 2026-07-10 by escaping to `` `\"\"` ``).
- Complements ENH's sibling capture on lossy serialization (see BUG-2588): a
  schema-aware validator and a non-lossy serializer address the write and read
  halves of the same integrity gap.

## Session Log
- manual session - 2026-07-10T21:08:10Z - captured from decisions.yaml corruption investigation
