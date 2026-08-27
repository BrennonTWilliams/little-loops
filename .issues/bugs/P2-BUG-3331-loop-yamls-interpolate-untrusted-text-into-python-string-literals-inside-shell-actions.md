---
id: BUG-3331
type: BUG
title: Loop YAMLs interpolate untrusted text into Python string literals inside shell
  actions
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-26'
captured_at: '2026-08-26T21:00:00Z'
supersedes: []
decision_needed: false
---

# BUG-3331: Loop YAMLs interpolate untrusted text into Python string literals inside shell actions

## Summary

Loop `action_type: shell` states embed Python via a heredoc
(`python3 << 'PYEOF'`) and build that Python by **textually substituting**
`${context.*}` and `${captured.*.output}` directly into string literals. The
FSM's interpolation engine is pure text substitution
(`scripts/little_loops/fsm/interpolation.py`) with no quoting or escaping, so
the substituted value is not data — it is *source code*.

Two consequences, both live today:

- **A quote character in the value is a `SyntaxError`.** A goal containing
  `don't` terminates the single-quoted literal it lands in; an LLM response
  containing `"""` terminates the triple-quoted literal it lands in. The state
  dies with an opaque Python traceback that names neither the loop nor the
  offending input.
- **The value can inject arbitrary Python.** Anything that closes the literal
  and continues with a new statement executes inside the loop's shell action,
  with the run's full privileges.

Split out of BUG-3327 (its "class (2) — code literal" sites). BUG-3327 covers
prompt fencing; this issue covers code-literal quoting. The two share no code,
no test shape, and no rationale.

**BUG-3327 named four sites. The survey below found ~60.**

## Current Behavior

Scalar user input into a single-quoted literal
(`scripts/little_loops/loops/loop-router.yaml:192`):

```python
inp = (input_m.group(1).strip() if input_m else '') or '${context.goal}'
```

LLM output into a triple-quoted literal (`loop-router.yaml:185`):

```python
output = """${captured.project_score.output}"""
```

Both sit inside `python3 << 'PYEOF'`. The heredoc *is* quoted, so bash performs
no expansion — the injection is not a shell injection. The substitution happens
one layer earlier, in the FSM interpolation pass over the raw action string,
before bash ever sees the text. Quoting the heredoc does not help.

## Steps to Reproduce

1. Run `loop-router` with a goal containing an apostrophe:
   `ll-loop run loop-router --input "don't break the build"`.
2. `parse_project_score` interpolates it into
   `... or '${context.goal}'`, producing
   `... or 'don't break the build'`.
3. Observe: `SyntaxError: invalid syntax` from the heredoc'd Python. The state
   fails, and the error names neither `loop-router` nor the goal.

For the LLM-output variant, no adversary is needed — any model response
containing `"""` reproduces it non-deterministically.

## Expected Behavior

Untrusted text reaches Python as **data**, never as source. Two established
in-repo idioms, one per value shape:

1. **Scalars → environment.** Bind the value to an env var on the `python3`
   invocation and read it with `os.environ`. Existing precedent:
   `mechanize-skills.yaml:162` (`RUN_DIR="$RUN_DIR" python3 << 'PYEOF'` +
   `os.environ`), `:283`, `:511`, `:528`; `autodev.yaml:405`
   (`ISSUE_FILE="$ISSUE_FILE" python3 << 'PYEOF'`); `flux-image-generator.yaml:275`
   (`abs_dir = os.environ["ABS_DIR"]`).
2. **Multi-line LLM output → a file.** Write the captured output to a run-dir
   file via its own quoted heredoc, then `open()` that file from the Python
   heredoc (Option B — see Decision Rationale under Proposed Solution).
   Precedent: `brainstorm.yaml:160-169` (BUG-2468, shipped/tested),
   `cua-agent-desktop.yaml:417-423` (shell-only sibling).

## Motivation

This is the sharper half of what BUG-3327 surfaced, and it is not latent — the
apostrophe break fires on ordinary English input, and the LLM-output variant
fires on ordinary model output with no adversary at all. Unlike the fencing
work, it has an unambiguous, already-used-in-repo remedy; what it lacks is
coverage.

## Site survey

Counted across `scripts/little_loops/loops/**.yaml` (2026-08-26):

### Class A — user/config input into a single-quoted Python literal (~23 sites)

Apostrophe-breakable and injectable. The value originates from operator CLI
input, so the security severity is self-inflicted; the **availability** impact
is not — an ordinary goal breaks the loop.

Representative: `loop-router.yaml:34, 53, 192, 252, 345`;
`loop-composer.yaml:231`; `goal-cluster.yaml:347, 389`;
`apply-research.yaml:216, 217`.

### Class B — LLM output into a triple-quoted Python literal (27 sites, 10 loops)

**The sharper class.** The value is model-generated, so nothing constrains it:
a `"""` anywhere in the response breaks the state, and prompt-injected content
in the model's own output becomes executed Python.

Representative: `loop-router.yaml:127, 141, 185, 245, 338, 472`;
`apply-research.yaml:168, 306`; `assumption-firewall.yaml:66, 128, 158`;
`goal-cluster.yaml:207, 436, 566, 639`; `learning-tests-audit.yaml:114-116, 225`;
`migrate-sdk-version.yaml:171, 183`.

### Class C — `run_dir` and similar loop-controlled paths (~10 sites)

Same textual shape (`run_dir = '${context.run_dir}'`), but the value is
constructed by the runner, not by a user or a model. **Lowest priority** — fix
opportunistically while touching a file, do not sweep for it.

### Explicitly out of scope

`${context.*}` interpolated into **prompt** text (e.g.
`incremental-refactor.yaml:88, 93, 136, 165`) is not a code literal — no
interpreter parses it. That is BUG-3327's territory.

## Proposed Solution

1. Convert **class A** sites to the env-var idiom: `VAR="${context.goal}"
   python3 << 'PYEOF'` + `os.environ.get("VAR", "")`.
2. Convert **class B** sites per the decision below.
3. Leave **class C** alone except where already editing the surrounding state.
4. Add a lint (see Follow-up) so new sites cannot be introduced.

### Open decision — how class B passes multi-line LLM output

Env-var binding is **not sufficient on its own** for class B. The binding
itself is a bash double-quoted string (`VAR="${captured.x.output}"`), so a `"`
in the value closes it and a `$(...)` inside it command-substitutes — the same
defect relocated from Python to bash. Multi-line values make it worse.

Three options; pick one and record it:

**Option A**: Runner-side capture-to-file. Have the FSM persist each `capture:`
variable to a file under the run dir and expose its path (e.g.
`${captured.x.path}`), so shell actions read it with `open(...)`. Cleanest and
fixes the class permanently, but it is a runner change plus a schema addition,
not a per-site edit. Note captured values are already carried in the
checkpoint state (`fsm/persistence.py:332, 379`) but are not exposed as a
per-variable file a shell action can open.

**Option B**: Per-site heredoc for the value. Write the captured output to a
run-dir file in the same action via its own quoted heredoc, then read that
file from the Python heredoc. No runner change; ~27 hand-edits with a
repeated boilerplate block.

> **Selected:** Option B — Per-site heredoc for the value. Already a shipped,
> tested in-repo precedent for this exact failure mode
> (`brainstorm.yaml`'s `dedup_novelty` state, BUG-2468, done), plus a
> shell-only sibling in `cua-agent-desktop.yaml`. No runner or schema change,
> lower risk than Option A's untested runner change, and unlike Option C it
> closes the live, non-adversarial defect now instead of deferring it.

**Option C**: Scope this issue to class A and file class B separately.
Defensible given that (a) is a different kind of change, but leaves the
sharper class open.

**Recommended**: (a) Runner-side capture-to-file, with (b) as the fallback if
the schema addition proves contentious. Do **not** ship env-binding for class
B — it looks like a fix and is not one.

### Decision Rationale

**Selected: Option B — Per-site heredoc for the value.**

`/ll:decide-issue` re-evaluated the issue's own "Recommend (a)" note against
fresh codebase evidence and overturned it: the issue's Codebase Research
Findings claimed "no existing in-repo pattern writes untrusted multi-line
capture output to a run-dir file for later `open()`" — that claim is false.
`brainstorm.yaml`'s `dedup_novelty` state (`scripts/little_loops/loops/brainstorm.yaml:160-169`)
already implements exactly this shape — write untrusted LLM output to a file
via a quoted shell heredoc, then `open()` it from the Python heredoc — as the
shipped, tested fix for BUG-2468 (`status: done`,
`scripts/tests/test_brainstorm.py::TestBug2468ErrorRouting`), which is the
identical `"""`-breaks-triple-quoted-literal failure mode this issue
describes. `cua-agent-desktop.yaml:417-423` has a shell-only sibling of the
same pattern. Option B therefore generalizes an already-proven idiom rather
than inventing new mechanism, needs no FSM runner or schema change (unlike
Option A), and — unlike Option C — resolves the live, non-adversarial class-B
defect now instead of deferring it to a new issue (a defer-risk borne out by
this same split lineage's sibling, FEAT-3332, still sitting open).

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — runner-side `.path` accessor | 2 | 1 | 2 | 1 | 6/12 |
| **B — per-site heredoc-to-file** | **3** | **2** | **3** | **2** | **10/12** |
| C — defer class B to a new issue | 2 | 3 | 3 | 1 | 9/12 |

Key evidence:
- `brainstorm.yaml:156-169` — shipped BUG-2468 fix, identical failure mode, identical mechanism
- `cua-agent-desktop.yaml:417-423` — shell-only sibling instance, explicit "~25% failure rate" comment on the raw-interpolation defect it replaced
- `scripts/little_loops/fsm/validation/shell_safety.py:37-41,154,178-180` (MR-11) — the regression-guard lint already tracks quoted-heredoc boundaries structurally; it needs to stop treating "safe from bash" as "safe from the re-parsed Python literal," not be built from scratch
- Known residual risk to address during implementation: static heredoc sentinels (`RAWEOF`, `PLANEOF`, etc.) are not collision-proof against LLM output that happens to contain the sentinel line verbatim — no in-repo instance uses a randomized/per-run sentinel yet; worth hardening while converting the ~27 sites

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/loop-router.yaml` — the densest single file
  (both classes)
- `scripts/little_loops/loops/loop-composer.yaml`,
  `loop-composer-adaptive.yaml`, `goal-cluster.yaml`, `apply-research.yaml`,
  `assumption-firewall.yaml`, `learning-tests-audit.yaml`,
  `migrate-sdk-version.yaml`, `auto-refine-and-implement.yaml`
- Under option (a): `scripts/little_loops/fsm/interpolation.py` and
  `scripts/little_loops/fsm/executor.py` for the `.path` accessor, plus
  `scripts/little_loops/fsm/fsm-loop-schema.json`

### Dependent Files (Callers/Importers)

- N/A — loops are invoked by ID via the FSM runner, not imported

### Similar Patterns

- Safe idiom already in-repo: `mechanize-skills.yaml:162, 283, 511, 528`;
  `autodev.yaml:405`; `flux-image-generator.yaml:275`;
  `interactive-component-generator.yaml:529`; `openscad-model-generator.yaml:330`;
  `html-website-generator.yaml:211`
- The interpolation engine itself: `scripts/little_loops/fsm/interpolation.py`
  (`VARIABLE_PATTERN` / `InterpolationContext.resolve()`) — pure text
  substitution, no escaping hook to extend

### Tests

- `scripts/tests/test_builtin_loops.py` — behavioral cases in the established
  extract-action / `subprocess.run(["bash", "-c", action])` shape:
  - a goal containing `don't` runs `loop-router`'s `parse_project_score`
    action to exit 0 (today: `SyntaxError`);
  - a captured output containing `"""` and a newline runs the class-B action to
    exit 0;
  - a goal containing `'; import os; os.system("touch /tmp/pwned") #` does not
    create the file.
- A static sweep asserting no built-in loop interpolates `${context.*}` or
  `${captured.*}` inside a Python string literal in a `python3` heredoc — this
  is the regression guard, and the survey above is its expected-clean baseline.

### Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — document the env-var (and
  file-passing) idiom as the required way to get external text into a
  heredoc'd Python body, alongside the MR rule table

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- Existing lint precedent for the Notes "Follow-up": MR-11 (`_validate_unsafe_context_interpolation`, `scripts/little_loops/fsm/validation/shell_safety.py:191-227`) already walks `state.action` tracking heredoc state via `_QUOTED_HEREDOC_START_RE` (`shell_safety.py:41`) and flags matches of `_UNSAFE_CONTEXT_INTERP_RE` (`shell_safety.py:33-35`). It currently treats being inside a quoted heredoc (`<< 'EOF'`) as an unconditionally safe position — safe from bash's perspective — and does not distinguish that from being unsafe once the heredoc body is re-parsed as a Python string literal. The Follow-up should extend MR-11's existing heredoc-tracking rather than add a new rule from scratch.
- The env-var idiom is not applied uniformly even within one file: `mechanize-skills.yaml:283-286` binds `SKILL_FILE` via the env-var idiom (`SKILL_FILE="${captured.current_skill.output}" python3 << 'PYEOF'` / `os.environ["SKILL_FILE"]`) but still raw-interpolates `${captured.run_dir.output}` into a Python string literal (`open("${captured.run_dir.output}/diagnosis.json")`) on the very next line inside the same heredoc. Any regression sweep must check every interpolation site per-heredoc, not treat a file as clean once one site is converted.
- No existing in-repo pattern writes untrusted multi-line capture output to a run-dir file for later `open()` (relevant to Open Decision option (b)/(a)). The two existing file-handoff shapes found are: (1) an LLM self-managing its own artifact file per prose instructions in `generate_prompt`/`rubric` (e.g. `html-website-generator.yaml:67-95`), and (2) a Python heredoc opening a JSON file at a `${captured.run_dir.output}`-derived path that a prior state wrote (e.g. `mechanize-skills.yaml:286,337,370,581`) — there only the harness-controlled *path* is interpolated raw, not the untrusted file *contents*. Neither is a precedent for passing arbitrary untrusted captured text via file.

## Program Design

### Signatures

- No Python API change under options (b)/(c).
- Under option (a): a `${captured.<name>.path}` accessor resolving to a run-dir
  file holding that capture's raw output verbatim.
- `_run_action(self, action_template: str, state: StateConfig, ctx: InterpolationContext, on_usage: UsageCallback | None = None) -> ActionResult` (`scripts/little_loops/fsm/executor.py:2097`) — the single write site (`:2370-2391`) where a `path` key would be added to `self.captured[state.capture]` under option (a).
- `_build_context(self) -> InterpolationContext` (`scripts/little_loops/fsm/executor.py:3284`) — constructs each interpolation context with `captured=self.captured` by reference, so a `path` key added at the write site above is visible with no further plumbing.

### Call Path

`InterpolationContext.resolve()` substitutes into the raw action string ->
`bash -c` (`scripts/little_loops/fsm/runners.py:297`) -> quoted heredoc ->
`python3` parses the substituted text **as source**. The fix breaks the last
arrow: the value must arrive through `os.environ` or `open()`, never through
the parser.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-27 — based on codebase analysis:_

- `InterpolationContext.resolve()` (`scripts/little_loops/fsm/interpolation.py:78`) and `_get_nested()` (`:119`) already generically resolve any dot-path under the `captured` namespace via plain dict traversal (`path.split(".")`, `:133`) — a `${captured.X.path}` accessor requires no change to `VARIABLE_PATTERN` (`:28`) or the `:default=`/`?`/`:shell` suffix-parsing block in `interpolate()` (`:209-274`). It resolves automatically once `self.captured["X"]["path"]` exists as a key — this is a data-population problem, not an interpolation-syntax problem.
- Capture write site: `_run_action()` (`scripts/little_loops/fsm/executor.py`, signature at line 2097) populates `self.captured[state.capture] = {"output": ..., "stderr": ..., "exit_code": ..., "duration_ms": ..., "failure_type": ..., "timeout_kind": ...}` at lines 2370-2391. A `path` key (plus the corresponding file write of `result.output`/`result.stderr` under `${context.run_dir}`) would be added at this single site.
- `_build_context()` (`executor.py:3284-3303`) constructs each `InterpolationContext` with `captured=self.captured` passed by reference. A `path` key added at the write site above is therefore visible to every subsequent state's interpolation with no additional plumbing — `_build_context` is called from multiple sites (`executor.py:3294, 3755, 3802`), all referencing the same instance dict.
- `run_dir` is available inside the executor via `self.fsm.context.get("run_dir", "")` (`executor.py:1692`, `:3031`) — the same dict backing `${context.run_dir}` — not as a dedicated attribute on the executor.
- `LoopState.captured` (`scripts/little_loops/fsm/persistence.py:332`, dataclass field) and `to_dict()` (`:379`) serialize the captured dict opaquely with no per-key shape enforcement — a new `path` key round-trips through checkpointing with no persistence-layer code change.
- `fsm-loop-schema.json:489-492` — `capture` is currently a bare `{"type": "string", "description": "Variable name to store action output"}` with no destination-path sibling key. Any new schema key for this accessor is purely additive; nothing existing to reconcile with.
- `bash -c` invocation (`scripts/little_loops/fsm/runners.py:297`, `cmd = ["bash", "-c", action]`) confirms interpolation is fully resolved into `action` (via `interpolate()` at `executor.py:2115`) before bash — and therefore python3 — ever sees the text, confirming the issue's stated Call Path.

## Implementation Steps

1. ~~Settle the class-B decision (a/b/c) above.~~ Decided: Option B — see
   Decision Rationale under Proposed Solution.
2. Convert class A sites to the env-var idiom, loop by loop, running
   `ll-loop validate` on each.
3. Implement Option B (per-site heredoc-to-file, hardened against sentinel
   collision) and convert the 27 class-B sites.
4. Add the behavioral tests and the static regression sweep.
5. Document the idiom in `HARNESS_OPTIMIZATION_GUIDE.md`.

## Impact

- **Priority**: P2 — an ordinary apostrophe in a goal breaks `loop-router` and
  `loop-composer` today, and class B fails non-deterministically on ordinary
  model output. The injection path is real but mostly self-inflicted (operator
  input), which is what keeps this off P1.
- **Effort**: Medium — ~50 mechanical site edits across 10 loop files, plus
  either a runner/schema addition (option a) or repeated boilerplate (option b),
  plus tests.
- **Risk**: Low-Medium — each edit is local and `ll-loop validate`-checkable,
  but the sites are numerous and a missed one is invisible until it fires. The
  static regression sweep is what makes the sweep verifiable rather than
  hopeful.
- **Breaking Change**: No — unless option (a) adds a schema key, which is
  additive.

## Notes

Split from BUG-3327's "Site classification" section, class (2), per the
decision recorded there on 2026-08-26. BUG-3327 is now class-(1)-only
(prompt fencing) and links here.

Sequencing: independent of BUG-3326 and FEAT-3328. Can land in parallel;
nothing in the `workflow-generator` chain touches these files.

**Follow-up worth considering:** a `fsm/validation` rule flagging any
`${context.*}` / `${captured.*}` interpolation that lands inside a quote
character in a `python3` heredoc body. That is the same import-don't-restate
spirit as FEAT-3328's gate-completeness rule and would use the same
regex-over-raw-action-string shape.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P2


## Session Log
- `/ll:decide-issue` - 2026-08-27T03:02:59 - `4a4c9942-5c58-4b71-851d-896694066b21.jsonl`
- `/ll:refine-issue` - 2026-08-27T01:45:46 - `091f85a6-5523-4888-8bc0-8e7acb268aae.jsonl`
