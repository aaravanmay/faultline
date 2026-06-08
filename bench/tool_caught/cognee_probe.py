"""faultline mode-2 catching the real cognee oversized-chunk bug. No LLM, real (unpatched) cognee.

Rule it checks: every chunk produced must respect the size limit. The tool injects one over-long
word into a normal sentence and sees the REAL cognee silently emit a chunk far bigger than the
limit (which then gets fed into the AI's memory).
"""
import sys, types, importlib.util
import faultline as fl

for _n in ("cognee", "cognee.infrastructure", "cognee.infrastructure.databases",
           "cognee.infrastructure.databases.vector", "cognee.infrastructure.databases.vector.embeddings",
           "cognee.tasks", "cognee.tasks.chunks"):
    _m = types.ModuleType(_n); _m.__path__ = []; sys.modules[_n] = _m
sys.modules["cognee.infrastructure.databases.vector.embeddings"].get_embedding_engine = lambda *a, **k: None

def _load(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(sp); sys.modules[name] = mod; sp.loader.exec_module(mod); return mod
_load("cognee.tasks.chunks.chunk_by_word", "/tmp/cog_word_unpatched.py")
CHUNK = _load("cognee.tasks.chunks.chunk_by_sentence", "/tmp/cog_sentence_unpatched.py")
CHUNK.get_word_size = lambda w, *a, **k: len(w)   # word size = character length (no embeddings needed)

MAX = 5
def chunk_sizes(text):
    return [size for (_pid, _s, size, _t) in CHUNK.chunk_by_sentence(text, maximum_size=MAX)]

def every_chunk_within_limit(inp, out, err):
    if err is None and out and max(out) > MAX:
        return "a chunk of size %d exceeds the %d-token limit (an oversized word slipped through)" % (max(out), MAX)

cases = fl.mutations(
    "hi ok no done",                                                     # all short words
    ("inject-oversized-word", lambda s: s.replace("ok", "supercalifragilistic")),
)
fl.probe(chunk_sizes, cases, [every_chunk_within_limit],
         label="cognee: chunk size limit", unpack=False).report()
