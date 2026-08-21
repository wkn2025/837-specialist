"""Build the declared-override fixture from a synthetic allocation.

The two canonical fixtures reserve the 990000001 / 990000101 identifier bands
and are built the same way - never out of the real masterfile, so committing
one costs no identifiers.
"""
import hashlib
import io
import json
import os
import sys

SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(SK))
sys.path.insert(0, os.path.join(SK, "scripts"))
import generate                                          # noqa: E402
import masterfile as M                                   # noqa: E402
import overrides                                         # noqa: E402
import seeds                                             # noqa: E402

CLAIMS = 3
DOC = {
    "identity": {
        "subscriber": {"last": "OKONKWO", "first": "ADAEZE",
                       "memberId": "909001777001"},
        "attendingProvider": {"npi": "1487654321"},
    },
    "claims": [
        {"n": 1, "principalDiagnosis": "E1165"},
        {"n": 2, "lines": [{"date": "20240203", "billed": "500.00"},
                           {"date": "20240204", "billed": "250.00"}]},
    ],
}

alloc = M.Allocation(
    isa13="990000201", gs06="995",
    envelope_date="20240315", envelope_time="0930",
    window_start="20240301", window_end="20240307",
    statement="20240301-20240307",
    service_dates=["2024030%d" % d for d in range(1, 8)],
    st02=["%09d" % (990000201 + i) for i in range(CLAIMS)],
    bht03=["2403150%03d" % (i + 1) for i in range(CLAIMS)],
    clm01=["TEST240315%03d" % (i + 1) for i in range(CLAIMS)],
    ref_f8=["%011d" % (99012156001 + i) for i in range(CLAIMS)],
    ref_9a=["E2E24031512125%03d" % (i + 1) for i in range(CLAIMS)])

profile = seeds.get("I")
ov = overrides.parse(DOC, profile, CLAIMS)
text = generate.render(
    generate.build(seeds.load_seed(profile, REPO), profile, alloc, CLAIMS, ov))
with open(seeds.seed_path(profile, REPO), "rb") as fh:
    seed_sha = hashlib.sha256(fh.read()).hexdigest()
record = generate.manifest_record(
    alloc, profile, CLAIMS,
    "skill/generating-uhcg-edi-files/tests/fixtures/declared_3claims.x12",
    hashlib.sha256(text.encode("ascii")).hexdigest(), seed_sha, DOC)
# A wall-clock stamp would make every rebuild a diff. The canonical fixtures
# carry a fixed midnight stamp for the same reason; nothing validates it.
record["timestamp"] = "2026-08-21T00:00:00"

fx = os.path.join(SK, "tests", "fixtures")
with io.open(os.path.join(fx, "declared_3claims.x12"), "w",
             encoding="ascii", newline="") as fh:
    fh.write(text)
with io.open(os.path.join(fx, "declared_3claims.manifest.json"), "w",
             encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
print("wrote declared_3claims.x12 (%d bytes)" % len(text))
