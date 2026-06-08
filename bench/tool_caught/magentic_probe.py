"""faultline mode-2 (probe / DIFFERENTIAL oracle) catching the real magentic parser bug. No LLM.

Run:  python3 bench/tool_caught/magentic_probe.py

Differential testing: magentic's streamed-JSON-array parser must agree with the stdlib `json`
module on how many elements an array has. The `inject-escaped-quote` mutator produces a valid
JSON array whose element contains a quote; the property "parser element-count == json element-count"
then catches that the REAL (unpatched) magentic parser silently returns ZERO elements.
"""
import json
import importlib.util

import faultline as fl

# load the real, UNPATCHED magentic streaming module standalone (it's pure stdlib)
_spec = importlib.util.spec_from_file_location("mstream", "/tmp/magentic_streaming_unpatched.py")
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)


def parse_element_count(json_array_string):
    return len(list(_m.iter_streamed_json_array([json_array_string])))


def must_agree_with_json(inp, out, err):
    expected = len(json.loads(inp))
    if err is None and out != expected:
        return "parser returned %d elements but json.loads says %d (parser desynced, elements lost)" % (out, expected)


BASE = json.dumps(["alpha", "bravo"])                       # 2 elements, no quotes inside
cases = fl.mutations(
    BASE,
    ("inject-escaped-quote", lambda s: json.dumps(['he said "hi"', "bravo"])),  # still 2 elements
)
fl.probe(parse_element_count, cases, [must_agree_with_json],
         label="magentic: streamed parser vs json oracle", unpack=False).report()
