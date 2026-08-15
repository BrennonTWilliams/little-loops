---
target: hatchling
date: '2026-08-14'
status: proven
assertions:
- claim: files physically placed under scripts/little_loops/skills/**/ are picked
    up by the existing `include = ["little_loops/**", "LICENSE"]` wheel glob with
    no further pyproject.toml change (BUG-3177 Option A's core claim)
  result: pass
- claim: non-SKILL.md companion files (e.g. reference.md) under the same directory
    are also picked up by the same glob, with no separate registration
  result: pass
- claim: 'building the wheel with the current unpinned `requires = ["hatchling"]`
    (resolves latest hatchling, 1.31.0 observed) succeeds against this project''s
    current pyproject.toml as committed on main'
  result: pass
  note: re-verified 2026-08-15 after BUG-3179 (readme brought inside scripts/,
    no longer escapes the packaging root via ../)
- claim: PACKAGE_DATA_ASSETS registration in package_data.py is required for a file
    to be included in the built wheel
  result: fail
raw_output_path: .ll/learning-tests/raw/hatchling.txt
---
