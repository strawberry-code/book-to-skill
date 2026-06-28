---
type: Framework
title: The reviewer's charter
description: A review answers four questions in order — correct? safe? clear? small enough to understand?
tags: [code-review]
timestamp: 2026-06-28T00:00:00Z
aliases: [four questions of review]
confidence: high
contested: false
status: established
---

# The reviewer's charter

A good review answers four questions, in order: **Is it correct? Is it safe? Is it clear? Is it small
enough to understand?** If it is not small enough, the honest review is "please split this" — a diff you
cannot hold in your head is a diff you cannot actually review.

- **When:** when a change touches many files or mixes concerns.
- **How:** ask for the split before reviewing further; review the pieces.

## Related
- [Code review](/concepts/code-review.md) — the activity this framework guides
- [Small diffs](/principles/small-diffs.md) — the answer to the fourth question

# Citations
[1] [Ch 1] "Is it correct? Is it safe? Is it clear? Is it small enough to understand?" — [The Mini Guide to Python Code Review](/references/python-code-review.md)
