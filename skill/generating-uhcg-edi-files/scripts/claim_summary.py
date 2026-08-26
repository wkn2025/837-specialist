"""Build the claim-and-line reference .docx that accompanies a generated file.

Every value is read from the .x12. Nothing is recomputed - the only arithmetic
is the per-claim reconciliation, which sums the service lines and compares the
total against CLM02. That sum must not share a source with the number it
audits, so it is done here and nowhere else.
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys

from docx import Document

import seeds
import x12_parse as X


I_COLS = ["Line", "Rev", "Proc", "Mod", "DOS", "Units", "Billed",
          "Allowed", "Savings"]
P_COLS = ["Line", "Proc", "Mod", "POS", "DOS", "Units", "Billed",
          "Allowed", "Savings"]


def claim_blocks(segs):
    """The ST..SE block of every claim, in file order."""
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]


def clm01_of(block):
    for s in block:
        if s.startswith("CLM" + X.ELEM):
            return X.elems(s)[1]
    return ""


def _proc_and_mod(composite):
    """HC:97530:25 -> ("97530", "25"). Qualifier dropped, modifiers joined."""
    parts = composite.split(X.COMP)
    if len(parts) < 2:
        return composite, ""
    return parts[1], ", ".join(parts[2:])


def _fmt_date(value):
    """20240205 -> 02/05/2024; an RD8 range keeps both sides."""
    if "-" in value:
        parts = value.split("-")
        # RD8_same_day ranges carry the same date twice; show it once.
        if len(set(parts)) == 1:
            return _fmt_date(parts[0])
        return " - ".join(_fmt_date(v) for v in parts)
    if len(value) == 8 and value.isdigit():
        return "%s/%s/%s" % (value[4:6], value[6:8], value[:4])
    return value


def service_lines(block):
    """One dict per service line, values taken straight from the segments."""
    out = []
    cur = None
    for seg in block:
        e = X.elems(seg)
        if e[0] == "LX":
            cur = {"Line": e[1], "DOS": "", "Allowed": "", "Savings": ""}
            out.append(cur)
        elif cur is None:
            continue
        elif e[0] == "SV2":
            proc, mod = _proc_and_mod(e[2])
            cur.update({"Rev": e[1], "Proc": proc, "Mod": mod,
                        "Billed": e[3], "Units": "%s %s" % (e[5], e[4])})
        elif e[0] == "SV1":
            proc, mod = _proc_and_mod(e[1])
            cur.update({"Proc": proc, "Mod": mod, "Billed": e[2],
                        "Units": "%s %s" % (e[4], e[3]),
                        "POS": e[5] if len(e) > 5 else ""})
        elif e[0] == "DTP" and e[1] == "472":
            cur["DOS"] = _fmt_date(e[3])
        elif e[0] == "HCP":
            cur["Allowed"], cur["Savings"] = e[2], e[3]
    return out


def _seg(block, sid, *match):
    """The first segment with this id whose leading elements match."""
    for seg in block:
        e = X.elems(seg)
        if e[0] != sid:
            continue
        if all(len(e) > i + 1 and e[i + 1] == v for i, v in enumerate(match)):
            return e
    return None


def _money(value):
    """1234.5 -> 1,234.50, for the totals this module computes itself."""
    return "{:,.2f}".format(value)


def claim_facts(block, profile):
    """The claim detail rows, in display order, as (label, value)."""
    clm = _seg(block, "CLM") or []
    il = _seg(block, "NM1", "IL")
    dmg = _seg(block, "DMG")
    sbr = _seg(block, "SBR")
    bill = _seg(block, "NM1", "85")
    ref9a = _seg(block, "REF", "9A")
    reff8 = _seg(block, "REF", "F8")
    his = [X.elems(seg) for seg in block if seg.startswith("HI" + X.ELEM)]
    hcp = _seg(block, "HCP")
    clm05 = clm[5].split(X.COMP) if len(clm) > 5 else []

    name = ""
    if il:
        name = ", ".join(p for p in (il[3], il[4] if len(il) > 4 else "") if p)
    dx_principal, dx_other = "", []
    for hi in his:
        for comp in hi[1:]:
            parts = comp.split(X.COMP)
            if parts[0] == "ABK" and not dx_principal:
                dx_principal = parts[1]
            elif parts[0] == "ABF":
                dx_other.append(parts[1])

    rows = [
        ("Patient / Subscriber", name),
        ("Member ID", il[9] if il and len(il) > 9 else ""),
        ("DOB / Gender", "%s  /  %s" % (_fmt_date(dmg[2]), dmg[3])
         if dmg else ""),
        ("Group Number", sbr[3] if sbr and len(sbr) > 3 else ""),
        ("Billing Provider", bill[3] if bill else ""),
        ("Patient Control No (CLM01)", clm[1] if len(clm) > 1 else ""),
        ("Total Billed (CLM02)", clm[2] if len(clm) > 2 else ""),
    ]
    if profile.line_id == "SV2":
        rows.append(("Bill Type / Freq (CLM05)",
                     "%s / freq %s" % (clm05[0], clm05[2])
                     if len(clm05) > 2 else ""))
        stmt = _seg(block, "DTP", "434")
        rows.append(("Statement Dates", _fmt_date(stmt[3]) if stmt else ""))
        cl1 = _seg(block, "CL1")
        rows.append(("Admission Info (CL1)",
                     "Adm Type %s / Src %s / Disch %s" % (cl1[1], cl1[2],
                                                          cl1[3])
                     if cl1 else ""))
    else:
        rows.append(("Place of Service (CLM05)",
                     clm05[0] if clm05 else ""))
    rows += [
        ("Repriced Claim No (REF*9A)", ref9a[2] if ref9a else ""),
        ("Payer Claim Control No (REF*F8)", reff8[2] if reff8 else ""),
    ]
    # Void-and-replace, when the claim carries it. REF*9F is loop 2300's
    # "Original UHAP Claim ID" and the claim-level NTE*ADD is its special
    # instruction; both are absent from an original claim, so neither row is
    # shown unless the file has one.
    ref9f = _seg(block, "REF", "9F")
    if ref9f:
        rows.append(("Replaces Claim (REF*9F)", ref9f[2]))
    nte = _seg(block, "NTE", "ADD")
    if nte:
        rows.append(("Claim Note (NTE*ADD)", nte[2]))
    rows += [
        ("Principal Dx (ABK)", dx_principal),
        ("Other Dx (ABF)", ", ".join(dx_other)),
        ("Claim Allowed (HCP02)", hcp[2] if hcp else ""),
        ("Claim Savings (HCP03)", hcp[3] if hcp else ""),
        ("Pricing Method / Policy",
         "%s / %s" % (hcp[1], hcp[4]) if hcp and len(hcp) > 4 else ""),
    ]
    return rows


def build(x12_path, manifest_path, out_path=None):
    """Write the summary next to the .x12 and return the path written."""
    _, segs = X.read_segments(x12_path)
    blocks = claim_blocks(segs)
    with io.open(manifest_path, encoding="utf-8") as fh:
        man = json.loads(fh.read())
    profile = seeds.get(man["type"])
    cols = I_COLS if profile.line_id == "SV2" else P_COLS
    if out_path is None:
        out_path = x12_path[:-4] + "_ClaimSummary.docx"

    doc = Document()
    doc.add_heading("837%s Claim & Line Summary" % profile.code, level=0)
    doc.add_paragraph("Source file: %s" % os.path.basename(x12_path))
    billed = sum(float(_seg(b, "CLM")[2]) for b in blocks)
    doc.add_paragraph("Claims in file: %d    |    Total billed: %s"
                      % (len(blocks), _money(billed)))
    doc.add_paragraph("Data-entry verification reference. Values shown "
                      "exactly as transmitted.")

    for i, block in enumerate(blocks, 1):
        doc.add_heading("Claim %d - %s" % (i, clm01_of(block)), level=1)
        claim_summary_table(doc, claim_facts(block, profile))
        doc.add_paragraph("Service Lines")
        lines = service_lines(block)
        grid = doc.add_table(rows=1, cols=len(cols))
        grid.style = "Table Grid"
        for c, name in enumerate(cols):
            grid.rows[0].cells[c].text = name
        for line in lines:
            row = grid.add_row()
            for c, name in enumerate(cols):
                row.cells[c].text = line.get(name, "")
        line_total = sum(float(ln["Billed"]) for ln in lines)
        clm02 = float(_seg(block, "CLM")[2])
        doc.add_paragraph(
            "Line total: %s   |   Claim billed: %s   |   %s"
            % (_money(line_total), _money(clm02),
               "MATCH" if abs(line_total - clm02) < 0.005 else "MISMATCH"))
    doc.save(out_path)
    return out_path


def claim_summary_table(doc, rows):
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    out = build(args.file, args.manifest, args.out)
    sys.stdout.write("wrote %s\n" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
