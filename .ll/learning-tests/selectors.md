---
target: selectors
date: '2026-09-04'
status: proven
assertions:
- claim: sel.select(timeout=0) returns an empty list immediately without blocking, distinct
    from timeout=None which blocks indefinitely
  result: pass
- claim: SelectorKey is a namedtuple exposing .fileobj, .fd, .events, and .data by attribute
    access
  result: pass
- claim: sel.unregister() on a fileobj that was never registered raises KeyError
  result: pass
- claim: sel.modify(fileobj, events) without a data argument resets key.data to None, discarding
    the previously registered data
  result: pass
- claim: sel.get_key(fileobj) returns the same SelectorKey as the one returned by sel.register()
  result: pass
raw_output_path: .ll/learning-tests/raw/selectors.txt
---
