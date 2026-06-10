# Hunt 04 — Aider wrote a file back missing its bottom half

**Target:** [Aider](https://github.com/Aider-AI/aider) (45k★, AI pair-programming agent)
**Label:** CATCH — [PR #5236](https://github.com/Aider-AI/aider/pull/5236) (open)

## The setup
Aider reads a file, asks the model to edit it, and writes the result back. I armed faultline so
the file **read** came back truncated to its first half — the realistic case of a partial read,
an encoding hiccup, or a tool that silently caps output length.

## What happened
I gave Aider a real task: fix a bug in the top half of `mathutils.py` (`add` returned `a - b`).
Aider fixed the bug correctly — and then **wrote the file back missing everything it never read.**
The file went from 25 lines to 13. Three functions in the bottom half — `area_of_circle`,
`perimeter`, `describe` — were silently deleted. No error, no warning.

```
fault armed : True (read_text truncated to first half)
lines       : before 25  ->  after 13
bottom-half markers lost: ['area_of_circle', 'describe', 'perimeter']

⚠ SILENT FAILURE — aider wrote the file back MISSING code it never read, with no error.
```

The edit it was asked to make succeeded. The data loss was a silent side effect of a bad read.

## The fix
Guard the read (assert it was complete) or assert no-shrink before writing the file back — and
fail loudly instead of committing a truncated file. Regression test in `tests/basic/`.

## Why it matters
A coding agent silently deleting code it didn't see is a direct, expensive failure: it lands in
a commit, passes tests that don't cover the deleted functions, and is found later in production.
