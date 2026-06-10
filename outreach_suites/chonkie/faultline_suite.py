"""faultline suite for chonkie — catches the silent-content-loss class from PR #604.

What it tests: a pipeline reads its chunking config from a tool, builds a real
chonkie TokenChunker, and chunks a document. faultline corrupts the config the
way real systems do (a bent number, a stale/empty payload) and fails CI if the
pipeline silently loses the document instead of erroring.

Verified against chonkie 1.6.8: chunk_overlap >= 1.0 (e.g. a relative overlap
that drifts to 1.25) returns 0 chunks with NO error — this suite catches that.

Run:  pip install faultline chonkie  &&  faultline run faultline_suite.py
"""
import faultline as fl
from chonkie import TokenChunker

DOC = "The quick brown fox jumps over the lazy dog. " * 60


@fl.tool
def get_chunker_config():
    """Where chunk params come from in a real system (db/env/upstream svc)."""
    return {"chunk_size": 128, "chunk_overlap": 0.25}


def chunk_document(task):
    cfg = get_chunker_config()
    chunker = TokenChunker(chunk_size=cfg["chunk_size"], chunk_overlap=cfg["chunk_overlap"])
    chunks = chunker.chunk(DOC)
    covered = sum(len(c.text) for c in chunks)
    return {"n_chunks": len(chunks), "coverage": covered / len(DOC)}


def no_silent_content_loss(run):
    out = run.get("output") or {}
    if out.get("n_chunks", 0) == 0 or out.get("coverage", 0) < 0.9:
        return ("chunker silently dropped content (chunks=%s, coverage=%.0f%%) — no error was raised"
                % (out.get("n_chunks"), 100 * out.get("coverage", 0)))


def faultline_suite():
    return {
        "agent": chunk_document,
        "task": {},
        "faults": [
            fl.WrongNumber(targets=["get_chunker_config"]),   # overlap 0.25 -> 1.25: the PR #604 class
            fl.NullResponse(targets=["get_chunker_config"]),  # empty config payload
            fl.Truncate(targets=["get_chunker_config"]),      # partial config payload
        ],
        "invariants": [no_silent_content_loss],
        "trials": 3,
    }
