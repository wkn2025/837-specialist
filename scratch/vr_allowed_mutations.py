"""Mutate throwaway copies of the V&R / allowed>billed file; assert each check goes red.

A check that has never been watched fail is not evidence. Every mutation below
names the validate_vr_allowed_file.py check that must catch it.
"""
from __future__ import annotations
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import validate_vr_allowed_file as V

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = V.DEFAULT_FILE
SOURCE = V.DEFAULT_SOURCE
VALIDATOR = os.path.join(HERE, "validate_vr_allowed_file.py")

# (label, old, new, count to replace, occurrences the literal must have,
# expected failing check). The two counts are separate on purpose: a literal
# that starts matching more places than declared is BROKEN, not narrowed.
MUTATIONS = [
    ("second_claim_dropped",
     "ST*837*010649911*005010X223A2~\n", "", 1, 1, 1),
    ("iea02_out_of_step", "IEA*1*780100240~", "IEA*1*780100299~", 1, 1, 2),
    ("isa13_reuses_parent_icn", "*780100240*1*T*", "*780100228*1*T*", 1, 1, 3),
    ("st03_version_wrong",
     "ST*837*010649910*005010X223A2~", "ST*837*010649910*005010X222A1~", 1, 1, 4),
    ("se01_decremented", "SE*37*010649910~", "SE*36*010649910~", 1, 1, 5),
    ("bht03_back_to_17_chars",
     "BHT*0019*00*010649911*20260817*1426*CH~",
     "BHT*0019*00*E2E26081112125710*20260817*1426*CH~", 1, 1, 6),
    # HL*2*1*22*0 occurs once per claim; only the first is mutated.
    ("hl_self_parent", "HL*2*1*22*0~", "HL*2*2*22*0~", 1, 2, 7),
    ("vr_frequency_back_to_original",
     "CLM*TEST260812001*420.00***13:A:7**A*Y*Y~",
     "CLM*TEST260812001*420.00***13:A:1**A*Y*Y~", 1, 1, 8),
    ("vr_ref9f_points_at_itself",
     "REF*9F*E2E26081112125701~", "REF*9F*E2E26081112125711~", 1, 1, 8),
    ("inv10_allowed_below_billed",
     "HCP*01*500.00*0.00*9327*******UN*1~", "HCP*01*357.00*0.00*9327*******UN*1~",
     1, 1, 9),
    ("inv10_negative_repriced_saving",
     "HCP*01*500.00*0.00*9327*0.00**0.00****UN*2~",
     "HCP*01*500.00*-80.00*9327*0.00**0.00****UN*2~", 1, 1, 10),
    ("space_padded_segment",
     "N3*PO BOX 30532~", "N3* PO BOX 30532~", 1, 2, 11),
    ("payload_amount_drifted_from_source",
     "SV2*0430*HC:97530*420.00*UN*2~", "SV2*0430*HC:97530*421.00*UN*2~", 1, 2, 12),
    ("member_id_altered",
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969~",
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333970~", 1, 2, 13),
    ("artifact_edited_without_the_generator",
     "NTE*ADD*VOID AND REKEY OF CCN 24012154121~",
     "NTE*ADD*VOID AND REKEY OF CCN 24012154122~", 1, 1, 14),
]


def stage():
    tmp = tempfile.mkdtemp(prefix="x12vr-")
    dst = os.path.join(tmp, os.path.basename(TARGET))
    shutil.copyfile(TARGET, dst)
    return dst


def mutate(path, old, new, count, occurrences):
    raw = io.open(path, encoding="utf-8", newline="").read()
    present = raw.count(old)
    if present != occurrences:
        return present, False
    mutated = raw.replace(old, new, count)
    if mutated == raw:
        return present, False
    io.open(path, "w", encoding="utf-8", newline="").write(mutated)
    return present, True


def run_validator(path):
    r = subprocess.run([sys.executable, VALIDATOR, "--file", path,
                        "--source", SOURCE], capture_output=True, text=True)
    return sorted(int(m) for m in re.findall(r"\[FAIL\]\s+(\d+)\.", r.stdout)), r.returncode


def main():
    base = stage()
    fails, rc = run_validator(base)
    if fails or rc != 0:
        print("BASELINE NOT CLEAN: fails %s (exit %d)" % (fails, rc))
        return 1
    print("baseline: clean copy passes every check\n")

    uncaught, broken = [], []
    print("mutation                             expect  caught      failing checks")
    for label, old, new, count, occurrences, expect in MUTATIONS:
        path = stage()
        present, ok_mut = mutate(path, old, new, count, occurrences)
        if not ok_mut:
            print("%-36s BROKEN - literal occurs %d times, expected %d"
                  % (label, present, occurrences))
            broken.append(label)
            continue
        fails, rc = run_validator(path)
        ok = expect in fails and rc != 0
        if not ok:
            uncaught.append(label)
        print("%-36s %-7d %-11s %s"
              % (label, expect, "YES" if ok else "*** NO ***", fails))

    print("\n%d mutations, %d uncaught, %d broken"
          % (len(MUTATIONS), len(uncaught), len(broken)))
    return 1 if (uncaught or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
