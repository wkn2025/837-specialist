"""Mutate throwaway copies of the output file; assert the right check catches each one."""
from __future__ import annotations
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "837 Sample",
                      "fromUHCG-837I-WKN_9claims.x12")

ALL = "all"  # substitute every occurrence, whatever the count happens to be

MUTATIONS = [
    ("old_member_one_claim",
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969~",
     "NM1*IL*1*TEST*TEST****MI*9091333957~", 1, 4),
    ("old_dob_one_claim",
     "DMG*D8*19941217*F~", "DMG*D8*19570810*F~", 1, 4),
    ("retired_account_number",
     "CLM*TEST260812001*", "CLM*PA0078*", 1, 10),
    ("duplicate_clm01",
     "CLM*TEST260812002*", "CLM*TEST260812001*", 1, 10),
    ("duplicate_reff8",
     "REF*F8*24012154122~", "REF*F8*24012154121~", 1, 10),
    ("short_reff8",
     "REF*F8*24012154123~", "REF*F8*2401215412~", 1, 10),
    ("swapped_name_order",
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969~",
     "NM1*IL*1*WILLIAM*NISHIMURA****MI*909001333969~", 1, 4),
    ("gender_changed",
     "DMG*D8*19941217*F~", "DMG*D8*19941217*M~", 1, 4),
    # --- regressions for the 2026-08-12 code review findings ---
    # C1: a stray ST inside an open transaction set used to be swallowed silently.
    ("stray_duplicate_st",
     "ST*837*010649901*005010X223A2~\n",
     "ST*837*010649901*005010X223A2~\nST*837*010649901*005010X223A2~\n", 1, 24),
    # C1 second layer: an unclosed ST ahead of the group trailer.
    ("orphan_trailing_st",
     "GE*9*1~\n", "ST*837*010649910*005010X223A2~\nGE*9*1~\n", 1, 24),
    # C1 third layer: a well-formed extra ST..SE pair the parser accepts, so
    # check 24 is exercised on a file that never trips the parser guard.
    ("extra_full_st_se_pair",
     "GE*9*1~\n",
     "ST*837*010649910*005010X223A2~\nBHT*0019*00*010649910*20250225*0520*CH~\n"
     "SE*3*010649910~\nGE*9*1~\n", 1, 24),
    # I1: BHT03 was masked by normalize_spine and asserted nowhere.
    ("bht03_all_same",
     r"re:BHT\*0019\*00\*01064990\d", "BHT*0019*00*010649901", ALL, 10),
    ("bht03_duplicate_one_claim",
     "BHT*0019*00*010649903", "BHT*0019*00*010649901", 1, 10),
    ("bht03_retired_source_value",
     "BHT*0019*00*010649901", "BHT*0019*00*010649973", 1, 10),
    ("bht03_emptied",
     "BHT*0019*00*010649905", "BHT*0019*00*", 1, 10),
    # I2: claim-level money had no format assertion, and MONEY allowed leading zeros.
    ("clm02_leading_zero",
     "CLM*TEST260812001*420.00*", "CLM*TEST260812001*0420.00*", 1, 8),
    ("claim_hcp_three_decimals",
     "HCP*10*357.00*63.00*9327*******UN*1~",
     "HCP*10*357.000*63.000*9327*******UN*1~", 1, 8),
    ("claim_hcp_signed",
     "HCP*10*357.00*63.00*9327*******UN*1~",
     "HCP*10*+357.00*63.00*9327*******UN*1~", 1, 8),
    ("line_sv203_leading_zero",
     "SV2*0430*HC:97530*420.00*UN*2~", "SV2*0430*HC:97530*0420.00*UN*2~", 1, 8),
    ("line_hcp_leading_zeros",
     "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
     "HCP*10*0357.00*063.00*9327*0.00**0.00****UN*2~", 1, 8),
    # SV205/HCP12 are masked too, so their literal form needs the same guard as
    # the money fields: 02 and 2.0 are Decimal-equal to 2 but wrong bytes.
    ("line_units_leading_zero",
     "SV2*0430*HC:97530*420.00*UN*2~\nDTP*472*D8*20241121~\n"
     "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
     "SV2*0430*HC:97530*420.00*UN*02~\nDTP*472*D8*20241121~\n"
     "HCP*10*357.00*63.00*9327*0.00**0.00****UN*02~", 1, 9),
    ("line_units_decimal",
     "SV2*0430*HC:97530*420.00*UN*2~\nDTP*472*D8*20241121~\n"
     "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
     "SV2*0430*HC:97530*420.00*UN*2.0~\nDTP*472*D8*20241121~\n"
     "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2.0~", 1, 9),
]


def run_validator(path):
    r = subprocess.run([sys.executable, os.path.join(HERE, "validate_9claims.py"), path],
                       capture_output=True, text=True)
    fails = sorted(int(m) for m in re.findall(r"\[FAIL\]\s+(\d+)\.", r.stdout))
    return fails, r.returncode


def main():
    raw = io.open(TARGET, encoding="utf-8", newline="").read()
    tmp = tempfile.mkdtemp(prefix="x12mut-")
    failures = []

    # A mutation is only evidence if the unmutated file is clean: otherwise
    # "expect in fails" can be satisfied by a check that was already red.
    base_fails, base_rc = run_validator(TARGET)
    if base_fails or base_rc != 0:
        print("BASELINE NOT CLEAN: failing checks %s (exit %d) - battery aborted"
              % (base_fails, base_rc))
        return 1
    print("baseline: 0 failing checks, exit 0\n")

    print("mutation                     expect  caught     exit  all failing checks")
    broken = []
    for name, old, new, count, expect in MUTATIONS:
        # `count` is the number of substitutions the mutation must make, in both
        # modes; ALL means every occurrence. Asserting the count is what stops a
        # mutation that silently stopped matching from being scored as "the
        # validator failed to catch it".
        if old.startswith("re:"):
            pat = old[3:]
            mutated, made = re.subn(pat, new.replace("\\", "\\\\"), raw,
                                    count=0 if count is ALL else count)
        else:
            pat = old
            made = raw.count(old) if count is ALL else min(raw.count(old), count)
            mutated = raw.replace(old, new, -1 if count is ALL else count)
        if made == 0 or mutated == raw:
            print("%-28s BROKEN - pattern made no change: %r" % (name, pat))
            broken.append(name)
            continue
        if count is not ALL and made != count:
            print("%-28s BROKEN - made %d substitutions, expected %d: %r"
                  % (name, made, count, pat))
            broken.append(name)
            continue
        path = os.path.join(tmp, name + ".x12")
        io.open(path, "w", encoding="utf-8", newline="").write(mutated)
        fails, rc = run_validator(path)
        caught = "YES" if expect in fails else "*** NO ***"
        if expect not in fails:
            failures.append(name)
        print("%-28s %-7d %-10s %-5d %s" % (name, expect, caught, rc, fails))
    # A broken mutation is not an uncaught one: it means the pattern rotted and
    # nothing was actually tested. Counted separately, still fails the run.
    print("\n%d mutations, %d uncaught, %d broken"
          % (len(MUTATIONS), len(failures), len(broken)))
    return 1 if (failures or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
