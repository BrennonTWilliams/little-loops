---
target: hypothesis
date: '2026-08-08'
status: proven
assertions:
- claim: '@example(x) forces a specific value to be tried in addition to generated
    ones'
  result: pass
- claim: assume(condition) skips an example when condition is False, without failing
    the test
  result: pass
- claim: st.composite allows building custom strategies via a draw function
  result: pass
- claim: Hypothesis shrinks a failing example to a minimal counterexample before
    reporting
  result: pass
- claim: st.integers(min_value=, max_value=) only produces values within the given
    bounds
  result: pass
- claim: settings(deadline=None) disables the per-example time limit
  result: pass
raw_output_path: .ll/learning-tests/raw/hypothesis.txt
---
