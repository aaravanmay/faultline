"""faultline catching the real DB-GPT NULL-row chart bug (no LLM; runs the real function in isolation).

Rule it checks: a NULL value in a result row must not crash the chart builder or mis-label a point.
The REAL DB-GPT, on a NULL row with a date-keyed result, labels the point with the wrong column's
value (or crashes) - silently wrong chart data.
"""
import sys, types, importlib.util, datetime
import faultline as fl

def _pkg(name):
    m = types.ModuleType(name); m.__path__ = []; sys.modules[name] = m
for _n in ("dbgpt", "dbgpt._private", "dbgpt_app", "dbgpt_app.scene",
           "dbgpt_app.scene.chat_dashboard", "dbgpt_app.scene.chat_dashboard.data_preparation"):
    _pkg(_n)
_cfg = types.ModuleType("dbgpt._private.config")
class _C:
    def __init__(self, *a, **k): pass
_cfg.Config = _C; sys.modules["dbgpt._private.config"] = _cfg
import pydantic
_pyd = types.ModuleType("dbgpt._private.pydantic"); _pyd.__getattr__ = lambda n: getattr(pydantic, n)
sys.modules["dbgpt._private.pydantic"] = _pyd
def _load(name, path):
    sp = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(sp)
    sys.modules[name] = mod; sp.loader.exec_module(mod); return mod
_load("dbgpt_app.scene.chat_dashboard.data_preparation.report_schma", "/tmp/dbgpt_schema_unpatched.py")
DL = _load("dbgpt_app.scene.chat_dashboard.data_loader", "/tmp/dbgpt_dataloader_unpatched.py")

_loader = DL.DashboardDataLoader()
def chart_labels(datas):
    _fields, values = _loader.get_chart_values_by_data(["event_date", "sales", "cost"], datas, "SELECT ...")
    return [str(v.name) for v in values]

def null_row_must_be_handled(inp, out, err):
    if err is not None:
        return "a NULL value in a row crashed the chart builder (%s) - a normal DB value broke it" % type(err).__name__
    if out and "150" in out:
        return "a NULL row was labeled with the wrong column's value (150) instead of the date"

cases = fl.mutations(
    [(datetime.date(2024, 1, 2), 200, 100)],                                   # no nulls
    ("row-contains-a-null", lambda b: [(datetime.date(2024, 1, 1), None, 150)] + b),
)
fl.probe(chart_labels, cases, [null_row_must_be_handled],
         label="DB-GPT: NULL row chart label", unpack=False).report()
