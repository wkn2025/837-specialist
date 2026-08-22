"""Guide-derived validation rules for returned 837P (Professional) EDI2.

These deterministic checks have synthetic fixture coverage, but no
human-reviewed returned Professional file is available as a golden fixture.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation

from findings import ADVISORY, BLOCKER, Finding
from rules import rule
import rules_837i
import rules_common


VERSION_837P = "005010X222A1"
CG = "UHCG_837P_Companion_Guide_FULL.csv"
VR = "UHCG_Validation_Rules_Professional.csv"
VR_REDUCTIONS = "UHCG_Validation_Professional_With_Reduction_Scenarios.csv"
OVR = "UHCG_Overview_Reference.md"
P_RULES = []
ZERO = Decimal("0")

PROFESSIONAL_VALIDATION_NOTE = (
    "Professional validation is guide-derived with deterministic synthetic "
    "fixtures; no human-reviewed returned Professional EDI2 golden fixture "
    "has been provided yet."
)


def p_rule(rule_id, severity, citation):
    return rule(rule_id, severity, citation, registry=P_RULES, workflow="P")


def registry():
    """Return proven common checks followed by isolated Professional checks."""
    common = [item for item in rules_common.registry(rules_837i.registry())
              if item.id != "FMT-BHT03-LEN"]
    overview_rules = {
        "ENV-CLAIM-LIMIT", "ENV-FILENAME", "STR-EMPTY-SEGMENT",
        "FMT-MONEY-FORM", "FMT-MONEY-NEGATIVE",
        "ADJ-CLM20-FILE-PREFIX",
    }
    nte_rules = {"FMT-NTE-DELIMITER", "FMT-NTE-LENGTH", "NTE-NO-ECHO"}
    validation_rules = {"FMT-COVERAGE-PCT"}

    def source_for(rule_id):
        if rule_id in overview_rules:
            return OVR
        if rule_id in nte_rules:
            return rules_837i.NTEG
        if rule_id in validation_rules:
            return VR
        return CG

    cited_for_p = [replace(
        item,
        citation="%s; shared deterministic check (%s)"
                 % (source_for(item.id), item.id),
    ) for item in common]
    return cited_for_p + list(P_RULES)


def _decimal(value):
    try:
        parsed = Decimal(value) if value not in (None, "") else None
        return parsed if parsed is None or parsed.is_finite() else None
    except InvalidOperation:
        return None


def _sum(values):
    return sum((value if value is not None else ZERO for value in values), ZERO)


def _k3(segments):
    result = {"decision": None, "pa": None, "na": None, "cp": None,
              "reductions": [], "decision_segment": None}
    for seg in segments:
        if seg.sid != "K3":
            continue
        value = seg.el(1)
        if "|" in value:
            amount, _, tag = value.partition("|")
            key = tag.lower()
            if key in ("pa", "na", "cp"):
                result[key] = amount
        elif value in ("1", "2", "3", "4") and result["decision"] is None:
            result["decision"] = value
            result["decision_segment"] = seg
        elif value:
            result["reductions"].append(value)
    return result


def _cas(segments):
    result = {}
    for seg in segments:
        if seg.sid != "CAS":
            continue
        group = seg.el(1)
        for index in range(2, len(seg.elems), 3):
            reason, amount = seg.el(index), seg.el(index + 1)
            parsed = _decimal(amount)
            if reason and parsed is not None:
                key = (group, reason)
                result[key] = result.get(key, ZERO) + parsed
    return result


def _amt(claim, qualifier="EAF"):
    for seg in claim.loop_segs("2320"):
        if seg.sid == "AMT" and seg.el(1) == qualifier:
            return _decimal(seg.el(2))
    return None


def _has_ref(claim, qualifier):
    return any(seg.el(1) == qualifier and seg.el(2)
               for seg in claim.loop_segs("2300", "REF"))


def _frequency(claim):
    clm = claim.seg("CLM")
    parts = clm.el(5).split(":") if clm is not None else []
    return parts[2] if len(parts) > 2 else ""


def _line_amounts(line):
    cas = _cas(line.segments)
    hcp, svd, sv1 = line.seg("HCP"), line.seg("SVD"), line.seg("SV1")
    return {
        "billed": _decimal(sv1.el(2)) if sv1 is not None else None,
        "allowed": _decimal(hcp.el(2)) if hcp is not None else None,
        "deductible": cas.get(("PR", "1")),
        "coinsurance": cas.get(("PR", "2")),
        "copay": cas.get(("PR", "3")),
        "not_covered": cas.get(("PR", "96")),
        "net_paid": _decimal(svd.el(2)) if svd is not None else None,
        "co45": cas.get(("CO", "45")),
        "coverage": cas.get(("OA", "23")),
    }


def _line_anchor(line):
    return line.seg("K3") or line.seg("SVD") or line.seg("LX")


@p_rule("P-ENV-VERSION", BLOCKER,
        "%s, GS08/ST03: 005010X222A1 for Professional" % CG)
def p_env_version(ctx):
    gs = ctx.edi.seg("GS")
    if gs is None or gs.el(8) != VERSION_837P:
        yield Finding("P-ENV-VERSION", "",
                      "GS08 is %r, expected %s"
                      % (gs.el(8) if gs is not None else "", VERSION_837P),
                      segment_index=gs.index if gs is not None else None)
    for claim in ctx.edi.claims:
        if claim.st.el(3) != VERSION_837P:
            yield Finding("P-ENV-VERSION", "",
                          "ST03 is %r, expected %s"
                          % (claim.st.el(3), VERSION_837P),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@p_rule("P-FMT-MONEY", BLOCKER,
        "%s: Professional SV102 is an unsigned monetary amount" % CG)
def p_fmt_money(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            sv1 = line.seg("SV1")
            value = sv1.el(2) if sv1 is not None else ""
            valid_form = bool(rules_837i.MONEY_RE.match(value))
            leading_zero = value.startswith("0") and not value.startswith("0.")
            if value and (not valid_form or leading_zero or
                          _decimal(value) is None):
                yield Finding("P-FMT-MONEY", "",
                              "line %d SV102 is not a valid unsigned amount: %r"
                              % (line.lx, value), claim=claim.uhap_id,
                              lx=line.lx, segment_index=sv1.index)


@p_rule("P-FMT-BHT03-LEN", BLOCKER,
        "%s, BHT03: AN 1-50" % CG)
def p_fmt_bht03_len(ctx):
    for claim in ctx.edi.claims:
        bht = claim.seg("BHT")
        value = bht.el(3) if bht is not None else ""
        if not 1 <= len(value) <= 50:
            yield Finding("P-FMT-BHT03-LEN", "",
                          "BHT03 length is %d, expected 1 through 50"
                          % len(value), claim=claim.uhap_id,
                          segment_index=bht.index if bht is not None
                          else claim.st.index)


@p_rule("P-REQ-LINE-SV1", BLOCKER,
        "%s, Loop 2400 SV1: Professional service is required" % CG)
def p_req_line_sv1(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            sv1 = line.seg("SV1")
            if sv1 is None or not sv1.el(1) or not sv1.el(2) or not sv1.el(4):
                yield Finding("P-REQ-LINE-SV1", "",
                              "line %d requires SV101 procedure, SV102 billed "
                              "amount, and SV104 units" % line.lx,
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("LX").index)


@p_rule("P-REQ-CLAIM-BENEFIT-DECISION", BLOCKER,
        "%s, Loop 2300 K3 (2): claim benefit decision is required inbound" % CG)
def p_req_claim_decision(ctx):
    for claim in ctx.edi.claims:
        if _k3(claim.segments)["decision"] is None:
            yield Finding("P-REQ-CLAIM-BENEFIT-DECISION", "",
                          "claim-level benefit decision K3 is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@p_rule("P-REQ-LINE-BENEFIT-DECISION", BLOCKER,
        "%s, Loop 2400 K3: Professional line benefit decision is required inbound" % CG)
def p_req_line_decision(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            if _k3(line.segments)["decision"] is None:
                yield Finding("P-REQ-LINE-BENEFIT-DECISION", "",
                              "line %d benefit decision K3 is missing" % line.lx,
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("LX").index)


@p_rule("P-CLAIM-BENEFIT-DECISION-VALUE", BLOCKER,
        "%s, Loop 2300 K3: claim values 1, 2, 3, or 4" % CG)
def p_claim_decision_value(ctx):
    for claim in ctx.edi.claims:
        for seg in claim.segs("K3"):
            value = seg.el(1)
            if "|" not in value and value.isdigit() and value not in ("1", "2", "3", "4"):
                yield Finding("P-CLAIM-BENEFIT-DECISION-VALUE", "",
                              "claim benefit decision %r is not 1, 2, 3, or 4" % value,
                              claim=claim.uhap_id, segment_index=seg.index)


@p_rule("P-LINE-BENEFIT-DECISION-VALUE", BLOCKER,
        "%s, Loop 2400 K3: line values 1 Covered, 2 Not Covered, 3 Duplicate" % CG)
def p_line_decision_value(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            for seg in line.segs("K3"):
                if "|" not in seg.el(1) and seg.el(1) not in ("1", "2", "3"):
                    yield Finding("P-LINE-BENEFIT-DECISION-VALUE", "",
                                  "line %d benefit decision %r is not 1, 2, or 3"
                                  % (line.lx, seg.el(1)), claim=claim.uhap_id,
                                  lx=line.lx, segment_index=seg.index)


@p_rule("P-REQ-CLAIM-ADJUDICATION", BLOCKER,
        "%s, Loops 2300/2320: PA, NA, CP, HCP, CAS and AMT*EAF are required inbound" % CG)
def p_req_claim_adjudication(ctx):
    for claim in ctx.edi.claims:
        k3 = _k3(claim.segments)
        other_payer = claim.loop_segs("2320")
        cas = _cas(other_payer)
        missing = [tag.upper() for tag in ("pa", "na", "cp") if k3[tag] is None]
        if claim.seg("HCP") is None:
            missing.append("HCP")
        if not claim.loop_segs("2320", "SBR"):
            missing.append("SBR")
        for key in (("PR", "1"), ("PR", "2"), ("PR", "3")):
            if key not in cas:
                missing.append("CAS*%s*%s" % key)
        if _amt(claim) is None:
            missing.append("AMT*EAF")
        if missing:
            yield Finding("P-REQ-CLAIM-ADJUDICATION", "",
                          "claim adjudication is missing " + ", ".join(missing),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@p_rule("P-REQ-LINE-ADJUDICATION", BLOCKER,
        "%s, Loop 2430: SVD and PR/CO/OA CAS combinations are required inbound" % CG)
def p_req_line_adjudication(ctx):
    expected = (("PR", "1"), ("PR", "2"), ("PR", "3"), ("PR", "96"),
                ("CO", "45"), ("OA", "23"))
    for claim in ctx.edi.claims:
        for line in claim.lines:
            cas, missing = _cas(line.segments), []
            if line.seg("SVD") is None:
                missing.append("SVD")
            missing.extend("CAS*%s*%s" % key for key in expected if key not in cas)
            if missing:
                yield Finding("P-REQ-LINE-ADJUDICATION", "",
                              "line %d adjudication is missing %s"
                              % (line.lx, ", ".join(missing)),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("LX").index)


@p_rule("P-SVD-SERVICE-PARITY", BLOCKER,
        "%s, SVD03 copies SV101, SVD04 is not used, and SVD05 copies SV104" % CG)
def p_svd_service_parity(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            sv1, svd = line.seg("SV1"), line.seg("SVD")
            if sv1 is None or svd is None:
                continue
            problems = []
            if svd.el(3) != sv1.el(1):
                problems.append("SVD03 %r does not match SV101 %r"
                                % (svd.el(3), sv1.el(1)))
            if svd.el(4):
                problems.append("SVD04 is %r but Professional marks it not used"
                                % svd.el(4))
            if svd.el(5) != sv1.el(4):
                problems.append("SVD05 %r does not match SV104 %r"
                                % (svd.el(5), sv1.el(4)))
            if problems:
                yield Finding("P-SVD-SERVICE-PARITY", "", "; ".join(problems),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=svd.index)


@p_rule("P-MATH-LINE", BLOCKER,
        "%s: SVD02 equals CO*45 and allowed equals payment plus patient amounts" % VR)
def p_math_line(ctx):
    for claim in ctx.edi.claims:
        reductions = {value.lower() for value in _k3(claim.segments)["reductions"]}
        if "r&c" in reductions:
            continue
        for line in claim.lines:
            values = _line_amounts(line)
            decision = _k3(line.segments)["decision"]
            problems = []
            if values["net_paid"] is not None and values["co45"] is not None \
                    and values["net_paid"] != values["co45"]:
                problems.append("SVD02 net paid %s does not equal CAS*CO*45 %s"
                                % (values["net_paid"], values["co45"]))
            components = [values[key] for key in
                          ("net_paid", "deductible", "coinsurance", "copay",
                           "not_covered")]
            ordinary_covered = decision == "1" and not reductions.intersection(
                {"ices", "duplicate", "r&c"})
            if ordinary_covered and values["allowed"] is not None \
                    and all(v is not None for v in components):
                expected = _sum(components)
                if values["allowed"] != expected:
                    problems.append("allowed %s does not reconcile to %s"
                                    % (values["allowed"], expected))
            if problems:
                yield Finding("P-MATH-LINE", "", "; ".join(problems),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=_line_anchor(line).index)


@p_rule("P-MATH-CLAIM", BLOCKER,
        "%s: claim PA/NA/PR totals equal the Professional line totals" % VR)
def p_math_claim(ctx):
    for claim in ctx.edi.claims:
        if not claim.lines:
            continue
        k3 = _k3(claim.segments)
        if "r&c" in {value.lower() for value in k3["reductions"]}:
            continue
        claim_cas = _cas(claim.loop_segs("2320"))
        lines = [_line_amounts(line) for line in claim.lines]
        comparisons = [
            ("net paid", _decimal(k3["pa"]), _sum(x["net_paid"] for x in lines)),
            ("not covered", _decimal(k3["na"]), _sum(x["not_covered"] for x in lines)),
            ("deductible", claim_cas.get(("PR", "1")),
             _sum(x["deductible"] for x in lines)),
            ("coinsurance", claim_cas.get(("PR", "2")),
             _sum(x["coinsurance"] for x in lines)),
            ("copay", claim_cas.get(("PR", "3")), _sum(x["copay"] for x in lines)),
        ]
        problems = ["claim %s %s does not equal line total %s" % (label, actual, expected)
                    for label, actual, expected in comparisons
                    if actual is not None and actual != expected]
        patient = _amt(claim)
        not_covered = claim_cas.get(("PR", "96"))
        if not_covered is None:
            not_covered = _decimal(k3["na"])
        expected_patient = _sum([
            claim_cas.get(("PR", "1")), claim_cas.get(("PR", "2")),
            claim_cas.get(("PR", "3")), not_covered])
        if patient is not None and patient != expected_patient:
            problems.append("AMT*EAF %s does not equal patient amounts %s"
                            % (patient, expected_patient))
        if problems:
            yield Finding("P-MATH-CLAIM", "", "; ".join(problems),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@p_rule("P-SCEN-LINE-DECISION", BLOCKER,
        "%s: Not Covered and Duplicate Professional line amount semantics" % VR)
def p_scen_line_decision(ctx):
    for claim in ctx.edi.claims:
        reductions = {value.lower()
                      for value in _k3(claim.segments)["reductions"]}
        if "r&c" in reductions:
            continue
        for line in claim.lines:
            decision = _k3(line.segments)["decision"]
            if decision not in ("2", "3"):
                continue
            amounts = _line_amounts(line)
            zero_keys = ["coverage", "deductible", "coinsurance", "copay", "net_paid"]
            if decision == "3":
                zero_keys.append("not_covered")
            nonzero = [key for key in zero_keys
                       if amounts[key] is not None and amounts[key] != ZERO]
            expected_not_covered = (amounts["allowed"] if "cob" in reductions
                                    else amounts["billed"])
            if decision == "2" and expected_not_covered is not None \
                    and amounts["not_covered"] != expected_not_covered:
                basis = "allowed" if "cob" in reductions else "billed"
                nonzero.append("not_covered (expected %s %s)"
                               % (basis, expected_not_covered))
            if nonzero:
                label = "Not Covered" if decision == "2" else "Duplicate"
                yield Finding("P-SCEN-LINE-DECISION", "",
                              "line %d decision %s requires zero %s"
                              % (line.lx, label, ", ".join(nonzero)),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=_line_anchor(line).index)


@p_rule("P-SCEN-CLAIM-DECISION", BLOCKER,
        "%s: all-line Not Covered and Duplicate decisions agree at claim and line" % VR)
def p_scen_claim_decision(ctx):
    for claim in ctx.edi.claims:
        k3 = _k3(claim.segments)
        if k3["reductions"] or k3["decision"] not in ("2", "3"):
            continue
        expected = k3["decision"]
        mismatches = [line.lx for line in claim.lines
                      if _k3(line.segments)["decision"] not in (None, expected)]
        claim_cas = _cas(claim.loop_segs("2320"))
        zero_values = [
            ("coverage", _decimal(k3["cp"])),
            ("net paid", _decimal(k3["pa"])),
            ("deductible", claim_cas.get(("PR", "1"))),
            ("coinsurance", claim_cas.get(("PR", "2"))),
            ("copay", claim_cas.get(("PR", "3"))),
        ]
        if expected == "3":
            zero_values.extend([
                ("not covered", _decimal(k3["na"])),
                ("patient responsibility", _amt(claim)),
            ])
        nonzero = ["%s is %s" % (label, value) for label, value in zero_values
                   if value is not None and value != ZERO]
        if mismatches or nonzero:
            details = []
            if mismatches:
                details.append("conflicts with line decisions on %s"
                               % ", ".join(map(str, mismatches)))
            if nonzero:
                details.append("requires zero " + "; ".join(nonzero))
            yield Finding("P-SCEN-CLAIM-DECISION", "",
                          "claim decision %s %s" % (expected, "; ".join(details)),
                          claim=claim.uhap_id,
                          segment_index=k3["decision_segment"].index)


@p_rule("P-NTE-LINE-REMARK-REQUIRED", BLOCKER,
        "%s: a remark is required on every line with Not Covered greater than zero" % VR)
def p_nte_line_remark(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            not_covered = _line_amounts(line)["not_covered"]
            has_remark = any(seg.el(1) == "TPO" and seg.el(2)
                             for seg in line.segs("NTE"))
            if not_covered is not None and not_covered > ZERO and not has_remark:
                yield Finding("P-NTE-LINE-REMARK-REQUIRED", "",
                              "line %d has not covered %s but no NTE*TPO remark"
                              % (line.lx, not_covered),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=_line_anchor(line).index)


@p_rule("P-SCEN-ICES-COVERED", BLOCKER,
        "%s: Professional iCES rows use line decision Covered (1), coverage 100, "
        "and zero adjudication amounts" % VR_REDUCTIONS)
def p_scen_ices(ctx):
    for claim in ctx.edi.claims:
        reductions = {value.lower() for value in _k3(claim.segments)["reductions"]}
        if "ices" not in reductions:
            continue
        for line in claim.lines:
            decision = _k3(line.segments)["decision"]
            amounts = _line_amounts(line)
            problems = []
            if decision != "1":
                problems.append("benefit decision is %r, expected Covered (1)" % decision)
            if amounts["coverage"] is not None and amounts["coverage"] != Decimal("100"):
                problems.append("coverage is %s, expected 100" % amounts["coverage"])
            for key in ("deductible", "coinsurance", "copay", "not_covered", "net_paid"):
                if amounts[key] is not None and amounts[key] != ZERO:
                    problems.append("%s is %s, expected zero" % (key, amounts[key]))
            if problems:
                yield Finding("P-SCEN-ICES-COVERED", "", "; ".join(problems),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=_line_anchor(line).index)


@p_rule("P-SCEN-DUPLICATE-REDUCTION", BLOCKER,
        "%s: a Professional Duplicate reduction row uses line decision "
        "Duplicate (3)" % VR_REDUCTIONS)
def p_scen_duplicate_reduction(ctx):
    for claim in ctx.edi.claims:
        reductions = {value.lower() for value in _k3(claim.segments)["reductions"]}
        if "duplicate" not in reductions:
            continue
        for line in claim.lines:
            decision = _k3(line.segments)["decision"]
            if decision != "3":
                yield Finding("P-SCEN-DUPLICATE-REDUCTION", "",
                              "line %d carries Duplicate reduction but benefit "
                              "decision is %r, expected Duplicate (3)"
                              % (line.lx, decision), claim=claim.uhap_id,
                              lx=line.lx, segment_index=_line_anchor(line).index)


@p_rule("P-COR-REFERENCE", ADVISORY,
        "%s: Professional frequency/resubmission designates corrected claims; "
        "%s REF*9F identifies voided and replacement claims" % (OVR, CG))
def p_cor_reference(ctx):
    for claim in ctx.edi.claims:
        frequency, has_9f = _frequency(claim), _has_ref(claim, "9F")
        if frequency not in ("", "1") and not has_9f:
            clm = claim.seg("CLM")
            yield Finding("P-COR-REFERENCE", "",
                          "Professional frequency %s is non-original but REF*9F "
                          "does not identify the original UHAP claim" % frequency,
                          claim=claim.uhap_id,
                          segment_index=clm.index if clm is not None else claim.st.index)
        elif has_9f and frequency in ("", "1"):
            ref = next(seg for seg in claim.segs("REF") if seg.el(1) == "9F")
            yield Finding("P-COR-REFERENCE", "",
                          "REF*9F is present with Professional original/default "
                          "frequency %s; confirm corrected-claim intent"
                          % (frequency or "blank"), claim=claim.uhap_id,
                          segment_index=ref.index)


@p_rule("P-ADV-RC-REDUCTION", ADVISORY,
        "%s has R&C rows, while %s names COB, iCES, and Duplicate as supported "
        "reduction types" % (VR_REDUCTIONS, OVR))
def p_adv_rc_reduction(ctx):
    for claim in ctx.edi.claims:
        if any(value.upper() == "R&C" for value in _k3(claim.segments)["reductions"]):
            yield Finding("P-ADV-RC-REDUCTION", "",
                          "R&C reduction is present; validation remains advisory "
                          "because repository sources conflict on supported reductions",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@p_rule("P-ADV-MRR-AMOUNTS", ADVISORY,
        "%s supports claim decision 4, but %s has no MRR amount scenario" % (CG, VR))
def p_adv_mrr(ctx):
    for claim in ctx.edi.claims:
        k3 = _k3(claim.segments)
        if k3["decision"] == "4":
            yield Finding("P-ADV-MRR-AMOUNTS", "",
                          "claim decision 4 is present; amount semantics are "
                          "advisory because no Professional MRR scenario row exists",
                          claim=claim.uhap_id,
                          segment_index=k3["decision_segment"].index)
