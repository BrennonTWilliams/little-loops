---
id: BUG-3231
type: BUG
title: 'll-loop list --running: unreadable or malformed run state is absorbed into
  an affirmative "No running loops", and --json is ignored on that path'
priority: P2
status: open
discovered_by: little-loops-hermes-audit
discovered_date: '2026-08-16'
labels:
- loops
- cli-json
testable: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 19
score_change_surface: 20
---

# BUG-3231: ll-loop list --running: unreadable or malformed run state is absorbed into an affirmative "No running loops"

## Summary

Two defects on the same path, one of which conceals the other.

1. `list_running_loops` (`scripts/little_loops/fsm/persistence.py:1109`) skips any state file it cannot read — `except (json.JSONDecodeError, KeyError): continue` at lines 1129-1130 — without recording that it did. An unreadable `.loops/.running/` directory is likewise indistinguishable from an empty one. A caller therefore cannot tell "nothing is running" from "I could not read what is running", and the CLI states the former.

2. `cmd_list` (`scripts/little_loops/cli/loop/info.py:120`) prints the prose string `No running loops` and returns before the `--json` branch at line 122 is reached. So `--json` does not imply JSON output: the empty case emits an unparseable line where `[]` belongs.

   **This applies to both empty cases in that block, not just `--running`.** The
   `status_filter` branch immediately above (`info.py:118-119`) prints
   `No loops with status: {status_filter}` and returns **1**, from the same
   early-return position above the same `--json` check. Fixing only the
   `--running` case leaves `ll-loop list --status running --json` equally
   unparseable. Note also the exit-code asymmetry between the two empty cases —
   `0` for `--running`, `1` for `--status` — which should be settled or
   deliberately preserved as part of this fix.

Together, a project whose run state is corrupt answers `ll-loop list --running --json` with the bare text `No running loops`, exit 0, empty stderr — an affirmative, unparseable, and false clean bill of health.

## Current Behavior

Probed live in `.loops/.running/` (the directory `RUNNING_DIR` actually names, `persistence.py:43` — note this is `.loops/.running/`, not `.loops/runs/`).

Corrupt state file:

```console
$ echo 'not json {{{' > .loops/.running/probe.state.json
$ ll-loop list --running --json; echo "exit=$?"
No running loops
exit=0
# stderr: empty
```

Well-formed JSON of the wrong shape (the `KeyError` branch):

```console
$ echo '{"unexpected": true}' > .loops/.running/probe.state.json
$ ll-loop list --running --json; echo "exit=$?"
No running loops
exit=0
# stderr: empty
```

Unreadable directory:

```console
$ chmod 000 .loops/.running
$ ll-loop list --running --json; echo "exit=$?"
No running loops
exit=0
# stderr: empty
```

All three are byte-identical to the genuinely-idle case. There is no exit code, no stderr, and no stdout difference to distinguish them.

### Mechanism of the unreadable-directory case (corrected)

An earlier draft of this issue attributed the unreadable-directory symptom to
`running_dir.exists()` at `persistence.py:1121` returning `False`. **That is
wrong**, and it matters because it points the fix at the wrong line. Probed
directly:

```python
>>> d = Path('probe/.running')   # chmod 000
>>> d.exists()
True
>>> d.is_dir()
True
>>> list(d.glob('*.state.json'))
[]
```

`exists()` and `is_dir()` both return **`True`** — `stat()` on the directory
itself succeeds as long as the *parent* is traversable; it is reading the
directory's contents that is denied. The silence comes one line later: `Path.glob`
swallows the `PermissionError` internally and yields nothing, so the `for` loop at
line 1126 simply never executes.

Consequence for the fix: adding a readability test to the `exists()` check is not
sufficient on its own to be *correct*, but it is the right place to put one —
what it must not be is a *change* to `exists()`'s meaning. Use an explicit
`os.access(running_dir, os.R_OK | os.X_OK)` probe (or wrap the glob iteration in
`try/except PermissionError`), because the failure being detected is not the one
`exists()` reports on.

## Expected Behavior

- `--json` should emit `[]` for the genuinely-empty case rather than prose, so a caller can parse every outcome uniformly — for **both** the `--running` and `--status` empty cases.
- A state file that is skipped should be reported rather than dropped: a stderr warning naming the file, surfaced in the human rendering too.
- An unreadable `.loops/.running/` should be distinguishable from an absent one. Note this is *not* an `exists()` fix — see the corrected mechanism above.

### `[]` is the settled house convention, not a new choice

No design debate needed on the empty-JSON shape: `print_json([])` is already the
pattern at seven sites, two of them **in this same file** —
`cli/loop/info.py:209`, `cli/loop/info.py:274`, `cli/logs.py:1267`,
`cli/logs.py:1995`, `cli/sprint/manage.py:22`, `cli/loop/next_loop.py:231`,
`cli/loop/next_loop.py:246`. `cmd_list` is the outlier.

### The skipped-file channel must not change the JSON shape

The suggestion of `{"running": [...], "unreadable": [...]}` is **rejected**, and
this needs deciding here rather than during implementation. The non-empty `--json`
output today is a bare **array**: `print_json([s.to_dict() for s in states])`
(`info.py:123`). Wrapping it in an object would break every caller on the
*populated* path — a far wider break than the empty-string one this issue already
flags, and one the Breaking Change section did not account for.

Decision: **keep the array shape**; emit skipped-file warnings on **stderr**
only. A caller that wants them reads stderr, which is where the other diagnostics
in this CLI already go. If a machine-readable warnings channel turns out to be
genuinely required, it should arrive later behind an explicit opt-in flag
(e.g. `--json-envelope`) rather than by silently re-shaping the default.

## Steps to Reproduce

1. `mkdir -p .loops/.running`
2. `echo 'not json {{{' > .loops/.running/probe.state.json`
3. `ll-loop list --running --json` — prints `No running loops`, exit 0, empty stderr. Note the output is not JSON despite `--json`.
4. Replace with `{"unexpected": true}` and repeat — same result via the `KeyError` branch.
5. `chmod 000 .loops/.running` and repeat — same result again.
6. Compare against a directory with no state files at all: identical in every observable respect.

## Proposed Solution

For (2), move the `--json` check ahead of **both** prose `print`s in `cmd_list` (the `--status` empty case at lines 118-119 and the `--running` empty case at line 120) so each emits `[]`. `ll-issues` has the same prose-on-empty habit under `-j` and it is a known friction point for callers; this is the same fix.

For (1), have `list_running_loops` report skipped files rather than discarding them, at the `except (json.JSONDecodeError, KeyError): continue` (lines 1129-1130), and add a `PermissionError`-aware readability check for the directory itself (see the corrected mechanism above — `exists()` is not the lever).

The two are separable and (2) is a small move, but fixing (2) alone still leaves a false `[]`, so (1) is the substantive half.

### Do not change `list_running_loops`'s return type

`list_running_loops` has a **second caller**: `transport.py:588`
`_make_seed_callback`, which iterates the result directly
(`for state in list_running_loops(Path(".loops")):`) to seed a newly-connected
socket client. Returning a `(states, skipped)` tuple breaks it silently — it
would iterate the tuple and treat `states` itself as a `LoopState`.

Prefer one of:

- **(a)** Keep the signature; emit `logger.warning(...)` per skipped file from
  inside `list_running_loops`. Simplest, and the warning reaches stderr for both
  callers. Recommended.
- **(b)** Add a sibling `list_running_loops_detailed()` returning the pair, and
  implement the existing function in terms of it. Use only if `cmd_list` needs
  the skipped list as structured data for its human rendering.

Do not add an optional out-param that mutates a caller-supplied list; it reads
as an accident at the second call site.

## Impact

- **Priority**: P2 — "Is anything running?" is a question callers act on: a false "no" can lead to launching a duplicate loop against state that is merely unreadable. The output is also unparseable under `--json` on the exact path most likely to be hit by automation.
- **Effort**: Small for the `--json` ordering; Small-to-Medium for threading skipped-file information out of `list_running_loops`, which has one other caller shape to keep consistent.
- **Risk**: Low. Emitting `[]` under `--json` is what the flag already promises. Adding a warning on skip changes stderr only.
- **Breaking Change**: Yes, narrowly — anything matching on the literal string `No running loops` under `--json` would need to parse `[]` instead. That string-matching is itself a symptom of the bug (`little-loops-hermes` does exactly this today, of necessity).

  **Two in-tree tests encode the current behavior and must be updated as part of
  this fix** — they are the concrete break surface, not just downstream consumers:

  - `scripts/tests/test_ll_loop_commands.py:3692-3706`
    `test_list_running_json_empty` — constructs `Namespace(running=True,
    status=None, json=True)` and asserts `"No running loops" in out`. Its
    docstring states the buggy behavior as the contract
    (*"exits 0 with 'No running loops' message"*). Rewrite to assert
    `json.loads(out) == []`.
  - `scripts/tests/test_ll_loop_integration.py:325` — asserts
    `"No running loops" in captured.out`. **Leave this one alone**: its argv is
    `["ll-loop", "list", "--running"]` with no `--json` (line 318), so it covers
    the human path, which this fix does not change. It is listed here only so it
    is not "fixed" by reflex alongside the other.

  The JSON output shape on the **populated** path is explicitly unchanged (bare
  array) — see the Proposed Solution. Only the empty-case rendering changes.

## Root Cause

The skip at `persistence.py:1129-1130` is deliberate and its comment says so (`# Skip malformed files`) — robustness against a half-written state file during a concurrent write. But robustness was implemented as *silence*, so an unreadable file and an absent one converge on the same answer, and the answer is a positive claim rather than an absence.

The `--json` ordering in `cmd_list` is a separate oversight: the early `print`/`return` at lines 115-121 sits above the `if getattr(args, "json", False)` branch at line 122, so the flag is never consulted on either empty path.

## Integration Map

| Site | Role |
| --- | --- |
| `scripts/little_loops/fsm/persistence.py:1109` `list_running_loops` | Defect (1); silent skip at 1129-1130, unreadable-dir blindness at the glob on 1126. |
| `scripts/little_loops/fsm/persistence.py:43` `RUNNING_DIR` | Names `.loops/.running/` (not `.loops/runs/`). |
| `scripts/little_loops/cli/loop/info.py:110-123` `cmd_list` | Defect (2); both empty-case early returns sit above the `--json` check. |
| `scripts/little_loops/cli/loop/info.py:209`, `:274` | In-file `print_json([])` precedent for the empty case. |
| `scripts/little_loops/transport.py:588` `_make_seed_callback` | Second caller of `list_running_loops`; constrains the signature. |
| `scripts/tests/test_ll_loop_commands.py:3692` | Test asserting the buggy empty-case string under `json=True`. |
| `scripts/tests/test_ll_loop_integration.py:318,325` | Second `"No running loops"` assertion — human path (no `--json`); must **not** change. |

## Program Design

### Signatures
- `list_running_loops(loops_dir: Path | None = None) -> list[LoopState]` — signature **unchanged** (recommendation (a)); gains a `logger.warning` per skipped state file and a readability probe on the directory, so both callers benefit without either being touched; see `scripts/little_loops/fsm/persistence.py:1109`.
- `list_running_loops_detailed(loops_dir: Path | None = None) -> tuple[list[LoopState], list[str]]` — optional sibling under recommendation (b), returning skipped filenames alongside states; adopt only if `cmd_list` needs them as structured data, and reimplement the plain function in terms of it.
- `cmd_list(args: argparse.Namespace, loops_dir: Path) -> int` — signature unchanged; the `--json` check moves above both empty-case early returns; see `scripts/little_loops/cli/loop/info.py:105`.
- `_make_seed_callback() -> Callable[[_SocketClient], None]` — untouched, but it is the constraint that keeps the signature above stable, since it iterates the result directly; see `scripts/little_loops/transport.py:588-591`.

### Types
No new types, and deliberately no change to the `--json` payload type: it stays a bare `list[dict]` from `[s.to_dict() for s in states]`, with `[]` for the empty case. The rejected envelope (`{"running": [...], "unreadable": [...]}`) would have changed this from `list` to `dict` on the populated path — a wider break than the one this issue set out to fix. Skipped-file information is therefore carried on stderr as log lines, not as a typed field.

### Call Path
`ll-loop list --running --json` → `cmd_list` (`info.py:105`) → `list_running_loops(loops_dir)` (`:113`) → `running_dir.exists()` (`persistence.py:1121`) returns `True` even for a `chmod 000` directory → `running_dir.glob("*.state.json")` (`:1126`) swallows `PermissionError` and yields nothing, **or** yields a corrupt file whose `json.loads`/`from_dict` raises and hits `except (json.JSONDecodeError, KeyError): continue` (`:1129-1130`) → empty `states` list returned with no diagnostic anywhere → back in `cmd_list`, `if not states` (`:116`) → `print("No running loops")`, `return 0` (`:120-121`) — reached **before** the `if getattr(args, "json", False)` check at `:122`. The `--status` variant exits one branch earlier at `:118-119` with `return 1`, above the same check.

### Decision Rules
Three rules, each currently absent: (a) *absent* and *unreadable* are different outcomes — an unreadable `.loops/.running/` warns, an absent one stays silent, and neither is inferred from `exists()`, which returns `True` for both; (b) a skipped state file is a reported event, not a discarded one — the existing skip remains (robustness against a half-written file during a concurrent write is still correct) but gains a warning naming the file and the reason; (c) `--json` is honoured on **every** exit of `cmd_list`, so an empty result renders `[]` rather than prose, for both the `--running` and `--status` branches. Exit codes are held constant across the change (`0` for empty `--running`, `1` for empty `--status`) so this is an output-only fix; the asymmetry between them is pre-existing and either preserved deliberately or settled explicitly, not altered as a side effect.

## Implementation Steps

1. In `cmd_list`, hoist the `--json` check above both empty-case early returns so
   each emits `print_json([])`. Settle the `0` vs `1` exit-code asymmetry between
   the `--running` and `--status` empty cases (recommend preserving current codes
   and documenting them, to keep this change output-only).
2. In `list_running_loops`, replace the bare `continue` at 1129-1130 with a
   `logger.warning` naming the skipped file and the reason, then `continue`.
3. Add an `os.access(running_dir, os.R_OK | os.X_OK)` check alongside the
   `exists()` test at line 1121, warning when the directory exists but cannot be
   read. Do not alter the `exists()` semantics.
4. Update the two tests named in the Breaking Change section.
5. Add the regression tests below.

## Acceptance Criteria

- [ ] `ll-loop list --running --json` with nothing running prints `[]` (parses
      via `json.loads` to an empty list), exit 0.
- [ ] `ll-loop list --status running --json` with no matches prints `[]`, and its
      exit code is asserted explicitly.
- [ ] `ll-loop list --running --json` with a running loop still prints a bare
      **array** of state dicts — populated-path shape unchanged.
- [ ] A corrupt `.loops/.running/probe.state.json` (`not json {{{`) yields `[]` on
      stdout **and** a stderr warning naming `probe.state.json`.
- [ ] A well-formed-but-wrong-shape state file (`{"unexpected": true}`, the
      `KeyError` branch) does the same.
- [ ] A `chmod 000` `.loops/.running/` yields a stderr warning distinguishing it
      from an absent directory. Guard this test with a skip when running as root
      (permissions are not enforced for uid 0) and on non-POSIX platforms.
- [ ] An absent `.loops/.running/` still yields `[]` with **no** warning — the
      genuinely-idle case stays quiet.
- [ ] `transport.py:_make_seed_callback` still iterates `list_running_loops`
      correctly (signature unchanged, or updated at that call site).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found while auditing `little-loops-hermes`, whose `ll_status` tool shells out to `ll-loop list --running --json`. Hermes cannot work around this one: the CLI writes no diagnostic anywhere for it to surface, which is why the fix has to be here. Its `idle_outputs` string-match on `"No running loops"` exists solely because of defect (2).

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-17T04:01:31 - `03558def-29ef-40d7-87ba-66fe5fe13be8.jsonl`
