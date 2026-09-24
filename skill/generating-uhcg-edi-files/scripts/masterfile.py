"""Masterfile: the append-only run log that keeps identifiers unique.

The masterfile allocates, but it does not get the last word. Every read of
"what is already used" also rescans every .x12 on disk, so a hand-edited file,
a restored-from-backup masterfile, or a file that arrived from outside cannot
cause a silent duplicate.
"""
from __future__ import annotations
from contextlib import contextmanager
import errno
import glob
import hashlib
import io
import json
import os
import tempfile
import time

import x12_parse as X

MASTERFILE_REL = "EDI1/masterfile.json"
VERSION = 1

KEYS = ("isa13", "gs06", "st02", "bht03", "clm01", "ref_f8", "ref_9a")


class MasterfileError(Exception):
    """The masterfile is missing, unreadable, or of an unknown version."""


def path(repo):
    return os.path.join(repo, *MASTERFILE_REL.split("/"))


def _generation_lock_path(repo):
    return path(repo) + ".lock"


@contextmanager
def generation_lock(repo):
    """Cross-process exclusive lock for one repository's generation state.

    The stable lock file is never unlinked: deleting it while another process
    waits could split contenders across two file identities. The operating
    system owns the lock itself and releases it when the descriptor closes or
    the process exits, including an abrupt crash.
    """
    lock_path = _generation_lock_path(repo)
    lock_dir = os.path.dirname(lock_path)
    if lock_dir and not os.path.isdir(lock_dir):
        os.makedirs(lock_dir, exist_ok=True)
    fh = open(lock_path, "a+b")
    locked = False
    try:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        fh.seek(0)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN,
                                         errno.EDEADLK):
                        raise
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            locked = True
        yield
    finally:
        try:
            if locked:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def scan_disk(repo):
    """Identifier values present in every .x12 under the repo."""
    return scan_disk_excluding(repo, None, None)


def scan_disk_excluding(repo, abspath, basename, skip_sha=None):
    """scan_disk, skipping any file matching abspath, basename or skip_sha.

    All three exclusions are needed: when a validator runs against a temp copy,
    the committed original is still on disk under the same name, and without
    the basename exclusion every identifier collides with itself. skip_sha
    covers the remaining case - a byte-identical copy filed under a different
    name, which is what a pinned replay produces.
    """
    found = {k: set() for k in KEYS}
    pattern = os.path.join(repo, "**", "*.x12")
    for p in glob.glob(pattern, recursive=True):
        if abspath and os.path.abspath(p) == abspath:
            continue
        if basename and os.path.basename(p) == basename:
            continue
        if skip_sha:
            with open(p, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() == skip_sha:
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
    fd, tmp = tempfile.mkstemp(prefix=".masterfile-", suffix=".tmp", dir=d)
    try:
        with io.open(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(mf, indent=2, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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


def ccn_for_uhap(mf, uhap):
    """Every (run output, CCN) a recorded run issued alongside this UHAP id.

    A run records ref_9a and ref_f8 index-aligned, one entry per claim, so a
    claim's Claim Control Number is the ref_f8 sitting at the same index as
    its REF*9A. UHCG assigns a CCN once per claim - "11 digit # assigned to
    claim by UHCG" (UHCG_837P_Companion_Guide_FULL.csv loop 2300 REF*F8;
    UHCG_837I_Companion_Guide_FULL.csv likewise) - and keeps it across
    reworks, so a replacement claim inherits the original's rather than being
    issued a new one.

    Bootstrap and retired runs are skipped: their lists are inventories of
    what was found on disk, not per-claim allocations, so their indices line
    up with nothing.
    """
    hits = []
    for run in mf.get("runs", []):
        if run.get("type") in ("imported", "retired"):
            continue
        nines = run.get("ref_9a") or []
        f8s = run.get("ref_f8") or []
        for i, value in enumerate(nines):
            if value != uhap:
                continue
            if i >= len(f8s):
                raise MasterfileError(
                    "run %s records REF*9A %s as claim %d with no REF*F8 "
                    "beside it" % (run.get("output", "?"), uhap, i + 1))
            hits.append((run.get("output", "?"), f8s[i]))
    return hits


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


# --------------------------------------------------------------------------
# Allocation
# --------------------------------------------------------------------------
import datetime
from dataclasses import dataclass, field
from typing import List

YEAR = 2024
WINDOW_DAYS = 7
ENVELOPE_TIME = "0930"
MAX_CLAIMS = 999
UHAP_CEILING = 19000000      # a UHAP must never be date-shaped: REF*9A is
                              # ST02 stripped of its leading zero, and an
                              # 8-digit value starting 19/20 reads as a date
                              # to the raw-text scan in validator check 8
JAN1 = datetime.date(YEAR, 1, 1)
DEC31 = datetime.date(YEAR, 12, 31)


class Exhausted(MasterfileError):
    """2024 has no unused window or envelope date left."""


def _date(y, m, d):
    return datetime.date(y, m, d)


def _add(d, n):
    return d + datetime.timedelta(days=n)


def _fmt(d):
    return d.strftime("%Y%m%d")


def _parse(s):
    return datetime.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def next_window(mf, window_days=WINDOW_DAYS):
    """First unused window of `window_days` days inside 2024.

    Starts step a whole window at a time; once those are all issued the step
    drops to 1 day. Windows are keyed by start date, so an institutional and
    a professional window can never share a start even though they differ in
    length.
    """
    taken = used_windows(mf)
    last_start = _add(DEC31, -(window_days - 1))
    for step in (window_days, 1):
        d = JAN1
        while d <= last_start:
            if _fmt(d) not in taken:
                return _fmt(d), _fmt(_add(d, window_days - 1))
            d = _add(d, step)
    raise Exhausted(
        "every %d-day window in %d has been used (%d issued)"
        % (window_days, YEAR, len(taken)))


def next_envelope_date(mf, window_end):
    """First unused 2024 date on or after the window end."""
    taken = used_envelope_dates(mf)
    d = _parse(window_end)
    while d <= DEC31:
        if _fmt(d) not in taken:
            return _fmt(d)
        d = _add(d, 1)
    raise Exhausted(
        "no unused %d envelope date on or after %s" % (YEAR, window_end))


def _next_numeric(used_set, width):
    """max(used) + 1, zero-padded to width. Ignores non-numeric values."""
    best = 0
    for v in used_set:
        n = _numeric(v)
        if n > best:
            best = n
    nxt = best + 1
    out = "%0*d" % (width, nxt)
    if len(out) > width:
        raise MasterfileError(
            "next value %d does not fit in %d characters" % (nxt, width))
    return out


def _next_numeric_below(used_set, width, ceiling):
    """max(used below ceiling) + 1, zero-padded. Raises when the band is full."""
    best = 0
    for v in used_set:
        n = _numeric(v)
        if best < n < ceiling:
            best = n
    nxt = best + 1
    if nxt >= ceiling:
        raise MasterfileError(
            "the 8-digit UHAP ST02 band is full (last used %d)" % best)
    return "%0*d" % (width, nxt)


@dataclass
class Allocation:
    isa13: str
    gs06: str
    envelope_date: str
    envelope_time: str
    window_start: str
    window_end: str
    statement: str
    service_dates: List[str]
    st02: List[str] = field(default_factory=list)
    bht03: List[str] = field(default_factory=list)
    clm01: List[str] = field(default_factory=list)
    ref_f8: List[str] = field(default_factory=list)
    ref_9a: List[str] = field(default_factory=list)

    def as_record(self, type_code, claims, output_rel, sha256,
                  seed_rel, seed_sha256):
        return {
            "timestamp": datetime.datetime.now().replace(
                microsecond=0).isoformat(),
            "type": type_code,
            "claims": claims,
            "output": output_rel,
            "sha256": sha256,
            "seed": seed_rel,
            "seed_sha256": seed_sha256,
            "isa13": self.isa13,
            "gs06": self.gs06,
            "envelope_date": self.envelope_date,
            "envelope_time": self.envelope_time,
            "statement": self.statement,
            "service_dates": list(self.service_dates),
            "st02": list(self.st02),
            "bht03": list(self.bht03),
            "clm01": list(self.clm01),
            "ref_f8": list(self.ref_f8),
            "ref_9a": list(self.ref_9a),
        }


def allocate(mf, repo, profile, claims):
    if not isinstance(claims, int) or not 1 <= claims <= MAX_CLAIMS:
        raise MasterfileError(
            "claim count must be between 1 and %d, got %r"
            % (MAX_CLAIMS, claims))
    u = used(mf, repo)
    window_days = len(profile.src_dates)
    window_start, window_end = next_window(mf, window_days)
    envelope_date = next_envelope_date(mf, window_end)
    yymmdd = envelope_date[2:]

    start = _parse(window_start)
    service_dates = [_fmt(_add(start, i)) for i in range(window_days)]

    f8_width = max(11, max((len(v) for v in u["ref_f8"]), default=11))
    f8_first = int(_next_numeric(u["ref_f8"], f8_width))

    if profile.id_style == "i_e2e":
        st02_first = int(_next_numeric(u["st02"], 9))
        st02 = ["%09d" % (st02_first + i) for i in range(claims)]
        bht03 = ["%s%04d" % (yymmdd, i + 1) for i in range(claims)]
        ref_9a = ["E2E%s12125%03d" % (yymmdd, i + 1) for i in range(claims)]
    elif profile.id_style == "p_uhap":
        # REF*9A is the ST02 without its leading zero, and UHCG's is 8
        # digits, so the ST02 has to come from below the ceiling - the
        # reserved fixture range would otherwise push it to 9.
        st02_first = int(_next_numeric_below(u["st02"], 9, UHAP_CEILING))
        if st02_first + claims - 1 >= UHAP_CEILING:
            raise MasterfileError(
                "the 8-digit UHAP ST02 band is full (needs %d from %d)"
                % (claims, st02_first))
        st02 = ["%09d" % (st02_first + i) for i in range(claims)]
        bht03 = list(st02)
        ref_9a = [str(int(v)) for v in st02]
    else:
        raise MasterfileError("unknown id_style %r" % profile.id_style)

    isa13 = _next_numeric(u["isa13"], 9)
    alloc = Allocation(
        isa13=isa13,
        gs06=str(_numeric(_next_numeric(u["gs06"], 9))),
        envelope_date=envelope_date,
        envelope_time=ENVELOPE_TIME,
        window_start=window_start,
        window_end=window_end,
        statement="%s-%s" % (window_start, window_end),
        service_dates=service_dates,
        st02=st02,
        bht03=bht03,
        # Keyed on the never-reused ISA13, not the recycled 2024 envelope
        # date, so no CLM01 repeats one already sent. AN 1-38 in both
        # companion guides (loop 2300 CLM01, Patient Control Number).
        clm01=["WKN%s%03d" % (isa13, i + 1) for i in range(claims)],
        ref_f8=["%0*d" % (f8_width, f8_first + i) for i in range(claims)],
        ref_9a=ref_9a,
    )

    for key, values in (("isa13", [alloc.isa13]), ("gs06", [alloc.gs06]),
                        ("st02", alloc.st02), ("bht03", alloc.bht03),
                        ("clm01", alloc.clm01), ("ref_f8", alloc.ref_f8),
                        ("ref_9a", alloc.ref_9a)):
        clash = sorted(set(values) & u[key])
        if clash:
            raise MasterfileError(
                "allocated %s values already in use: %s" % (key, clash))
    for v in alloc.bht03:
        if not 1 <= len(v) <= 10:
            raise MasterfileError("BHT03 %r is %d characters, must be 1-10"
                                  % (v, len(v)))
    return alloc
