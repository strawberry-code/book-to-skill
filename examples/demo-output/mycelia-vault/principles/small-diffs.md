---
type: Principle
title: Small diffs
description: Prefer many small, focused diffs over one large one — small diffs get a real review.
tags: [code-review]
timestamp: 2026-06-28T00:00:00Z
aliases: [keep changes small, small pull requests]
confidence: high
contested: false
status: established
---

# Small diffs

The strongest predictor of a useful review is the size of the change. Prefer many small, focused diffs
over one large one, because a small diff gets a real review and a large one gets a rubber stamp. Separate
refactors from behavior changes into different commits or pull requests.

- **When:** always; especially when a change starts to mix refactoring with behavior change.
- **Trade-off:** more pull requests to manage, far higher review quality per change.

## Related
- [Code review](/concepts/code-review.md) — the activity this principle serves
- [The reviewer's charter](/frameworks/the-reviewers-charter.md) — "small enough to understand?"
- [Rubber-stamping a large diff](/anti-patterns/rubber-stamping-large-diff.md) — what large diffs invite

# Citations
[1] [Ch 3] "Prefer many small, focused diffs over one large one" — [The Mini Guide to Python Code Review](/references/python-code-review.md)
