# Chapter 1: The Code Review Mindset

## Core Idea
A review is a conversation about intent, not a style gate — read for *what the author
was trying to do* before reacting to *how they did it*.

## Frameworks Introduced
- **Review for Intent, Not Style**: spend attention where it pays — correctness and intent — and let tools handle style.
  - When to use: every review, before the first line-level comment.
  - How: read the whole diff once for what changed and why; only then read it again for line-level issues.
  - Source: [Ch 1] "review for intent first, let the formatter handle style."
- **The Reviewer's Charter**: a review answers four questions in order — correct? safe? clear? small enough to understand?
  - When to use: when a change touches many files or mixes concerns.
  - How: if it is not small enough, ask for it to be split, then review the pieces.
  - Source: [Ch 1] "Is it correct? Is it safe? Is it clear? Is it small enough to understand?"

## Key Concepts
- **Intent**: what the author was trying to achieve; judge it before mechanics. [Ch 1]
- **Reviewer's Charter**: the ordered correctness → safety → clarity → size checklist. [Ch 1]

## Mental Models
- Think of style comments as the linter's job, not yours — when you start typing one, let the tool say it instead.
- Use "please split this" as a valid review outcome.
  - Source: [Ch 1] "a diff you cannot hold in your head is a diff you cannot actually review."

## Anti-patterns
- **Rubber-stamping a large diff**: approving a change you did not understand launders the risk under your name — Source: [Ch 1] "If you cannot explain what a hunk does, you have not reviewed it"

## Key Takeaways
1. Read the whole diff for intent before commenting on lines.
2. Let formatters/linters own style; spend human attention on correctness and safety.
3. "Split this" is a legitimate and often correct review.

## Connects To
- **Ch 3**: the Small Diffs pattern is the Charter's "small enough" question made into a habit.
