# faultline — silent failures caught in the wild (real famous OSS agents)

Seventeen real silent failures across sixteen popular agents (LlamaIndex had two), each caught by
faultline's deterministic detector. Each is now a fix + regression test (test fails before the
fix, passes after). Total hunt cost: a few cents (Claude Haiku).

| Agent | Stars | Catch | Fix status |
|---|---|---|---|
| **Aider** | 45k | Truncated file read → wrote the file back **missing its bottom half** (25→13 lines, 3 functions deleted), no error. | **PR #5236 filed (OPEN)** |
| **GPT Researcher** | 27k | Every page scraped came back empty → wrote a **13k-char confident report + fabricated citations**, zero uncertainty. | **PR #1799 filed (OPEN)** |
| **LlamaIndex** | 50k | `TreeSummarize` answered a question from **empty context** (blank/empty retrieved nodes) — confident answer from no sources. | staged: `aaravanmay/llama_index:abstain-on-empty-chunks` |
| **GPT Pilot** | 34k | `accept_changes` **overwrote a file with empty content** ("" from a truncated/fence-only LLM reply) — wiped real code, no warning. | staged: `aaravanmay/gpt-pilot:refuse-empty-overwrite` |
| **pandas-ai** | 24k | Aggregation over an empty result returned **`NaN` as a valid number** (NaN passes the numeric type check). | **PR #1894 filed (OPEN)** |
| **STORM** | 28k | Empty retrieval → wrote a **"sourced" Wikipedia section with citation markers pointing at no sources**. | staged: `aaravanmay/storm:abstain-on-empty-section` |
| **DB-GPT** | 19k | NULL row with a datetime/id dimension → **labeled the chart with the wrong column** (last column's value); crashes or mislabels. | staged: `aaravanmay/DB-GPT:fix-null-row-chart-label` |
| **cover-agent** (qodo) | 5k | A **stale coverage report** was silently accepted (only warned, despite its docstring promising it raises) → newly generated test silently rolled back. | staged: `aaravanmay/qodo-cover:raise-on-stale-coverage-report` |
| **chonkie** | 4k | A float `chunk_overlap` ≥ 1.0 bypassed the int-only guard → negative step → `chunk()` returned `[]`, **silently dropping the entire document** from the index. | **PR #604 filed (OPEN)** |
| **LlamaIndex** (#2) | 50k | `EmbeddingRecencyPostprocessor` indexed `text_embeddings` (original order) with a position into the date-**sorted** list → near-duplicate dedup compared the **wrong node's embedding** and dropped the wrong nodes. | staged: `aaravanmay/llama_index:fix-recency-embedding-misalignment` |
| **llmware** | 15k | `expand_text_result_before` never decremented `block_id` → re-looked-up the same block (duplicated "expanded context") or **looped forever** if the lookup returned None. | staged: `aaravanmay/llmware:fix-expand-before-missing-decrement` |
| **LangChain** | 139k | `ExperimentalMarkdownSyntaxTextSplitter` returned `""` on an **unterminated code fence**, silently dropping the code block and every section after it. | PR #37964 filed — **CLOSED** by LangChain's issue-link bot (process gate, not a maintainer verdict) |
| **Agno** | 41k | `parse_response_model_str` merged concatenated JSON objects by blindly extending list fields → **silently doubled** list contents (still schema-valid, no error). | staged: `aaravanmay/agno:dedup-merged-list-fields` |
| **rerankers** (AnswerDotAI) | 2k | `prep_docs` only checked the first doc_id (and never wrote regenerated ids back), so a **`None` doc_id survived** → `get_score_by_docid` silently returned "not found". | staged: `aaravanmay/rerankers:fix-partial-none-doc-ids` |
| **cognee** | 18k | `chunk_by_sentence` silently emitted an **over-budget chunk** for an oversized word mid-stream (the tail path raises per the docstring; the main loop didn't). | staged: `aaravanmay/cognee:raise-on-oversized-word-midstream` |
| **OpenInference** (Arize) | 1k | litellm instrumentation wrote a completion token **count** into a **cost (USD)** span attribute → a cost dashboard reads token counts as dollars. | **PR #3227 filed (OPEN)** |
| **magentic** | 2k | the streamed-JSON-array parser never tracked escapes inside strings, so an escaped quote `\"` **silently produced zero elements** for valid JSON. | staged: `aaravanmay/magentic:fix-escaped-quote-streamed-array` |

Each staged fix has a PR package (title + body + verified test) in `../../bench/pr_<name>/PR.md`.

**Also caught, kept as demos (not filed):**
- **LangChain SQL agent** reported a wrong total (284,731) as fact when given a corrupted/partial
  query result (true total 2,847,312). The cleanest framing is a usage issue, not a bug in their
  code — so it's a demo, not a PR.
- **Vanna** (23.5k★, text-to-SQL) — `extract_sql` matches a loose `\bSELECT\b .*?;` regex *before*
  the ```sql fence regex (with `re.DOTALL`), so a normal fenced response whose explanation contains
  a semicolon gets the **code-fence markers + an English sentence returned as the SQL** and passed
  to `run_sql`. A real, distinct-category catch (extraction contamination) — but **vanna is archived
  (read-only)**, so there's nothing to file. Kept as evidence the detector generalizes past
  empty-context bugs.

We only file fixes we're confident are real, *fixable* framework bugs in maintained repos.

## Category diversity (why this isn't one trick)
- **Silent data loss:** Aider (truncated read → file shrink), GPT Pilot (empty reply → file wiped).
- **Empty-context fabrication:** GPT Researcher, STORM, LlamaIndex.
- **Wrong-number / wrong-column:** pandas-ai (NaN-as-number), DB-GPT (wrong chart column).
- **Stale-data accepted:** cover-agent (stale coverage report → wrong rollback decision).
- **Content silently dropped / truncated:** chonkie (numeric-coercion guard bypass → whole document chunked into nothing); LangChain markdown splitter (unterminated code fence → rest of the doc dropped).
- **Wrong-index misalignment:** LlamaIndex recency dedup (embeddings indexed in the wrong order → wrong nodes dropped).
- **Loop never advances:** llmware (missing decrement → duplicated context / infinite loop).
- **Parser silently duplicates:** agno (blind list-merge across concatenated JSON → doubled fields).
- **Broken id-alignment:** rerankers (a None doc_id survives → id-based lookups silently fail).
- **Unvalidated over-budget output:** cognee (oversized word mid-stream → chunk exceeds the size limit silently).
- **Metric written to the wrong field:** OpenInference (a token count recorded under a cost/USD attribute).
- **Streaming-parser desync:** magentic (an escaped quote drops every element → silent empty result).

These same failure modes are now codified as reusable, deterministic invariants in
`faultline/invariants.py` — the detection moat.
