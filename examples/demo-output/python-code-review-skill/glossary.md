# Glossary — python-code-review-skill

**Bare except** — an `except:` or `except Exception:` clause whose body swallows the error instead of handling or re-raising it (Ch 2)
**Guard clause** — an early `return`/`raise` that handles an exceptional case up front, keeping the success path flat (Ch 3)
**Intent** — what the author was trying to achieve with a change; judged before mechanics in a review (Ch 1)
**Mutable default argument** — a list/dict/set used as a parameter default, evaluated once and shared across calls (Ch 3)
**Parameterized query** — a SQL statement whose values are bound by the driver rather than spliced into the query string (Ch 2)
**Remote code execution (RCE)** — an attacker controlling what code runs in your process, e.g. via `eval`/`exec` on input (Ch 2)
**Reviewer's Charter** — the ordered review checklist: correct? safe? clear? small enough to understand? (Ch 1)
**Rubber-stamping** — approving a change you did not actually understand, laundering its risk under your name (Ch 1)
**Sentinel default** — a `None` (or other immutable) default that is replaced by a freshly built value inside the function (Ch 3)
**Small Diffs** — the practice of preferring many small, focused changes over one large one to earn a real review (Ch 3)
