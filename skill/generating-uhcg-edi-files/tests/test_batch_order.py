"""A new batch takes the number after the highest one ever used."""
import json
import os

import generate as G


def _repo(tmp_path, dirs, outputs):
    for d in dirs:
        (tmp_path / "EDI1" / d).mkdir(parents=True)
    (tmp_path / "EDI1").mkdir(exist_ok=True)
    (tmp_path / "EDI1" / "masterfile.json").write_text(json.dumps(
        {"version": 1, "runs": [{"output": o} for o in outputs]}))
    return str(tmp_path)


def test_gap_on_disk_is_not_reused(tmp_path):
    repo = _repo(tmp_path, ["Batch 1", "Batch 26"], ["EDI1/Batch 9/x.x12"])
    out = G._default_output(repo, "P", 1, stamp="20261110120000")
    assert os.path.basename(os.path.dirname(out)) == "Batch 27"
    assert out.endswith("fromUHCG-837P-WKN_1claims_20261110120000.x12")


def test_removed_batch_still_owns_its_number(tmp_path):
    repo = _repo(tmp_path, ["Batch 1"], ["edi1/Batch 30/x.x12"])
    assert "Batch 31" in G._default_output(repo, "I", 2)


def test_empty_repo_starts_at_one(tmp_path):
    repo = _repo(tmp_path, [], [])
    assert "Batch 1" in G._default_output(repo, "I", 2)
