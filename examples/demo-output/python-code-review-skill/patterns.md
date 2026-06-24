# Patterns — python-code-review-skill

## Review for Intent, Not Style
**When to use**: every review, before writing any line-level comment.
**How**: read the whole diff once for what changed and why; only then read it again for line-level issues; let the formatter/linter own style.
**Trade-offs**: a slower first pass, but human attention lands on correctness and safety instead of spacing.
**Source**: [Ch 1] "review for intent first, let the formatter handle style."

## The Reviewer's Charter
**When to use**: any non-trivial change, especially one that touches many files or mixes concerns.
**How**: answer in order — is it correct? safe? clear? small enough to understand? — and if it is not small enough, ask for a split before continuing.
**Trade-offs**: more round-trips when changes are large, but each piece gets a genuine review.
**Source**: [Ch 1] "Is it correct? Is it safe? Is it clear? Is it small enough to understand?"

## Parameterized Queries (vs string-built SQL)
**When to use**: any SQL statement that includes a user-supplied value.
**How**: pass values as bound parameters (`execute(sql, (v,))`); never concatenate or f-string input into the query text.
**Trade-offs**: none worth mentioning — it is both safer and usually clearer.
**Source**: [Ch 2] "Never concatenate or f-string user input into SQL; pass it as a bound parameter."

## Guard Clause
**When to use**: a function with nested validation before its real work.
**How**: check each precondition and `return`/`raise` immediately, leaving the success path unindented at the top level.
**Trade-offs**: more `return` statements, but a flatter, more scannable function.
**Source**: [Ch 3] "Return early on the exceptional cases so the main path stays flat and at the top."

## Sentinel Default (vs mutable default argument)
**When to use**: any function that wants a mutable default (list/dict/set).
**How**: default the parameter to `None`, then build the real value inside the function body.
**Trade-offs**: two extra lines per function; eliminates a whole class of shared-state bugs.
**Source**: [Ch 3] "A mutable default argument is shared state wearing the costume of a fresh value."

## Small Diffs
**When to use**: always; especially when a change begins mixing refactor with behavior change.
**How**: separate refactors from behavior changes into different commits or pull requests.
**Trade-offs**: more pull requests to manage, far higher review quality per change.
**Source**: [Ch 3] "Prefer many small, focused diffs over one large one"
