"""CLI: parse an EDI2 file, run the 837I rules, optionally fix and report."""
from __future__ import annotations
import argparse
import datetime
import json
import os
import sys

import apply_fixes as A
import findings as F
import rules
import rules_837i  # noqa: F401 - importing registers every 837I rule
import x12_model as M

VERSION_837I = rules_837i.VERSION_837I
VERSION_837P = rules_837i.VERSION_837P


class UnsupportedTransaction(Exception):
    pass


def _preflight(edi, path):
    gs = edi.seg("GS")
    version = gs.el(8) if gs is not None else ""
    if version == VERSION_837P:
        raise UnsupportedTransaction(
            "%s is an 837P (%s); this skill implements 837I (%s) only"
            % (os.path.basename(path), VERSION_837P, VERSION_837I))
    return version


def find_guides(start):
    """Walk up from the file looking for the UHCG reference package."""
    here = os.path.abspath(os.path.dirname(start))
    while True:
        candidates = [
            os.path.join(here, "UMR_UHCG_837_EDI_Reference"),
            os.path.join(here, "docs", "reference", "umr-uhcg-837"),
        ]
        for candidate in candidates:
            if os.path.isdir(candidate):
                return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def load_scenarios(path):
    """Read recorded per-claim judgment, keyed by UHAP claim id.

    Shape: {"<UHAP id>": {"benefit_decision": "4", "reason": "..."}}. This is
    the decision a human or the model already took - the expected-results
    matrix itself is never read by the script.
    """
    if not path:
        return {}
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("%s must hold an object keyed by UHAP claim id" % path)
    return data


def run(path, source_path=None, matrix_path=None, fix=False, out_dir=None,
        now=None, next_isa13=None, scenarios_path=None):
    edi = M.parse(path)
    version = _preflight(edi, path)
    source = M.parse(source_path) if source_path else None
    filename = os.path.basename(path)
    scenarios = load_scenarios(scenarios_path)

    ctx = rules.Context(edi=edi, source=source, matrix=matrix_path,
                        filename=filename, scenarios=scenarios)
    items = rules.run_all(ctx, rules_837i.registry())

    guides = find_guides(path)
    meta = {
        "file": path,
        "filename": filename,
        "version": version,
        "claims": len(edi.claims),
        "source_file": source_path or "",
        "matrix_file": matrix_path or "",
        "scenarios_file": scenarios_path or "",
        "guides": guides or "",
        "mode": "cited" if guides else "distilled",
        "generated": (now or datetime.datetime.now()).isoformat(timespec="seconds"),
    }

    out = {"findings": items, "meta": meta, "corrected_path": "",
           "corrected_findings": []}
    if not fix:
        return out

    directory = out_dir or os.path.dirname(os.path.abspath(path))
    control = next_isa13 or A.next_control_number(directory, edi.seg("ISA").el(13))
    result = A.apply(edi, items, now=now, next_isa13=control)
    corrected_path = os.path.join(directory, result.filename)
    with open(corrected_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(result.text)

    fixed = M.parse(corrected_path)
    fixed_ctx = rules.Context(edi=fixed, source=source, matrix=matrix_path,
                              filename=result.filename, scenarios=scenarios)
    out["corrected_path"] = corrected_path
    out["corrected_findings"] = rules.run_all(fixed_ctx, rules_837i.registry())
    out["edits"] = result.edits
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--source")
    ap.add_argument("--matrix")
    ap.add_argument("--scenarios",
                    help="JSON of recorded per-claim judgment, keyed by UHAP id")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--out-dir")
    ap.add_argument("--report")
    args = ap.parse_args(argv)

    try:
        result = run(args.file, args.source, args.matrix, args.fix, args.out_dir,
                     scenarios_path=args.scenarios)
    except UnsupportedTransaction as exc:
        print("[STOP] %s" % exc)
        return 2
    except M.ParseError as exc:
        print("[STOP] parse failed at offset %d: %s" % (exc.offset, exc))
        return 2

    blockers = 0
    for f in result["findings"]:
        tag = "FAIL" if f.severity == F.BLOCKER else "WARN"
        blockers += 1 if f.severity == F.BLOCKER else 0
        print("[%s] %-28s %s%s" % (tag, f.rule_id,
                                   ("claim %s: " % f.claim) if f.claim else "",
                                   f.message))
    fired = {f.rule_id for f in result["findings"]}
    print("[ OK ] %d rules passed" % (len(rules_837i.registry()) - len(fired)))
    if result["corrected_path"]:
        remaining = [f for f in result["corrected_findings"]
                     if f.severity == F.BLOCKER]
        print("[FIXED] %s - %d blockers remain"
              % (result["corrected_path"], len(remaining)))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(F.to_json(result["findings"], result["meta"]))

    if args.report:
        import report
        corrected_edi = (M.parse(result["corrected_path"])
                         if result["corrected_path"] else None)
        meta = dict(result["meta"])
        meta["corrected_path"] = result["corrected_path"]
        report.render(result["findings"], meta, result["corrected_findings"],
                      result.get("edits", []), args.report,
                      corrected_edi=corrected_edi)
        print("[REPORT] %s" % args.report)

    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
