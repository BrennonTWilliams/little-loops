---
id: ENH-3052
title: Pin the /ll:commit command to haiku via `model:` frontmatter
type: ENH
priority: P4
status: done
discovered_by: user-request
discovered_date: 2026-08-05
captured_at: '2026-08-05T02:00:45Z'
labels:
- commands
- cost
- plugin-config
decision_needed: false
testable: true
confidence_score: 100
outcome_confidence: 95
score_complexity: 2
score_test_coverage: 5
score_ambiguity: 3
score_change_surface: 2
completed_at: '2026-08-05T02:00:45Z'
---

# ENH-3051: Pin the /ll:commit command to haiku

## Summary

`/ll:commit` is a mechanical, high-frequency command — stage, summarize a diff, write a
conventional-commit message, confirm. It ran on whatever model the ambient session happened to
be using, which for this project is Opus. Pin it to `haiku` with a `model:` frontmatter key on
`commands/commit.md` so the command's cost and latency stop tracking the session default.

## Current Behavior

`commands/commit.md` frontmatter declared only `description` and `allowed-tools`:

```yaml
---
description: Create git commits with user approval and no Claude attribution
allowed-tools:
  - Bash(git:*)
---
```

With no `model:` key, Claude Code runs the command on the session's active model. Skills in this
repo already use the key — `grep -rn "^model:" commands/ skills/ agents/` returns ~20 hits, all
under `skills/`, all alias-form (`model: sonnet` on most, `model: haiku` on
`skills/analyze-history/SKILL.md`). No file under `commands/` carried a `model:` key before this
change; `commands/commit.md` is the first.

## Expected Behavior

`/ll:commit` runs on Haiku regardless of the ambient session model, and the pin is expressed in
the same alias form the skills already use, so the two surfaces stay readable as one convention.

## Motivation

Commit-message authoring is the cheapest reasoning task in the toolkit and one of the most
frequently invoked — it is called by hand, by `/ll:manage-issue`, and by loop states. Paying
Opus rates for it is pure waste, and Haiku's lower latency is directly felt because the command
sits in the interactive path between finishing work and moving on.

## Proposed Solution

Add one line to `commands/commit.md` frontmatter:

```yaml
---
description: Create git commits with user approval and no Claude attribution
model: haiku
allowed-tools:
  - Bash(git:*)
---
```

Alias form (`haiku`) rather than a pinned model ID (`claude-haiku-4-5-20251001`) for two reasons:
it matches every existing `model:` declaration in the repo, and it lets the command follow the
host's current Haiku tier without a future edit when the ID rolls.

## Integration Map

- **`commands/commit.md`** — the prompt source for `/ll:commit`. This is the only edited file.
- **`skills/ll-commit/SKILL.md`** — deliberately *not* edited. It is a generated bridge stub
  ("Bridged from `commands/commit.md` for Codex Skills API discovery. See the source command
  file for the full prompt body."), emitted by `scripts/little_loops/adapters/codex.py:108` with
  `disable-model-invocation: true`. Hand-edits here are overwritten on the next adapter sync, and
  the stub carries no prompt body to run, so a `model:` key on it would have no effect for
  Claude Code.
- **Distribution** — this repo is the plugin source and every little-loops project on this
  machine is `local-editable` against this checkout, so the pin took effect in all of them the
  moment the file was written. No reinstall.

## Program Design

### Types
No new type. The change is a single YAML scalar in a Markdown frontmatter block; no dataclass or
`config-schema.json` field is added. The value's type is the frontmatter mapping's own
`dict[str, Any]`, where `fm["model"] = "haiku"` joins the existing `description` and
`allowed-tools` keys.

### Signatures
No signature changes. The two existing signatures that read command frontmatter and must stay
tolerant of the new key:

- `_is_model_invocation_disabled(fm: dict) -> bool` — `scripts/little_loops/adapters/core.py:180`.
  Reads only `fm["disable-model-invocation"]`; indifferent to `model`.
- `process_commands(emitter: HostEmitter, commands_dir: Path, output_dir: Path, apply: bool,
  quiet: bool) -> tuple[int, int, int]` — `scripts/little_loops/adapters/core.py:336`. Walks
  `commands_dir`, applies the filter above, and delegates to `emitter.emit_command`.

### Call Path
`model:` is consumed by the Claude Code host when it loads `commands/*.md`, not by any code in
this repo. The little-loops adapters read command frontmatter for a different purpose:
`process_commands` (`adapters/core.py:336`) → `_is_model_invocation_disabled`
(`adapters/core.py:180`) → `emitter.emit_command`, with the Codex emitter writing its stub
frontmatter literally at `adapters/codex.py:108`. That path selects on
`disable-model-invocation` alone and passes unrecognized keys through untouched, which is why
`model:` is inert there rather than a parse error — and also why the generated stub does not
inherit the pin.

### Data Flow
Host reads `commands/commit.md` → parses frontmatter → dispatches the command body to the model
named by `model:` (falling back to the session model when absent). Nothing in the little-loops
Python package participates.

## Implementation Steps

1. Add `model: haiku` as the second frontmatter key of `commands/commit.md`, between
   `description` and `allowed-tools`. — **done**
2. Leave `skills/ll-commit/SKILL.md` untouched (generated stub). — **done**
3. Run the frontmatter/command/adapter test slice to confirm the new key does not trip a
   validator. — **done**

## Acceptance Criteria

- [x] `grep -n "^model: haiku" commands/commit.md` exits 0.
- [x] `model:` is alias-form, matching the existing declarations found by
      `grep -rn "^model:" commands/ skills/ agents/`.
- [x] `skills/ll-commit/SKILL.md` is unmodified in the working tree.
- [x] `python -m pytest scripts/tests/ -k "command or frontmatter or codex or adapter"` exits 0.

## Impact

**Scope**: one line in one file. No Python, no schema, no docs surface.

**Cost/latency**: every `/ll:commit` invocation — interactive, from `/ll:manage-issue`, and from
loop states that commit — drops from the session model to Haiku.

**Risk**: low, and the failure mode is visible rather than silent. If Haiku proves too weak for
diff summarization on large changesets, the symptom is a vague commit message, caught at the
approval step the command already requires. Reverting is deleting the line.

**Precedent**: establishes `model:` on `commands/*.md` as a supported knob in this repo. Other
mechanical commands (`/ll:run-tests`, `/ll:help`) are candidates for the same treatment but were
left alone — out of scope here.

## Scope Boundaries

**In scope**: the `model:` pin on `commands/commit.md`.

**Out of scope**: pinning any other command; changing the alias-vs-ID convention repo-wide;
teaching `adapters/codex.py` to propagate `model:` into generated bridge stubs; adding a
validator that asserts commands declare a model.

## Related Key Documentation

- `.claude/CLAUDE.md` § Distribution — the `local-editable` propagation note that makes this pin
  immediately live in downstream projects.
- `docs/reference/COMMANDS.md` — command catalog; not updated, as it documents command purpose
  rather than per-command model selection.

## Status

**Completed** | Created: 2026-08-05 | Completed: 2026-08-05 | Priority: P4

## Session Log
- `/ll:refine-issue` - 2026-08-05T02:04:39 - `75e4749d-8b4c-43bd-ac6f-b724665a513c.jsonl`
- `hook:posttooluse-status-done` - 2026-08-05T02:01:31 - `78b80840-5577-4179-95d0-0f368e10d2bb.jsonl`

### 2026-08-05 — implementation

- Resolved `/ll:commit` to its prompt source. Both `commands/commit.md` and
  `skills/ll-commit/SKILL.md` matched the name; read the skill and found it is a generated Codex
  bridge stub pointing back at the command, so the command is the edit site.
- Surveyed existing convention with `grep -rn "^model:" commands/ skills/ agents/` — all hits
  under `skills/`, all alias-form. Chose `haiku` over the full model ID to match.
- Applied the one-line frontmatter edit to `commands/commit.md`.
- Ran `python -m pytest scripts/tests/ -k "command or frontmatter or codex or adapter"`:
  **1634 passed, 1 skipped** in 13.58s.

## Resolution

- **Action**: improve
- **Completed**: 2026-08-05
- **Status**: Completed

### Files Changed

- `commands/commit.md` — added `model: haiku` to frontmatter (1 line added).

### Verification Results

- `python -m pytest scripts/tests/ -k "command or frontmatter or codex or adapter"` → 1634
  passed, 1 skipped, 0 failed.
- Full suite (`python -m pytest scripts/tests/`) not run; the change touches no Python and the
  targeted slice covers command/skill frontmatter parsing and the Codex adapter.
- Runtime confirmation that the host dispatches `/ll:commit` to Haiku was not observed in this
  session — the pin is verified as written, not as executed.

### Commits

- Not yet committed at time of writing; `commands/commit.md` is modified in the working tree.
