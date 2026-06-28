---
type: AntiPattern
title: SQL built by string concatenation
description: Gluing user input into SQL text is the classic injection bug; bind parameters instead.
tags: [security, sql, python]
timestamp: 2026-06-28T00:00:00Z
aliases: [f-string SQL, string-built query]
confidence: high
contested: false
status: established
---

# SQL built by string concatenation

Building a SQL statement by gluing user input into a string is the classic injection bug: the input can
close the literal and append arbitrary SQL.

```python
# WRONG — user_id flows straight into the query text
cursor.execute("SELECT * FROM users WHERE id = " + user_id)
# RIGHT — the driver binds the value, never the string
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

- **Why it fails:** input becomes query code, not data.
- **Fix:** a parameterized query / prepared statement for every user-supplied value.

## Related
- [SQL injection](/concepts/sql-injection.md) — the vulnerability this shape creates
- [Python](/entities/python.md) — DB-API parameter binding is the fix

# Citations
[1] [Ch 2] "Never concatenate or f-string user input into SQL; pass it as a bound parameter." — [The Mini Guide to Python Code Review](/references/python-code-review.md)
