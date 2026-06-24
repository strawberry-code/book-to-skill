# Review Rules — python-code-review-skill

Audit a codebase against this book's rules; each is checkable by Read/Grep/Glob.
Citations are chapter-level only (no per-rule page anchors); the quoted name after
[Ch N] is the verbatim anti-pattern title from that chapter file.

## Rules index
| id | rule | severity | confidence | scope | source |
|----|------|----------|------------|-------|--------|
| PY-SQLI-01 | SQL built by string concatenation | violation | high | Python code | ch02 |
| PY-EVAL-02 | eval/exec on untrusted input | violation | high | Python code | ch02 |
| PY-EXCEPT-03 | bare except that swallows errors | violation | medium | Python code | ch02 |
| PY-ASSERT-04 | assert used for runtime validation | violation | medium | Python code | ch02 |
| PY-MUTDEF-05 | mutable default argument | suggestion | high | Python code | ch03 |

## Rules

### PY-SQLI-01 — SQL query built by string concatenation
- intent: user input must never be concatenated into SQL; use parameterized queries.
- scope.glob: ["**/*.py"]
- detect.grep:                       # broad ERE candidate-catchers (a hit is NOT yet a finding)
  - '(SELECT|INSERT|UPDATE|DELETE|WHERE)[^;]*"\s*\+\s*'
  - 'f"[^"]*\b(SELECT|INSERT|UPDATE|DELETE)\b[^"]*\{'
- detect.context: the interpolated token must be a variable/param, not a literal or a validated allowlist constant. Confirm by Reading the hit line ±3.
- detect.requires: ≥1 SQL-keyword signal AND ≥1 interpolation signal on the same statement.
- severity: violation
- confidence: high
- exclude.glob: ["**/test*/**","**/*_test.py","**/*_spec.py","**/migrations/**","**/fixtures/**","**/examples/**","**/vendor/**","**/node_modules/**","**/generated/**"]
- exclude.when: the interpolated value is a literal, an enum/allowlist constant, or a validated table/column name.
- source: [Ch 2] "SQL built by string concatenation"
- fix: use a parameterized query / prepared statement; bind user values, never build the string.

### PY-EVAL-02 — eval or exec on untrusted input
- intent: `eval`/`exec` turn data into code; over request/argv data this is remote code execution.
- scope.glob: ["**/*.py"]
- detect.grep:
  - '\b(eval|exec)\s*\('
- detect.context: a finding only when the argument can originate from input (request, argv, file, env, socket). `eval` over a trusted literal constant is not a finding.
- detect.requires: the argument traces to external/untrusted data.
- severity: violation
- confidence: high
- exclude.glob: ["**/test*/**","**/*_test.py","**/fixtures/**","**/examples/**","**/vendor/**","**/generated/**"]
- exclude.when: the argument is a hardcoded literal under the author's control, or it is `ast.literal_eval` (a safe parser, not `eval`).
- source: [Ch 2] "eval or exec on untrusted input"
- fix: parse with a real parser (`json.loads`, `ast.literal_eval` for literals); never `eval` input.

### PY-EXCEPT-03 — bare except that swallows errors
- intent: a bare `except:` (or `except Exception:`) with an empty/`pass` body hides failures.
- scope.glob: ["**/*.py"]
- detect.grep:
  - 'except\s*:'
  - 'except\s+Exception\s*:'
- detect.context: a finding only when the handler body is `pass`/empty or merely swallows. A handler that logs, re-raises, or handles meaningfully is fine. Read the hit ±3 lines.
- detect.requires: handler body does not log, re-raise, or otherwise act on the error.
- severity: violation
- confidence: medium
- exclude.glob: ["**/test*/**","**/*_test.py","**/fixtures/**","**/examples/**","**/vendor/**","**/generated/**"]
- exclude.when: the body logs, re-raises, returns a meaningful fallback, or the bare except is the documented top-level last-resort guard of a long-running loop.
- source: [Ch 2] "Bare except that swallows errors"
- fix: catch the specific exception you expect; log or re-raise the rest.

### PY-ASSERT-04 — assert used for runtime validation
- intent: `assert` is stripped under `python -O`; security/correctness checks must always run.
- scope.glob: ["**/*.py"]
- detect.grep:
  - '^\s*assert\s+'
- detect.context: a finding only when the assertion guards a security or correctness invariant (auth, input validation, state guarantee) — not an internal developer sanity-check or a test.
- detect.requires: the asserted condition is a runtime precondition that must hold in production.
- severity: violation
- confidence: medium
- exclude.glob: ["**/test*/**","**/*_test.py","**/*_spec.py","**/fixtures/**","**/examples/**","**/conftest.py"]
- exclude.when: the file is a test, or the assert is a pure internal invariant with no security/correctness consequence.
- source: [Ch 2] "assert used for runtime validation"
- fix: raise an explicit exception (e.g. `raise PermissionError(...)`) for anything that must always run.

### PY-MUTDEF-05 — mutable default argument
- intent: a mutable default (list/dict/set) is evaluated once and shared across calls, leaking state.
- scope.glob: ["**/*.py"]
- detect.grep:
  - 'def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|set\(\))'
- detect.context: a literal mutable default in a function signature. Confirm by Reading the signature.
- detect.requires: a `[]`, `{}`, or `set()` literal as a parameter default.
- severity: suggestion
- confidence: high
- exclude.glob: ["**/test*/**","**/*_test.py","**/fixtures/**","**/examples/**","**/vendor/**","**/generated/**"]
- exclude.when: the default is an immutable value or a sentinel (`None`, a tuple, a frozenset).
- source: [Ch 3] "Mutable default argument"
- fix: default to `None` and build the real value inside the function body.
