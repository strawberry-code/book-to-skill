# Activation Cues — python-code-review-skill
When the current task matches a trigger below, recall the named framework and, if
useful, read the cited chapter before advising.

| When you're… (trigger) | Recall | Where |
|------------------------|--------|-------|
| reviewing a PR / diff, "code review", "approve" | Review for Intent, Not Style + Reviewer's Charter | ch01 |
| a diff touches many files / mixes refactor + behavior | Small Diffs / "please split this" | ch01, ch03 |
| building a SQL string with `+` or an f-string in `execute(...)` | SQL built by string concatenation → parameterize | ch02 |
| `eval(` / `exec(` over request, argv, env, or file data | eval/exec on untrusted input → RCE | ch02 |
| `except:` or `except Exception:` followed by `pass` | Bare except that swallows errors | ch02 |
| `assert` guarding auth / input validation / a real check | assert used for runtime validation | ch02 |
| a function signature with `=[]`, `={}`, or `=set()` default | Mutable default argument → sentinel default | ch03 |
| a function body indenting steadily to the right | Guard Clause → return early | ch03 |

## Triggers index (keyword → framework → chapter)
- **code review**, **PR**, **diff**, **approve** → Review for Intent, Not Style → ch01
- **large diff**, **mixed concerns** → Small Diffs → ch03
- **SQL**, **execute**, **query** + interpolation → SQL built by string concatenation → ch02
- **eval**, **exec** + input → eval/exec on untrusted input → ch02
- **except**, **pass** → Bare except that swallows errors → ch02
- **assert** + validation → assert used for runtime validation → ch02
- **def … =[]**, **mutable default** → Mutable default argument → ch03
- **nested if**, **deep indentation** → Guard Clause → ch03
