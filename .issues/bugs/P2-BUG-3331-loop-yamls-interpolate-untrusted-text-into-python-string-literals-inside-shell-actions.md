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
2. **Multi-line LLM output → a file.** See the open decision below.

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

- **(a) Runner-side capture-to-file.** Have the FSM persist each `capture:`
  variable to a file under the run dir and expose its path (e.g.
  `${captured.x.path}`), so shell actions read it with `open(...)`. Cleanest and
  fixes the class permanently, but it is a runner change plus a schema addition,
  not a per-site edit. Note captured values are already carried in the
  checkpoint state (`fsm/persistence.py:332, 379`) but are not exposed as a
  per-variable file a shell action can open.
- **(b) Per-site heredoc for the value.** Write the captured output to a run-dir
  file in the same action via its own quoted heredoc, then read that file from
  the Python heredoc. No runner change; ~27 hand-edits with a repeated
  boilerplate block.
- **(c) Scope this issue to class A and file class B separately.** Defensible
  given that (a) is a different kind of change, but leaves the sharper class
  open.

**Recommend (a)**, with (b) as the fallback if the schema addition proves
contentious. Do **not** ship env-binding for class B — it looks like a fix and
is not one.

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

## Program Design

### Signatures

- No Python API change under options (b)/(c).
- Under option (a): a `${captured.<name>.path}` accessor resolving to a run-dir
  file holding that capture's raw output verbatim.

### Call Path

`InterpolationContext.resolve()` substitutes into the raw action string ->
`bash -c` (`scripts/little_loops/fsm/runners.py:297`) -> quoted heredoc ->
`python3` parses the substituted text **as source**. The fix breaks the last
arrow: the value must arrive through `os.environ` or `open()`, never through
the parser.

## Implementation Steps

1. Settle the class-B decision (a/b/c) above.
2. Convert class A sites to the env-var idiom, loop by loop, running
   `ll-loop validate` on each.
3. Implement the chosen class-B mechanism and convert those 27 sites.
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
