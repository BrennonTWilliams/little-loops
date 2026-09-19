---
target: MutationObserver
date: '2026-09-19'
status: proven
assertions:
- claim: the callback is delivered asynchronously, after the mutating code finishes but before a setTimeout(0) task
  result: pass
- claim: multiple synchronous mutations are batched into one callback invocation with multiple records
  result: pass
- claim: setting textContent on an element yields a single childList record with one added and one removed node
  result: pass
- claim: setting textContent on an element does not emit a characterData record, but mutating an existing text node's data does
  result: pass
- claim: attributeOldValue reports the prior value (null for a new attribute), and attributeFilter excludes other attributes
  result: pass
- claim: without subtree:true, mutations to a grandchild are not observed; with subtree:true they are
  result: pass
- claim: takeRecords() returns pending records synchronously and suppresses the callback; disconnect() drops pending records
  result: pass
- claim: observe() with no attributes/childList/characterData option throws TypeError
  result: pass
- claim: mutating the observed node inside the callback re-invokes the callback
  result: pass
- claim: setAttribute to an identical value still queues an attributes record
  result: pass
raw_output_path: .ll/learning-tests/raw/mutationobserver.txt
---
