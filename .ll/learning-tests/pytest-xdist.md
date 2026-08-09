---
target: pytest-xdist
date: '2026-08-08'
status: proven
assertions:
- claim: 'pytest.Config instances running inside an xdist worker have a non-empty workerinput dict attribute containing a workerid key'
  result: pass
- claim: 'pytest.Config instances running on the xdist controller (or in serial mode) do NOT have a workerinput attribute'
  result: pass
- claim: 'Under -n N (N>=1), no test item body ever executes on the controller process itself -- only worker (gwN) processes run test bodies'
  result: pass
- claim: 'A pytest_collection_modifyitems hook that skips items when hasattr(config, "workerinput") causes the test to be SKIPPED on every worker under -n N, with zero non-skipped executions anywhere in that run'
  result: pass
- claim: pytest_xdist_auto_num_workers(config) is invokable as a callable hook returning an int
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest-xdist.txt
---
