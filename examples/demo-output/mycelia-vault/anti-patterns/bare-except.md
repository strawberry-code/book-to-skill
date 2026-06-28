---
type: AntiPattern
title: Bare except that swallows errors
description: An empty or bare except hides the very failure you need to see.
tags: [python, error-handling]
timestamp: 2026-06-28T00:00:00Z
aliases: [silent except, except pass]
confidence: high
contested: false
status: established
---

# Bare except that swallows errors

A bare `except:` (or `except Exception:` with an empty body) hides the failure you most need to see — a
silent except is a bug you have agreed not to find out about.

```python
# WRONG — the real error vanishes
try:
    charge_card(order)
except:
    pass
```

- **Why it fails:** failures disappear instead of being handled or surfaced.
- **Fix:** catch the specific exception you expect, and log or re-raise the rest.

## Related
- [Python](/entities/python.md) — the language whose exception model this misuses

# Citations
[1] [Ch 2] "A silent except is a bug you have agreed not to find out about." — [The Mini Guide to Python Code Review](/references/python-code-review.md)
