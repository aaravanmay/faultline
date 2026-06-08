# PR to rerankers (AnswerDotAI) — "prep_docs: regenerate doc_ids when ANY is None, and write them back"

**Repo:** https://github.com/AnswerDotAI/rerankers  (1.6k★, active)
**Fork branch (pushed):** https://github.com/AnswerDotAI/rerankers/compare/main...aaravanmay:rerankers:fix-partial-none-doc-ids
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").
*(Confirm the base branch name — `main` vs `master` — in the compare URL.)*

## What it fixes
`prep_docs` (`rerankers/utils.py`), in the branch that takes pre-built `Document` objects with
`doc_ids=None`:

```python
elif doc_ids is None:
    doc_ids = [doc.doc_id for doc in docs]
    if doc_ids[0] is None:                       # only checks the FIRST id
        print("'None' doc_ids detected, reverting to auto-generated integer ids...")
        doc_ids = list(range(len(docs)))         # ...and never written back to docs
```

Two silent problems:
1. **Only `doc_ids[0]` is checked.** If the first doc has a valid id but any *later* doc has
   `doc_id=None` (common — a vector-store hit that lost its id, or a partially-tagged list), the
   guard is skipped and the `None` id silently survives into the returned `Document`s.
2. **The regenerated ids are never applied.** Even in the all-None case, `doc_ids` is reassigned
   to `range(...)` but the `Document` objects are returned unchanged (the sibling branch does
   `doc.doc_id = doc_ids[i]`; this branch doesn't), so the docs keep their `None` ids.

A surviving `None` doc_id then silently breaks id-based lookups —
`RankedResults.get_score_by_docid` / `get_result_by_docid` do
`next((r ... if r.document.doc_id == doc_id), None)` → return `None` ("not found") — and the
langchain integration's `doc_list[r.doc_id]` indexing. No exception, no warning.

Verified: `prep_docs([Document("A",doc_id="a"), Document("B",doc_id=None), Document("C",doc_id="c")])`
returns ids `['a', None, 'c']` on `main`.

## The fix — `rerankers/utils.py`
```python
            if any(doc_id is None for doc_id in doc_ids):
                print("'None' doc_ids detected, reverting to auto-generated integer ids...")
                doc_ids = list(range(len(docs)))
                for i, doc in enumerate(docs):
                    doc.doc_id = doc_ids[i]
```

## The test — `tests/test_prep_docs_partial_none.py` (in the fork)
Three docs, the middle one with `doc_id=None`; asserts no `None` ids survive. No LLM, no ML deps
(torch imports in `utils.py` are guarded by try/except).

**Verified:** with the fix → **PASS**; on `main` → **FAIL** (`assert None not in ['a', None, 'c']`).

## Friendly PR title + body
**Title:** prep_docs: detect None in any doc_id (not just the first) and apply regenerated ids

**Body:**
> In `prep_docs`, when `doc_ids` is `None`, it harvested ids from the `Document`s but only
> checked `doc_ids[0]`, so a `None` id on any later doc survived silently — and it never wrote
> the regenerated integer ids back onto the docs, so even the all-None path returned docs with
> `None` ids. A surviving `None` doc_id then breaks `get_score_by_docid`/`get_result_by_docid`
> (they return `None`) and the langchain `doc_list[r.doc_id]` indexing, with no error.
>
> This checks all ids with `any(...)` and assigns the regenerated ids back to the docs. Includes
> a regression test (no LLM/ML deps) that fails on `main` and passes with the change.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"** (confirm base branch).
2. Paste the title + body. Submit.
3. (Re-check `prep_docs` still matches current upstream first.)
