---
type: AntiPattern
title: Mutable default argument
description: A mutable default is evaluated once and shared across calls, leaking state between them.
tags: [python, correctness]
timestamp: 2026-06-28T00:00:00Z
aliases: [default list argument, shared default]
confidence: high
contested: false
status: established
---

# Mutable default argument

A default argument is evaluated once, at definition time, and shared across every call. A mutable default
— a list or dict — therefore leaks state between calls: it is shared state wearing the costume of a fresh
value.

```python
# WRONG — the same list is reused on every call
def append_item(item, bucket=[]):
    bucket.append(item)
    return bucket
# RIGHT — sentinel default, fresh list each call
def append_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
```

- **Why it fails:** state accumulates across calls that look independent.
- **Fix:** default to `None` and build the real value inside the function.

## Related
- [Python](/entities/python.md) — the evaluation rule that causes this
- [Guard clause](/methods/guard-clause.md) — the `if bucket is None` sentinel check

# Citations
[1] [Ch 3] "A mutable default argument is shared state wearing the costume of a fresh value." — [The Mini Guide to Python Code Review](/references/python-code-review.md)
