"""D1 regression: two concurrent generator processes must serialize.

The race this pins: generate.py used to read allocator state, allocate,
publish and append its run with no lock, so two overlapping runs read the
same masterfile, minted identical identifier sets, published conflicting
batches, and one append_run clobbered the other - a run vanished from
history. The whole sequence now sits under M.generation_lock, so each
process gets disjoint identifiers and both runs are recorded.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import masterfile as M  # noqa: E402

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
GEN = os.path.join(SCRIPTS, "generate.py")


def _spawn(repo, out):
    """One full generation as its own OS process against an isolated repo."""
    return subprocess.Popen(
        [sys.executable, GEN, "--repo", repo, "--type", "I",
         "--claims", "3", "--output", out, "--json"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class TestConcurrentGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edi_race_")
        shutil.copytree(os.path.join(REPO, "EDI1"),
                        os.path.join(self.tmp, "EDI1"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_processes_allocate_disjoint_ids_and_keep_both_runs(self):
        outs = [os.path.join(self.tmp, "EDI1", "Batch %d" % n, "o.x12")
                for n in (91, 92)]
        procs = [_spawn(self.tmp, o) for o in outs]
        payloads = []
        for proc, out in zip(procs, outs):
            stdout, stderr = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0,
                             stderr.decode("utf-8", "replace"))
            payloads.append(json.loads(stdout.decode("utf-8")))

        # No shared identifier anywhere: the second process must have seen
        # the first's allocation.
        self.assertNotEqual(payloads[0]["isa13"], payloads[1]["isa13"])
        self.assertNotEqual(payloads[0]["gs06"], payloads[1]["gs06"])
        self.assertNotEqual(payloads[0]["clm01"][0], payloads[1]["clm01"][0])
        self.assertNotEqual(payloads[0]["statement"],
                            payloads[1]["statement"])

        # And neither run disappears from the masterfile history.
        mf = M.load(self.tmp)
        recorded = [r.get("output") for r in mf["runs"]]
        for payload in payloads:
            self.assertIn(payload["x12"].replace("\\", "/"), recorded)


if __name__ == "__main__":
    unittest.main()
