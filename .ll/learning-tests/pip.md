---
target: pip
date: '2026-09-11'
status: proven
assertions:
- claim: pip --version embeds the absolute site-packages path and python tag of the interpreter pip is bound to
  result: pass
- claim: the shebang interpreter of bare pip is a different file than bare python's sys.executable (PATH drift)
  result: pass
- claim: python -m pip reports a site-packages path under the invoking python's own prefix
  result: pass
- claim: bare pip and python -m pip disagree on the install Location of the little-loops distribution
  result: pass
- claim: the little_loops module imported by bare python does not live in the site-packages bare pip manages
  result: pass
- claim: bare pip and python -m pip see different installed-package counts (separate universes)
  result: pass
raw_output_path: .ll/learning-tests/raw/pip.txt
---
