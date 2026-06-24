# Cheatsheet — python-code-review-skill

## Review order (the Reviewer's Charter)
1. **Correct?** — does it do what it intends?
2. **Safe?** — any of the dangerous shapes below?
3. **Clear?** — will the next reader understand it?
4. **Small enough?** — if not, ask to split. *(Ch 1)*

## Dangerous shapes — spot them in the diff
| Shape | Signal | Fix | Rule |
|-------|--------|-----|------|
| SQL by concatenation | `"… " + var` / f-string in `execute()` | bound parameter | PY-SQLI-01 |
| eval/exec on input | `eval(` / `exec(` over request/argv | real parser; never eval input | PY-EVAL-02 |
| bare except | `except:` / `except Exception:` + `pass` | catch specific; log/re-raise | PY-EXCEPT-03 |
| assert validation | `assert` guarding a real check | `raise` an explicit exception | PY-ASSERT-04 |
| mutable default | `def f(x=[])` / `={}` | `=None`, build inside | PY-MUTDEF-05 |

## Style vs intent
- Spacing, quotes, import order → **linter/formatter**, not a review comment.
- Correctness, safety, clarity, size → **the reviewer**. *(Ch 1)*

## When a change is too big
- "Please split this" is a valid review. A diff you cannot hold in your head cannot be reviewed. *(Ch 1, Ch 3)*
