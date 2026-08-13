# verify-issue-loop Templates

The per-mode state-synthesis templates that used to live here (criteria-mode
`verify-criterion-N` chain, adversarial-mode fixed 3-probe template) moved to
Python: `ll-loop scaffold-verify <ID> [--adversarial]`
(`scripts/little_loops/cli/loop/scaffold_verify.py`, FEAT-2948). The CLI builds
and validates the `FSMLoop`/`StateConfig` objects directly and emits the
completed YAML — there is nothing left here for an LLM to fill in or chain by
hand.

See `SKILL.md` for the shared resolve/generate/write spine and argument
parsing.
