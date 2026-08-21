"""The generate CLI's document-driven entry points: --data, --print-defaults,
--json.

Every test that ALLOCATES runs against a scratch repo holding nothing but a
copy of each seed, so no test ever draws identifiers out of the real
EDI1/masterfile.json. --print-defaults allocates nothing and reads the real
repo directly.
"""
from __future__ import annotations
import io
import json
import os
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import generate                                          # noqa: E402
import masterfile as M                                   # noqa: E402
import overrides                                         # noqa: E402
import seeds                                             # noqa: E402


@pytest.fixture
def scratch(repo):
    """An isolated repo: one seed per registered type, an empty masterfile."""
    root = tempfile.mkdtemp(prefix="edi_t8_")
    try:
        for code in ("I", "P"):
            profile = seeds.get(code)
            dst = os.path.join(root, os.path.dirname(profile.rel_path))
            if not os.path.isdir(dst):
                os.makedirs(dst)
            shutil.copy(seeds.seed_path(profile, repo),
                        os.path.join(root, profile.rel_path))
        M.bootstrap(root)
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def work():
    """A scratch directory for documents and outputs.

    Deliberately not pytest's tmp_path: this environment refuses pytest's own
    basetemp, and mkdtemp is what the rest of the suite already uses.
    """
    d = tempfile.mkdtemp(prefix="edi_t8_work_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _doc(work, obj):
    path = os.path.join(work, "ov.json")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj))
    return path


def _read(path):
    with io.open(path, encoding="ascii") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# --data
# --------------------------------------------------------------------------

def test_data_file_drives_the_output(scratch, work):
    doc = _doc(work, {"identity": {"subscriber": {"last": "DOE"}}})
    out = os.path.join(work, "o.x12")
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--data", doc, "--output", out])
    assert rc == 0
    assert "NM1*IL*1*DOE*WILLIAM****MI*909001333969" in _read(out)


def test_the_data_document_is_recorded_in_the_manifest(scratch, work):
    obj = {"identity": {"subscriber": {"last": "DOE"}}}
    out = os.path.join(work, "o.x12")
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--data", _doc(work, obj), "--output", out])
    assert rc == 0
    with io.open(out[:-4] + ".manifest.json", encoding="utf-8") as fh:
        man = json.loads(fh.read())
    # The declaration is the yardstick checks 9 and 12 measure against, so it
    # has to survive into the manifest verbatim, not be re-derived later.
    assert man["overrides"] == obj
    assert M.load(scratch)["runs"][-1]["overrides"] == obj


def test_data_reads_stdin_when_the_path_is_a_dash(scratch, work, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"identity": {"subscriber": {"last": "DOE"}}})))
    out = os.path.join(work, "o.x12")
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--data", "-", "--output", out])
    assert rc == 0
    assert "*DOE*" in _read(out)


def test_a_bad_override_exits_non_zero_with_the_reason(scratch, work, capsys):
    doc = _doc(work, {"claims": [{"n": 99}]})
    out = os.path.join(work, "o.x12")
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--data", doc, "--output", out])
    assert rc != 0
    assert "outside the batch" in capsys.readouterr().err
    assert not os.path.exists(out)


def test_malformed_json_is_refused_not_raised(scratch, work, capsys):
    path = os.path.join(work, "ov.json")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--data", path,
                        "--output", os.path.join(work, "o.x12")])
    assert rc != 0
    assert "is not valid JSON" in capsys.readouterr().err


def test_a_missing_data_file_is_refused_not_raised(scratch, work, capsys):
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--data", os.path.join(work, "nope.json"),
                        "--output", os.path.join(work, "o.x12")])
    assert rc != 0
    assert "cannot be read" in capsys.readouterr().err


def test_data_and_pin_together_are_refused(scratch, work, capsys):
    # --pin replays the declaration the manifest already records; a second
    # document would silently lose to it and produce a file that is not what
    # either input asked for.
    doc = _doc(work, {})
    rc = generate.main(["--repo", scratch, "--pin", doc, "--data", doc])
    assert rc != 0
    assert "--data cannot be combined with --pin" in capsys.readouterr().err


# --------------------------------------------------------------------------
# --print-defaults
# --------------------------------------------------------------------------

def test_print_defaults_is_a_valid_override_document(repo, capsys):
    rc = generate.main(["--repo", repo, "--type", "I", "--print-defaults"])
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    overrides.parse(doc, seeds.get("I"), len(doc["claims"]))   # must not raise


def test_print_defaults_allocates_nothing(scratch, capsys):
    before = json.dumps(M.load(scratch), sort_keys=True)
    rc = generate.main(["--repo", scratch, "--type", "I", "--print-defaults"])
    assert rc == 0
    capsys.readouterr()
    assert json.dumps(M.load(scratch), sort_keys=True) == before


def test_print_defaults_needs_no_claim_count(repo, capsys):
    rc = generate.main(["--repo", repo, "--type", "P", "--print-defaults"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["identity"]["subscriber"]


# --------------------------------------------------------------------------
# --print-allocation
# --------------------------------------------------------------------------

def test_print_allocation_matches_what_a_real_run_takes(scratch, work, capsys):
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "2",
                        "--print-allocation"])
    assert rc == 0
    peek = json.loads(capsys.readouterr().out)
    out = os.path.join(work, "o.x12")
    assert generate.main(["--repo", scratch, "--type", "I", "--claims", "2",
                          "--output", out]) == 0
    capsys.readouterr()
    run = M.load(scratch)["runs"][-1]
    # The point of the flag: the tiles show the allocator's own answer, not a
    # second implementation of the allocation rules in the browser.
    for key in ("isa13", "gs06", "envelope_date", "statement", "st02",
                "bht03", "clm01", "ref_f8", "ref_9a", "service_dates"):
        assert peek[key] == run[key], key
    assert peek["nextBatch"] == 2


def test_print_allocation_allocates_nothing(scratch, capsys):
    before = json.dumps(M.load(scratch), sort_keys=True)
    for _ in range(2):
        assert generate.main(["--repo", scratch, "--type", "P", "--claims",
                              "3", "--print-allocation"]) == 0
    first, second = capsys.readouterr().out.strip().splitlines()
    # Twice in a row, same answer: peeking must not move the masterfile.
    assert first == second
    assert json.dumps(M.load(scratch), sort_keys=True) == before


def test_print_allocation_needs_a_claim_count(scratch, capsys):
    rc = generate.main(["--repo", scratch, "--type", "I",
                        "--print-allocation"])
    assert rc != 0
    assert "--type and --claims are required" in capsys.readouterr().err


# --------------------------------------------------------------------------
# --json
# --------------------------------------------------------------------------

def test_json_emits_one_parseable_object_on_stdout(scratch, work, capsys):
    out = os.path.join(work, "o.x12")
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--output", out, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)          # must not raise
    assert payload["x12FilePath"] == out
    assert payload["manifestPath"] == out[:-4] + ".manifest.json"
    # 1-based index into masterfile runs, counting the "imported" pseudo-run
    # bootstrap writes - so the first generated batch in a fresh repo is 2.
    runs = M.load(scratch)["runs"]
    assert payload["batchId"] == len(runs) == 2
    assert runs[payload["batchId"] - 1]["sha256"] == json.loads(
        io.open(payload["manifestPath"], encoding="utf-8").read())["sha256"]
    assert os.path.exists(payload["docxFilePath"])


def test_json_keeps_progress_lines_off_stdout(scratch, work, capsys):
    out = os.path.join(work, "o.x12")
    generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                   "--output", out, "--json"])
    captured = capsys.readouterr()
    assert "wrote " not in captured.out
    assert "wrote " in captured.err


def test_json_prints_nothing_on_a_refused_run(scratch, work, capsys):
    doc = _doc(work, {"claims": [{"n": 99}]})
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--data", doc, "--output", os.path.join(work, "o.x12"),
                        "--json"])
    assert rc != 0
    assert capsys.readouterr().out == ""
