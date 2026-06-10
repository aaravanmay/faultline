# Hunt 05 — Haystack builds a "grounded" prompt from zero documents

**Target:** [Haystack](https://github.com/deepset-ai/haystack) (22k★, RAG/LLM pipeline framework)
**Label:** DEMONSTRATION — *not* a fileable bug (read this carefully)

This one is honest about its limits. It is **not** a bug in Haystack and I did **not** file a PR.
It is a demonstration that faultline's invariant fires on real Haystack code for a *known* risk
Haystack doesn't claim to guard against. Including it because publishing the boundary is the point.

## The setup
The canonical Haystack RAG pipeline: `Retriever -> PromptBuilder -> Generator`. I injected the
exact shape Haystack's retriever really returns on a no-match — `{"documents": []}`, a clean,
HTTP-200, well-formed empty result (a wrong filter, an empty index, a query nothing scores on).
Invariant: *when the retrieved context is empty, the thing handed to the model must reflect that.*

## What happened
With zero documents, `PromptBuilder` still renders the template verbatim — "Answer using ONLY
the documents below" followed by an empty Documents block — and hands it to the model as if it
were grounded. No flag, no abstain instruction, no error. The model is told to answer from
documents while given none: the classic "confident answer from nothing."

```
WHAT THE GENERATOR ACTUALLY RECEIVED under an empty-documents retrieval:
'Answer the question using ONLY the documents below.\nDocuments:\nQuestion: ...\nAnswer:'
RESULT: a confident, non-abstaining prompt with zero grounding, 200-OK everywhere.
```

(Note: faultline's generic `NullResponse`/`Truncate` faults — which mangle the *whole* return
value into `None` or `{}` — crash Haystack loudly. That's correct behavior. The dangerous case
is only the *well-formed-but-empty* one above.)

## Why it's a DEMONSTRATION, not a CATCH
"A RAG pipeline answers from empty context" is a well-known risk that Haystack leaves to the app
author to handle — it's not a defect Haystack claims to prevent. So this stays in the
demonstration bucket: real library code, real invariant firing, *not* "a bug we found in
Haystack." The value is narrow and real — faultline catches the silent fabrication on real,
popular code, not a toy harness.
