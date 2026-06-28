---
type: MOC
title: "The Mini Guide to Python Code Review — map of content"
description: "Navigation hub for every note sourced from the Python code review guide."
tags: [code-review, python, moc]
timestamp: 2026-06-28T00:00:00Z
source: /references/python-code-review.md
---

# The Mini Guide to Python Code Review — Map of Content

## Concepts
- [Code review](/concepts/code-review.md) — a conversation about intent
- [SQL injection](/concepts/sql-injection.md) — untrusted input reaching the query text

## Frameworks
- [Review for intent, not style](/frameworks/review-for-intent.md)
- [The reviewer's charter](/frameworks/the-reviewers-charter.md)

## Principles
- [Small diffs](/principles/small-diffs.md)

## Methods
- [Guard clause](/methods/guard-clause.md)

## Entities
- [Python](/entities/python.md)

## Anti-patterns
- [Rubber-stamping a large diff](/anti-patterns/rubber-stamping-large-diff.md)
- [SQL built by string concatenation](/anti-patterns/sql-string-concatenation.md)
- [eval / exec on untrusted input](/anti-patterns/eval-exec-on-untrusted-input.md)
- [Bare except that swallows errors](/anti-patterns/bare-except.md)
- [assert used for runtime validation](/anti-patterns/assert-for-runtime-validation.md)
- [Mutable default argument](/anti-patterns/mutable-default-argument.md)
