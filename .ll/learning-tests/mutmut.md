---
target: mutmut
date: '2026-09-14'
status: proven
assertions:
- claim: 'mutmut --help lists subcommands apply, browse, print-time-estimates, results,
    run, show, tests-for-mutant (no dedicated junitxml subcommand)'
  result: pass
- claim: invoking via `python -m mutmut run` crashes with RuntimeError ("context
    has already been set") from a multiprocessing fork-context conflict; the installed
    `mutmut` console script runs the same project without error
  result: pass
- claim: '`mutmut run` exits 0 even when one or more mutants survive -- the process
    exit code does not reflect mutation-testing outcome'
  result: pass
- claim: mutant identifiers are `<module>.<mangled_function_name>` (e.g. calc.x_is_positive__mutmut_1),
    not bare integers -- `mutmut show <int>` raises FileNotFoundError while `mutmut
    show <full-name>` succeeds
  result: pass
- claim: '`mutmut run` materializes a full mirror of the project under mutants/
    (mutated sources plus copied tests/, pyproject.toml, .pytest_cache) rather than
    a single sqlite db or diff-only store'
  result: pass
- claim: '`mutmut show <mutant-name>` prints a unified diff of just the mutated
    line'
  result: pass
raw_output_path: .ll/learning-tests/raw/mutmut.txt
---
