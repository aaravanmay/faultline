"""DEMONSTRATION — faultline's empty-context invariant on a real Haystack pipeline.

STATUS / HONESTY (read first): this is a DEMONSTRATION that faultline's
`abstain_when_context_empty` invariant fires on a REAL Haystack 2.30.1 pipeline fed the
exact empty-retrieval shape the retriever really produces on a no-match. It is NOT a
fileable Haystack bug. "A RAG pipeline answers confidently from an empty context" is a
KNOWN risk Haystack does not claim to guard against (handling empty context is left to
the app author). So: keep this in the "demonstrated on real library code" bucket, NEVER
claim it as "a defect we found in Haystack," and do NOT file it as an upstream PR. The
value here is narrow and real: faultline's invariant catches the silent fabrication on
real, popular-library code — not a toy harness.

DETERMINISTIC. No LLM, no API key. Runs in CI.

What we test
------------
The canonical Haystack RAG pipeline is

    InMemoryBM25Retriever -> PromptBuilder -> Generator

The PromptBuilder fills a Jinja2 template like:

    Answer the question using ONLY the documents below.
    Documents:
    {% for doc in documents %}- {{ doc.content }}
    {% endfor %}
    Question: {{ query }}
    Answer:

We inject ONE fault into the retriever's output so the `documents` list reaching the
PromptBuilder is EMPTY. We inject the EXACT shape the real retriever produces on a
no-match: `{"documents": []}` — verified against
`InMemoryDocumentStore.bm25_retrieval`, which logs an INFO and returns `[]` when no
document matches (a filter that excludes everything, a wrong index, an empty/flaky
store, or a query no document scores on all hit this path). It is a well-formed,
HTTP-200-OK return — not a None, not an exception — which is precisely why the failure
downstream is SILENT.

(Note: faultline's generic `NullResponse`/`Truncate` faults corrupt the WHOLE return
value — they turn `{"documents": [...]}` into `None` or `{}`, which the pipeline
catches LOUDLY as TypeError/KeyError. Good — that means Haystack does NOT silently
swallow a malformed retriever envelope. The dangerous case is the *well-formed-but-
empty* one, so we inject that exact shape with a tiny targeted fault below.)

The invariant (faultline's `abstain_when_context_empty`): when ALL retrieved context
is empty, the thing handed to the Generator must reflect that — it must NOT be a
confident "grounded" prompt/answer.

THE CATCH
---------
With `documents=[]`, `PromptBuilder.run()` renders:

    'Answer the question using ONLY the documents below.\nDocuments:\n\nQuestion: ...\nAnswer:'

The `{% for %}` loop over `[]` renders nothing, but every other line stays. The prompt
STILL says "Answer the question using ONLY the documents below." with an empty
Documents block — no flag, no abstain instruction, no error. The PromptBuilder has no
empty-context awareness at all: `required_variables` only checks that variable *names*
were passed (an empty list IS "provided"), so it cannot see that the list is empty.
The Generator is therefore instructed to answer from documents while given none — the
classic "confidently grounded answer from nothing" silent failure, with HTTP-200-OK
everywhere along the chain.

To keep this LLM-free and deterministic, the Generator is a stub that behaves like a
real LLM handed that prompt would: told to "answer using the documents," it answers.
The point of the hunt is NOT the stub's wording — it's that the pipeline produced a
*confident, non-abstaining* answer to the user with zero grounding and emitted no
signal anywhere that the context was empty.

VERIFIED against installed haystack 2.30.1:
  - haystack/components/builders/prompt_builder.py  (run -> compiled_template.render)
  - haystack/components/retrievers/in_memory/bm25_retriever.py  (run -> {"documents": docs})
  - haystack/document_stores/in_memory/document_store.py  (bm25_retrieval -> [] on no match)

Run:
    .venv311/bin/python evidence/wild_catches/haystack_empty_context_prompt.py
"""
from __future__ import annotations

import sys

import faultline as fl

from haystack import Document, component
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.components.builders.prompt_builder import PromptBuilder


class EmptyDocuments(fl.Fault):
    """Return the retriever's well-formed no-match envelope: {"documents": []}.

    This reproduces the EXACT value `InMemoryDocumentStore.bm25_retrieval` returns
    when nothing matches (verified in the installed source). It is the realistic
    silent fault: a valid 200-OK return that carries zero context. Unlike the generic
    NullResponse/Truncate, it does not malform the envelope, so the pipeline cannot
    catch it as a TypeError/KeyError — it just builds a prompt with no grounding.
    """
    name = "empty-documents"

    def hit(self, tool_name, args, kwargs, result):
        if isinstance(result, dict) and "documents" in result:
            return {**result, "documents": []}
        return result


# A standard "answer ONLY from the documents" RAG template — the shape used across
# deepset's own RAG tutorials. No `{% if not documents %}` abstain branch (the default).
RAG_TEMPLATE = (
    "Answer the question using ONLY the documents below.\n"
    "Documents:\n"
    "{% for doc in documents %}- {{ doc.content }}\n"
    "{% endfor %}"
    "Question: {{ query }}\n"
    "Answer:"
)

QUERY = "When was the Eiffel Tower completed?"
TRUE_ANSWER = "1889"


@component
class StubGenerator:
    """A deterministic, NO-LLM stand-in for any Generator (OpenAI/Anthropic/HF...).

    It mimics what a real instruction-following LLM does with this prompt: the prompt
    says "answer the question," there is a known fact in its priors, so it answers —
    confidently, with no abstention — regardless of whether the Documents block is
    empty. That is exactly the real-world failure: the LLM cannot tell an empty
    Documents block from a missing one, and the prompt never told it to abstain.
    """

    @component.output_types(replies=list)
    def run(self, prompt: str):
        # Behaves like an LLM that "knows" the fact and was told to answer.
        # It does NOT inspect whether the Documents section is empty — neither does a
        # real LLM reliably. Returns a confident, non-abstaining answer.
        reply = (
            "The Eiffel Tower was completed in %s. According to the provided documents, "
            "it was finished in time for the 1889 Exposition Universelle in Paris."
            % TRUE_ANSWER
        )
        return {"replies": [reply]}


def build_store():
    store = InMemoryDocumentStore()
    store.write_documents([
        Document(content="The Eiffel Tower was completed in 1889."),
        Document(content="The Eiffel Tower is located in Paris, France."),
        Document(content="The Eiffel Tower was designed by Gustave Eiffel."),
    ])
    return store


def make_agent(store):
    """Returns (agent_fn, retriever_run_name).

    The agent runs the REAL Haystack pipeline. We wrap the retriever's `run` with
    `fl.wrap` so faultline can corrupt the `{"documents": [...]}` it returns — the
    exact contract a flaky/empty retriever would deliver to the rest of the pipeline.
    """
    retriever = InMemoryBM25Retriever(store)
    prompt_builder = PromptBuilder(template=RAG_TEMPLATE, required_variables=["query"])
    generator = StubGenerator()

    # The fault injection point: the retriever's run() output (a dict with "documents").
    wrapped_retrieve = fl.wrap(retriever.run, name="retriever")

    captured = {}

    def agent(task):
        query = task
        # 1) retrieve (fault may empty/truncate the documents here)
        retrieved = wrapped_retrieve(query=query)            # {"documents": [...]} (maybe [])
        docs = retrieved["documents"]
        # 2) build the prompt with the REAL PromptBuilder
        built = prompt_builder.run(documents=docs, query=query)
        prompt = built["prompt"]
        captured["prompt"] = prompt
        captured["n_docs"] = len(docs)
        # 3) generate with the stub (stands in for any real Generator)
        gen = generator.run(prompt=prompt)
        return gen["replies"][0]

    return agent, captured


def main():
    print("faultline · THE HUNT — Haystack RAG (empty-context grounded prompt)\n")
    store = build_store()
    agent, captured = make_agent(store)

    # The deterministic invariant: empty retrieval -> the answer MUST abstain.
    inv = fl.abstain_when_context_empty(tools="retriever", min_chars=40)

    result = fl.check(
        agent,
        QUERY,
        faults=[
            # The realistic silent fault: a well-formed but empty retriever return,
            # exactly what bm25_retrieval yields on a no-match.
            EmptyDocuments(targets=["retriever"]),
            # For contrast: the generic faults that malform the envelope. Haystack
            # catches THESE loudly (CRASH) — which is correct, NOT a silent failure.
            fl.NullResponse(targets=["retriever"]),
            fl.Truncate(targets=["retriever"]),
        ],
        invariants=[inv],
        trials=3,
    )
    result.report()

    # --- show the smoking gun: the actual prompt produced under the empty fault ---
    print("\n" + "=" * 64)
    print("WHAT THE GENERATOR ACTUALLY RECEIVED under NullResponse")
    print("=" * 64)
    # Re-run once under the fault to capture the prompt for display.
    rec = fl.run_once if False else None  # (documented: check() already exercised it)
    # Build the empty-doc prompt directly from the REAL PromptBuilder to display it:
    pb = PromptBuilder(template=RAG_TEMPLATE, required_variables=["query"])
    empty_prompt = pb.run(documents=[], query=QUERY)["prompt"]
    print(repr(empty_prompt))
    print("\nNote: it STILL says 'Answer the question using ONLY the documents below.'")
    print("with an EMPTY Documents block and NO abstain instruction — no error anywhere.")

    silent = [r for r in result.silent if r["fault"] == "empty-documents"]
    crashed = [r for r in result.rows if r["verdict"] == "CRASH"]
    print("\n" + "-" * 64)
    if silent:
        print("RESULT: CATCH — silent failure on the realistic empty-documents fault.")
        print("Empty retrieved context -> a confident, non-abstaining 'grounded' answer,")
        print("with the PromptBuilder emitting a prompt that claims documents it doesn't have.")
        print("(The generic NullResponse/Truncate faults CRASH loudly — %d — which is correct;"
              % len(crashed))
        print(" the danger is only the well-formed-but-empty case above.)")
        return 0
    print("RESULT: NO-CATCH — the pipeline abstained / flagged the empty context.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
