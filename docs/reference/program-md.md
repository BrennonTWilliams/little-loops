# `.ll/program.md` — Loop Steering Convention

`.ll/program.md` is a human-authored Markdown file that provides directive input for long-horizon, unattended loop runs. It gives power users a single, obvious place to declare what to optimize, which files to target, which benchmark to run, and any guardrails — without assembling configuration across multiple CLI flags.

The file is **optional**. If absent, affected loops fall back to their existing defaults and `--context` flags. No existing loop behavior changes when the file is not present.

---

## Structure

The file uses conventional `##` headings. Unrecognized headings are ignored.

```markdown
## Directive

[Free-form prose describing what to optimize and why. This text is visible
to the loop's LLM states as the primary optimization goal.]

## Targets

- path/to/file.md
- skills/my-skill/SKILL.md
- path/to/glob/**/*.md

## Benchmark

task_dir: evals/my-suite
scorer: ./scripts/score.sh

## Budget

wall_clock: 8h

## Constraints

[Free-form guardrails, e.g.:
- Do not touch CLAUDE.md
- Keep changes to under 50 lines per iteration]
```

### Section reference

| Section | Context key(s) | Notes |
|---------|----------------|-------|
| `## Directive` | `directive` | Prose passed to the loop's LLM prompt as the primary goal |
| `## Targets` | `targets` | Bullet list → space-separated string (matches `harness-optimize` `targets` context variable) |
| `## Benchmark` | key:value pairs injected directly | `task_dir` → `task_dir`, `scorer` → `scorer`, etc. |
| `## Budget` | `budget` | Prose; interpretation is loop-specific |
| `## Constraints` | `constraints` | Prose; interpretation is loop-specific |

---

## Precedence

Higher wins:

1. Explicit `--context KEY=VALUE` CLI flags
2. `.ll/program.md` parsed sections
3. Loop YAML `context:` block defaults

---

## Invocation

```bash
# Reads .ll/program.md automatically when present
ll-loop run harness-optimize

# Explicit path override
ll-loop run harness-optimize --program-md path/to/my-program.md

# --context overrides program.md values
ll-loop run harness-optimize --context scorer=./scripts/my-scorer.sh
```

---

## Worked Example

Populate `.ll/program.md`:

```markdown
## Directive

Improve the `refine-issue` skill so it produces more actionable implementation
steps. Focus on the integration map section — it currently lists files without
explaining how they connect.

## Targets

- skills/refine-issue/SKILL.md

## Benchmark

task_dir: evals/refine-issue
scorer: ./scripts/score.sh

## Budget

wall_clock: 8h
```

Then run overnight:

```bash
ll-loop run harness-optimize
```

The loop reads `.ll/program.md`, sets `targets`, `task_dir`, and `scorer` from
the file, and feeds the Directive prose to each LLM proposal step so the model
knows the optimization goal.

---

## Supported Loops

| Loop | Uses `program.md` |
|------|-------------------|
| `harness-optimize` | Yes — reads Directive, Targets, Benchmark sections |

Other loops ignore `.ll/program.md` unless they are explicitly written to
consume it. Adding support to a custom loop requires no framework changes —
the parsed values are already present in `fsm.context` before execution begins.

---

## Notes

- The file is gitignored by default in new projects (`.ll/` is personal config).
  Commit it intentionally if you want a shared run configuration.
- No schema is enforced. Convention-over-spec: formalize only if section drift
  causes problems.
- The `## Directive` section is the most important — it gives the LLM a goal.
  Other sections override context variables that the loop already declares.
