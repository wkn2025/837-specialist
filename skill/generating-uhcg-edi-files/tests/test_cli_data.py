"""The generate CLI's document-driven entry points: --data, --print-defaults,
--json.

Every test that ALLOCATES runs against a scratch repo holding nothing but a
copy of each seed, so no test ever draws identifiers out of the real
EDI1/masterfile.json. --print-defaults allocates nothing and reads the real
repo directly.
"""
from __future__ import annotations
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

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


def _tree(root):
    """Relative directory/file names, including empty directories."""
    found = []
    for parent, directories, files in os.walk(root):
        for name in directories:
            found.append(("d", os.path.relpath(
                os.path.join(parent, name), root)))
        for name in files:
            found.append(("f", os.path.relpath(
                os.path.join(parent, name), root)))
    return sorted(found)


def _write_concurrency_wrapper(work):
    """CLI wrapper whose post-allocation barrier makes the old race exact."""
    gate = os.path.join(work, "gate")
    os.makedirs(gate)
    wrapper = os.path.join(work, "concurrent_generate.py")
    source = textwrap.dedent("""
        import glob
        import os
        import sys
        import time

        sys.path.insert(0, {scripts!r})
        import generate

        real_allocate = generate.M.allocate

        def allocate_together(*args, **kwargs):
            allocation = real_allocate(*args, **kwargs)
            marker = os.path.join({gate!r}, str(os.getpid()))
            with open(marker, "w") as fh:
                fh.write("ready")
            deadline = time.monotonic() + 1.5
            while len(glob.glob(os.path.join({gate!r}, "*"))) < 2:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            return allocation

        generate.M.allocate = allocate_together
        generate.claim_summary.build = lambda *args, **kwargs: None
        raise SystemExit(generate.main())
    """).format(scripts=os.path.abspath(SCRIPTS), gate=gate)
    with io.open(wrapper, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(source)
    return wrapper


def _write_pinned_concurrency_wrapper(work):
    """Make two pinned publishers pass the old unlocked existence check."""
    gate = os.path.join(work, "pin-gate")
    os.makedirs(gate)
    wrapper = os.path.join(work, "concurrent_pin.py")
    source = textwrap.dedent("""
        import glob
        import os
        import sys
        import time

        sys.path.insert(0, {scripts!r})
        import generate

        real_load_seed = generate.seeds.load_seed

        def load_together(*args, **kwargs):
            marker = os.path.join({gate!r}, str(os.getpid()))
            with open(marker, "w") as fh:
                fh.write("ready")
            deadline = time.monotonic() + 1.5
            while len(glob.glob(os.path.join({gate!r}, "*"))) < 2:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            return real_load_seed(*args, **kwargs)

        generate.seeds.load_seed = load_together
        generate.claim_summary.build = lambda *args, **kwargs: None
        raise SystemExit(generate.main())
    """).format(scripts=os.path.abspath(SCRIPTS), gate=gate)
    with io.open(wrapper, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(source)
    return wrapper


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


def test_simultaneous_generation_transactions_never_overlap_identifiers(
        scratch, work):
    wrapper = _write_concurrency_wrapper(work)
    argv = [sys.executable, wrapper, "--repo", scratch, "--type", "I",
            "--claims", "1", "--json"]
    processes = [subprocess.Popen(argv, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
                 for _ in range(2)]
    results = [p.communicate(timeout=30) for p in processes]
    payloads = []
    for p, (stdout, stderr) in zip(processes, results):
        assert p.returncode == 0, stderr.decode("utf-8", "replace")
        payloads.append(json.loads(stdout.decode("utf-8")))
    assert {payload["batchId"] for payload in payloads} == {2, 3}

    manifests = []
    for batch in (2, 3):
        path = os.path.join(
            scratch, "EDI1", "Batch %d" % batch,
            "fromUHCG-837I-WKN_1claims.manifest.json")
        with io.open(path, encoding="utf-8") as fh:
            manifests.append(json.loads(fh.read()))

    for key in M.KEYS:
        left = manifests[0][key]
        right = manifests[1][key]
        left = set(left if isinstance(left, list) else [left])
        right = set(right if isinstance(right, list) else [right])
        assert left.isdisjoint(right), (key, left & right)
    assert len(M.load(scratch)["runs"]) == 3


def test_simultaneous_pinned_publishers_cannot_both_claim_one_output(
        scratch, work):
    source = os.path.join(work, "source.x12")
    assert generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                          "--output", source]) == 0
    pin = source[:-4] + ".manifest.json"
    target = os.path.join(work, "pinned.x12")
    wrapper = _write_pinned_concurrency_wrapper(work)
    argv = [sys.executable, wrapper, "--repo", scratch, "--pin", pin,
            "--output", target]
    processes = [subprocess.Popen(argv, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
                 for _ in range(2)]
    results = [p.communicate(timeout=30) for p in processes]
    assert sorted(p.returncode for p in processes) == [0, 1]
    refusal = [stderr.decode("utf-8", "replace")
               for p, (_stdout, stderr) in zip(processes, results)
               if p.returncode == 1]
    assert len(refusal) == 1
    assert "exists; pass --force to overwrite" in refusal[0]
    assert os.path.exists(target)
    assert len(M.load(scratch)["runs"]) == 2


def test_append_failure_rolls_back_artifacts_and_releases_lock(
        scratch, work, monkeypatch, capsys):
    out = os.path.join(work, "failed.x12")

    def fail_append(*_args, **_kwargs):
        raise OSError("atomic append failed")

    monkeypatch.setattr(M, "append_run", fail_append)
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--output", out])
    assert rc != 0
    assert "atomic append failed" in capsys.readouterr().err
    assert not os.path.exists(out)
    assert not os.path.exists(out[:-4] + ".manifest.json")
    assert len(M.load(scratch)["runs"]) == 1

    monkeypatch.undo()
    retry = os.path.join(work, "retry.x12")
    assert generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                          "--output", retry]) == 0
    assert os.path.exists(retry)
    assert len(M.load(scratch)["runs"]) == 2


def test_default_output_failure_removes_the_new_empty_batch_directory(
        scratch, monkeypatch, capsys):
    # The stable advisory sidecar is intentionally persistent operational
    # state, so establish it before comparing the repository tree.
    with M.generation_lock(scratch):
        pass
    before_tree = _tree(scratch)
    with open(M.path(scratch), "rb") as fh:
        before_masterfile = fh.read()

    def fail_append(*_args, **_kwargs):
        raise OSError("atomic append failed")

    monkeypatch.setattr(M, "append_run", fail_append)
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1"])
    assert rc != 0
    assert "atomic append failed" in capsys.readouterr().err
    assert _tree(scratch) == before_tree
    with open(M.path(scratch), "rb") as fh:
        assert fh.read() == before_masterfile


def test_second_backup_failure_never_loses_an_existing_output_pair(
        scratch, work, monkeypatch, capsys):
    out = os.path.join(work, "existing.x12")
    man = out[:-4] + ".manifest.json"
    with open(out, "wb") as fh:
        fh.write(b"original x12")
    with open(man, "wb") as fh:
        fh.write(b"original manifest")

    real_replace = os.replace
    calls = []

    def fail_second_replace(source, destination):
        calls.append((source, destination))
        if len(calls) == 2:
            raise OSError("second backup failed")
        return real_replace(source, destination)

    monkeypatch.setattr(generate.os, "replace", fail_second_replace)
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--output", out, "--force"])
    assert rc != 0
    assert "second backup failed" in capsys.readouterr().err
    with open(out, "rb") as fh:
        assert fh.read() == b"original x12"
    with open(man, "rb") as fh:
        assert fh.read() == b"original manifest"
    assert len(M.load(scratch)["runs"]) == 1


def test_restore_failure_leaves_the_original_in_a_recoverable_sidecar(
        scratch, work, monkeypatch, capsys):
    out = os.path.join(work, "existing.x12")
    man = out[:-4] + ".manifest.json"
    with open(out, "wb") as fh:
        fh.write(b"original x12")
    with open(man, "wb") as fh:
        fh.write(b"original manifest")

    real_replace = os.replace

    def fail_manifest_restore(source, destination):
        if source.startswith(man + ".previous-") and destination == man:
            raise OSError("manifest restore failed")
        return real_replace(source, destination)

    def fail_append(*_args, **_kwargs):
        raise OSError("atomic append failed")

    monkeypatch.setattr(generate.os, "replace", fail_manifest_restore)
    monkeypatch.setattr(M, "append_run", fail_append)
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--output", out, "--force"])
    assert rc != 0
    error = capsys.readouterr().err
    assert "artifact restore failed" in error
    assert "manifest restore failed" in error
    with open(out, "rb") as fh:
        assert fh.read() == b"original x12"
    assert not os.path.exists(man)
    recoverable = glob.glob(man + ".previous-*")
    assert len(recoverable) == 1
    with open(recoverable[0], "rb") as fh:
        assert fh.read() == b"original manifest"
    assert len(M.load(scratch)["runs"]) == 1


@pytest.mark.parametrize("failed_artifact", ["x12", "manifest"])
def test_atomic_publication_failure_leaves_no_partial_artifact(
        failed_artifact, scratch, monkeypatch, capsys):
    # Use the default path so the assertion also covers cleanup of the newly
    # selected Batch directory.
    out = os.path.join(
        scratch, "EDI1", "Batch 2", "fromUHCG-837I-WKN_1claims.x12")
    man = out[:-4] + ".manifest.json"
    failed_destination = out if failed_artifact == "x12" else man
    real_replace = os.replace

    def fail_publication(source, destination):
        if destination == failed_destination and ".edi_gen_" in source:
            raise OSError("%s publication failed" % failed_artifact)
        return real_replace(source, destination)

    monkeypatch.setattr(generate.os, "replace", fail_publication)
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1"])
    assert rc != 0
    assert "%s publication failed" % failed_artifact in capsys.readouterr().err
    assert not os.path.exists(out)
    assert not os.path.exists(man)
    assert not os.path.exists(os.path.dirname(out))
    assert len(M.load(scratch)["runs"]) == 1


def test_failed_published_file_cleanup_is_reported(
        scratch, work, monkeypatch, capsys):
    out = os.path.join(work, "unrecorded.x12")
    real_unlink = os.unlink

    def fail_output_cleanup(path):
        if path == out:
            raise OSError("output cleanup failed")
        return real_unlink(path)

    def fail_append(*_args, **_kwargs):
        raise OSError("atomic append failed")

    monkeypatch.setattr(generate.os, "unlink", fail_output_cleanup)
    monkeypatch.setattr(M, "append_run", fail_append)
    rc = generate.main(["--repo", scratch, "--type", "I", "--claims", "1",
                        "--output", out])
    assert rc != 0
    error = capsys.readouterr().err
    assert "artifact cleanup failed" in error
    assert "output cleanup failed" in error
    assert os.path.exists(out)
    assert len(M.load(scratch)["runs"]) == 1


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
