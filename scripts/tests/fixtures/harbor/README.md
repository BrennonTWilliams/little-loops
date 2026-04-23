# Harbor-Format Fixture Directory

This directory contains three Harbor-format task directories used in `test_benchmark_fragment.py`.

## Format

Each task directory contains:
- `task.md` — Task instructions in Markdown
- `expected.json` — Expected outcome: `{"score": float, "criteria": [str]}`

## Scorer Contract

A Harbor scorer receives a task directory path as its argument and must:
- Print a single float (0.0–1.0) to stdout
- Exit 0 on success, non-zero on failure

The `harbor_scorer` evaluator interprets the result:
- `exit_code != 0` → verdict `"no"`
- `exit_code == 0`, stdout not parseable as float → verdict `"error"`
- `exit_code == 0`, stdout parses as float → verdict `"yes"` with `details={"score": <float>, "exit_code": 0}`
