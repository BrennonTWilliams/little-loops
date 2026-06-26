---
target: pytest
date: '2026-06-26'
status: proven
assertions:
- claim: pytest.mark.parametrize iterates a test function once per parameter value
  result: pass
- claim: monkeypatch.setenv changes os.environ within test scope and restores it after
  result: pass
- claim: using an unregistered marker with --strict-markers active causes collection
    error (exit non-zero)
  result: fail
- claim: pytest.mark.skipif(True, reason=...) skips the test without failing the suite
  result: pass
- claim: a fixture defined in conftest.py is visible to tests in subdirectories of
    the same package
  result: pass
- claim: a fixture defined in a non-conftest test file is NOT visible to tests in
    sibling test files
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest.txt
---
