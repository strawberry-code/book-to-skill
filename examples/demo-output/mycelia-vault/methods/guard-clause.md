---
type: Method
title: Guard clause
description: Return early on exceptional cases so the main path stays flat and at the top.
tags: [maintainability, python]
timestamp: 2026-06-28T00:00:00Z
aliases: [early return]
confidence: high
contested: false
status: established
---

# Guard clause

Deeply nested `if` blocks hide the happy path. Return early on the exceptional cases so the main path
stays flat and unindented at the top. A function whose body marches steadily to the right is asking to be
flattened with guard clauses.

- **When:** any function with nested validation before its real work.
- **How:** check each precondition and `return`/`raise` immediately; leave the success path unindented.
- **Trade-off:** more `return` statements, but a flatter, more scannable function.

## Related
- [Code review](/concepts/code-review.md) — maintainability is part of what a review defends
- [Mutable default argument](/anti-patterns/mutable-default-argument.md) — another Python readability/correctness trap

# Citations
[1] [Ch 3] "Return early on the exceptional cases so the main path stays flat and at the top." — [The Mini Guide to Python Code Review](/references/python-code-review.md)
