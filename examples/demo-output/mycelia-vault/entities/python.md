---
type: Entity
title: Python
description: The programming language whose everyday security bugs recur as a handful of recognizable shapes.
tags: [language, python]
timestamp: 2026-06-28T00:00:00Z
aliases: [CPython]
confidence: high
contested: false
status: established
---

# Python

Python is the language this guide reviews. Its common, real-world security bugs are not exotic: they are
a small set of shapes that recur and are visible in the diff if you know what to look for. Each is
catalogued as an anti-pattern below.

## Related
- [SQL injection](/concepts/sql-injection.md) — prevented by Python DB-API parameter binding
- [SQL built by string concatenation](/anti-patterns/sql-string-concatenation.md)
- [eval / exec on untrusted input](/anti-patterns/eval-exec-on-untrusted-input.md)
- [Bare except that swallows errors](/anti-patterns/bare-except.md)
- [assert used for runtime validation](/anti-patterns/assert-for-runtime-validation.md)
- [Mutable default argument](/anti-patterns/mutable-default-argument.md)

# Citations
[1] [Ch 2] "a handful of shapes that recur" — [The Mini Guide to Python Code Review](/references/python-code-review.md)
