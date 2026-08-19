"""Install the skill tree into ~/.claude/skills, and bootstrap the masterfile.

~/.claude/skills is not version controlled, so the repo copy is the source of
truth and this script pushes it out.

Usage:
    python install.py --repo ROOT [--force]
    python install.py --repo ROOT --bootstrap
"""
from __future__ import annotations
import argparse
import filecmp
import os
import shutil
import sys

import masterfile as M

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
NAME = os.path.basename(SRC)
DST = os.path.join(os.path.expanduser("~"), ".claude", "skills", NAME)

SKIP_DIRS = {"__pycache__", ".git"}


def _files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, f)
            yield os.path.relpath(full, root).replace("\\", "/")


def diverged():
    """Installed files that differ from the repo copy."""
    out = []
    for rel in _files(SRC):
        a, b = os.path.join(SRC, rel), os.path.join(DST, *rel.split("/"))
        if os.path.exists(b) and not filecmp.cmp(a, b, shallow=False):
            out.append(rel)
    return out


def install(force):
    if os.path.isdir(DST):
        bad = diverged()
        if bad and not force:
            sys.stderr.write(
                "installed copy differs from the repo in %d file(s):\n  %s\n"
                "pass --force to overwrite\n" % (len(bad), "\n  ".join(bad)))
            return 1
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sys.stdout.write("installed %s -> %s\n" % (SRC, DST))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--bootstrap", action="store_true")
    args = ap.parse_args()
    if args.bootstrap:
        try:
            mf = M.bootstrap(os.path.abspath(args.repo))
        except M.MasterfileError as exc:
            sys.stderr.write("%s\n" % exc)
            return 1
        run = mf["runs"][0]
        sys.stdout.write("bootstrapped %s\n" % M.path(args.repo))
        sys.stdout.write("imported %d ST02, %d BHT03, %d CLM01 values\n"
                         % (len(run["st02"]), len(run["bht03"]),
                            len(run["clm01"])))
        return 0
    return install(args.force)


if __name__ == "__main__":
    sys.exit(main())
