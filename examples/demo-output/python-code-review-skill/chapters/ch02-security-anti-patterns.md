# Chapter 2: Security Anti-Patterns in Python

## Core Idea
Most real Python security bugs are a handful of recurring shapes, and every one of them is
visible in the diff once you know what to look for.

## Frameworks Introduced
- **Dangerous-shape recognition**: learn the small set of injection/error shapes by sight so they jump out of a diff.
  - When to use: every review of code that touches input, queries, or error handling.
  - How: scan for the four shapes below (SQL concat, eval/exec on input, bare except, assert-validation).
  - Source: [Ch 2] "They are a handful of shapes that recur"

## Key Concepts
- **Parameterized query**: a query whose values are bound by the driver, never spliced into the string. [Ch 2]
- **Remote code execution (RCE)**: an attacker controlling what executes in your process. [Ch 2]

## Anti-patterns
- **SQL built by string concatenation**: input can close the literal and append arbitrary SQL — Source: [Ch 2] "Never concatenate or f-string user input into SQL; pass it as a bound parameter."
- **eval or exec on untrusted input**: the user gains a Python interpreter — Source: [Ch 2] "Treat `eval`/`exec` on request data as remote code execution, because that is exactly what it is."
- **Bare except that swallows errors**: failures disappear instead of being handled — Source: [Ch 2] "A silent except is a bug you have agreed not to find out about."
- **assert used for runtime validation**: `-O` drops the assertion and the check with it — Source: [Ch 2] "Validation that disappears under optimization is not validation"

## Code Examples
```python
# WRONG — user_id flows straight into the query text
cursor.execute("SELECT * FROM users WHERE id = " + user_id)

# RIGHT — the driver binds the value, never the string
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```
- **What it demonstrates**: parameter binding closes the SQL-injection shape.

## Reference Tables
| Shape | Signal in the diff | Fix |
|-------|--------------------|-----|
| SQL concat | `"... " + var` / f-string in `execute(...)` | bound parameter |
| eval/exec on input | `eval(`/`exec(` over request/argv data | real parser; never eval input |
| bare except | `except:` / `except Exception:` + `pass` | catch specific, log or re-raise |
| assert validation | `assert` guarding security/correctness | `raise` an explicit exception |

## Key Takeaways
1. Bind every user-supplied value; never build SQL by concatenation.
2. `eval`/`exec` over input is RCE — parse instead.
3. Never swallow exceptions silently; never guard production checks with `assert`.

## Connects To
- **Ch 1**: these are the "Is it safe?" question of the Reviewer's Charter, made concrete.
