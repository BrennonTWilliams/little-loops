---
target: pytest-xdist
date: '2026-09-26'
status: proven
assertions:
- claim: '@pytest.mark.xdist_group(name=...) pins grouped tests to the same worker under --dist loadgroup'
  result: pass
- claim: under -n 2 exactly two distinct worker ids (gw0/gw1) are used across all items
  result: pass
- claim: --dist loadscope groups same-class tests onto one worker
  result: pass
- claim: -p no:xdist disables the plugin so -n is not a recognized option
  result: pass
- claim: -n auto worker count reported in the run summary matches os.cpu_count()
  result: pass
- claim: --maxprocesses 2 caps -n auto at 2 workers
  result: pass
- claim: with -n 0 tests run in the controller process and worker_id is 'master'
  result: pass
- claim: under -n 2 worker_id is never 'master' (tests run only in gwN workers)
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest-xdist.txt
---
