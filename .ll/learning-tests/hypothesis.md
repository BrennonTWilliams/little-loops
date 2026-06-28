---
target: hypothesis
date: '2026-06-27'
status: proven
assertions:
- claim: '@given(st.text()) feeds random strings to the test function on each call'
  result: pass
- claim: '@settings(max_examples=N) controls the number of generated examples per test'
  result: pass
- claim: st.sampled_from(sequence) produces only values from the supplied sequence
  result: pass
- claim: st.from_regex(pattern, fullmatch=True) generates strings that fully match
    the pattern
  result: pass
- claim: st.lists(st.text(), max_size=N) generates lists with at most N elements
  result: pass
- claim: suppress_health_check=list(HealthCheck) is a valid @settings argument
  result: pass
- claim: st.one_of(st.none(), st.text()) generates either None or a string
  result: pass
raw_output_path: .ll/learning-tests/raw/hypothesis.txt
---
