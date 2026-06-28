---
type: Framework
title: Review for intent, not style
description: Spend review attention on intent (only a human can judge it); let the formatter handle style.
tags: [code-review]
timestamp: 2026-06-28T00:00:00Z
aliases: [intent over style]
confidence: high
contested: false
status: established
---

# Review for intent, not style

Style is cheap to fix and a machine can do it; intent is expensive to get wrong and only a human can
judge it. So spend attention where it pays: read the whole diff once for *what changed and why*, then
again for line-level issues. When you catch yourself commenting on spacing or quotes, let the linter say
it instead.

- **When:** every review, before the first line-level comment.
- **How:** read for intent first; defer style to tooling.

## Related
- [Code review](/concepts/code-review.md) — the activity this framework guides
- [Rubber-stamping a large diff](/anti-patterns/rubber-stamping-large-diff.md) — the failure when intent isn't actually understood

# Citations
[1] [Ch 1] "review for intent first, let the formatter handle style" — [The Mini Guide to Python Code Review](/references/python-code-review.md)
