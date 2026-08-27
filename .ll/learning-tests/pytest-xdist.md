---
target: pytest-xdist
date: '2026-08-26'
status: proven
assertions:
- claim: '@pytest.mark.xdist_group(name=...) pins grouped tests to the same worker
    under --dist loadgroup'
  result: pass
- claim: -n auto worker count reported in the run summary matches os.cpu_count()
  result: fail
- claim: -p no:xdist disables the plugin so -n is not a recognized option
  result: pass
- claim: --dist loadscope groups same-class tests onto one worker
  result: pass
- claim: under -n 2 exactly two distinct worker ids (gw0/gw1) are used across all
    items
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest-xdist.txt
---
