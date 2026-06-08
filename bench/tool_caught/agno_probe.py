"""faultline mode-2 catching the real agno duplicate-merge bug. No LLM, real (unpatched) agno code.

Rule it checks: if the AI repeats its answer (a common hiccup), parsing it should give the SAME
result as parsing it once - not a doubled list. The tool feeds the same JSON object twice and sees
the REAL agno parser silently double the list.
"""
import sys, types, importlib.util
import faultline as fl

# agno's string.py needs one internal logger module — stub it so we can load just that file
_log = types.ModuleType("agno.utils.log")
_log.log_warning = lambda *a, **k: None
_log.logger = types.SimpleNamespace(warning=lambda *a, **k: None, debug=lambda *a, **k: None,
                                    error=lambda *a, **k: None, info=lambda *a, **k: None)
for _n in ("agno", "agno.utils"):
    _mod = types.ModuleType(_n); _mod.__path__ = []
    sys.modules.setdefault(_n, _mod)
sys.modules["agno.utils.log"] = _log
_reason = types.ModuleType("agno.utils.reasoning")
_reason.extract_thinking_content = lambda content: (None, content)   # no <think> block -> use as-is
sys.modules["agno.utils.reasoning"] = _reason
_spec = importlib.util.spec_from_file_location("agno_string", "/tmp/agno_string_unpatched.py")
_m = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_m)

from pydantic import BaseModel
class Article(BaseModel):
    keywords: list[str]

def parse_keywords(content):
    obj = _m.parse_response_model_str(content, Article)
    return obj.keywords if obj else None

ONE = '{"keywords": ["ai", "agents"]}'
baseline = parse_keywords(ONE)            # -> ["ai", "agents"]

def echo_must_not_double(inp, out, err):
    if err is None and out != baseline:
        return "an echoed/duplicated reply doubled the list to %r (should still be %r)" % (out, baseline)

fl.probe(parse_keywords, [("ai-echoed-its-answer-twice", ONE + " " + ONE)],
         [echo_must_not_double], label="agno: duplicate-reply idempotence", unpack=False).report()
