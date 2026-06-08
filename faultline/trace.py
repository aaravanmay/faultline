"""faultline.trace — recording harness.

Wraps tool calls so a Recorder can observe (and optionally corrupt) them
without touching real side-effects for action tools.
"""
from __future__ import annotations

import contextlib
import contextvars
import functools

_active: contextvars.ContextVar = contextvars.ContextVar("faultline_active", default=None)


class Recorder:
    """Accumulates EVENT dicts for a single agent run."""

    def __init__(self) -> None:
        self.events: list = []
        self.fault = None


def wrap(fn, is_action: bool = False):
    """Return a wrapper around *fn* that participates in fault injection.

    If no Recorder is active the wrapper is transparent — it just calls fn.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        recorder = _active.get()
        if recorder is None:
            # no active session — pass-through
            return fn(*args, **kwargs)

        name = fn.__name__

        # For action tools we never invoke the real function; produce a stub.
        if is_action:
            result = {"_faultline_stub": "ok"}
        else:
            result = fn(*args, **kwargs)

        faulted = False
        fault = recorder.fault

        if fault is not None and fault.applies_to(name):
            try:
                result = fault.hit(name, list(args), dict(kwargs), result)
                faulted = True
            except Exception:
                # The fault raised — record it and re-raise.
                event = {
                    "tool": name,
                    "args": list(args),
                    "kwargs": dict(kwargs),
                    "faulted": True,
                    "raised": True,
                    "result": None,
                    "is_action": is_action,
                }
                recorder.events.append(event)
                raise

        event = {
            "tool": name,
            "args": list(args),
            "kwargs": dict(kwargs),
            "faulted": faulted,
            "raised": False,
            "result": result,
            "is_action": is_action,
        }
        recorder.events.append(event)
        return result

    wrapper._faultline_tool = True
    return wrapper


def tool(fn):
    """Decorator: mark fn as an observable, injectable tool (not an action)."""
    return wrap(fn, is_action=False)


@contextlib.contextmanager
def session(recorder: Recorder, fault=None):
    """Context manager that arms *recorder* (and optionally *fault*) for the
    duration of the block, then resets on exit regardless of exceptions."""
    recorder.fault = fault
    token = _active.set(recorder)
    try:
        yield recorder
    finally:
        _active.reset(token)
        recorder.fault = None


def run_once(agent, task, fault=None) -> dict:
    """Run *agent(task)* once under the given fault (or no fault).

    Returns a RUN dict: {"events": [...], "output": <return value or None>,
    "error": <exception or None>}.
    """
    recorder = Recorder()
    output = None
    error = None
    with session(recorder, fault):
        try:
            output = agent(task)
        except Exception as exc:  # noqa: BLE001
            error = exc
    return {"events": recorder.events, "output": output, "error": error}
