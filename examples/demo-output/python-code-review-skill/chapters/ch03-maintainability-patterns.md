# Chapter 3: Maintainability Patterns

## Core Idea
Code is read far more often than written, so the reviewer defends the next reader — three
small habits carry most of the weight.

## Frameworks Introduced
- **Guard Clause**: return early on exceptional cases so the main path stays flat and at the top.
  - When to use: any function with nested validation before its real work.
  - How: check each precondition and `return`/`raise` immediately; leave the success path unindented.
  - Source: [Ch 3] "Return early on the exceptional cases so the main path stays flat and at the top."
- **Small Diffs**: prefer many small, focused changes over one large one.
  - When to use: always; especially when a change starts mixing refactor with behavior change.
  - How: separate refactors from behavior changes into different commits or pull requests.
  - Source: [Ch 3] "Prefer many small, focused diffs over one large one"

## Key Concepts
- **Guard clause**: an early `return`/`raise` that handles an exceptional case up front. [Ch 3]
- **Sentinel default**: `None` default replaced by a fresh value inside the function. [Ch 3]

## Mental Models
- A function whose body marches steadily to the right is asking to be flattened with guard clauses.
- A small diff gets a real review; a large one gets a rubber stamp.

## Anti-patterns
- **Mutable default argument**: a default is evaluated once and shared across calls, leaking state — Source: [Ch 3] "A mutable default argument is shared state wearing the costume of a fresh value."

## Code Examples
```python
# WRONG — the same list is reused on every call
def append_item(item, bucket=[]):
    bucket.append(item)
    return bucket

# RIGHT — sentinel default, fresh list each call
def append_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
```
- **What it demonstrates**: the sentinel-default fix for the mutable-default shape.

## Key Takeaways
1. Default mutable arguments to `None`; build the real value inside the function.
2. Flatten nested validation with guard clauses.
3. Keep diffs small and single-purpose to earn a real review.

## Connects To
- **Ch 1**: Small Diffs operationalizes the Charter's "small enough to understand" question.
