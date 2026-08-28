---
id: EPIC-3336
type: EPIC
title: Loop YAMLs interpolate untrusted text into Python string literals inside shell
  actions
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-27'
captured_at: '2026-08-27T17:51:35Z'
supersedes: [BUG-3331]
---

# EPIC-3336: Loop YAMLs interpolate untrusted text into Python string literals inside shell actions

## Summary

`InterpolationContext.resolve()` substitutes `${context.*}` / `${captured.*}`
into a loop action's raw text before `bash -c <action>` runs
(`scripts/little_loops/fsm/interpolation.py`, `fsm/runners.py:297`). Where that
action embeds a Python body — either a quoted heredoc (`python3 << 'PYEOF'`) or
a bash double-quoted `python3 -c "…"` — the substituted value is parsed **as
Python source**. An apostrophe breaks the state; a `"""` in model output breaks
it harder; and under the `-c "` shape the value is additionally exposed to bash
expansion, making it a live shell injection.

**276 interpolation sites across 33 loop files** (recursive survey,
2026-08-27 — see the class table below). This epic converts the 145 class-A and
class-B sites to two safe idioms, builds the static sweep that makes 145
hand-edits verifiable, and widens the MR-11 lint so the class cannot return.

Full research provenance is `BUG-3331` (superseded by this epic, retained for
its 939-line survey and decision record).

## Motivation

- **Availability, today, non-adversarially.** An ordinary user goal containing
  `don't` raises `SyntaxError` inside `loop-router`'s `parse_project_score`
  state. No attacker required.
- **Injection, class B especially.** Class-B values are model-generated, so
  nothing constrains them: prompt-injected content in a model's own output
  becomes executed Python, and at a `-c "` site, executed shell.
- **The corpus is MR-11-clean today** — no loop sets
  `unsafe_context_interpolation_ok` — so every new warning this work produces is
  a regression signal, not ambient noise. That property is worth preserving.

## Site survey

Recounted 2026-08-27 across `scripts/little_loops/loops/**/*.yaml`, **recursive**
(the original non-recursive glob missed `lib/` and `oracles/` — 28 sites, 8
files).

| Class | Heredoc | `-c "` | Total | Remedy |
|---|---|---|---|---|
| A — user/config scalar into a Python literal | 55 | 23 | **78** | `LL_ARG_X=${context.x:shell}` + `os.environ` (BUG-3340) |
| B — LLM output into a Python literal | 56 | 11 | **67** | heredoc-to-file + `open()` (BUG-3341) |
| C — `run_dir` / loop-controlled paths | 112 | 19 | **131** | leave alone; fix opportunistically |
| **Total** | 223 | 53 | **276** | |

Densest files: `sft-corpus.yaml` (38), `loop-router.yaml` (35),
`recursive-refine.yaml` (29), `goal-cluster.yaml` (19), `autodev.yaml` (13),
`loop-composer-adaptive.yaml` (13), `mechanize-skills.yaml` (13, all class C).

**These counts were provisional (hand-run scan) and are now superseded.**
ENH-3338 landed `interp_sweep.scan_corpus()` and seeded
`scripts/tests/data/loop_interpolation_baseline.json` from `main` — the table
below is that baseline's authoritative count, per the site-anchor key
`(file, state, var, class)`:

| Class | Heredoc | `-c "` | Total | Remedy |
|---|---|---|---|---|
| A — user/config scalar into a Python literal | 52 | 22 | **74** | `LL_ARG_X=${context.x:shell}` + `os.environ` (BUG-3340) |
| B — LLM/`prev`-output/other-namespace into a Python literal | 67 | 16 | **83** | heredoc-to-file + `open()` (BUG-3341) |
| C — `run_dir` / loop-controlled paths | 61 | 7 | **68** | leave alone; fix opportunistically |
| **Total** | 180 | 45 | **225** | |

Densest files by baselined site count: `sft-corpus.yaml` (35),
`recursive-refine.yaml` (19), `goal-cluster.yaml` (18), `loop-router.yaml`
(18), `loop-composer-adaptive.yaml` (12), `autodev.yaml` (10),
`loop-composer.yaml` (9), `refine-to-ready-issue.yaml` (9). The gap from the
hand-run 276 to the baseline's 225 reflects the sweep's stricter per-site
(not per-file) counting, the column-0 heredoc-terminator fix, `harness-
optimize.yaml`'s `apply` state being correctly excluded (`action_type:
prompt`, not a live invocation), and AC 11's data-sink-heredoc exclusion
(a `cat > file << 'MARKER'` heredoc, e.g. `brainstorm.yaml`'s `RAWEOF`
block, writes to disk and never reaches the Python parser) — child ACs
remain phrased against the baseline reaching empty for classes A and B, not
against either historical number.

`${context.*}` interpolated into **prompt** text is out of scope — no interpreter
parses it (that is BUG-3327's territory).

**The survey did not count the `prev` namespace at all.** `interpolate()`
supports it, and `${prev.output}` carries the same untrusted LLM-or-command text
a `captured` reference does. Corpus usage as of 2026-08-27: 7 `${prev.output}`,
3 `${prev.exit_code}`, 2 `${prev.state}`, 1 `${prev.timeout_kind}`. `prev.output`
and `prev.stderr` are **class B**; the rest are class C. ENH-3338's classifier
covers them, and the live bash-position site
`rlhf-svg-evaluate.yaml:517` — `PREV_OUTPUT="${prev.output}"`, model output
inside a bash double-quoted assignment where `$(...)` command-substitutes — is
ENH-3342's to catch, since the sweep's baseline covers Python-body sites only.

## Goal

Every class-A and class-B interpolation site reaches its Python body through
`os.environ` or `open()`, never through the parser; a checked-in ratcheting
baseline proves it; MR-11 prevents new sites.

## Scope

### In scope
- `interpolation.py` suffix-parse normalization so `:shell` composes (ENH-3337)
- the static classifying sweep + ratcheting baseline (ENH-3338)
- `-c "` → quoted-heredoc conversion (BUG-3339)
- class-A → `:shell` env-var binding (BUG-3340)
- class-B → heredoc-to-file (BUG-3341)
- MR-11 widening, the per-site `# ll-lint: mr11-ok(<var>)` marker, and guide
  documentation (ENH-3342)
- the four behavioral injection tests (ENH-3347)

### Out of scope
- The 131 class-C sites (`run_dir` and similar loop-controlled paths). Fix
  opportunistically while already editing a state; do not sweep. The count is
  large enough that sweeping would dominate the diff without closing a live
  defect.
- Prompt-text interpolation (BUG-3327).
- Option A's runner-side `${captured.x.path}` accessor — considered and
  rejected in favor of per-site Option B (see BUG-3331 § Decision Rationale).

## Settled decisions

Carried forward from BUG-3331; children implement these, they do not re-litigate
them.

| # | Decision | Where it binds |
|---|---|---|
| S1 | Make `:shell` **compose** with `:default=` and `?` rather than raise | ENH-3337 |
| `:shell` position | `:shell` is safe **only at a bash token position**. Inside a Python body it is a *misapplied remedy*, not a clean site — `shlex.quote("don't")` is `'\'don\'"\'"\'t\''`, which is a `SyntaxError` in a Python literal. Both the sweep and MR-11 must flag it, never clear it (added 2026-08-27 during epic review) | ENH-3338, ENH-3342, BUG-3340 |
| `prev` namespace | `${prev.output}` / `${prev.stderr}` are the same untrusted text as `${captured.*}` and classify as **class B**; `prev.exit_code`/`state`/`timeout_kind` are runner-constructed, class C (added 2026-08-27) | ENH-3338, ENH-3342 |
| Class B | **Option B** — per-site quoted heredoc writing the captured value to a run-dir file, read back with `open()`. Precedent: `brainstorm.yaml:160-169` (shipped BUG-2468 fix) | BUG-3341 |
| Sentinel | **Fixed improbable marker** `LL_RAW_9F3C1A7E_EOF`. Randomizing forces a double-quoted heredoc, which re-enables expansion and defeats the mechanism | BUG-3341 |
| Env prefix | Every binding this work introduces is named `LL_ARG_<NAME>` — `runners.py:305` spawns actions with a full `os.environ.copy()`, so a bare `GOAL=`/`TASK=` shadows the operator's environment | BUG-3340, BUG-3341 |
| `-c "` scope | **Narrow** — only the files containing a class-A/B site, not all 29 files / 114 invocations | BUG-3339 |
| Baseline | Ratcheting checked-in baseline, green on `main` at every commit — never a red test | ENH-3338 |
| Escape hatch | A per-site `# ll-lint: mr11-ok(<var>) <reason>` marker, naming the variable it exempts and citing a tracking issue; malformed markers are an ERROR and the corpus marker count is ratcheted. It exists so success metric 2 can stay absolute. **It ships in ENH-3342, which runs last — so it is NOT available to BUG-3339/3340/3341.** For those three, a new MR-11 warning means a failed conversion, full stop (added 2026-08-27) | ENH-3342 |

## Child sequencing

The order is **strict**, and BUG-3339/3340/3341 additionally contend on the same
files (`autodev.yaml`, `loop-router.yaml`, `general-task.yaml`,
`lib/composer.yaml`, `sft-corpus.yaml`).

```
ENH-3337 (S1: :shell composes)
    ↓
ENH-3338 (sweep + ratcheting baseline)
    ↓
BUG-3339 (-c " → quoted heredoc)      ← serial from here: shared files
    ↓
BUG-3340 (class A → LL_ARG_/:shell)
    ↓
BUG-3341 (class B → heredoc-to-file)
    ↓
ENH-3347 (behavioral injection tests)
    ↓
ENH-3342 (widen MR-11 + document idiom)
```

**Do not run 3339 / 3340 / 3341 concurrently.** `parallel.epic_branches.enabled`
is `true` and `sprints.default_max_workers` is `2`; without the `blocked_by`
edges these three would be dispatched to separate branches editing the same YAML
files and collide on merge. The edges are set in frontmatter; keep them.

ENH-3347's `blocks: [ENH-3342]` edge is mirrored in ENH-3342's `blocked_by`
(fixed 2026-08-27 — it was one-sided, which let `parallel.epic_branches` dispatch
ENH-3342 before the behavioral tests existed).

ENH-3337 must land on `main` before anything else starts — BUG-3331 Step 1a:
*"Nothing else starts until this is on main."* 130 sites carry a `:default=` or
`?` suffix, and their conversion is a runtime hard failure until S1 ships.

## Integration Map

### Files to Modify

**Engine / lint (small, high-leverage):**
- `scripts/little_loops/fsm/interpolation.py` — suffix parse (`:242-256`),
  `None`-before-quote ordering (`:270-273`), `VARIABLE_PATTERN` (`:28`)
- `scripts/little_loops/cli/loop/run.py:284-300` — the context pre-flight's
  suffix stripper
- `scripts/little_loops/fsm/validation/shell_safety.py` — MR-11 pattern,
  `:shell` recognition (`:183`), column-0 heredoc terminator (`:173`)

**Loop corpus:** 33 files hold sites. Ordered by class-A+B density —
`sft-corpus.yaml`, `loop-router.yaml`, `recursive-refine.yaml`,
`goal-cluster.yaml`, `autodev.yaml`, `loop-composer-adaptive.yaml`,
`loop-composer.yaml`, `refine-to-ready-issue.yaml`, `rn-implement.yaml`,
`harness-optimize.yaml`, `general-task.yaml`, `rn-plan-apo.yaml`,
`apply-research.yaml`, `assumption-firewall.yaml`, `learning-tests-audit.yaml`,
`migrate-sdk-version.yaml`, `auto-refine-and-implement.yaml`, `rn-build.yaml`,
`workflow-generator.yaml`, `cli-anything-bootstrap.yaml`,
`prompt-across-issues.yaml`, plus the 8 subdirectory files
(`lib/composer.yaml`, `lib/policy-router.yaml`, `lib/rubric-router.yaml`,
`oracles/code-run-gate.yaml`, `oracles/enumerate-and-prove.yaml`,
`oracles/generator-evaluator.yaml`, `oracles/oracle-capture-issue.yaml`,
`oracles/verify-confidence-scores.yaml`).

`mechanize-skills.yaml` (13 sites, all class C) needs no change — its
`SKILL_FILE` env-binding at `:283-286` is the shape to copy, and its very next
line is the counterexample proving the sweep must assert **per site**, not per
file.

### Dependent Files (Callers/Importers)

- N/A — loops are invoked by ID via the FSM runner, not imported.

### Tests

- `scripts/tests/test_builtin_loops.py` — the four behavioral cases (ENH-3347)
  and the sweep's completeness guard
- `scripts/tests/test_fsm_validation_shell_safety.py` — MR-11 units
- `scripts/tests/test_ll_loop_commands.py:7433-7501` — the existing `:shell`
  pre-flight cases that ENH-3337 extends
- `scripts/tests/test_interpolation.py` (new) — S1 ordering units
- `scripts/tests/data/loop_interpolation_baseline.json` (new) — the ratcheting
  baseline
- `scripts/little_loops/fsm/interp_sweep.py` (new) — the shared scanner and
  classifier

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the two safe idioms, alongside
  the MR rule table (ENH-3342)

### Configuration

- N/A

## Children

- **ENH-3337** — Make :shell interpolation suffix compose with :default= and ? (open)
- **ENH-3338** — Add static sweep detecting unsafe context/captured interpolation in loop YAMLs (open)
- **BUG-3339** — Convert python3 -c heredoc-unsafe invocations to quoted heredocs (open)
- **BUG-3340** — Convert class-A scalar interpolations to :shell env-var binding (open)
- **BUG-3341** — Convert class-B LLM-output interpolations to heredoc-to-file (open)
- **ENH-3347** — Add behavioral tests for loop interpolation injection and quote-breaking (open)
- **ENH-3342** — Widen MR-11 lint and document the safe loop-interpolation idiom (open)

## Impact

- **Priority**: P2 — a live availability defect on ordinary input (apostrophe in
  a goal) plus an injection surface on model-generated text. Not P1: exploitation
  of class A is operator-self-inflicted, and class B requires an upstream prompt
  injection.
- **Effort**: Large — ~145 site edits across 33 files, plus three engine/lint
  changes and a new sweep. Individually mechanical; the volume and the file
  contention are the cost.
- **Risk**: Medium–High. BUG-3339 is the sharp edge: it is the only step that
  changes shell *structure* rather than a token, and a malformed conversion is
  invisible until the affected state runs. ENH-3338 landing first is what makes
  the rest verifiable.
- **Breaking Change**: Yes, narrowly — S1 changes what an empty/absent value
  emits under `:shell` (`''` instead of nothing) at 5 existing bare-token sites,
  and may change `:default=` behavior on a resolved `None`. Both are audited in
  ENH-3337.

## Success Metrics

1. ENH-3338's baseline has **zero** class-A and class-B entries; class-C entries
   may remain.
2. `ll-loop validate` is clean across the **whole corpus** with **no** MR-11
   warnings and **no** loop setting `unsafe_context_interpolation_ok`. The
   corpus's zero-warning property — what makes any future warning a regression
   signal rather than ambient noise — is preserved continuously, never traded
   away for a migration window. ENH-3342's widening surfaces pre-existing
   findings in files this epic does not otherwise touch; each is either converted
   or carries a per-site `# ll-lint: mr11-ok(<var>) <reason>` marker citing a
   tracking issue. That marker is scoped into ENH-3342 specifically so this
   metric can stay absolute (decided 2026-08-27; baselining is not an option —
   MR-11 does not read ENH-3338's baseline).
3. `python -m pytest scripts/tests/` exits 0 at **every** commit of this work,
   not only at the end.
4. `grep -rl LL_RAW_9F3C1A7E_EOF scripts/little_loops/loops/` enumerates every
   completed class-B conversion; `grep -r LL_ARG_` enumerates every class-A one.
5. The four ENH-3347 behavioral cases pass: apostrophe goal, `"""` capture,
   Python injection, shell injection at a converted `-c "` site.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR rule table; destination for
  the idiom documentation
- `.issues/bugs/P2-BUG-3331-*.md` — superseded parent; full survey and decision
  provenance

## Status

**Open** | Created: 2026-08-27 | Priority: P2

## Session Log
- `/ll:scope-epic` - 2026-08-27T17:51:44 - `c766dcf0-a664-4805-9c8a-6eba323145c8.jsonl`
