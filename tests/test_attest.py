"""Attestation report (Rung 3) — tests. Deterministic, no API, no network.

Covers:
  1. deterministic hash   — attest the same suite twice -> SAME content hash
  2. verify clean         — verify passes on a freshly attested report (exit 0 path)
  3. verify tampered      — flip ONE verdict -> hash mismatch -> verify FAILS + names it
  4. verify edited number — change ONE number in a body field -> verify FAILS
  5. round-trip           — attest -> write -> load -> verify holds
  6. meta excluded        — changing only duration_ms / created_at / git_* does NOT
                            change the hash (non-deterministic fields are out of the body)
  7. CLI gate + exit codes — attest exits 1 on FAIL, verify exits 0 clean / 1 tampered / 2 missing

All deterministic: the suite below has fixed verdicts, so hashes are reproducible.

Run:  python3 tests/test_attest.py   (expects all passed).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import faultline as fl
from faultline import attest

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ok  " if cond else "FAIL  ") + name)


# ---------------------------------------------------------------------------
# A tiny, fully deterministic suite -> fixed verdicts -> reproducible hash.
# (Wrong-number on inventory makes a buggy agent oversell: a SILENT FAIL.)
# ---------------------------------------------------------------------------
@fl.tool
def _get_stock(item):
    return 2


def _agent(task):
    stock = _get_stock(task["item"])
    if stock is None:
        return {"decision": "DECLINE"}
    if stock >= task["qty"]:
        return {"decision": "BUY"}
    return {"decision": "DECLINE"}


def _oversell(run):
    out = run.get("output")
    if out and out.get("decision") == "BUY":
        return "agent ordered more than stock"
    return None


def _run_check():
    return fl.check(
        _agent,
        {"item": "widget", "qty": 3},
        [fl.WrongNumber(factor=5, targets=["_get_stock"])],
        invariants=[_oversell],
        trials=3,
    )


# ---------------------------------------------------------------------------
# 1. Deterministic hash — same suite attested twice -> identical content hash.
# ---------------------------------------------------------------------------
_r1 = attest.build_report(_run_check(), agent="agent_a", trials=3)
_r2 = attest.build_report(_run_check(), agent="agent_a", trials=3)
_h1 = _r1["attestation"]["content_hash"]
_h2 = _r2["attestation"]["content_hash"]
check("deterministic: two attest runs produce the SAME content hash", _h1 == _h2)
check("content hash is a 64-char sha256 hex", isinstance(_h1, str) and len(_h1) == 64)
check("report is versioned v1", _r1.get("report_version") == 1)
check("report kind is faultline.report", _r1.get("kind") == "faultline.report")
check("attestation declares algorithm sha256", _r1["attestation"].get("algorithm") == "sha256")
check("attestation note disavows secret-key signature / cert",
      "not a secret-key" in _r1["attestation"].get("note", "")
      and "certification" in _r1["attestation"].get("note", ""))


# ---------------------------------------------------------------------------
# 2. verify passes on a clean report.
# ---------------------------------------------------------------------------
_ok, _msg = attest.verify_report(_r1)
check("verify: clean report passes", _ok is True)
check("verify: clean message reports verdict count + hash OK", "verdict" in _msg and "hash OK" in _msg)


# ---------------------------------------------------------------------------
# 3. verify FAILS when one verdict is flipped (tamper-evident).
# ---------------------------------------------------------------------------
_tampered = json.loads(json.dumps(_r1))   # deep copy
_flipped = False
for row in _tampered["body"]["results"]:
    if row["verdict"] == "fail":
        row["verdict"] = "pass"            # fake a clean run
        _flipped = True
        break
check("setup: a fail verdict existed to flip", _flipped)
_ok, _msg = attest.verify_report(_tampered)
check("verify: flipped verdict is detected (FAILS)", _ok is False)
check("verify: failure message says hash mismatch", "hash mismatch" in _msg)


# ---------------------------------------------------------------------------
# 4. verify FAILS when one NUMBER is edited inside the hashed body.
# ---------------------------------------------------------------------------
_num_tampered = json.loads(json.dumps(_r1))
_num_tampered["body"]["trials"] = 99       # was 3 -> changes the canonical body
_ok, _msg = attest.verify_report(_num_tampered)
check("verify: edited number in body is detected (FAILS)", _ok is False)
check("verify: edited-number failure also says hash mismatch", "hash mismatch" in _msg)


# ---------------------------------------------------------------------------
# 5. Round-trip: build -> write -> load -> verify still holds, hash preserved.
# ---------------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="faultline_attest_")
_path = os.path.join(_tmpdir, "faultline.report.json")
attest.write_report(_r1, _path)
_loaded = attest.load_report(_path)
check("round-trip: loaded report keeps the same content hash",
      _loaded["attestation"]["content_hash"] == _h1)
_ok, _msg = attest.verify_report(_loaded)
check("round-trip: loaded report verifies clean", _ok is True)


# ---------------------------------------------------------------------------
# 6. Non-deterministic fields excluded: changing only meta does NOT move the hash.
# ---------------------------------------------------------------------------
_meta_edited = json.loads(json.dumps(_r1))
_meta_edited["meta"]["duration_ms"] = 123456789
_meta_edited["meta"]["created_at"] = "2099-12-31T23:59:59Z"
_meta_edited["meta"]["git_sha"] = "cafef00d"
_meta_edited["meta"]["ci_run_url"] = "https://example.test/run/999"
check("meta excluded: recomputed hash unchanged after meta-only edits",
      attest.compute_hash(_meta_edited) == _h1)
_ok, _msg = attest.verify_report(_meta_edited)
check("meta excluded: a meta-only edit still verifies clean", _ok is True)

# And: two reports that differ ONLY in non-deterministic fields hash the same.
# (build_report stamps created_at from a clock; force two distinct clocks.)
import datetime
_early = attest.build_report(_run_check(), agent="agent_a", trials=3,
                             now=datetime.datetime(2020, 1, 1, 0, 0, 0))
_late = attest.build_report(_run_check(), agent="agent_a", trials=3,
                            now=datetime.datetime(2026, 6, 9, 12, 0, 0))
check("meta excluded: different timestamps -> identical hash",
      _early["attestation"]["content_hash"] == _late["attestation"]["content_hash"])
check("meta excluded: timestamps actually differ in the report",
      _early["meta"]["created_at"] != _late["meta"]["created_at"])


# ---------------------------------------------------------------------------
# 7. CLI gate + exit codes (real subprocess against the offline demo suite).
# ---------------------------------------------------------------------------
def _cli(*args):
    p = subprocess.run([sys.executable, "-m", "faultline.cli", *args],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode, p.stdout, p.stderr


_demo = os.path.join(ROOT, "faultline", "examples", "quickstart.py")
_rpath = os.path.join(_tmpdir, "demo.report.json")

_code, _out, _err = _cli("attest", _demo, "--out", _rpath)
# Demo suite has a SILENT FAIL + CRASH -> gate semantics: non-zero exit.
check("cli attest: gate exits non-zero on a failing suite (still gates CI)", _code == 1)
check("cli attest: wrote the report file", os.path.exists(_rpath))
check("cli attest: report announces a sha256 content hash", "sha256" in (_out + _err))

_code, _out, _err = _cli("verify", _rpath)
check("cli verify: clean report exits 0", _code == 0)
check("cli verify: prints 'hash OK'", "hash OK" in _out)

# Tamper the written file (flip a verdict on disk) -> verify must exit non-zero.
_disk = attest.load_report(_rpath)
for row in _disk["body"]["results"]:
    if row["verdict"] == "fail":
        row["verdict"] = "pass"
        break
with open(_rpath, "w") as fh:
    fh.write(json.dumps(_disk, indent=2, sort_keys=True))
_code, _out, _err = _cli("verify", _rpath)
check("cli verify: tampered report exits non-zero", _code == 1)
check("cli verify: names the mismatch", "mismatch" in (_out + _err).lower())

# verify on a missing file -> usage error (exit 2), mirrors run's contract.
_code, _out, _err = _cli("verify", os.path.join(_tmpdir, "nope.json"))
check("cli verify: missing file exits 2 (usage error)", _code == 2)

# attest on a missing suite file -> usage error (exit 2), mirrors run's contract.
_code, _out, _err = _cli("attest", os.path.join(_tmpdir, "nosuite.py"))
check("cli attest: missing suite file exits 2 (usage error)", _code == 2)


# ---------------------------------------------------------------------------
# Tally
# ---------------------------------------------------------------------------
_passed = sum(1 for _, c in results if c)
_failed = len(results) - _passed
print("\n%d passed, %d failed" % (_passed, _failed))
sys.exit(0 if _failed == 0 else 1)
