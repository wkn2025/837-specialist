"""Render findings to the batch1 report layout with python-docx."""
from __future__ import annotations
from collections import OrderedDict

from docx import Document
from docx.shared import Pt

import findings as F
import rules_837i as R

TITLE = "UHCG Adjudicated 837I - Validation Findings and Applied Fixes"
SUBTITLE = "Institutional (UB) adjudication return file, ECUSA -> UHCG"
NOT_CHECKED_SOURCE = ("Immutability: not checked, source outbound file not supplied")
NOT_CHECKED_MATRIX = ("Expected results: not checked, matrix not supplied")
DISTILLED = "skill rule tables, guide package not located"


def _table(doc, headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    for cell, text in zip(t.rows[0].cells, headers):
        cell.text = str(text)
    for row in rows:
        cells = t.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = "" if text is None else str(text)
    return t


def _mono(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    return p


def adjudication_summary(edi):
    out = []
    for claim in edi.claims:
        k3 = R.k3_values(claim)
        clm, hcp = claim.seg("CLM"), claim.seg("HCP")
        out.append({
            "uhap": claim.uhap_id,
            "bd": k3["bd"] or "",
            "billed": clm.el(2) if clm else "",
            "allowed": hcp.el(2) if hcp else "",
            "netpaid": k3["pa"] or "",
            "notcov": k3["na"] or "",
            "resp": str(R.claim_patient_resp(claim) or ""),
            "cov": k3["cp"] or "",
        })
    return out


def render(items, meta, corrected_items, edits, out_path, judgments=None,
           corrected_edi=None):
    judgments = judgments or []
    doc = Document()
    doc.add_heading(TITLE, level=0)
    doc.add_paragraph(SUBTITLE)

    remaining = [f for f in corrected_items if f.severity == F.BLOCKER]
    blockers = [f for f in items if f.severity == F.BLOCKER]
    by_rule = OrderedDict()
    for f in blockers:
        by_rule.setdefault(f.rule_id, []).append(f)

    result = ("%d defect classes found across %d claims"
              % (len(by_rule), len({f.claim for f in blockers if f.claim})))
    if corrected_items:
        result += ("; corrected file re-validated clean" if not remaining
                   else "; %d blockers remain" % len(remaining))

    _table(doc, ["Item", "Value"], [
        ["File validated", meta.get("file", "")],
        ["Corrected file produced", meta.get("corrected_path", "") or "not produced"],
        ["Source outbound file", meta.get("source_file", "") or "not supplied"],
        ["Transaction", "837I, %s, %s claims, 1 claim per ST-SE"
         % (meta.get("version", ""), meta.get("claims", ""))],
        ["Validated against",
         meta.get("guides", "") if meta.get("mode") == "cited" else DISTILLED],
        ["Date", meta.get("generated", "")],
        ["Result", result],
    ])

    doc.add_heading("1. Summary of findings", level=1)
    rows = []
    for n, (rule_id, group) in enumerate(by_rule.items(), start=1):
        claims = ", ".join(sorted({f.claim for f in group if f.claim})) or "all claims"
        rows.append([n, claims, group[0].message, group[0].severity.title()])
    _table(doc, ["#", "Claim (UHAP ID)", "Defect", "Severity"], rows)

    doc.add_heading("2. Errors and fixes in detail", level=1)
    for n, (rule_id, group) in enumerate(by_rule.items(), start=1):
        doc.add_heading("Error %d - %s" % (n, group[0].message), level=2)
        doc.add_paragraph("Rule: %s" % rule_id)
        doc.add_paragraph("Claims: %s"
                          % (", ".join(sorted({f.claim for f in group if f.claim}))
                             or "all"))
        if group[0].citation:
            doc.add_paragraph("Guide: %s" % group[0].citation)
        for f in group:
            if f.fix:
                _mono(doc, "%s  ->  %s" % (f.fix.old_text, f.fix.new_text))

    doc.add_heading("3. Envelope and control-number changes", level=1)
    if edits:
        _table(doc, ["Element", "Before", "After", "Reason"],
               [[e.segment_index, e.before, e.after, e.reason] for e in edits])
    else:
        doc.add_paragraph("No envelope changes were required.")

    doc.add_heading("4. Checks that passed on the original file", level=1)
    fired = {f.rule_id for f in items}
    import rules
    passed = [r for r in rules.registered_ids() if r not in fired]
    doc.add_paragraph("%d rules passed: %s" % (len(passed), ", ".join(passed)))
    if not meta.get("source_file"):
        doc.add_paragraph(NOT_CHECKED_SOURCE)
    if not meta.get("matrix_file"):
        doc.add_paragraph(NOT_CHECKED_MATRIX)

    doc.add_heading("5. Advisory notes (non-blocking)", level=1)
    advisories = [f for f in items if f.severity == F.ADVISORY]
    if advisories:
        for f in advisories:
            doc.add_paragraph("%s - %s" % (f.rule_id, f.message), style="List Bullet")
    else:
        doc.add_paragraph("None.")

    doc.add_heading("6. Verification", level=1)
    doc.add_paragraph(
        "Rules were derived from the UHCG reference package and are mutation-tested: "
        "each deliberate corruption in the suite is detected by its own rule, and no "
        "corruption fires every rule.")
    _table(doc, ["File", "Findings"], [
        [meta.get("filename", ""), len(blockers)],
        [meta.get("corrected_path", "") or "not produced", len(remaining)],
    ])
    if remaining:
        doc.add_paragraph("%d blockers remain on the corrected file." % len(remaining))
    if corrected_edi is not None:
        rows = [[r["uhap"], r["bd"], r["billed"], r["allowed"], r["netpaid"],
                 r["notcov"], r["resp"], r["cov"]]
                for r in adjudication_summary(corrected_edi)]
        _table(doc, ["UHAP ID", "BD", "Billed", "Allowed", "Net paid",
                     "Not covered", "Patient resp.", "Cov %"], rows)

    doc.add_heading("7. Open items to confirm with UMR", level=1)
    rows = []
    seen = set()
    for f in items:
        if f.fix and f.fix.uncertain and f.fix.reason not in seen:
            seen.add(f.fix.reason)
            rows.append([len(rows) + 1, f.message, f.fix.reason])
    for j in judgments:
        rows.append([len(rows) + 1, j["item"], j["why"]])
    if rows:
        _table(doc, ["#", "Item", "Why it needs confirmation"], rows)
    else:
        doc.add_paragraph("None.")

    doc.save(out_path)
    return out_path
