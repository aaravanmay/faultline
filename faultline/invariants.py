"""faultline.invariants — reusable behavioral invariants distilled from REAL silent
failures we found (and fixed) in popular open-source agents.

An *invariant* is a callable ``inv(run) -> Optional[str]``: it returns a short message
when the rule is broken, else ``None``. Pass a list to ``fl.check(..., invariants=[...])``.

Unlike a stochastic LLM-judge, these are **deterministic and fault-specific** — that is the
detection rigor that makes "200 OK but wrong" catchable in CI rather than in production.

A ``run`` is::

    {"events": [ {"tool", "args", "kwargs", "result", ...}, ... ],
     "output": <whatever the agent returned>,
     "error":  <exception or None>}

Provenance — every invariant here ships because we hit the exact bug in the wild and filed
or staged a fix for it:

  numeric_answer_finite        <- pandas-ai: NaN from an aggregation over empty data was
                                  returned as a valid number (PR: reject-nan-number).
  abstain_when_context_empty   <- GPT Researcher #1799 / STORM / LlamaIndex: a confident,
                                  "sourced" report written from empty retrieval.
  no_poison_parroting          <- the WrongNumber / StaleData family: the corrupted value
                                  echoed verbatim into the answer as if it were true.
  no_silent_shrink             <- Aider #5236: a truncated read silently rewrote a file to a
                                  fraction of its original size.

All invariants are factories returning a closure, so you parametrize them once and reuse:

    inv = numeric_answer_finite()
    res = fl.check(agent, task, faults=[...], invariants=[inv])
"""
from __future__ import annotations

import math
import re

__all__ = [
    "numeric_answer_finite",
    "abstain_when_context_empty",
    "no_poison_parroting",
    "no_silent_shrink",
    "tools_really_called",
    "DEFAULT_ABSTAIN_MARKERS",
]

DEFAULT_ABSTAIN_MARKERS = (
    "could not", "couldn't", "cannot", "can't", "no sources", "no source",
    "no results", "no data", "not able", "no information", "insufficient information",
    "unable to", "i don't know", "i do not know", "n/a", "empty",
)


# ---------------------------------------------------------------------------
# Helpers over RUN / event dicts
# ---------------------------------------------------------------------------

def _text(value):
    """Best-effort flatten of an agent output into a single searchable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_text(v) for v in value)
    return str(value)


def _is_empty_result(result):
    """True if a tool *result* carries no usable content (the empty/blank/null case)."""
    if result is None:
        return True
    if isinstance(result, str):
        return result.strip() == ""
    if isinstance(result, (list, tuple, dict, set)):
        # a container of only-empty things still counts as empty
        if len(result) == 0:
            return True
        items = result.values() if isinstance(result, dict) else result
        return all(_is_empty_result(x) for x in items)
    return False


def _events(run, tools):
    names = {tools} if isinstance(tools, str) else set(tools)
    return [ev for ev in run.get("events", []) if ev.get("tool") in names]


def _first_content(ev):
    """The 'content' argument of a write-like call: first positional arg, else first kwarg."""
    args = ev.get("args") or []
    if args:
        return args[0] if len(args) == 1 else args[-1]
    kwargs = ev.get("kwargs") or {}
    for k in ("content", "text", "data", "new_content", "body"):
        if k in kwargs:
            return kwargs[k]
    return next(iter(kwargs.values()), None) if kwargs else None


def _size(value):
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(value)
    except TypeError:
        return len(str(value))


def _extract_number(output):
    """Pull a single numeric answer out of common output shapes; None if not numeric."""
    if isinstance(output, bool):
        return None
    if isinstance(output, (int, float)):
        return float(output)
    if isinstance(output, dict):
        for k in ("value", "answer", "result", "number"):
            if k in output and isinstance(output[k], (int, float)) and not isinstance(output[k], bool):
                return float(output[k])
        return None
    if isinstance(output, str):
        m = re.search(r"-?\d+(?:\.\d+)?|nan|inf|-inf", output.strip(), re.IGNORECASE)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _looks_like_abstention(text, markers):
    # Word-boundary match, not bare substring — so a marker doesn't false-match inside an
    # unrelated word ("n/a" inside "n/applications", "empty" inside "emptyset"), which would
    # wrongly read a confident fabricated answer as an honest abstention (a false negative).
    low = text.lower()
    for m in markers:
        if re.search(r"(?<![a-z0-9])" + re.escape(m) + r"(?![a-z0-9])", low):
            return True
    return False


# ---------------------------------------------------------------------------
# The invariants
# ---------------------------------------------------------------------------

def numeric_answer_finite(extract=_extract_number):
    """The agent's numeric answer must be finite — never NaN or +/-inf.

    Origin: pandas-ai returned ``df["x"].mean()`` over a zero-row result (= NaN) as a
    valid number. NaN/inf are floats, so naive ``isinstance(v, float)`` checks pass them.

    ``extract(output) -> Optional[float]`` lets you adapt to your output shape; the default
    handles raw numbers, ``{"value": ...}``-style dicts, and the first number in a string.
    """
    def inv(run):
        val = extract(run.get("output"))
        if val is None:
            return None
        if isinstance(val, float) and not math.isfinite(val):
            return "numeric answer is not finite (%r) — likely an aggregation over empty data" % val
        return None
    return inv


def abstain_when_context_empty(tools, min_chars=200, abstain_markers=DEFAULT_ABSTAIN_MARKERS):
    """If EVERY result from the retrieval *tools* was empty, the output must abstain.

    Origin: GPT Researcher / STORM / LlamaIndex each wrote a long, confident, "sourced"
    answer when all retrieval came back empty (blocked, rate-limited, or no hits).

    Fires only when (a) at least one of *tools* was called, (b) all their results were
    empty/blank, and (c) the output is a long answer that does NOT read as an abstention.
    """
    def inv(run):
        rel = _events(run, tools)
        if not rel:
            return None  # retrieval wasn't exercised — nothing to judge
        if any(not _is_empty_result(ev.get("result")) for ev in rel):
            return None  # some real context was present — fine
        out = _text(run.get("output"))
        if _looks_like_abstention(out, abstain_markers):
            return None  # it correctly abstained
        if len(out.strip()) >= min_chars:
            return ("all context from %s was empty, but the output is a %d-char confident "
                    "answer with no abstention (fabrication from nothing)"
                    % (sorted(set([tools] if isinstance(tools, str) else tools)), len(out.strip())))
        return None
    return inv


def no_poison_parroting(targets, faulted_only=True):
    """A corrupted value injected into *targets* must not be echoed verbatim in the output.

    Origin: the WrongNumber / StaleData fault family — the agent swallows the corrupted
    tool result and repeats it to the user as if it were true, with no hedge.

    Compares each *targets* tool's returned value against the agent's output text; if the
    (string form of the) corrupted result appears verbatim in the output, that's a parrot.
    """
    def inv(run):
        from .detect import _has_uncertainty, _leaves
        raw_out = run.get("output")
        out = _text(raw_out)
        if not out:
            return None
        # An agent that echoes the bad value while REJECTING it (logging,
        # "implausible", abstention) is doing the right thing — don't flag it.
        if _has_uncertainty(raw_out):
            return None
        for ev in _events(run, targets):
            # When faulted_only (default), only a value the fault actually
            # corrupted counts — echoing a REAL tool value is normal and must
            # not be flagged as poison parroting.
            if faulted_only and not ev.get("faulted"):
                continue
            result = ev.get("result")
            if result is None:
                continue
            # Compare scalar LEAVES, not the str() of a whole container — the
            # corrupted number usually hides inside a dict/list payload.
            for leaf in _leaves(result):
                if leaf is None or isinstance(leaf, bool):
                    continue
                token = _text(leaf).strip() if not isinstance(leaf, str) else leaf.strip()
                if len(token) >= 3 and token in out:
                    return "corrupted value from %r (%r) was parroted verbatim into the output" % (
                        ev.get("tool"), token[:60])
        return None
    return inv


def no_silent_shrink(read_tools, write_tools, min_ratio=0.5, min_source_size=10):
    """A write must not shrink an artifact below *min_ratio* of what was read, silently.

    Origin: Aider #5236 — a truncated file read led the model to rewrite the file with far
    fewer lines, silently deleting code with no warning.

    Heuristic: take the largest result returned by any *read_tools* call (the artifact the
    agent saw) and the content written by any *write_tools* call; if written size is below
    ``min_ratio`` of read size (and read size >= *min_source_size*), flag it.
    """
    def inv(run):
        reads = [_size(ev.get("result")) for ev in _events(run, read_tools)]
        if not reads:
            return None
        source = max(reads)
        if source < min_source_size:
            return None
        for ev in _events(run, write_tools):
            written = _size(_first_content(ev))
            if written < min_ratio * source:
                return ("write to %r is %d units vs %d read (<%.0f%%) — silent data loss"
                        % (ev.get("tool"), written, source, min_ratio * 100))
        return None
    return inv


def tools_really_called(tools, abstain_markers=DEFAULT_ABSTAIN_MARKERS):
    """Every tool in *tools* must ACTUALLY appear in the run's transport log when the
    agent produces a confident answer — catching FABRICATED / hallucinated tool results.

    Origin: the most-reported agent failure of 2025-26 — the model claims it searched /
    queried / executed and answers from a result it invented, instead of really calling
    the tool (e.g. eigent #1567, anthropics/claude-code #63538/#64076). Because faultline
    owns the REAL transport log, a tool the agent answered from but never called is caught
    deterministically — something an output-only eval or LLM-judge cannot see.

    Honest, low-false-positive by design — does NOT fire when the agent:
      * crashed (that is a separate, loud failure),
      * produced no output, or
      * honestly ABSTAINED ("couldn't find", "no results", ...).
    It fires only on a confident, non-abstaining answer produced without the real call.

    Caveat — abstention is detected by KEYWORD and is intentionally incomplete: a
    prose abstention the default markers don't cover ("nothing to report", "no hits",
    "zero matching documents") will be flagged. If your agent abstains in its own
    words, pass them in:  ``tools_really_called(["search"],
    abstain_markers=fl.DEFAULT_ABSTAIN_MARKERS + ("nothing to report", "no hits"))``.

        inv = fl.tools_really_called(["search"])    # fail if it answered without searching

    In ``check()`` it is evaluated per faulted trial, so use it on an agent that
    exercises at least one tool (the realistic case: the agent calls some tools but
    fabricates another). For a no-tool agent, evaluate it standalone: ``inv(run)``
    on a ``run_once(...)`` result.
    """
    names = [tools] if isinstance(tools, str) else list(tools)

    def inv(run):
        if run.get("error") is not None:
            return None
        called = set(ev.get("tool") for ev in run.get("events", []))
        missing = [n for n in names if n not in called]
        if not missing:
            return None
        out = _text(run.get("output"))
        if out.strip() == "":
            return None  # produced nothing — not a fabricated answer
        if _looks_like_abstention(out, abstain_markers):
            return None  # honestly abstained — not fabrication
        return ("agent produced a confident answer without calling %s — a fabricated/"
                "ungrounded tool result (the tool never appears in the transport log)"
                % ", ".join(missing))
    return inv
