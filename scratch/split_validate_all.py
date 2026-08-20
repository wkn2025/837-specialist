"""Run the 24-check validator over each per-claim file, graded as claim N."""
from __future__ import annotations
import os
import subprocess
import sys

import split_claims as SC

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = SC.DEFAULT_OUTDIR
NAME = SC.NAME


def main():
    bad = []
    for n in range(1, 10):
        path = os.path.join(OUTDIR, NAME % n)
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "validate_9claims.py"), path,
             "--expect-claims", "1", "--claim-index", str(n),
             "--group-control", str(n)],
            capture_output=True, text=True)
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "<no output>"
        print("claim %d: exit %d  %s" % (n, r.returncode, tail))
        if r.returncode != 0:
            bad.append(n)
            for line in r.stdout.splitlines():
                if line.startswith("[FAIL]"):
                    print("        " + line.rstrip())
    print("\n%d files, %d failing" % (9, len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
