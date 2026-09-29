---
target: unittest
date: '2026-09-24'
status: proven
assertions:
- claim: unittest.main(exit=False) returns a TestProgram whose .result has wasSuccessful()
  result: pass
- claim: a failing assertEqual is recorded in result.failures (not result.errors) with AssertionError in the traceback
  result: pass
- claim: an uncaught non-assertion exception is recorded in result.errors, not result.failures
  result: pass
- claim: '@unittest.skip tests appear in result.skipped with their reason'
  result: pass
- claim: setUp runs before and tearDown after each test method, including a failing one
  result: pass
- claim: subTest failures are recorded individually in result.failures and do not stop later subtests
  result: pass
- claim: '@expectedFailure test that fails lands in result.expectedFailures'
  result: pass
raw_output_path: .ll/learning-tests/raw/unittest.txt
---
