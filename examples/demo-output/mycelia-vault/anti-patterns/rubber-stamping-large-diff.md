---
type: AntiPattern
title: Rubber-stamping a large diff
description: Approving a change you didn't understand launders its risk under your name.
tags: [code-review]
timestamp: 2026-06-28T00:00:00Z
aliases: [rubber stamp, LGTM without reading]
confidence: high
contested: false
status: established
---

# Rubber-stamping a large diff

Approving a change you did not actually understand is worse than not reviewing it, because it launders
the risk under your name. If you cannot explain what a hunk does, you have only seen it — you have not
reviewed it.

- **Why it fails:** unreviewed risk ships with your approval attached.
- **Fix:** ask to split the change; review pieces you can hold in your head.

## Related
- [Review for intent, not style](/frameworks/review-for-intent.md) — understand before approving
- [Small diffs](/principles/small-diffs.md) — what makes a real review possible

# Citations
[1] [Ch 1] "If you cannot explain what a hunk does, you have not reviewed it" — [The Mini Guide to Python Code Review](/references/python-code-review.md)
