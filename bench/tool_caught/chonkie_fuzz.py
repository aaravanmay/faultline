"""faultline mode-3 (FUZZING) DISCOVERING the chonkie bug on its own. No LLM, real chonkie.

I do NOT tell it which config is bad. I give it (a) the rule ("a non-empty document must not chunk
to nothing") and (b) a baseline config, and the fuzzer GENERATES edge-case configs and finds which
one silently breaks the rule. The tool does the finding.
"""
import faultline as fl
from chonkie import TokenChunker  # real released chonkie (unpatched)

DOC = "word " * 50

def chunk_with_overlap(chunk_overlap):
    return TokenChunker(tokenizer="character", chunk_size=10, chunk_overlap=chunk_overlap).chunk(DOC)

def content_must_survive(inp, out, err):
    if err is None and isinstance(out, list) and len(out) == 0:
        return "chunk_overlap=%r silently produced 0 chunks from a non-empty document" % (inp,)

# base = a sane overlap (0); the fuzzer invents the rest
fl.fuzz(chunk_with_overlap, 0, [content_must_survive],
        label="chonkie: fuzz the overlap config").report()
