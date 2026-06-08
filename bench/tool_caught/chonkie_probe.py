"""faultline mode-2 (probe) GENUINELY catching the real chonkie content-drop bug. No LLM.

Run:  python3 bench/tool_caught/chonkie_probe.py

No broken tool here - just a degenerate-but-accepted config value. The `degenerate-overlap`
mutator turns a sane chunk_overlap into a fractional one >= 1.0; the property "a non-empty
document must not chunk to nothing" then catches that the REAL chonkie silently dropped the
whole document. This is the second testing mode finding an edge-input bug fault-injection can't.
"""
import faultline as fl
from chonkie import TokenChunker  # the REAL released chonkie (unpatched)

DOC = "word " * 50  # a clearly non-empty, 250-char document


def chunk_with_overlap(chunk_overlap):
    chunker = TokenChunker(tokenizer="character", chunk_size=10, chunk_overlap=chunk_overlap)
    return chunker.chunk(DOC)


def content_must_survive(inp, out, err):
    if err is None and isinstance(out, list) and len(out) == 0:
        return "chunk_overlap=%r silently produced 0 chunks from a non-empty document (content lost)" % (inp,)


cases = fl.mutations(
    0,                                                  # baseline: a sane overlap
    ("degenerate-overlap>=1.0", lambda base: 1.5),      # mutator -> a valid-but-degenerate config
)
fl.probe(chunk_with_overlap, cases, [content_must_survive],
         label="chonkie: content preservation", unpack=False).report()
