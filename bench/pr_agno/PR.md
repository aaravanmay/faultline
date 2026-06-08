# PR to Agno (agno-agi) — "De-duplicate list fields when merging extracted JSON objects"

**Repo:** https://github.com/agno-agi/agno  (40.5k★, active — pushed 2026-06-06)
**Fork branch (pushed):** https://github.com/agno-agi/agno/compare/main...aaravanmay:agno:dedup-merged-list-fields
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`parse_response_model_str` (`libs/agno/agno/utils/string.py`) coerces raw LLM text into a
structured `BaseModel`. When the content isn't a single valid JSON object, it falls back to
`_parse_individual_json`, which `_extract_json_objects` splits into the individual objects and
merges. The merge does:

```python
if isinstance(field_value, list):
    if field_name not in merged_data:
        merged_data[field_name] = []
    merged_data[field_name].extend(field_value)   # blind extend, no dedup
else:
    merged_data[field_name] = field_value
```

Scalar fields use last-wins (fine), but **list** fields are blindly `.extend()`ed across every
extracted object. When an LLM emits its structured output as **two concatenated JSON objects**
(a common echo/retry, e.g. `{"keywords":["ai","agents"]} {"keywords":["ai","agents"]}`),
`json.loads` fails on the concatenation, the fallback runs, and every list field gets
**doubled** → `["ai","agents","ai","agents"]`.

**Why it's silent:** the doubled list still validates against the schema (`list[str]` of length 4
is a valid `list[str]`), so it's returned as a valid model with **no exception and no warning**.
The agent proceeds with duplicated list contents.

## The fix — `libs/agno/agno/utils/string.py`
De-duplicate while merging list fields:

```python
        for item in field_value:
            if item not in merged_data[field_name]:
                merged_data[field_name].append(item)
```

## The test — `libs/agno/tests/unit/utils/test_parse_merge_dedup.py` (in the fork)
Feeds two concatenated identical JSON objects; asserts the list field is `["ai","agents"]`, not
doubled. No LLM. Drops into agno's existing `libs/agno/tests/unit/utils/` suite.

**Verified:** with the fix → **PASS**; on `main` → **FAIL**
(`['ai','agents','ai','agents']`; the captured log shows the fallback path triggering).

## Friendly PR title + body
**Title:** Don't duplicate list fields when merging concatenated JSON objects in parse_response_model_str

**Body:**
> When an LLM returns its structured output as two concatenated JSON objects (a common
> echo/retry), `parse_response_model_str` falls back to `_parse_individual_json`, which blindly
> `.extend()`s list fields across every extracted object — so identical objects double the list.
> The doubled list still validates against the schema, so it's returned with no error or warning.
>
> This de-duplicates items when merging list fields. Includes a regression test (no LLM) that
> fails on `main` and passes with the change. (Last-wins for scalar fields is unchanged.)

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check the merge block still matches current `main` first.)
