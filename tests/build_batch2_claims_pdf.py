"""Render the batch2 837I file as a per-claim PDF report.

Parses edi2/batch2/UHCG_ECUSA_I_20260818235000.x12 straight from the wire
format - nothing is re-derived from the generator's tables - and writes an HTML
report, then prints it to PDF with headless Chrome.

Usage:
    python build_batch2_claims_pdf.py [--file PATH] [--out PATH] [--html-only]
"""
from __future__ import annotations
import argparse
import glob
import html
import io
import os
import subprocess
import sys
from decimal import Decimal

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DEFAULT_FILE = os.path.join(ROOT, "edi2", "batch2",
                            "UHCG_ECUSA_I_20260818235000.x12")
DEFAULT_OUT = os.path.join(ROOT, "edi2", "batch2",
                           "UHCG_ECUSA_I_20260818235000_claims.pdf")

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# ---------------------------------------------------------------- code tables
# All from UMR_UHCG_837_EDI_Reference: the 837I Companion Guide and the
# Special Instructions (NTE) guide.
BENEFIT_DECISION = {"1": "Covered", "2": "Not covered", "3": "Duplicate",
                    "4": "Medical record request"}
K3_QUAL = {"PA": "Net paid amount", "NA": "Not covered amount",
           "CP": "Coverage percentage"}
CLAIM_FREQ = {"1": "Original", "7": "Replacement of prior claim",
              "8": "Void/cancel of prior claim"}
ADMIT_TYPE = {"1": "Emergency", "2": "Urgent", "3": "Elective",
              "4": "Newborn", "5": "Trauma", "9": "Information not available"}
ADMIT_SRC = {"1": "Physician referral", "2": "Clinic referral",
             "4": "Transfer from a hospital", "5": "Transfer from a SNF",
             "7": "Emergency room", "9": "Information not available"}
PATIENT_STATUS = {"01": "Discharged to home / self care",
                  "02": "Discharged to another short-term hospital",
                  "03": "Discharged to SNF", "30": "Still patient"}
SBR_REL = {"18": "Self", "01": "Spouse", "19": "Child"}
SBR_CODE = {"P": "Primary", "S": "Secondary", "T": "Tertiary"}
HCP_METHOD = {"01": "Zero pricing (allowed >= billed)",
              "10": "Repriced to per-diem / fee schedule"}
CAS_GROUP = {"PR": "Patient responsibility", "CO": "Contractual obligation",
             "OA": "Other adjustment", "PI": "Payer initiated reduction"}
CAS_REASON = {"1": "Deductible", "2": "Coinsurance", "3": "Copay",
              "23": "Impact of prior payer adjudication",
              "45": "Charge exceeds fee schedule / contracted amount",
              "96": "Non-covered charge"}
ENTITY = {"41": "Submitter", "40": "Receiver", "85": "Billing provider",
          "IL": "Subscriber", "PR": "Payer", "71": "Attending provider",
          "77": "Service facility"}
DTP_QUAL = {"096": "Discharge hour", "434": "Statement period",
            "472": "Service date"}


def money(v):
    try:
        return "%0.2f" % Decimal(v)
    except Exception:
        return v


def d8(v):
    return "%s-%s-%s" % (v[0:4], v[4:6], v[6:8]) if len(v) == 8 else v


def rd8(v):
    a, _, b = v.partition("-")
    return "%s to %s" % (d8(a), d8(b))


def esc(v):
    return html.escape(str(v))


def e(seg, i, default=""):
    parts = X.elems(seg)
    return parts[i] if i < len(parts) else default


def find(block, prefix):
    return [s for s in block if s.startswith(prefix)]


def one(block, prefix):
    hits = find(block, prefix)
    return hits[0] if hits else None


def nm1(block, code):
    """The NM1 for an entity code, plus the N3/N4 that follow it."""
    for i, s in enumerate(block):
        if s.startswith("NM1*%s*" % code):
            addr, city = [], None
            for t in block[i + 1:]:
                if t.startswith("N3*"):
                    addr.extend(p for p in X.elems(t)[1:] if p)
                elif t.startswith("N4*"):
                    city = t
                elif t.startswith(("NM1*", "HL*", "CLM*", "LX*", "SBR*")):
                    break
            ent = X.elems(s)
            if ent[2] == "1":
                name = ", ".join(p for p in [ent[3], ent[4]] if p)
            else:
                name = ent[3]
            idq, idv = (ent[8], ent[9]) if len(ent) > 9 else ("", "")
            city_line = ""
            if city:
                c = X.elems(city)
                zipc = c[3] if len(c) > 3 else ""
                if len(zipc) == 9:
                    zipc = zipc[:5] + "-" + zipc[5:]
                city_line = "%s, %s %s" % (c[1], c[2] if len(c) > 2 else "",
                                           zipc)
            return {"name": name, "id_qual": idq, "id": idv,
                    "addr": addr, "city": city_line}
    return None


def service_lines(block):
    """Split the 2400 loops out of a claim block."""
    starts = [i for i, s in enumerate(block) if s.startswith("LX*")]
    lines = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(block) - 1
        seg = block[start:end]
        sv2 = one(seg, "SV2*")
        hcp = one(seg, "HCP*")
        svd = one(seg, "SVD*")
        dtp = one(seg, "DTP*472*")
        lines.append({
            "lx": e(sv2 and block[start] or block[start], 1),
            "rev": e(sv2, 1) if sv2 else "",
            "proc": e(sv2, 2).replace("HC:", "") if sv2 else "",
            "charge": money(e(sv2, 3)) if sv2 else "",
            "unit": e(sv2, 4) if sv2 else "",
            "units": e(sv2, 5) if sv2 else "",
            "dos": d8(e(dtp, 3)) if dtp else "",
            "hcp_method": e(hcp, 1) if hcp else "",
            "allowed": money(e(hcp, 2)) if hcp else "",
            "saving": money(e(hcp, 3)) if hcp else "",
            "pricing_org": e(hcp, 4) if hcp else "",
            "svd_paid": money(e(svd, 2)) if svd else "",
            "cas": [cas_pairs(s) for s in find(seg, "CAS*")],
            "nte": [(e(s, 1), e(s, 2)) for s in find(seg, "NTE*")],
            "segments": seg,
        })
    return lines


def cas_pairs(seg):
    """CAS group code plus its (reason, amount, quantity) triplets."""
    parts = X.elems(seg)
    group = parts[1]
    items = []
    i = 2
    while i < len(parts):
        reason, amount = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        if reason:
            items.append((reason, money(amount)))
        i += 3
    return {"group": group, "items": items}


def parse_claim(block):
    clm = one(block, "CLM*")
    clm05 = e(clm, 5).split(":")
    cl1 = one(block, "CL1*")
    hcp = one(block, "HCP*")
    k3 = [e(s, 1) for s in find(block, "K3*")]
    k3_amounts = {}
    decision = ""
    for v in k3:
        if "|" in v:
            amt, _, qual = v.partition("|")
            k3_amounts[qual] = amt
        else:
            decision = v
    hi = find(block, "HI*")
    dx_principal, dx_other = "", []
    for s in hi:
        for comp in X.elems(s)[1:]:
            bits = comp.split(":")
            if bits[0] in ("ABK", "BK"):
                dx_principal = bits[1]
            elif bits[0] in ("ABF", "BF"):
                dx_other.append(bits[1])
    lines = service_lines(block)
    return {
        "st02": e(one(block, "ST*"), 2),
        "bht03": e(one(block, "BHT*"), 3),
        "bht_created": "%s %s:%s" % (d8(e(one(block, "BHT*"), 4)),
                                     e(one(block, "BHT*"), 5)[:2],
                                     e(one(block, "BHT*"), 5)[2:]),
        "clm01": e(clm, 1),
        "total_charge": money(e(clm, 2)),
        "facility_type": clm05[0] if clm05 else "",
        "facility_qual": clm05[1] if len(clm05) > 1 else "",
        "freq": clm05[2] if len(clm05) > 2 else "",
        "provider_signature": e(clm, 6),
        "assignment": e(clm, 7),
        "benefits_assign": e(clm, 8),
        "release_info": e(clm, 9),
        "statement": rd8(e(one(block, "DTP*434*"), 3))
        if one(block, "DTP*434*") else "",
        "discharge_hour": e(one(block, "DTP*096*"), 3)
        if one(block, "DTP*096*") else "",
        "admit_type": e(cl1, 1) if cl1 else "",
        "admit_src": e(cl1, 2) if cl1 else "",
        "patient_status": e(cl1, 3) if cl1 else "",
        "ccn": e(one(block, "REF*F8*"), 2) if one(block, "REF*F8*") else "",
        "uhap": e(one(block, "REF*9A*"), 2) if one(block, "REF*9A*") else "",
        "ref_d9": e(one(block, "REF*D9*"), 2) if one(block, "REF*D9*") else "",
        "tax_id": e(one(block, "REF*EI*"), 2) if one(block, "REF*EI*") else "",
        "decision": decision,
        "net_paid": money(k3_amounts.get("PA", "")) if "PA" in k3_amounts else "",
        "not_covered": money(k3_amounts.get("NA", "")) if "NA" in k3_amounts else "",
        "coverage_pct": k3_amounts.get("CP", ""),
        "hcp_method": e(hcp, 1) if hcp else "",
        "allowed": money(e(hcp, 2)) if hcp else "",
        "saving": money(e(hcp, 3)) if hcp else "",
        "pricing_org": e(hcp, 4) if hcp else "",
        "amt_eaf": money(e(one(block, "AMT*EAF*"), 2))
        if one(block, "AMT*EAF*") else "",
        "claim_cas": [cas_pairs(s) for s in find(block, "CAS*")
                      if block.index(s) < (block.index(one(block, "LX*"))
                                           if one(block, "LX*") else len(block))],
        "claim_nte": [(e(s, 1), e(s, 2)) for s in block
                      if s.startswith("NTE*ADD*")],
        "dx_principal": dx_principal,
        "dx_other": dx_other,
        "billing": nm1(block, "85"),
        "subscriber": nm1(block, "IL"),
        "payer": nm1(block, "PR"),
        "attending": nm1(block, "71"),
        "facility": nm1(block, "77"),
        "submitter": nm1(block, "41"),
        "receiver": nm1(block, "40"),
        "sbr": one(block, "SBR*"),
        "dmg": one(block, "DMG*"),
        "lines": lines,
        "segments": block,
    }


# ------------------------------------------------------------------- rendering
CSS = """
:root { --ink:#16181d; --muted:#6b7280; --rule:#d8dce3; --soft:#f4f6f9;
        --accent:#0f4c81; --warn:#8a3b12; }
* { box-sizing: border-box; }
body { font: 10pt/1.45 "Segoe UI", Arial, sans-serif; color: var(--ink);
       margin: 0; }
h1 { font-size: 19pt; margin: 0 0 2mm; letter-spacing: -.2pt; }
h2 { font-size: 12.5pt; margin: 0 0 1mm; color: var(--accent); }
h3 { font-size: 8.5pt; margin: 5mm 0 1.5mm; text-transform: uppercase;
     letter-spacing: .8pt; color: var(--muted);
     border-bottom: 1px solid var(--rule); padding-bottom: 1mm; }
.page { page-break-after: always; padding: 0 0 4mm; }
.page:last-child { page-break-after: auto; }
.mono { font-family: Consolas, "Courier New", monospace; }
.sub { color: var(--muted); font-size: 8.5pt; }
.hdr { display:flex; justify-content:space-between; align-items:flex-end;
       border-bottom: 2px solid var(--accent); padding-bottom: 2mm;
       margin-bottom: 3mm; }
.hdr .right { text-align: right; }
.big { font-size: 15pt; font-weight: 600; }
table { width: 100%; border-collapse: collapse; font-size: 8.5pt; }
th { text-align: left; font-weight: 600; color: var(--muted);
     border-bottom: 1px solid var(--rule); padding: 1.4mm 2mm 1.4mm 0;
     font-size: 7.5pt; text-transform: uppercase; letter-spacing: .5pt; }
td { padding: 1.3mm 2mm 1.3mm 0; border-bottom: 1px solid #eceef2;
     vertical-align: top; }
td.num, th.num { text-align: right; padding-right: 3.5mm; }
td:last-child, th:last-child { padding-right: 0; }
tr.total td { font-weight: 600; border-top: 1.5px solid var(--rule);
              border-bottom: none; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 8mm; }
.grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0 6mm; }
dl { margin: 0; display: grid; grid-template-columns: 38mm 1fr; gap: .6mm 0;
     font-size: 8.7pt; }
dt { color: var(--muted); }
dd { margin: 0; }
.card { background: var(--soft); border: 1px solid var(--rule);
        border-radius: 2mm; padding: 2.5mm 3mm; }
.kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 2.5mm;
        margin: 2mm 0 1mm; }
.kpi { border: 1px solid var(--rule); border-radius: 2mm; padding: 2mm 2.5mm; }
.kpi .lab { font-size: 7pt; text-transform: uppercase; letter-spacing: .6pt;
            color: var(--muted); }
.kpi .val { font-size: 12pt; font-weight: 600; }
.tag { display: inline-block; font-size: 7.5pt; padding: .4mm 1.6mm;
       border-radius: 1mm; background: #e6edf5; color: var(--accent);
       margin-right: 1mm; }
.tag.warn { background: #fbeee4; color: var(--warn); }
.note { font-size: 8pt; color: var(--warn); }
.raw { font-family: Consolas, "Courier New", monospace; font-size: 6.6pt;
       line-height: 1.4; color: #444; white-space: pre-wrap;
       word-break: break-all; background: var(--soft);
       border: 1px solid var(--rule); border-radius: 1.5mm; padding: 2mm; }
@page { size: Letter; margin: 13mm 12mm 12mm; }
"""


def dl(rows):
    out = ["<dl>"]
    for k, v in rows:
        if v in ("", None):
            continue
        out.append("<dt>%s</dt><dd>%s</dd>" % (esc(k), v))
    out.append("</dl>")
    return "".join(out)


def party(p, title, extra=()):
    if not p:
        return ""
    rows = [("Name", "<strong>%s</strong>" % esc(p["name"]))]
    if p["id"]:
        label = {"XX": "NPI", "MI": "Member ID", "PI": "Payer ID",
                 "46": "ETIN"}.get(p["id_qual"], p["id_qual"])
        rows.append((label, '<span class="mono">%s</span>' % esc(p["id"])))
    if p["addr"]:
        rows.append(("Address", esc(", ".join(p["addr"]))))
    if p["city"]:
        rows.append(("City / ZIP", esc(p["city"])))
    rows.extend(extra)
    return '<div><h3>%s</h3>%s</div>' % (esc(title), dl(rows))


def cas_html(cas_list):
    if not cas_list:
        return '<span class="sub">none</span>'
    out = []
    for c in cas_list:
        bits = ", ".join(
            "%s %s <span class='sub'>(%s)</span>"
            % (esc(r), esc(a), esc(CAS_REASON.get(r, "reason %s" % r)))
            for r, a in c["items"])
        out.append("<div><span class='tag'>%s</span> "
                   "<span class='sub'>%s</span> &mdash; %s</div>"
                   % (esc(c["group"]), esc(CAS_GROUP.get(c["group"], "")),
                      bits))
    return "".join(out)


def claim_page(n, c, total):
    lines_html = []
    tot_charge = Decimal("0.00")
    tot_allowed = Decimal("0.00")
    tot_saving = Decimal("0.00")
    tot_paid = Decimal("0.00")
    for ln in c["lines"]:
        tot_charge += Decimal(ln["charge"] or "0")
        tot_allowed += Decimal(ln["allowed"] or "0")
        tot_saving += Decimal(ln["saving"] or "0")
        tot_paid += Decimal(ln["svd_paid"] or "0")
        nte = "".join("<div class='sub'>NTE %s: %s</div>"
                      % (esc(q), esc(v)) for q, v in ln["nte"])
        lines_html.append(
            "<tr><td class='mono'>%s</td><td class='mono'>%s</td>"
            "<td class='mono'>%s</td><td>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td>%s%s</td></tr>"
            % (esc(ln["lx"]), esc(ln["rev"]), esc(ln["proc"]), esc(ln["dos"]),
               esc(ln["units"]), esc(ln["charge"]), esc(ln["allowed"]),
               esc(ln["saving"]), esc(ln["svd_paid"]),
               cas_html(ln["cas"]), nte))

    lines_html.append(
        "<tr class='total'><td colspan='4'>Line totals</td>"
        "<td class='num'></td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num'>%s</td><td></td></tr>"
        % (money(tot_charge), money(tot_allowed), money(tot_saving),
           money(tot_paid)))

    sbr = c["sbr"]
    dmg = c["dmg"]
    subs_extra = [
        ("Relationship", "%s <span class='sub'>(%s)</span>"
         % (esc(e(sbr, 2)), esc(SBR_REL.get(e(sbr, 2), "")))) if sbr else ("", ""),
        ("Group / policy", '<span class="mono">%s</span>' % esc(e(sbr, 3)))
        if sbr else ("", ""),
        ("Payer sequence", "%s <span class='sub'>(%s)</span>"
         % (esc(e(sbr, 1)), esc(SBR_CODE.get(e(sbr, 1), "")))) if sbr else ("", ""),
        ("Date of birth", esc(d8(e(dmg, 2)))) if dmg else ("", ""),
        ("Gender", esc(e(dmg, 3))) if dmg else ("", ""),
    ]

    claim_nte = "".join(
        "<div class='note'>NTE %s (claim note): <span class='mono'>%s</span></div>"
        % (esc(q), esc(v)) for q, v in c["claim_nte"]) or \
        "<div class='sub'>none</div>"

    return """
<section class="page">
  <div class="hdr">
    <div>
      <div class="sub">Claim %d of %d &middot; 837I transaction set %s</div>
      <h1 class="mono">%s</h1>
      <div class="sub">%s &nbsp;|&nbsp; statement period %s</div>
    </div>
    <div class="right">
      <div class="sub">Total charge</div>
      <div class="big">%s USD</div>
      <div class="sub">%d service line(s)</div>
    </div>
  </div>

  <div class="kpis">
    <div class="kpi"><div class="lab">Billed</div><div class="val">%s</div></div>
    <div class="kpi"><div class="lab">Allowed (HCP02)</div><div class="val">%s</div></div>
    <div class="kpi"><div class="lab">Net paid (K3 PA)</div><div class="val">%s</div></div>
    <div class="kpi"><div class="lab">Not covered (K3 NA)</div><div class="val">%s</div></div>
    <div class="kpi"><div class="lab">Coverage %%</div><div class="val">%s</div></div>
  </div>

  <h3>Parties</h3>
  <div class="grid3">
    %s
    %s
    %s
  </div>

  <h3>Claim detail</h3>
  <div class="grid">
    %s
    %s
  </div>

  <h3>Adjudication values returned to UHCG</h3>
  <div class="grid">
    %s
    <div>
      %s
      <div style="margin-top:2mm"><span class="sub">Claim-level CAS</span>%s</div>
      <div style="margin-top:2mm"><span class="sub">Claim note</span>%s</div>
    </div>
  </div>

  <h3>Service lines (loop 2400)</h3>
  <table>
    <thead><tr>
      <th>LX</th><th>Rev</th><th>HCPCS</th><th>Service date</th>
      <th class="num">Units</th><th class="num">Billed</th>
      <th class="num">Allowed</th><th class="num">Saving</th>
      <th class="num">SVD paid</th><th>Line adjustments</th>
    </tr></thead>
    <tbody>%s</tbody>
  </table>

  <h3>Raw ST..SE segments (%d)</h3>
  <div class="raw">%s</div>
</section>
""" % (
        n, total, esc(c["st02"]), esc(c["clm01"]),
        esc(c["billing"]["name"] if c["billing"] else ""), esc(c["statement"]),
        esc(c["total_charge"]), len(c["lines"]),
        esc(c["total_charge"]), esc(c["allowed"] or "-"),
        esc(c["net_paid"] or "-"), esc(c["not_covered"] or "-"),
        esc(c["coverage_pct"] or "-"),
        party(c["billing"], "Billing provider (2010AA)",
              [("Tax ID (REF*EI)", '<span class="mono">%s</span>'
                % esc(c["tax_id"]))]),
        party(c["subscriber"], "Subscriber / patient (2010BA)",
              [r for r in subs_extra if r[0]]),
        party(c["payer"], "Payer (2010BB)", []),
        dl([
            ("Patient control no.", '<span class="mono">%s</span>'
             % esc(c["clm01"])),
            ("Claim control no. (F8)", '<span class="mono">%s</span>'
             % esc(c["ccn"])),
            ("UHAP claim ID (9A)", '<span class="mono">%s</span>'
             % esc(c["uhap"])),
            ("Reference (D9)", '<span class="mono">%s</span>' % esc(c["ref_d9"])),
            ("Transaction set (ST02)", '<span class="mono">%s</span>'
             % esc(c["st02"])),
            ("Batch control (BHT03)", '<span class="mono">%s</span> '
             '<span class="sub">%d chars</span>'
             % (esc(c["bht03"]), len(c["bht03"]))),
            ("Created", esc(c["bht_created"])),
        ]),
        dl([
            ("Type of bill", "%s%s%s <span class='sub'>(facility %s, "
             "frequency %s &ndash; %s)</span>"
             % (esc(c["facility_type"]), esc(c["facility_qual"]),
                esc(c["freq"]), esc(c["facility_type"]), esc(c["freq"]),
                esc(CLAIM_FREQ.get(c["freq"], "")))),
            ("Statement period", esc(c["statement"])),
            ("Discharge hour", esc(c["discharge_hour"])),
            ("Admission type", "%s <span class='sub'>(%s)</span>"
             % (esc(c["admit_type"]), esc(ADMIT_TYPE.get(c["admit_type"], "")))),
            ("Admission source", "%s <span class='sub'>(%s)</span>"
             % (esc(c["admit_src"]), esc(ADMIT_SRC.get(c["admit_src"], "")))),
            ("Patient status", "%s <span class='sub'>(%s)</span>"
             % (esc(c["patient_status"]),
                esc(PATIENT_STATUS.get(c["patient_status"], "")))),
            ("Principal diagnosis", '<span class="mono">%s</span> '
             '<span class="sub">ICD-10-CM, ABK</span>'
             % esc(c["dx_principal"])),
            ("Other diagnoses", '<span class="mono">%s</span> '
             '<span class="sub">ABF</span>'
             % esc(", ".join(c["dx_other"]))),
            ("Attending provider", "%s <span class='sub'>NPI %s</span>"
             % (esc(c["attending"]["name"]), esc(c["attending"]["id"]))
             if c["attending"] else ""),
            ("Service facility", "%s <span class='sub'>%s</span>"
             % (esc(c["facility"]["name"]), esc(c["facility"]["city"]))
             if c["facility"] else ""),
        ]),
        dl([
            ("Benefit decision (K3)", "%s <span class='sub'>(%s)</span>"
             % (esc(c["decision"]),
                esc(BENEFIT_DECISION.get(c["decision"], "")))),
            ("Net paid (K3 PA)", esc(c["net_paid"])),
            ("Not covered (K3 NA)", esc(c["not_covered"])),
            ("Coverage % (K3 CP)", esc(c["coverage_pct"])),
            ("Approved amount (AMT*EAF)", esc(c["amt_eaf"])),
        ]),
        dl([
            ("Pricing method (HCP01)", "%s <span class='sub'>(%s)</span>"
             % (esc(c["hcp_method"]),
                esc(HCP_METHOD.get(c["hcp_method"], "")))),
            ("Allowed (HCP02)", esc(c["allowed"])),
            ("Saving (HCP03)", esc(c["saving"])),
            ("Pricing org (HCP04)", '<span class="mono">%s</span>'
             % esc(c["pricing_org"])),
        ]),
        cas_html(c["claim_cas"]),
        claim_nte,
        "".join(lines_html),
        len(c["segments"]),
        esc("~\n".join(c["segments"]) + "~"),
    )


def cover_page(path, segs, claims):
    isa, gs = segs[0], segs[1]
    rows = []
    t_billed = t_allowed = t_paid = t_nc = Decimal("0.00")
    for i, c in enumerate(claims, 1):
        t_billed += Decimal(c["total_charge"] or "0")
        t_allowed += Decimal(c["allowed"] or "0")
        t_paid += Decimal(c["net_paid"] or "0")
        t_nc += Decimal(c["not_covered"] or "0")
        rows.append(
            "<tr><td>%d</td><td class='mono'>%s</td><td class='mono'>%s</td>"
            "<td class='mono'>%s</td><td class='num'>%d</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td>%s</td></tr>"
            % (i, esc(c["clm01"]), esc(c["ccn"]), esc(c["bht03"]),
               len(c["lines"]), esc(c["total_charge"]), esc(c["allowed"]),
               esc(c["net_paid"]), esc(c["not_covered"]),
               esc(c["coverage_pct"]),
               esc(BENEFIT_DECISION.get(c["decision"], c["decision"]))))
    rows.append(
        "<tr class='total'><td colspan='4'>Interchange totals</td>"
        "<td class='num'>%d</td><td class='num'>%s</td><td class='num'>%s</td>"
        "<td class='num'>%s</td><td class='num'>%s</td><td colspan='2'></td></tr>"
        % (sum(len(c["lines"]) for c in claims), money(t_billed),
           money(t_allowed), money(t_paid), money(t_nc)))

    return """
<section class="page">
  <div class="hdr">
    <div>
      <div class="sub">UMR / UHCG 837I outbound test file &mdash; batch2</div>
      <h1>Claim detail report</h1>
      <div class="sub mono">%s</div>
    </div>
    <div class="right">
      <div class="sub">Claims</div>
      <div class="big">%d</div>
      <div class="sub">%d service lines</div>
    </div>
  </div>

  <h3>Interchange envelope</h3>
  <div class="grid">
    %s
    %s
  </div>

  <h3>Claims in this interchange</h3>
  <table>
    <thead><tr>
      <th>#</th><th>Patient control no.</th><th>Claim control no. (F8)</th>
      <th>BHT03</th><th class="num">Lines</th><th class="num">Billed</th>
      <th class="num">Allowed</th><th class="num">Net paid</th>
      <th class="num">Not covered</th><th class="num">Cov %%</th>
      <th>Benefit decision</th>
    </tr></thead>
    <tbody>%s</tbody>
  </table>

  <h3>How to read this report</h3>
  <div class="card sub">
    <p style="margin:0 0 1.5mm">Every value on the following pages is parsed
    straight out of the X12 file named above; nothing is recomputed. Code
    meanings come from the UMR/UHCG 837I Companion Guide and the Special
    Instructions (NTE) guide in <span class="mono">UMR_UHCG_837_EDI_Reference</span>.</p>
    <p style="margin:0 0 1.5mm"><strong>K3</strong> segments are UHCG custom:
    benefit decision (1 covered, 2 not covered, 3 duplicate, 4 medical record
    request), then <span class="mono">amount|PA</span> net paid,
    <span class="mono">amount|NA</span> not covered,
    <span class="mono">percent|CP</span> coverage percentage.</p>
    <p style="margin:0 0 1.5mm"><strong>HCP</strong> carries repricing:
    HCP01 method, HCP02 allowed amount, HCP03 saving, HCP04 pricing
    organisation. <strong>SVD</strong> is the line paid amount and
    <strong>CAS</strong> the adjustment breakdown.</p>
    <p style="margin:0"><strong>NTE*ADD</strong> is the claim-level special
    instruction; <strong>NTE*TPO</strong> is the line-level reduction note
    UHCG expects wherever a not-covered amount is greater than zero.</p>
  </div>
</section>
""" % (
        esc(os.path.basename(path)), len(claims),
        sum(len(c["lines"]) for c in claims),
        dl([
            ("Sender (ISA06)", '<span class="mono">%s</span>'
             % esc(e(isa, 6).strip())),
            ("Receiver (ISA08)", '<span class="mono">%s</span>'
             % esc(e(isa, 8).strip())),
            ("Interchange control (ISA13)", '<span class="mono">%s</span>'
             % esc(e(isa, 13))),
            ("Interchange date/time", "%s %s:%s"
             % (esc(d8("20" + e(isa, 9))), esc(e(isa, 10)[:2]),
                esc(e(isa, 10)[2:]))),
            ("Usage indicator (ISA15)", "%s <span class='sub'>(%s)</span>"
             % (esc(e(isa, 15)),
                "test" if e(isa, 15) == "T" else "production")),
        ]),
        dl([
            ("Functional group (GS06)", '<span class="mono">%s</span>'
             % esc(e(gs, 6))),
            ("Group date/time", "%s %s:%s"
             % (esc(d8(e(gs, 4))), esc(e(gs, 5)[:2]), esc(e(gs, 5)[2:]))),
            ("Version (GS08)", '<span class="mono">%s</span>' % esc(e(gs, 8))),
            ("Transaction sets", "%s" % len(claims)),
            ("Segments in file", "%s" % len(segs)),
        ]),
        "".join(rows),
    )


def build_html(path):
    _raw, segs = X.read_segments(path)
    blocks = [segs[st:se + 1] for st, se in X.transaction_sets(segs)]
    claims = [parse_claim(b) for b in blocks]
    pages = [cover_page(path, segs, claims)]
    for i, c in enumerate(claims, 1):
        pages.append(claim_page(i, c, len(claims)))
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>batch2 claim detail</title><style>%s</style></head>"
            "<body>%s</body></html>" % (CSS, "".join(pages)))


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    for pat in (r"C:\Program Files*\**\chrome.exe",):
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()

    html_path = os.path.splitext(args.out)[0] + ".html"
    doc = build_html(args.file)
    io.open(html_path, "w", encoding="utf-8", newline="").write(doc)
    print("wrote %s (%d bytes)" % (html_path, len(doc)))
    if args.html_only:
        return 0

    chrome = find_chrome()
    if not chrome:
        sys.stderr.write("no Chrome/Edge found; rerun with --html-only\n")
        return 1
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer",
           "--print-to-pdf=%s" % os.path.abspath(args.out),
           "file:///%s" % os.path.abspath(html_path).replace("\\", "/")]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=180)
    if proc.returncode != 0 or not os.path.exists(args.out):
        sys.stderr.write(proc.stdout.decode("utf-8", "replace"))
        return 1
    print("wrote %s (%d bytes)" % (args.out, os.path.getsize(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
