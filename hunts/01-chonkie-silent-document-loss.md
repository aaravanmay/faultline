# Hunt 01 — chonkie silently dropped an entire document

**Target:** [chonkie](https://github.com/chonkie-inc/chonkie) (4k★, a popular text-chunking library for RAG)
**Label:** CATCH — [PR #604](https://github.com/chonkie-inc/chonkie/pull/604) (open)
**Cost:** a few cents (the hunt used faultline's fuzz mode)

## The setup
A RAG pipeline reads its chunking config from somewhere (a database, an env var, an
upstream service) and builds a `chonkie.TokenChunker`. I wrapped that config source as a
tool and gave faultline exactly one rule: *chunking must never silently return zero chunks.*

## What happened
faultline's **fuzz mode**, pointed at the real installed chonkie with only that rule,
autonomously generated 37 inputs and found the break by itself: a **float** `chunk_overlap`
of `1.25`. chonkie's overlap guard is gated on `isinstance(chunk_overlap, int)`, so a float
≥ 1.0 slips past it, becomes `int(1.25 * chunk_size)` ≥ `chunk_size`, the step goes
non-positive, and `chunk()` returns `[]` — **the entire document is dropped from the index,
with no error.** (The docstring already promises it raises in this case. It doesn't.)

```
import faultline as fl                       # verified on chonkie 1.6.8
...
⚠  wrong-number   FAIL   [SILENT, SILENT, SILENT]
   chunker silently dropped content (chunks=0, coverage=0%) — no error was raised
✗  null-response  CRASH  TypeError: 'NoneType' object is not subscriptable
✗  truncate       CRASH  KeyError: 'chunk_overlap'
Resilience: 0/3 faults handled
```

## The fix
Validate the *computed* overlap (after the float→int conversion), so any overlap ≥ chunk_size
raises `ValueError` as the docstring promises — instead of silently indexing nothing. A
regression test fails before the fix and passes after. PR is open for the maintainers to judge.

## Why it matters
In a RAG system this is the worst kind of failure: no crash, no log, no error — the document
just isn't in the index, and every later answer is silently missing it.
