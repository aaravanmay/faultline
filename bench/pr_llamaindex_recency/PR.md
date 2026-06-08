# PR to LlamaIndex (run-llama) — "Fix EmbeddingRecencyPostprocessor comparing against the wrong node's embedding"

**Repo:** https://github.com/run-llama/llama_index  (50k★, active)
**Fork branch (pushed):** https://github.com/run-llama/llama_index/compare/main...aaravanmay:llama_index:fix-recency-embedding-misalignment
**Status:** STAGED — fork pushed, verified. NOT filed yet. *(This is a second, independent bug in
llama_index — separate file/branch from the TreeSummarize PR.)*

## What it fixes
`EmbeddingRecencyPostprocessor._postprocess_nodes`
(`llama-index-core/llama_index/core/postprocessor/node_recency.py`) deduplicates near-duplicate
nodes, keeping the most recent. It sorts nodes by date into `sorted_nodes`, then:

```python
texts = [node.get_content(...) for node in nodes]                # ORIGINAL order
text_embeddings = self.embed_model.get_text_embedding_batch(texts=texts)
...
for idx, node in enumerate(sorted_nodes):                        # SORTED order
    query_embedding = ... sorted_nodes[idx] ...
    for idx2 in range(idx + 1, len(sorted_nodes)):
        node2 = sorted_nodes[idx2]                               # SORTED order
        if np.dot(query_embedding, text_embeddings[idx2]) > cutoff:   # text_embeddings is ORIGINAL-ordered
            node_ids_to_skip.add(node2.node.node_id)
```

`text_embeddings` is built in the **original** `nodes` order, but it's indexed with `idx2` — a
position into the **date-sorted** `sorted_nodes`. Unless the input is already sorted by date,
`text_embeddings[idx2]` belongs to a different node than `node2 = sorted_nodes[idx2]`, so the
similarity check compares the query against the **wrong node's embedding** and silently drops the
wrong nodes (or keeps real duplicates). All lists are the same length, so nothing raises — the
output is a plausible-but-wrong deduplicated list.

**Realistic fault:** the normal case — a retriever returns nodes in relevance order (not date
order), and this postprocessor is applied to drop older near-duplicate versions.

## The fix — `node_recency.py`
Build `texts` (and thus the embeddings) from `sorted_nodes`, so the `idx2` indexing aligns:

```python
texts = [
    node.get_content(metadata_mode=MetadataMode.EMBED) for node in sorted_nodes
]
```

## The test — `tests/postprocessor/test_recency_embedding_alignment.py` (in the fork)
A fake embedder maps `"alpha"`→x, `"bravo"`→y (orthogonal). Three nodes (two are true
duplicates, one unique), input order **not** date-sorted. Correct behavior keeps the newest
duplicate + the unique node and drops the older duplicate (`{n0, n1}`); the misindexing instead
drops the **unique** node (`{n0}`). No live LLM.

**Verified:** with the fix → survivors `{n0, n1}` (**PASS**); on `main` → `{n0}` (**FAIL**).

## Friendly PR title + body
**Title:** Fix EmbeddingRecencyPostprocessor dedup comparing against the wrong node's embedding

**Body:**
> In `EmbeddingRecencyPostprocessor._postprocess_nodes`, `text_embeddings` is built in the
> original `nodes` order, but the dedup loop indexes it with `idx2`, a position into the
> date-sorted `sorted_nodes`. When the input isn't already date-sorted (the normal case), the
> near-duplicate check compares the query against the wrong node's embedding and silently drops
> the wrong nodes. This builds the embeddings from `sorted_nodes` so the indexing aligns.
> Includes a deterministic regression test (fake embedder, no LLM) that fails on `main` and
> passes with the fix.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check the function still matches current `main` first.)
