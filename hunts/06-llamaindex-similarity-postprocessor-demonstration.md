# Hunt 06 — LlamaIndex drops the wrong context on a corrupted score

**Target:** [LlamaIndex](https://github.com/run-llama/llama_index) (40k★, the RAG framework) — `llama-index-core` 0.14
**Label:** DEMONSTRATION — *not* a fileable bug (read this carefully)

Like the Haystack hunt, this is honest about its limits. It is **not** a bug in LlamaIndex and no PR was
filed. It demonstrates that a faultline invariant fires on real LlamaIndex code when an upstream score is
corrupted — a real failure *class*, not a library defect.

## The setup
A RAG pipeline scores candidate documents, then keeps the relevant ones with the real
`SimilarityPostprocessor.postprocess_nodes(cutoff=0.5)`, then answers. faultline wraps the scoring step
(a reranker / embedding call) and injects `WrongNumber` — a plausible-but-wrong score, exactly what a
miscalibrated reranker or a stale embedding cache produces.

## What happened
With the scores bent down (0.92 → 0.18, etc.), the **real** `SimilarityPostprocessor` correctly filtered
on the scores it was given — and dropped **every** document. The pipeline then answered anyway, confidently,
from zero surviving context. No error, no warning.

```
import faultline as fl                       # verified on llama-index-core 0.14
...
⚠  wrong-number   FAIL   [SILENT, SILENT, SILENT]
   produced a confident answer with 0 surviving context documents — the similarity filter
   silently dropped everything on corrupted scores
```

Deterministic: 3/3 runs fired.

## Why it's a DEMONSTRATION, not a CATCH
The postprocessor did exactly the right thing with the scores it received — filtering on a corrupted score
is "garbage in," not a LlamaIndex defect. So this stays in the **demonstration** bucket: real library code,
real invariant firing, *not* "a bug we found in LlamaIndex." The value is narrow and real — faultline
surfaces the silent context-loss on a real, popular RAG component, which is exactly the class
("agent answers from empty/wrong context") that costs RAG systems in production.

Reproduce: `evidence/wild_catches/llamaindex_similarity_postprocessor.py` (no API key, deterministic).
