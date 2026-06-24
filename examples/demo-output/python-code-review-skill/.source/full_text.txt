# The Mini Guide to Python Code Review

**Author**: Strawberry Code (original demo content)
**License**: CC0 1.0 — public-domain dedication. Free to copy, modify, and redistribute.

> This is an **original**, fully redistributable mini-guide written specifically as a safe demo input for [book-to-skill](https://github.com/strawberry-code/book-to-skill). It contains no copyrighted excerpts. It is deliberately small (three short chapters) so the generated skill is easy to read end-to-end.

---

## Chapter 1 — The Code Review Mindset

A code review is not a gate you stand at to block people. It is a conversation about intent. The single most useful habit a reviewer can build is to read for *what the author was trying to do* before reacting to *how they did it*.

### Framework: Review for Intent, Not Style

Style is cheap to fix and a machine can do it; intent is expensive to get wrong and only a human can judge it. So spend your attention where it pays: **review for intent first, let the formatter handle style.** When you find yourself writing a comment about spacing or quote characters, stop and let the linter say it instead.

- When to use: every review, before the first line-level comment.
- How: read the whole diff once for *what changed and why*; only then read it again for line-level issues.

### Framework: The Reviewer's Charter

A good review answers four questions in order: **Is it correct? Is it safe? Is it clear? Is it small enough to understand?** If the answer to "is it small enough" is no, the honest review is "please split this", because **a diff you cannot hold in your head is a diff you cannot actually review.**

- When to use: when a change touches many files or mixes concerns.
- How: ask for the change to be split before reviewing further; review the pieces.

### Anti-pattern: Rubber-stamping a large diff

Approving a change you did not actually understand is worse than not reviewing it, because it launders the risk under your name. **If you cannot explain what a hunk does, you have not reviewed it** — you have only seen it.

---

## Chapter 2 — Security Anti-Patterns in Python

Most real security bugs in everyday Python are not exotic. **They are a handful of shapes that recur**, and every one of them is visible in the diff if you know what to look for.

### Anti-pattern: SQL built by string concatenation

Building a SQL statement by gluing user input into a string is the classic injection bug. **Never concatenate or f-string user input into SQL; pass it as a bound parameter.**

```python
# WRONG — user_id flows straight into the query text
cursor.execute("SELECT * FROM users WHERE id = " + user_id)

# RIGHT — the driver binds the value, never the string
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

- Why it fails: the input can close the literal and append arbitrary SQL.
- Fix: use a parameterized query / prepared statement for every user-supplied value.

### Anti-pattern: eval or exec on untrusted input

`eval` and `exec` turn data into code. The moment any part of their argument can come from a user, you have handed that user a Python interpreter. **Treat `eval`/`exec` on request data as remote code execution, because that is exactly what it is.**

```python
# WRONG — arbitrary code from the request body
result = eval(request.data)
```

- Why it fails: an attacker controls what executes in your process.
- Fix: parse with a real parser (`json.loads`, `ast.literal_eval` for literals); never `eval` input.

### Anti-pattern: Bare except that swallows errors

A bare `except:` (or `except Exception:` with an empty body) hides the failure you most need to see. **A silent except is a bug you have agreed not to find out about.**

```python
# WRONG — the real error vanishes
try:
    charge_card(order)
except:
    pass
```

- Why it fails: failures disappear instead of being handled or surfaced.
- Fix: catch the specific exception you expect, and log or re-raise the rest.

### Anti-pattern: assert used for runtime validation

`assert` statements are removed when Python runs with `-O`. **Validation that disappears under optimization is not validation** — an `assert` guarding a security or correctness check is a check that may not run in production.

```python
# WRONG — vanishes under python -O
assert user.is_admin, "forbidden"
```

- Why it fails: optimized builds drop the assertion and the check with it.
- Fix: raise an explicit exception (`raise PermissionError(...)`) for anything that must always run.

---

## Chapter 3 — Maintainability Patterns

Code is read far more often than it is written, so the reviewer's job is partly to defend the next reader. Three small habits carry most of the weight.

### Anti-pattern: Mutable default argument

A default argument is evaluated once, at definition time, and then shared across every call. A mutable default — a list or dict — therefore leaks state between calls. **A mutable default argument is shared state wearing the costume of a fresh value.**

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

- Why it fails: state accumulates across calls that look independent.
- Fix: default to `None` and build the real value inside the function.

### Pattern: Guard Clause

Deeply nested `if` blocks hide the happy path. **Return early on the exceptional cases so the main path stays flat and at the top.** A function whose body marches steadily to the right is asking to be flattened with guard clauses.

- When to use: any function with nested validation before its real work.
- How: check each precondition and `return`/`raise` immediately; leave the success path unindented.
- Trade-offs: more `return` statements, but a flatter, more scannable function.

### Pattern: Small Diffs

The strongest predictor of a useful review is the size of the change. **Prefer many small, focused diffs over one large one**, because a small diff gets a real review and a large one gets a rubber stamp.

- When to use: always; especially when a change starts to mix refactoring with behavior change.
- How: separate refactors from behavior changes into different commits or pull requests.
- Trade-offs: more pull requests to manage, far higher review quality per change.

---

## Closing

Review for intent, keep changes small, and learn the handful of dangerous shapes by sight. Most of code review is not cleverness — it is attention, spent in the right order.
