"""Masterfile: the append-only run log that keeps identifiers unique.

The masterfile allocates, but it does not get the last word. Every read of
"what is already used" also rescans every .x12 on disk, so a hand-edited file,
a restored-from-backup masterfile, or a file that arrived from outside cannot
cause a silent duplicate.
"""
from __future__ import annotations
import glob
import io
import json
import os

import x12_parse as X

MASTERFILE_REL = "EDI1/masterfile.json"
VERSION = 1

KEYS = ("isa13", "gs06", "st02", "bht03", "clm01", "ref_f8", "ref_9a")


class MasterfileError(Exception):
    """The masterfile is missing, unreadable, or of an unknown version."""


def path(repo):
    return os.path.join(repo, *MASTERFILE_REL.split("/"))


def scan_disk(repo):
    """Identifier values present in every .x12 under the repo."""
    return scan_disk_excluding(repo, None, None)


def scan_disk_excluding(repo, abspath, basename):
    """scan_disk, skipping any file matching abspath or basename.

    Both exclusions are needed: when a validator runs against a temp copy, the
    committed original is still on disk under the same name, and without the
    basename exclusion every identifier collides with itself.
    """
    found = {k: set() for k in KEYS}
    pattern = os.path.join(repo, "**", "*.x12")
    for p in glob.glob(pattern, recursive=True):
        if abspath and os.path.abspath(p) == abspath:
            continue
        if basename and os.path.basename(p) == basename:
            continue
        with io.open(p, encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
        flat = text.replace("\r", "").replace("\n", "")
        for s in (x for x in flat.split(X.SEG) if x):
            e = X.elems(s)
            if e[0] == "ISA" and len(e) > 13:
                found["isa13"].add(e[13])
            elif e[0] == "GS" and len(e) > 6:
                found["gs06"].add(e[6])
            elif e[0] == "ST" and len(e) > 2:
                found["st02"].add(e[2])
            elif e[0] == "BHT" and len(e) > 3:
                found["bht03"].add(e[3])
            elif e[0] == "CLM" and len(e) > 1:
                found["clm01"].add(e[1])
            elif e[0] == "REF" and len(e) > 2 and e[1] == "F8":
                found["ref_f8"].add(e[2])
            elif e[0] == "REF" and len(e) > 2 and e[1] == "9A":
                found["ref_9a"].add(e[2])
    return found


def load(repo):
    p = path(repo)
    if not os.path.exists(p):
        raise MasterfileError(
            "no masterfile at %s; bootstrap it before generating" % p)
    try:
        with io.open(p, encoding="utf-8") as fh:
            mf = json.loads(fh.read())
    except ValueError as exc:
        raise MasterfileError("%s is not valid JSON: %s" % (p, exc))
    if mf.get("version") != VERSION:
        raise MasterfileError(
            "%s declares version %r, this tool understands %d"
            % (p, mf.get("version"), VERSION))
    if not isinstance(mf.get("runs"), list):
        raise MasterfileError("%s has no runs list" % p)
    return mf


def _write(repo, mf):
    p = path(repo)
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(mf, indent=2, sort_keys=True) + "\n")


def bootstrap(repo):
    """Create the masterfile from what is already on disk."""
    p = path(repo)
    if os.path.exists(p):
        raise MasterfileError(
            "%s already exists; refusing to overwrite it" % p)
    disk = scan_disk(repo)
    run = {
        "type": "imported",
        "note": "identifiers found on disk when the masterfile was created",
        "claims": 0,
        "isa13": sorted(disk["isa13"])[-1] if disk["isa13"] else "",
        "gs06": sorted(disk["gs06"], key=_numeric)[-1] if disk["gs06"] else "",
        "envelope_date": "",
        "statement": "",
    }
    for k in ("st02", "bht03", "clm01", "ref_f8", "ref_9a"):
        run[k] = sorted(disk[k])
    run["isa13_all"] = sorted(disk["isa13"])
    run["gs06_all"] = sorted(disk["gs06"], key=_numeric)
    mf = {"version": VERSION, "runs": [run]}
    _write(repo, mf)
    return mf


def _numeric(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def used(mf, repo):
    """Union of every recorded run and a fresh disk rescan."""
    out = {k: set() for k in KEYS}
    for k, v in scan_disk(repo).items():
        out[k] |= v
    for run in mf.get("runs", []):
        for k in ("st02", "bht03", "clm01", "ref_f8", "ref_9a"):
            out[k] |= set(run.get(k) or [])
        for scalar, plural in (("isa13", "isa13_all"), ("gs06", "gs06_all")):
            if run.get(scalar):
                out[scalar].add(run[scalar])
            out[scalar] |= set(run.get(plural) or [])
    return out


def used_envelope_dates(mf):
    return {r["envelope_date"] for r in mf.get("runs", [])
            if r.get("envelope_date")}


def used_windows(mf):
    """The set of statement-period start dates already issued."""
    out = set()
    for r in mf.get("runs", []):
        stmt = r.get("statement") or ""
        if "-" in stmt:
            out.add(stmt.split("-")[0])
    return out


def append_run(repo, record):
    mf = load(repo)
    mf["runs"].append(record)
    _write(repo, mf)
