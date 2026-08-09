---
target: pytest
date: '2026-08-08'
status: proven
assertions:
- claim: pytest.raises(ExcType) as a context manager captures the raised exception
    in .value
  result: pass
- claim: a session-scoped fixture is instantiated only once even when used by multiple
    test functions in the same file
  result: pass
- claim: tmp_path fixture yields a unique pathlib.Path per test invocation
  result: pass
- claim: pytest.mark.xfail(strict=True) causes an unexpectedly-passing test to fail
    the suite (XPASS(strict) counts as failure)
  result: pass
- claim: capsys.readouterr() captures stdout printed during the test body
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest.txt
proven_package: pytest
proven_version: 9.0.1
---
