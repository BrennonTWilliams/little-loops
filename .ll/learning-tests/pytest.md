---
target: pytest
date: '2026-08-16'
status: proven
assertions:
- claim: autouse=True fixtures run automatically without being requested by a test's
    signature
  result: pass
- claim: pytest.mark.parametrize with multiple argnames requires each tuple's values
    to match argnames order positionally
  result: pass
- claim: monkeypatch.setenv restores the original environment variable value after
    the test ends
  result: pass
- claim: pytest.approx treats two floats as equal within a default relative tolerance
    (~1e-6)
  result: pass
- claim: a fixture that depends on another fixture receives that fixture's fully
    resolved value before the test body runs
  result: pass
- claim: caplog captures log records emitted at WARNING level by default without
    explicit caplog.set_level
  result: pass
- claim: a syntax error in a test file causes a collection error (exit code 2) without
    running any other tests in the session
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest.txt
---
