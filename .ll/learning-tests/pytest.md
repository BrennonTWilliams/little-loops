---
target: pytest
date: '2026-09-18'
status: proven
assertions:
- claim: tmp_path is a fresh, existing directory per test
  result: pass
- claim: pytest.raises(match=) uses re.search (partial match), not a full match
  result: pass
- claim: a yield-fixture's teardown runs even when the test fails
  result: pass
- claim: a scope="module" fixture is set up once across all tests in the module
  result: pass
- claim: pytest.mark.xfail(strict=True) on a passing test fails the run (XPASS(strict))
  result: pass
- claim: pytest exits 1 when a test fails and 5 when no tests are collected
  result: pass
- claim: -k selects tests by name substring and reports the rest as deselected
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest.txt
---
