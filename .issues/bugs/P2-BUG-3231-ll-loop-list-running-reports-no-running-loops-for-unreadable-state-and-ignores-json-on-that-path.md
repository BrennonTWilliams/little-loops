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
---

# BUG-3231: ll-loop list --running: unreadable or malformed run state is absorbed into an affirmative "No running loops"

## Summary

Two defects on the same path, one of which conceals the other.

1. `list_running_loops` (`scripts/little_loops/fsm/persistence.py:1109`) skips any state file it cannot read — `except (json.JSONDecodeError, KeyError): continue` at lines 1129-1130 — without recording that it did. An unreadable `.loops/.running/` directory is likewise indistinguishable from an empty one. A caller therefore cannot tell "nothing is running" from "I could not read what is running", and the CLI states the former.

2. `cmd_list` (`scripts/little_loops/cli/loop/info.py:120`) prints the prose string `No running loops` and returns before the `--json` branch at line 121 is reached. So `--json` does not imply JSON output: the empty case emits an unparseable line where `[]` belongs.

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

## Expected Behavior

- `--json` should emit `[]` for the genuinely-empty case rather than prose, so a caller can parse every outcome uniformly.
- A state file that is skipped should be reported rather than dropped — at minimum a stderr warning naming the file, and ideally a field in the JSON output (e.g. `{"running": [], "unreadable": ["probe.state.json"]}` or a top-level `warnings` array) so a programmatic caller sees it too.
- An unreadable `.loops/.running/` should be distinguishable from an absent one; `running_dir.exists()` at line 1121 returns `False` for both.

## Steps to Reproduce

1. `mkdir -p .loops/.running`
2. `echo 'not json {{{' > .loops/.running/probe.state.json`
3. `ll-loop list --running --json` — prints `No running loops`, exit 0, empty stderr. Note the output is not JSON despite `--json`.
4. Replace with `{"unexpected": true}` and repeat — same result via the `KeyError` branch.
5. `chmod 000 .loops/.running` and repeat — same result again.
6. Compare against a directory with no state files at all: identical in every observable respect.

## Proposed Solution

For (2), move the `--json` check ahead of the prose `print` in `cmd_list` so the empty case emits `[]`. `ll-issues` has the same prose-on-empty habit under `-j` and it is a known friction point for callers; this is the same fix.

For (1), have `list_running_loops` collect skipped files rather than discarding them. The minimal version logs a warning per skipped file at the `continue` (lines 1129-1130); the useful version returns them alongside the states so `cmd_list` can surface them in both the human and JSON renderings. Distinguishing an unreadable `.loops/.running/` from an absent one needs the `exists()` check at line 1121 to also consider readability.

The two are separable and (2) is a one-line move, but fixing (2) alone still leaves a false `[]`, so (1) is the substantive half.

## Impact

- **Priority**: P2 — "Is anything running?" is a question callers act on: a false "no" can lead to launching a duplicate loop against state that is merely unreadable. The output is also unparseable under `--json` on the exact path most likely to be hit by automation.
- **Effort**: Small for the `--json` ordering; Small-to-Medium for threading skipped-file information out of `list_running_loops`, which has one other caller shape to keep consistent.
- **Risk**: Low. Emitting `[]` under `--json` is what the flag already promises. Adding a warning on skip changes stderr only.
- **Breaking Change**: Yes, narrowly — anything matching on the literal string `No running loops` under `--json` would need to parse `[]` instead. That string-matching is itself a symptom of the bug (`little-loops-hermes` does exactly this today, of necessity).

## Root Cause

The skip at `persistence.py:1129-1130` is deliberate and its comment says so (`# Skip malformed files`) — robustness against a half-written state file during a concurrent write. But robustness was implemented as *silence*, so an unreadable file and an absent one converge on the same answer, and the answer is a positive claim rather than an absence.

The `--json` ordering in `cmd_list` is a separate oversight: the early `print`/`return` at lines 119-121 sits above the `if getattr(args, "json", False)` branch at line 122, so the flag is never consulted on that path.

## Notes

Found while auditing `little-loops-hermes`, whose `ll_status` tool shells out to `ll-loop list --running --json`. Hermes cannot work around this one: the CLI writes no diagnostic anywhere for it to surface, which is why the fix has to be here. Its `idle_outputs` string-match on `"No running loops"` exists solely because of defect (2).

## Status

**Open** | Created: 2026-08-16 | Priority: P2
