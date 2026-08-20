---
id: ENH-3265
type: ENH
title: Codex bridge emitters are presence-only and lossy, hiding 11 drifted files
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T20:45:06Z'
relates_to:
- ENH-3062
- FEAT-2274
labels:
- host-adapters
- drift
- codex
confidence_score: 100
outcome_confidence: 85
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# ENH-3265: Codex bridge emitters are presence-only and lossy, hiding 11 drifted files

## Summary

`CodexEmitter.emit_command` (`adapters/codex.py:333-377`) and the
`skills/<name>/agents/openai.yaml` companion branch of
`CodexEmitter.emit_skill` (`:309-312`)
use presence-only `.exists()` checks rather than content comparisons. A
fully-drifted codex bridge tree therefore reports `0 adapted, 108 skipped`, and
a stale-but-present file is never rewritten even under `--apply`.

Switching those checks to content comparison — the pattern `emit_agent`
(`:405-414`) and `emit_mcp_config` (`:457`) already use — is a two-line change,
but it cannot land alone: it turns `emit_command` from create-once into
overwrite-always, and the current generators produce output that is **worse**
than what is on disk for 11 files. Those generator defects are the real work
here.

This issue is the prerequisite for **ENH-3062**, which adds the suite gate that
asserts no host mirror is stale. That gate arrives red unless this lands first.

## Current Behavior

Measured directly against HEAD on 2026-08-20 (reconfirmed by
content-comparing each bridged artifact against its own generator):

```
skills/ll-cleanup-worktrees/SKILL.md              skills/ll-cleanup-worktrees/agents/openai.yaml
skills/ll-create-sprint/SKILL.md                  skills/ll-commit/agents/openai.yaml
skills/ll-loop-suggester/SKILL.md                 skills/ll-loop-suggester/agents/openai.yaml
skills/ll-ready-issue/SKILL.md                    skills/ll-reconcile-issue/agents/openai.yaml
skills/ll-reconcile-issue/SKILL.md
skills/ll-refine-issue/SKILL.md
skills/ll-verify-issues/SKILL.md
```

`ll-adapt --host codex --dry-run` reports all 11 as `skipped`. 22 of the 29
bridged `SKILL.md` files are byte-identical to their generator, so this is real
divergence, not a systematically wrong generator.

Note what "mirror" means for codex: **there is no `.codex/` tree for skills or
commands.** `emit_skill` rewrites the real `skills/<name>/SKILL.md` in place;
`emit_command` writes `skills/ll-<stem>/` (64 git-tracked files). Only agents
land under `.codex/agents/`. The mirror for codex is the source tree itself.

## Expected Behavior

`emit_command` and the `openai.yaml` companion detect content drift and rewrite
it under `--apply`, and the resulting output is a strict improvement on what is
on disk today — no hand-added field silently reverted, no mid-word truncated
short-description introduced. Running `ll-adapt --host codex --apply` twice in a
row leaves `git status` clean.

## Motivation

The presence-only check does not merely fail to catch drift — it actively
reports success over it. Anyone running `ll-adapt --host codex --dry-run` today
gets a green light on a divergent tree. That is worse than having no check.

It also blocks ENH-3062's gate entirely: a gate that asserts `adapted == 0`
across the codex host is vacuous while the emitter can never report drift.

## Proposed Solution

Three classes of drift, each needing different handling. Established by
diffing every bridged artifact against its generator on 2026-08-20.

**All 11 diffs are purely additive** — on-disk equals generated output plus
extra fields, with no contradictions except `metadata.short-description`. That
observation is what makes Classes B and C tractable.

### Class A — genuine stale drift; regenerating is correct (3 files)

The source description changed and the bridged artifact did not.

- `ll-cleanup-worktrees/SKILL.md` + `agents/openai.yaml` — description gained
  `/ll-loop`
- `ll-commit/agents/openai.yaml` — "no Claude attribution" → "no assistant
  attribution"

No generator change needed; these are correct once content comparison exists.

### Class B — hand-added content the generator would delete (6 files)

| File | Hand-added content | Present in source `commands/*.md`? |
|---|---|---|
| `ll-refine-issue/SKILL.md` | `args:`, `allowed-tools:` (7), Status footnote | `allowed-tools` **yes, byte-identical**; `args` no; footnote no |
| `ll-ready-issue/SKILL.md` | `args:`, `allowed-tools:` (6), Status footnote | same shape |
| `ll-reconcile-issue/SKILL.md` | `args:`, `allowed-tools:` (6), Status footnote | same shape |
| `ll-verify-issues/SKILL.md` | `allowed-tools:` (6) | **yes** |
| `ll-create-sprint/SKILL.md` | `allowed-tools:` (1) | **yes, but source has 3** |
| `ll-loop-suggester/SKILL.md` | `argument-hint:` | **yes, byte-identical** |

Most of this is not unrecoverable hand-authored content — it is a manual
back-port of frontmatter the source command already carries. The fix is
**pass-through in `_synthesized_skill_md`**: emit `allowed-tools` and
`argument-hint` from the source command's frontmatter when present.

Two residuals genuinely are not derivable and need preservation-on-merge rather
than pass-through:

- `args:` (3 files) — a hand-invented field; the source carries
  `argument-hint:` plus a structured `arguments:` list, neither of which
  reproduces the `args:` string.
- The Status-enum footnote in the body (3 files).

One asymmetry to decide explicitly: `create-sprint`'s source declares 3
`allowed-tools` entries (`mkdir`, `ll-issues`, `ll-history-context`) while the
stub carries 1. Pass-through *changes* that file rather than preserving it.
That is almost certainly correct — the source is authoritative — but it means
"pass-through is a no-op on the existing tree" is false, and the change should
be reviewed as a deliberate widening.

**Considered and rejected: the `_LL_GENERATED_MARKERS` convention.**
`emit_agent` (`codex.py:405-410`) and `_find_ll_mcp_block` (`:272-277`) solve
the don't-clobber-hand-edits problem by refusing to rewrite a file that lacks a
leading `# generated by ll-adapt...` marker. That does not transfer here: a
comment line before `---` breaks markdown frontmatter parsing, and these stubs
are parsed as skills by every host. Recorded so an implementer does not
rediscover and pursue it.

### Class C — the generator is worse than what is on disk (4 files)

`_extract_skill_short_desc` (`codex.py:43-62`) truncates the source
`description` at `_MAX_SHORT_DESC = 80` chars, mid-word:

```
ll-loop-suggester   on-disk:   "Suggest FSM loops from message history, command catalog, or sequences."
                    generated: "Analyze user message history to suggest FSM loop configurations automatically. U"

ll-reconcile-issue  on-disk:   "Reconcile an issue's directive sections against its own research findings"
                    generated: "Rewrite an issue's Implementation Steps, Acceptance Criteria, and Integration Ma"
```

Affects `ll-loop-suggester/SKILL.md` + `agents/openai.yaml` and
`ll-reconcile-issue/SKILL.md` + `agents/openai.yaml` (the latter two overlap
Class B).

**Word-boundary truncation alone is not sufficient.** The on-disk values are
hand-written summaries, not prefixes of the source description — no truncation
strategy reproduces them. The fix has two parts:

1. Add an explicit short-description field to the affected source
   `commands/*.md` frontmatter and have `_extract_skill_short_desc` prefer it.
   **Note: zero of the 29 `commands/*.md` carry `metadata.short-description`
   today** — it is a field `_synthesized_skill_md` *writes* (`:112`), not one it
   reads. This is new source-side data, not an existing field to start
   consulting.
2. Fix the truncation itself to break on a word boundary with an ellipsis, as
   the fallback for commands with no explicit short-description.

## Scope Boundaries

**In scope**: `CodexEmitter.emit_command` and `emit_skill`'s `openai.yaml`
companion check; `_synthesized_skill_md` field pass-through and merge;
`_extract_skill_short_desc` truncation; short-description frontmatter on the
affected source commands; repairing the 11 drifted files.

**Out of scope**: the suite gate itself (ENH-3062), other hosts' emitters,
adding new hosts, the `.gemini`/`.kimi-code`/`.codex` tree layouts, and the
`disable-model-invocation` mirror-has-no-orphans question (a different gate;
see ENH-3062's resolved decisions).

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/codex.py` — `emit_command()` (`:333-377`,
  `.exists()` checks at `:359`, `:366`, `:368`, no `read_text()` anywhere);
  `emit_skill()`'s `yaml_exists = openai_yaml.exists()` (`:310`) gating the skip
  at `:312` and the write at `:320`; `_synthesized_skill_md()` (`:88-119`);
  `_extract_skill_short_desc()` (`:43-62`) and `_MAX_SHORT_DESC` (`:25`).
- `commands/loop-suggester.md`, `commands/reconcile-issue.md` (and any other
  command whose description exceeds 80 chars) — add the short-description
  frontmatter field.
- `skills/ll-cleanup-worktrees/`, `skills/ll-commit/`, `skills/ll-create-sprint/`,
  `skills/ll-loop-suggester/`, `skills/ll-ready-issue/`, `skills/ll-reconcile-issue/`,
  `skills/ll-refine-issue/`, `skills/ll-verify-issues/` — the 11 drifted files.
  Handling differs per class; **do not bulk-regenerate**.

_Wiring pass added by `/ll:wire-issue`:_
- Full enumeration of "any other command whose description exceeds 80 chars"
  (measured 2026-08-20; single-line `description:` field): `commands/scan-codebase.md`
  (83 chars), `commands/refine-issue.md` (97), `commands/analyze-workflows.md` (90),
  `commands/verify-issues.md` (98), `commands/normalize-issues.md` (100),
  `commands/ready-issue.md` (142). Block-scalar (`description: |`, multi-paragraph)
  descriptions, also over 80 chars in total: `commands/tradeoff-review-issues.md`,
  `commands/open-pr.md`, `commands/manage-release.md`, `commands/review-sprint.md`,
  `commands/sync-issues.md`. 11 commands total beyond the two named examples — all
  need the `metadata.short-description` frontmatter field for AC1 to be
  comprehensive, not just the two cited in Class C. [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/adapt_skills_for_codex.py:20,23,26` imports from
  `adapters/codex.py` and imports `_insert_skill_fields` directly.
- `scripts/little_loops/cli/adapt_agents_for_codex.py:15,19` imports
  `CodexEmitter` but only exercises the agents pathway — unaffected by the
  `emit_command` change. Awareness only.
- `scripts/little_loops/cli/adapt.py:32` (`main_adapt`) delegates to
  `adapters/core.py`'s `process_skills()` (`:414`) / `process_commands()`
  (`:471`); `process_commands` passes the plugin `skills/` dir as `output_dir`
  for every host, and only `CodexEmitter.emit_command` consumes it.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/adapters/core.py:54` — dispatch-table entry
  `"codex": ("little_loops.adapters.codex", "CodexEmitter")`; the module-level
  registration point that resolves `CodexEmitter`, in addition to the
  `process_skills`/`process_commands` call sites already cited above.
  Awareness only — not modified by this issue. [Agent 1 finding]
- `scripts/little_loops/adapters/capabilities.py:75` — defines
  `HOST_CAPABILITIES["codex"].frontmatter_fields_read`, which `codex.py:74`
  reads. Out of scope per this issue's own Codebase Research Findings below;
  confirm no incidental widening. [Agent 1/2 finding]
- `scripts/little_loops/cli/verify_host_map.py` and
  `scripts/little_loops/text_utils.py:212-214` — cross-validate / consume the
  shared `HOST_CAPABILITIES` structure. Neither calls `codex.py` directly;
  awareness only, unaffected since this issue does not touch
  `HOST_CAPABILITIES` itself. [Agent 1 finding]

### Similar Patterns
- `emit_agent` (`codex.py:405-414`) and `emit_mcp_config` (`:457`) already do
  `existing == new_content` comparisons — the target shape.
- `GeminiEmitter.emit_skill` (`gemini.py:94`):
  `if out_path.exists() and out_path.read_text() == new_content` — the
  cross-host convention.

### Tests
- `scripts/tests/test_adapters.py` — `TestCodexEmitterEmitCommand` (`:489-501`)
  has `test_dry_run_does_not_write` / `test_returns_adapted_on_first_run` /
  `test_already_adapted_returns_skipped` but no `test_idempotent` or
  content-drift case, consistent with the presence-only check giving nothing to
  compare. `test_already_adapted_returns_skipped` reuses the same `meta` on both
  calls, so it stays green under both old and new logic and does **not** catch
  this defect.
- `TestCodexEmitterEmitAgent` (`:576-604`) is the pattern to copy:
  `test_up_to_date_returns_skipped`, `test_idempotent`.
- `TestCodexEmitterEmitMcpConfig._config_path` (`:658-677`) —
  `monkeypatch.setenv("CODEX_HOME", str(tmp_path))`, the only precedent for
  isolating real-filesystem side effects.
- `scripts/tests/test_adapt_skills_for_codex.py`,
  `scripts/tests/test_adapt_golden_corpus.py` — golden-corpus expectations will
  move when the generators change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_skills_for_codex.py::TestSynthesizedSkillMd` — six
  methods call `_synthesized_skill_md(stem, description)` with exactly two
  positional args: `test_contains_namespaced_name` (`:477`),
  `test_contains_description_verbatim` (`:482`),
  `test_contains_metadata_short_description` (`:486`),
  `test_short_description_truncated_to_80` (`:491`),
  `test_body_references_source_command` (`:502`),
  `test_contains_disable_model_invocation` (`:507`). Once the Program Design's
  signature widening to `_synthesized_skill_md(stem, description, fm, existing=None)`
  lands, all six raise `TypeError: missing required positional argument` unless
  `fm` gets a default — **will break**, needs an `fm=` argument added at each
  call site regardless. [Agent 2/3 finding]
- `scripts/tests/test_adapt_skills_for_codex.py::TestExtractShortDesc.test_truncates_to_80_chars`
  — pins the current hard-cutoff-at-80 behavior with `"A" * 100` (no word
  boundary to violate). Passes unmodified only if the new word-boundary+ellipsis
  logic falls back to hard truncation when no boundary is found; otherwise
  needs updating to expect an ellipsis or shorter cutoff. [Agent 3 finding]
- `scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard`
  (`:379-467`) / `TestRealCommandsIntegrationGuard` (`:677-761`) — walk the real
  `skills/*/SKILL.md` and `commands/*.md` trees on disk and assert structural
  invariants, including `test_all_real_skills_have_metadata_short_description`
  (`:437-439`) and `test_every_bridged_skill_has_required_frontmatter` (`:747`)
  requiring `len(short_desc) <= 80`. AC1's truncation output must stay within
  this bound for these to remain green. [Agent 3 finding]
- `scripts/tests/test_adapters.py::TestCodexEmitterEmitAgent.test_up_to_date_returns_skipped`
  / `test_idempotent` (`:594-604`) — the literal pattern to copy for the new
  `emit_command`/`emit_skill` drift tests required by AC5/AC6. [Agent 3 finding]
- No existing fixture seeds a bridged `SKILL.md` with `allowed-tools:`/`args:`/
  `argument-hint:` plus an `openai.yaml` companion the way the 6 Class-B files
  actually look (`test_adapters.py:1857` and `:2027-2044` cover unrelated
  hosts/paths). AC2's preservation test needs a new fixture helper, e.g. a
  `_make_bridged_skill_md(tmp_path, stem, extra_fields=...)` sibling to
  `TestCodexEmitterEmitCommand`'s existing `_make_command`. [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` § ll-adapt
- `docs/reference/HOST_COMPATIBILITY.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- `scripts/little_loops/adapters/capabilities.py:75` — `HOST_CAPABILITIES["codex"].frontmatter_fields_read` = `("description", "name", "metadata.short-description", "tools")`. This data-driven policy governs `emit_skill`'s `_insert_skill_fields`/`_select_frontmatter_fields` path only, not `_synthesized_skill_md`/`emit_command`. Adding `allowed-tools`/`argument-hint` pass-through to `_synthesized_skill_md` is a separate code path and does not require widening this policy — but the scope boundary is worth confirming explicitly rather than assuming, since the two mechanisms read overlapping frontmatter keys through different code.

## Program Design

### Signatures

- `_extract_skill_short_desc(text: str) -> str` — existing, `adapters/codex.py:43`. Currently returns `desc.splitlines()[0][:_MAX_SHORT_DESC]`. Gains an explicit-field preference and word-boundary truncation. Signature unchanged.
- `_synthesized_skill_md(stem: str, description: str) -> str` — existing, `adapters/codex.py:88`. Must widen to see the source command's full frontmatter and any existing on-disk stub, e.g. `_synthesized_skill_md(stem: str, description: str, fm: dict, existing: str | None = None) -> str`. `fm` supplies `allowed-tools`/`argument-hint` for pass-through; `existing` supplies `args:` and body content for preservation. Callers: `CodexEmitter.emit_command` only (`:366`).
- `_make_openai_yaml_content(display_name: str, short_desc: str) -> str` — existing, `adapters/codex.py:83`. Unchanged; its output becomes content-compared rather than presence-checked.
- `CodexEmitter.emit_command(self, cmd_meta: dict) -> str` — existing, `adapters/codex.py:333`. The `.exists()` skip at `:359-362` becomes an `existing == new_content` comparison, and the per-file write guards at `:366`/`:368` drop their `if not ...exists()` conditions.
- `CodexEmitter.emit_skill(self, skill_meta: dict) -> str` — existing, `adapters/codex.py:294`. `yaml_exists = openai_yaml.exists()` (`:310`) becomes a content comparison feeding the same `skill_changed`-style boolean; the `:320` write guard drops its existence condition.

### Call Path

`main_adapt()` (`cli/adapt.py:32`) → `process_commands(emitter, commands_dir, output_dir, apply, quiet)` (`adapters/core.py:471`) → `CodexEmitter.emit_command` → `_synthesized_skill_md` / `_make_openai_yaml_content`. `process_commands` passes the plugin `skills/` dir as `output_dir` for every host; only `CodexEmitter.emit_command` consumes it, deriving `skills/ll-<stem>/`.

The skill path is `main_adapt()` → `process_skills(emitter, skills_dir, apply, quiet)` (`core.py:414`) → `CodexEmitter.emit_skill` → `_insert_skill_fields` (`:308`, already content-comparing) and the `agents/openai.yaml` companion branch (`:309-320`, the presence-only half).

Note `process_skills` filters `disable-model-invocation: true` skills before `emit_skill` is called (`core.py:438-443`) — all 64 bridged stubs carry that flag, so they are reached only through `emit_command`, never `emit_skill`. Verified against HEAD 2026-08-20.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- Confirmed exact current body of `_synthesized_skill_md` (codex.py:88-119): a pure `(stem: str, description: str) -> str` builder — it accepts no `fm`/`existing` parameter today, so `allowed-tools`/`argument-hint`/hand-added `args:` are structurally unreachable from inside it, not merely unused.
- `fm` (the source command's parsed frontmatter dict) is already in scope inside `emit_command` as `cmd_meta["fm"]` (codex.py:338) but is never forwarded to `_synthesized_skill_md` (:367) or to `_extract_skill_short_desc` (:349) — the latter instead independently re-parses raw `content` via its own internal `yaml.safe_load` (codex.py:43-62), rather than reusing the already-parsed `fm` dict sitting in the caller's scope. Pass-through is therefore a signature-widening + dict-lookup change (`fm.get("allowed-tools")` / `fm.get("argument-hint")`), not new parsing.
- `_read_frontmatter` (core.py:89-100) plus the upstream skip in `process_commands` (core.py:504-509, `fm is None` → skip before `emit_command` is ever called) together guarantee `fm` is always a `dict` (possibly missing specific keys, never `None`) by the time `emit_command` runs — so `fm.get("allowed-tools")` returning `None` when absent is the only case pass-through code needs to handle; it must be treated as "omit the field," not emitted as a literal `null` line.
- No malformed-on-disk-stub handling exists anywhere in `emit_command` today: presence-only checks never call `.read_text()` on the existing file, so an existing-but-unparseable `out_skill_md`/`out_openai_yaml` is currently unreachable code. Introducing content comparison is the first point this method would need to read and (if pass-through/merge parses it) tolerate a malformed existing stub.

## Implementation Steps

1. Fix `_extract_skill_short_desc`: prefer an explicit source short-description
   field; fall back to word-boundary truncation with ellipsis. Add the field to
   the affected source commands.
2. Teach `_synthesized_skill_md` to pass `allowed-tools` and `argument-hint`
   through from source frontmatter, and to preserve an existing `args:` field
   and body content below the generated stub body on regeneration.
3. Switch `emit_command`'s presence-only check and `emit_skill`'s `openai.yaml`
   companion check to content comparison, and drop the per-file `.exists()`
   write guards so `--apply` actually rewrites.
4. Regenerate; verify the diff against the Class A/B/C triage file-by-file
   rather than accepting it wholesale.
5. Add the drift/idempotency tests; run the full suite.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update the 6 `TestSynthesizedSkillMd` call sites in
  `scripts/tests/test_adapt_skills_for_codex.py` (`:477,482,486,491,502,507`) to
  pass an `fm=` argument once `_synthesized_skill_md`'s signature widens.
- Add `metadata.short-description` frontmatter to all 11 commands whose
  description exceeds 80 chars, not just `loop-suggester.md`/`reconcile-issue.md`:
  `commands/scan-codebase.md`, `commands/refine-issue.md`,
  `commands/analyze-workflows.md`, `commands/verify-issues.md`,
  `commands/normalize-issues.md`, `commands/ready-issue.md`,
  `commands/tradeoff-review-issues.md`, `commands/open-pr.md`,
  `commands/manage-release.md`, `commands/review-sprint.md`,
  `commands/sync-issues.md`.
- Re-verify `TestExtractShortDesc.test_truncates_to_80_chars` against the
  word-boundary truncation fallback behavior chosen in Step 1; update if the
  no-boundary case no longer hard-truncates at exactly 80 chars.
- Build a new `_make_bridged_skill_md`-style fixture helper for AC2's
  preservation test (seed `allowed-tools:`/`args:`/`argument-hint:` on a
  bridged `SKILL.md`, run `emit_command` with `apply=True`, assert survival).

## Acceptance Criteria

1. **Truncation defect fixed.** `_extract_skill_short_desc` no longer emits
   mid-word truncation. Regenerating `ll-loop-suggester` and
   `ll-reconcile-issue` produces a readable short-description, not
   `"...automatically. U"`. A unit test pins a >80-char description to a
   word-boundary result.
2. **Hand-added fields survive.** After the change,
   `ll-adapt --host codex --apply` leaves `args:`, `allowed-tools:`,
   `argument-hint:`, and the Status-enum footnote intact in all six affected
   `skills/ll-*/SKILL.md` files. A test pins this: seed a bridged SKILL.md with
   an `allowed-tools:` block and an `args:` field, run `emit_command` with
   `apply=True`, assert both survive.
3. **`create-sprint`'s `allowed-tools` widening is deliberate.** The file gains
   the two source entries it is missing, and the diff is reviewed rather than
   auto-accepted.
4. **Class A drift repaired.** `ll-cleanup-worktrees` (SKILL.md + openai.yaml)
   and `ll-commit/agents/openai.yaml` match their generators.
5. **`emit_command` content-compares.** Calling with content A, mutating the
   source to content B, and calling again returns `"adapted"` (today:
   `"skipped"`); a third unchanged call returns `"skipped"`. Under `apply=True`
   the stale-but-present file is actually rewritten.
6. **`emit_skill`'s `agents/openai.yaml` companion content-compares**, with the
   same three-call assertion as AC5.
7. **End-to-end idempotency.** `ll-adapt --host codex --apply` run twice leaves
   `git status` clean and reports `0 adapted` on the second run. This is the
   proof that generator and tree agree; per-emitter unit tests can pass while
   this fails.
8. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — blast radius limited to non-Claude hosts, but the false
  green is actively misleading and it blocks ENH-3062.
- **Effort**: Medium — the emitter change is two lines; the generator fidelity
  work and the file-by-file triage are the bulk.
- **Risk**: Medium — this converts create-once into overwrite-always across 64
  git-tracked files. AC2 is the guard.
- **Breaking Change**: No (output-format change only, within this repo's own
  bridged tree).

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/HOST_COMPATIBILITY.md` | Which hosts have mirrors and why |
| `docs/reference/CLI.md` § ll-adapt | Adapter flags including `--dry-run` |

## Status

**Open**

## Session Log
- `/ll:confidence-check` - 2026-08-20T21:05:24 - `5922ca54-43fc-4aae-89e3-42687aa4c77e.jsonl`
- `/ll:wire-issue` - 2026-08-20T21:03:01 - `614e5ae4-ac51-444e-af33-4f7587a7e3d6.jsonl`
- `/ll:refine-issue` - 2026-08-20T20:55:41 - `03a7dd78-7b4c-4c1b-84cc-861a0bac0ea0.jsonl`
- split from ENH-3062 - 2026-08-20 - pre-implementation review found the
  prerequisite work (generator fidelity + content comparison + drift repair) was
  fused into the gate issue while its own resolved decisions said it should land
  as a preceding change. Diffed all 11 drifted files to establish that Class B
  is mostly source-derivable pass-through, not unrecoverable hand-authored
  content.
