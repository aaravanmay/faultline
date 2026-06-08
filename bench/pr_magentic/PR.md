# PR to magentic (jackmpcollins) — "Handle backslash escapes inside strings in the streamed JSON array parser"

**Repo:** https://github.com/jackmpcollins/magentic  (2.4k★, active)
**Fork branch (pushed):** https://github.com/jackmpcollins/magentic/compare/main...aaravanmay:magentic:fix-escaped-quote-streamed-array
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`JsonArrayParserState.update` (`src/magentic/streaming.py`), used by `iter_streamed_json_array`
to stream a function's `Iterable[...]` return out of the LLM's tool-call args:

```python
def update(self, char):
    if self.in_string:
        if char == '"' and not self.is_escaped:   # checks is_escaped...
            self.in_string = False
    elif char == '"':
        self.in_string = True
    ...
    elif char == "\\":                             # ...but this is only reachable when NOT in_string
        self.is_escaped = not self.is_escaped
    else:
        self.is_escaped = False
```

While **inside** a string, only the `if self.in_string:` branch runs — and it never sets
`is_escaped`. So `is_escaped` is always `False` inside strings, and an **escaped quote `\"`** is
read as the string's **closing** quote. That desyncs the parser (`array_level` never returns to
0, the element separator never fires), so `iter_streamed_json_array` **silently yields zero
elements** for perfectly valid JSON like `["he said \"hi\"", "bye"]`. No exception — and pydantic
happily validates the empty `list`.

**Realistic fault:** any magentic function typed `-> Iterable[str]` whose LLM output contains a
quote (extremely common in generated text). The user gets `[]` instead of the items.

Verified end-to-end: `list(iter_streamed_json_array([json.dumps(['he said "hi"', "bye"])]))`
returns **0** elements on `main`.

## The fix — `src/magentic/streaming.py`
Track escapes inside the string branch too:

```python
        if self.in_string:
            if self.is_escaped:
                self.is_escaped = False
            elif char == "\\":
                self.is_escaped = True
            elif char == '"':
                self.in_string = False
```

## The test — `tests/test_streaming_escaped_quote.py` (in the fork)
Streams `["he said \"hi\"", "bye"]` and asserts 2 elements that round-trip correctly. Pure stdlib
(`streaming.py` has no third-party imports).

**Verified:** with the fix → **2 elements (PASS)**; on `main` → **0 elements (FAIL)**.

## Friendly PR title + body
**Title:** Fix streamed JSON array parser dropping all elements on an escaped quote

**Body:**
> `JsonArrayParserState.update` never tracks backslash escapes while inside a string (the
> `elif char == "\\"` branch is only reachable when not in a string), so an escaped quote `\"`
> is read as the closing quote. That desyncs the parser and `iter_streamed_json_array` silently
> yields **zero** elements for valid JSON like `["he said \"hi\"", "bye"]` — no error, and the
> empty list passes validation. This handles escapes inside the string branch. Includes a
> regression test that fails on `main` (0 elements) and passes with the fix.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check `update` still matches current `main` first.)
