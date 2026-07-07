---
target: pytest-xdist
date: '2026-07-07'
status: proven
assertions:
- claim: 'pytest.Config instances running inside an xdist worker have a non-empty workerinput dict attribute containing a workerid key'
  result: pass
- claim: 'pytest.Config instances running on the xdist controller (or in serial mode) do NOT have a workerinput attribute'
  result: pass
- claim: Markers registered in [tool.pytest.ini_options].markers are accepted by --strict-markers collection
  result: pass
- claim: pytest.mark.skip(reason=...) constructs a MarkDecorator whose .mark.name == "skip" and .mark.kwargs["reason"] == <reason>
  result: pass
- claim: pytest_xdist_auto_num_workers(config) is invokable as a callable hook returning an int
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest-xdist.txt
---