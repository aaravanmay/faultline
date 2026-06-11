# Overnight bug-hunt run — state file

**Goal:** find + STAGE (not file) more real, deterministic, fileable bugs in famous OSS agents,
then do the durable product work (invariant library = the moat, launch post, demo script).
**Deadline:** ~6:00am. Decision: STAGE only (fork+fix+test+push+draft), NEVER auto-file —
public PRs under Aarav's name get his eyeball first. Quality > quantity.

## FILED (live PRs — check for maintainer replies)
- **Aider #5236** — apply_edits no-shrink guard (silent data loss). FILED.
- **GPT Researcher #1799** — write_report abstain-on-empty-context (fabrication). FILED.

## STAGED & VERIFIED — ready to file (morning checklist, one click each)
Each: fork pushed under github.com/aaravanmay, fix + deterministic regression test that
PASSES with the fix and FAILS on main (verified locally), PR.md with title+body in
`faultline/bench/pr_<name>/`.

| # | Repo | ★ | Bug (category) | Compare URL -> "Create PR" |
|---|------|---|----------------|---------------------------|
| 1 | stanford-oval/storm | 28k | ConvToSection writes a sourced section from empty retrieval (empty-context fabrication) | https://github.com/stanford-oval/storm/compare/main...aaravanmay:storm:abstain-on-empty-section |
| 2 | eosphoros-ai/DB-GPT | 19k | get_chart_values_by_data wrong column index on NULL rows (wrong-data / crash) | https://github.com/eosphoros-ai/DB-GPT/compare/main...aaravanmay:DB-GPT:fix-null-row-chart-label |
| 3 | sinaptik-ai/pandas-ai | 24k | _validate_response returns NaN/inf as a valid number (silent-wrong number) | https://github.com/sinaptik-ai/pandas-ai/compare/main...aaravanmay:pandas-ai:reject-nan-number |
| 4 | run-llama/llama_index | 50k | TreeSummarize answers from empty context (empty-context abstention) | https://github.com/run-llama/llama_index/compare/main...aaravanmay:llama_index:abstain-on-empty-chunks |
| 5 | Pythagora-io/gpt-pilot | 34k | CodeMonkey.accept_changes overwrites a file with "" (silent data loss) | https://github.com/Pythagora-io/gpt-pilot/compare/main...aaravanmay:gpt-pilot:refuse-empty-overwrite |
| 6 | qodo-ai/qodo-cover (cover-agent) | 5k | verify_report_update only warns on a stale report (violates its own docstring) → newly generated test silently rolled back | https://github.com/qodo-ai/qodo-cover/compare/main...aaravanmay:qodo-cover:raise-on-stale-coverage-report |
| 7 | chonkie-inc/chonkie | 4k | TokenChunker: float chunk_overlap≥1.0 bypasses the int-only guard → negative step → chunk() returns [] (whole doc silently dropped) | https://github.com/chonkie-inc/chonkie/compare/main...aaravanmay:chonkie:validate-computed-overlap |
| 8 | run-llama/llama_index (#2) | 50k | EmbeddingRecencyPostprocessor indexes text_embeddings (original order) with idx2 into sorted_nodes → dedup compares wrong node's embedding → drops wrong nodes | https://github.com/run-llama/llama_index/compare/main...aaravanmay:llama_index:fix-recency-embedding-misalignment |
| 9 | llmware-ai/llmware | 15k | expand_text_result_before never decrements block_id → re-looks-up same block (duplicated context) or infinite loop; fixed in retrieval.py + library.py | https://github.com/llmware-ai/llmware/compare/main...aaravanmay:llmware:fix-expand-before-missing-decrement |
| 10 | langchain-ai/langchain | 139k | ExperimentalMarkdownSyntaxTextSplitter._resolve_code_chunk returns "" on an unterminated code fence → drops the block + everything after it (base branch: master) | https://github.com/langchain-ai/langchain/compare/master...aaravanmay:langchain:preserve-unterminated-code-fence |
| 11 | agno-agi/agno | 41k | _parse_individual_json blindly .extend()s list fields across concatenated JSON objects → silently doubles list contents (still validates → no error) | https://github.com/agno-agi/agno/compare/main...aaravanmay:agno:dedup-merged-list-fields |
| 12 | AnswerDotAI/rerankers | 2k | prep_docs only checks doc_ids[0] AND never writes regenerated ids back → a None doc_id survives → get_score_by_docid/get_result_by_docid return None | https://github.com/AnswerDotAI/rerankers/compare/main...aaravanmay:rerankers:fix-partial-none-doc-ids |
| 13 | topoteretes/cognee | 18k | chunk_by_sentence main loop yields an over-budget chunk for an oversized word mid-stream (tail path raises per docstring; main path doesn't) → flows into embeddings | https://github.com/topoteretes/cognee/compare/main...aaravanmay:cognee:raise-on-oversized-word-midstream |
| 14 | Arize-ai/openinference | 1k | litellm instrumentation writes completion text_tokens (a COUNT) to LLM_COST_COMPLETION_DETAILS_OUTPUT (a USD cost attr) → cost dashboards show token counts as dollars. Fix adds symmetric semconv constant + routes there | https://github.com/Arize-ai/openinference/compare/main...aaravanmay:openinference:fix-completion-text-tokens-cost-attr |
| 15 | jackmpcollins/magentic | 2k | JsonArrayParserState never tracks escapes inside strings → escaped quote \" read as closing quote → iter_streamed_json_array silently yields 0 elements for valid JSON | https://github.com/jackmpcollins/magentic/compare/main...aaravanmay:magentic:fix-escaped-quote-streamed-array |

**Category diversity:** data-loss (Aider, gpt-pilot), empty-context fabrication (GPT-R, STORM, LlamaIndex-TreeSummarize),
wrong-index/column (DB-GPT, LlamaIndex-recency), NaN-as-number (pandas-ai), stale-data-accepted (cover-agent),
content-silently-dropped (chonkie, LangChain markdown splitter), loop-never-advances → duplicated/infinite (llmware),
parser-silently-duplicates (agno), id-alignment/partial-None (rerankers), over-budget-chunk-unvalidated (cognee).
15 distinct real bugs across 14 famous agents (llama_index ×2), 10 categories.

## CONCLUSION (~01:30 — hunt complete at 17 bugs)
Concluded the wave cadence at **17 cleanly-verified bugs across 16 famous agents (12 categories)** —
2 filed (Aider #5236, GPT-R #1799) + 15 staged (all fork branches pushed + verified). 11 scout waves
run. Concluding here is a deliberate judgment call (granted by the user): 17 verified bugs — each with
a fail-on-main/pass-with-fix test — is comprehensive proof many times over (the milestone was "catch 1").
Further grinding is low marginal value vs resource cost. **Backlog if more is wanted:** ragflow (82k,
heavy build), swarms (breaking-shape fix), MetaGPT (provider-import wall), crewAI (borderline). All
deliverables (MORNING_SUMMARY, README, evidence/wild_catches, dad write-up) consistent at 17. Next steps
on Aarav's word: file the 15 staged PRs (one-click checklist in MORNING_SUMMARY), build the backlog 4,
record the demo, build a LangGraph adapter example.

## Verified-by-scout, NOT yet built (backlog — each ~5-line fix, same recipe)
Honest status: scouts read the real source and confirmed the seam; I did not fully build/verify these.
- **geekan/MetaGPT (69k)** — `ConductResearch.run` writes a report from content="" (every URL failed).
  Fix authored on local branch `raise-on-empty-research-content`, but local verify is blocked by
  MetaGPT's eager provider-SDK import chain (sparkai/zhipuai/etc.). 3rd empty-context bug (category
  already covered). Buildable in a full MetaGPT env.
- **crewAIInc/crewAI (53k)** — `_build_observation_message("")` -> "Observation: " (empty tool result,
  no signal). Borderline severity (LLM may just retry) — lowest confidence; left rather than file a wontfix.

## Scout waves 2-3 (new-category hunt) — findings
- **chonkie-inc/chonkie (4.1k★) `TokenChunker`** — NEW category (content silently dropped). BUILT +
  VERIFIED + STAGED (#7 above). Float chunk_overlap≥1.0 bypasses the int-only guard. Active repo.
- **run-llama/llama_index `EmbeddingRecencyPostprocessor` (wave 3)** — wrong-index dedup. BUILT +
  VERIFIED + STAGED (#8). 2nd independent bug in llama_index.
- **llmware-ai/llmware `expand_text_result_before` (wave 3, 14.8k★)** — missing loop decrement →
  duplicated context / infinite loop. BUILT + VERIFIED + STAGED (#9). NEW category. (Gotcha: the repo
  uses CRLF line endings — edited in BINARY mode to avoid a whole-file reformat diff.)
- Rejections (wave 3, already-guarded/not-testable): openai-agents-python (raises MaxTurnsExceeded /
  ModelBehaviorError), langchain RecursiveCharacterTextSplitter (warns), semantic-router (compensated
  downstream), chonkie RecursiveChunker (logic in a Rust extension — not pure-Python testable).
- **Wave 6 finds (real, scout-verified, NOT built — friction noted; fork already created for ragflow):**
  - **infiniflow/ragflow (82k★, active) `rag/app/qa.py` `chunk` TXT branch** — TOP backlog pick. Mid-loop
    `if question and answer:` drops a well-formed Q&A pair with an empty answer cell, while the EOF path
    uses `if question:` (inconsistent sibling guard). Fix = match the EOF guard (1 line). NOT built: `qa.py`
    imports `deepdoc.parser` + `rag.nlp.rag_tokenizer` (heavy models/dicts) and the bug is inside a big
    file-parsing fn → needs a heavier install + test isolation (stub beAdoc/rag_tokenizer). High value (82k).
  - **kyegomez/swarms (6.8k★, active) `parse_and_execute_json`** — `results` dict keyed by function name, so
    two calls to the SAME tool silently overwrite (only last survives). Fix = list of {name,result} — but that
    CHANGES the return shape (breaking) → weaker PR; maintainer should pick the shape. NOT built.
  - Rejections: TaskWeaver + gpt-engineer (ARCHIVED), khoj (off-by-one was balanced / tab-heading is a hang
    not silent-wrong), agency-swarm legacy-citation (writer no longer in-tree).
- **vanna-ai/vanna (23.5k★) `extract_sql`** — NEW category (extraction contamination): a loose
  `\bSELECT\b .*?;` regex runs BEFORE the ```sql fence regex, with re.DOTALL, so on a normal
  fenced response whose prose contains a semicolon it captures the fence markers + an English
  sentence AS the SQL, handed straight to run_sql. Airtight + deterministic (verified). **BUT vanna
  is ARCHIVED (read-only) — a PR can't be merged → NOT fileable.** Keep as a faultline demo/evidence
  catch only (like the LangChain SQL one). Lead for an ACTIVE repo with the same regex-ordering smell:
  WrenAI's new `core/wren/src/wren/engine.py` path (scout couldn't confirm vs current source in budget).
- Rejections (already-guarded): instructor (`_handle_incomplete_output`), langroid (`run_query` row-cap
  warning). WrenAI restructured — old post-processor path 404s, unconfirmed.

## Recipe (the bar every bug clears)
1. DETERMINISTIC function missing a guard (not "the LLM was dumb").
2. Realistic fault (truncate cap / empty result / stale cache / NULL row), not adversarial.
3. Test FAILS on main, PASSES with a small guard, deterministic (mock/avoid the LLM).
4. Active repo, clean small fix, friendly framing. Verify by importing the FORK source (PYTHONPATH), not the installed pkg.

## Verification method note
For frameworks whose module-load pulls heavy global config (DB-GPT's `CFG = Config()`), I verified
the REAL function by loading its source file directly / stubbing only the unrelated module-level
dependency — the function logic under test runs exactly as in production.

## Durable product work (this run)
- [x] Invariant library (the moat) — `faultline/invariants.py`, 4 invariants, 16/16 tests pass (py3.9)
- [x] Launch post (Show HN / blog) draft — `LAUNCH_POST.md`
- [x] Self-contained demo (`examples/demo_silent_rag.py`) + `RECORDING_SCRIPT.md`
- [x] Updated `What_I_Built.html` (dad) + `evidence/wild_catches/README.md` for all 6 results
- [x] `MORNING_SUMMARY.md` — the one-file readout + file-each checklist
- [ ] (optional) stage a 5th bug (gpt-pilot) / commit faultline product work on a branch
