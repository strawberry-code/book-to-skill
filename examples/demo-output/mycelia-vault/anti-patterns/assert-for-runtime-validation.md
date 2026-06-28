---
type: AntiPattern
title: assert used for runtime validation
description: assert statements are stripped under python -O, so the check may not run in production.
tags: [python, security]
timestamp: 2026-06-28T00:00:00Z
aliases: [assert as a guard]
confidence: high
contested: false
status: established
---

# assert used for runtime validation

`assert` statements are removed when Python runs with `-O`. Validation that disappears under optimization
is not validation — an `assert` guarding a security or correctness check is a check that may not run in
production.

```python
# WRONG — vanishes under python -O
assert user.is_admin, "forbidden"
```

- **Why it fails:** optimized builds drop the assertion and the check with it.
- **Fix:** raise an explicit exception (`raise PermissionError(...)`) for anything that must always run.

## Related
- [Python](/entities/python.md) — the `-O` flag is what makes this dangerous

# Citations
[1] [Ch 2] "Validation that disappears under optimization is not validation" — [The Mini Guide to Python Code Review](/references/python-code-review.md)
