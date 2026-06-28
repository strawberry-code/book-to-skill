---
type: Concept
title: SQL injection
description: Untrusted input reaching SQL as code rather than data, letting an attacker rewrite the query.
tags: [security, sql, python]
timestamp: 2026-06-28T00:00:00Z
aliases: [SQLi, query injection]
confidence: high
contested: false
status: established
---

# SQL injection

When user input is glued into a SQL statement's text, the input can close the literal and append
arbitrary SQL — the classic injection bug. The fix is to pass values as bound parameters so the driver
treats them as data, never as query text.

## Related
- [SQL built by string concatenation](/anti-patterns/sql-string-concatenation.md) — the shape that causes it
- [Python](/entities/python.md) — the language whose DB-API parameter binding prevents it

# Citations
[1] [Ch 2] "Never concatenate or f-string user input into SQL; pass it as a bound parameter." — [The Mini Guide to Python Code Review](/references/python-code-review.md)
