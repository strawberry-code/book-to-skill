---
type: AntiPattern
title: eval / exec on untrusted input
description: eval and exec turn data into code; on request data that is remote code execution.
tags: [security, python]
timestamp: 2026-06-28T00:00:00Z
aliases: [eval injection, exec on request data]
confidence: high
contested: false
status: established
---

# eval / exec on untrusted input

`eval` and `exec` turn data into code. The moment any part of their argument can come from a user, you
have handed that user a Python interpreter — that is remote code execution.

```python
# WRONG — arbitrary code from the request body
result = eval(request.data)
```

- **Why it fails:** an attacker controls what executes in your process.
- **Fix:** parse with a real parser (`json.loads`, `ast.literal_eval` for literals); never `eval` input.

## Related
- [Python](/entities/python.md) — the interpreter being handed to the attacker

# Citations
[1] [Ch 2] "an attacker controls what executes in your process." — [The Mini Guide to Python Code Review](/references/python-code-review.md)
