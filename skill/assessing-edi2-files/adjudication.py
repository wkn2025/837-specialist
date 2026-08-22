"""Normalize transmitted EDI2 adjudication without changing X12 semantics."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


BENEFIT_DECISIONS = {
    "1": "Covered",
    "2": "Not Covered",
    "3": "Duplicate",
    "4": "Medical Record Request",
}


def observed(value, trace_ids=(), presence=None, derivation=None):
    row = {
        "value": value,
        "presence": presence or ("present" if value is not None else "missing"),
        "traceIds": list(trace_ids),
    }
    if derivation:
        row["derivation"] = derivation
    return row


class TraceIndex:
    def __init__(self):
        self.rows = {}

    def add(self, seg, element=None, loop_id=None):
        suffix = "e%d" % element if element is not None else ""
        trace_id = "s%d%s" % (seg.index, suffix)
        if element is None:
            start, end = seg.start, seg.end
            element_path = None
        else:
            start, end = seg.element_span(element)
            element_path = "%s%02d" % (seg.sid, element)
        self.rows[trace_id] = {
            "id": trace_id,
            "segmentIndex": seg.index,
            "transactionIndex": seg.transaction_index,
            "claimIndex": seg.claim_index,
            "lineNumber": seg.line_number,
            "loopId": loop_id,
            "segmentId": seg.sid,
            "elementPath": element_path,
            "rawSegment": seg.text,
            "charStart": start,
            "charEnd": end,
        }
        return trace_id


def _from_element(seg, element, traces, loop_id=None):
    if seg is None or not seg.el(element):
        return observed(None)
    return observed(seg.el(element),
                    [traces.add(seg, element, loop_id=loop_id)])


def _ref_rows(segments, traces, loop_id):
    rows = []
    for seg in segments:
        if seg.sid != "REF":
            continue
        rows.append({
            "qualifier": seg.el(1),
            "value": seg.el(2),
            "traceIds": [traces.add(seg, loop_id=loop_id)],
        })
    return rows


def _named_ref(rows, qualifier):
    for row in rows:
        if row["qualifier"] == qualifier and row["value"]:
            return observed(row["value"], row["traceIds"])
    return observed(None)


def _cas_rows(segments, traces, loop_id):
    rows = []
    for seg in segments:
        if seg.sid != "CAS":
            continue
        for element in range(2, len(seg.elems), 3):
            reason = seg.el(element)
            amount = seg.el(element + 1)
            quantity = seg.el(element + 2)
            if not reason:
                continue
            trace_ids = [traces.add(seg, element, loop_id)]
            if amount:
                trace_ids.append(traces.add(seg, element + 1, loop_id))
            rows.append({
                "groupCode": seg.el(1),
                "reasonCode": reason,
                "amount": amount or None,
                "quantity": quantity or None,
                "repetition": ((element - 2) // 3) + 1,
                "traceIds": trace_ids,
            })
    return rows


def _cas_value(rows, group, reason):
    matches = [row for row in rows
               if row["groupCode"] == group and row["reasonCode"] == reason
               and row["amount"] is not None]
    if not matches:
        return observed(None)
    if len(matches) == 1:
        return observed(matches[0]["amount"], matches[0]["traceIds"])
    try:
        value = sum((Decimal(row["amount"]) for row in matches), Decimal("0"))
    except InvalidOperation:
        return observed(None, [trace for row in matches for trace in row["traceIds"]])
    return observed(format(value, "f"),
                    [trace for row in matches for trace in row["traceIds"]],
                    presence="derived",
                    derivation="sum of repeated CAS %s/%s amounts" % (group, reason))


def _amt_rows(segments, traces, loop_id):
    return [{
        "qualifier": seg.el(1),
        "amount": seg.el(2) or None,
        "traceIds": [traces.add(seg, loop_id=loop_id)],
    } for seg in segments if seg.sid == "AMT"]


def _named_amt(rows, qualifier):
    for row in rows:
        if row["qualifier"] == qualifier and row["amount"] is not None:
            return observed(row["amount"], row["traceIds"])
    return observed(None)


def _notes(segments, traces, loop_id):
    rows = []
    for seg in segments:
        if seg.sid != "NTE":
            continue
        text = seg.el(2)
        remark = None
        if seg.el(1) == "TPO" and text.startswith("Y|"):
            remark = text[2:] or None
        elif seg.el(1) == "ADD" and text and " " not in text:
            remark = text
        rows.append({
            "qualifier": seg.el(1),
            "text": text,
            "remarkCode": remark,
            "traceIds": [traces.add(seg, loop_id=loop_id)],
        })
    return rows


def _k3_values(segments, traces, loop_id):
    decision = observed(None)
    tagged = {}
    reductions = []
    for seg in segments:
        if seg.sid != "K3":
            continue
        raw = seg.el(1)
        trace_id = traces.add(seg, 1, loop_id)
        if "|" in raw:
            value, _, tag = raw.partition("|")
            tagged[tag.upper()] = observed(value, [trace_id])
        elif raw in BENEFIT_DECISIONS and decision["value"] is None:
            decision = observed({"code": raw, "label": BENEFIT_DECISIONS[raw]},
                                [trace_id])
        elif raw:
            reductions.append({"value": raw, "traceIds": [trace_id]})
    return decision, tagged, reductions


def _money_from_hcp(hcp, traces, loop_id):
    return {
        "allowed": _from_element(hcp, 2, traces, loop_id),
        "repricedSavings": _from_element(hcp, 3, traces, loop_id),
    }


def _safe_decimal(value):
    try:
        return Decimal(value) if value is not None else None
    except InvalidOperation:
        return None


def _financial_outcome(amounts, trace_ids):
    net = _safe_decimal(amounts["netPaid"]["value"])
    not_covered = _safe_decimal(amounts["notCovered"]["value"])
    if not_covered is not None and not_covered > 0 and net == 0:
        value = "not-covered"
    elif not_covered is not None and not_covered > 0 and net is not None and net > 0:
        value = "partially-covered"
    elif net is not None and net > 0:
        value = "covered"
    else:
        value = "undetermined"
    return observed(value, trace_ids, presence="derived",
                    derivation="derived from transmitted net paid and not covered amounts")


def _service(line, workflow, traces):
    if workflow == "P":
        seg = line.seg("SV1")
        if seg is None:
            return {"kind": "professional", "procedure": observed(None),
                    "revenueCode": observed(None), "units": observed(None)}
        return {
            "kind": "professional",
            "procedure": _from_element(seg, 1, traces, "2400"),
            "revenueCode": observed(None, presence="not-applicable"),
            "units": _from_element(seg, 4, traces, "2400"),
            "placeOfService": _from_element(seg, 5, traces, "2400"),
        }
    seg = line.seg("SV2")
    if seg is None:
        return {"kind": "institutional", "procedure": observed(None),
                "revenueCode": observed(None), "units": observed(None)}
    return {
        "kind": "institutional",
        "procedure": _from_element(seg, 2, traces, "2400"),
        "revenueCode": _from_element(seg, 1, traces, "2400"),
        "units": _from_element(seg, 5, traces, "2400"),
        "placeOfService": observed(None, presence="not-applicable"),
    }


def _line(line, workflow, traces):
    loop_id = "2400"
    segments = line.segments
    cas = _cas_rows(segments, traces, "2430")
    amts = _amt_rows(segments, traces, "2430")
    decision, tagged, reductions = _k3_values(segments, traces, loop_id)
    hcp = line.seg("HCP")
    svd = line.seg("SVD")
    sv = line.seg("SV1") if workflow == "P" else line.seg("SV2")
    billed_element = 2 if workflow == "P" else 3
    amounts = {
        "billed": _from_element(sv, billed_element, traces, loop_id),
        **_money_from_hcp(hcp, traces, loop_id),
        "deductible": _cas_value(cas, "PR", "1"),
        "coinsurance": _cas_value(cas, "PR", "2"),
        "copay": _cas_value(cas, "PR", "3"),
        "notCovered": _cas_value(cas, "PR", "96"),
        "netPaid": _from_element(svd, 2, traces, "2430"),
        "coveragePercentage": _cas_value(cas, "OA", "23"),
    }
    amount_traces = (amounts["netPaid"]["traceIds"]
                     + amounts["notCovered"]["traceIds"])
    if workflow == "I":
        decision = observed(None, presence="not-applicable")
    return {
        "lineNumber": line.lx,
        "service": _service(line, workflow, traces),
        "serviceDate": _service_date(segments, traces, loop_id),
        "benefitDecision": decision,
        "reductionIndicators": reductions,
        "financialOutcome": _financial_outcome(amounts, amount_traces),
        "amounts": amounts,
        "cas": cas,
        "amts": amts,
        "notes": _notes(segments, traces, loop_id),
        "references": _ref_rows(segments, traces, loop_id),
    }


def _service_date(segments, traces, loop_id):
    for seg in segments:
        if seg.sid == "DTP" and seg.el(1) == "472":
            return _from_element(seg, 3, traces, loop_id)
    return observed(None)


def _other_payers(claim, traces):
    hcp = claim.seg("HCP")
    if hcp is None:
        return []
    return [{"sbr": seg.text, "traceIds": [traces.add(seg, loop_id="2320")]}
            for seg in claim.segs("SBR") if seg.index > hcp.index]


def _claim(claim, workflow, traces, claim_index):
    loop_id = "2300"
    clm = claim.seg("CLM")
    refs = _ref_rows(claim.segments, traces, loop_id)
    cas = _cas_rows(claim.segments, traces, "2320")
    amts = _amt_rows(claim.segments, traces, "2320")
    decision, tagged, reductions = _k3_values(claim.segments, traces, loop_id)
    hcp = claim.seg("HCP")
    frequency = None
    if clm is not None and clm.el(5):
        parts = clm.el(5).split(":")
        frequency = parts[2] if len(parts) > 2 else None
    amounts = {
        "billed": _from_element(clm, 2, traces, loop_id),
        **_money_from_hcp(hcp, traces, loop_id),
        "deductible": _cas_value(cas, "PR", "1"),
        "coinsurance": _cas_value(cas, "PR", "2"),
        "copay": _cas_value(cas, "PR", "3"),
        "notCovered": tagged.get("NA", _cas_value(cas, "PR", "96")),
        "netPaid": tagged.get("PA", observed(None)),
        "coveragePercentage": tagged.get("CP", observed(None)),
        "patientResponsibility": _named_amt(amts, "EAF"),
    }
    return {
        "claimIndex": claim_index,
        "transactionControl": _from_element(claim.st, 2, traces, "ST"),
        "claimIdentifier": _from_element(clm, 1, traces, loop_id),
        "identifiers": {
            "ccn": _named_ref(refs, "F8"),
            "uhapClaimId": _named_ref(refs, "9A"),
            "clientClaimId": _named_ref(refs, "D9"),
            "originalUhapClaimId": _named_ref(refs, "9F"),
            "all": refs,
        },
        "benefitDecision": decision,
        "reductionIndicators": reductions,
        "adjustment": {
            "clm20": _from_element(clm, 20, traces, loop_id),
            "frequencyCode": (observed(
                frequency, [traces.add(clm, 5, loop_id)])
                if frequency else observed(None)),
        },
        "amounts": amounts,
        "cas": cas,
        "amts": amts,
        "notes": _notes(claim.segments, traces, loop_id),
        "references": refs,
        "otherPayers": _other_payers(claim, traces),
        "lines": [_line(line, workflow, traces) for line in claim.lines],
    }


def _envelope(edi, traces):
    isa, gs = edi.seg("ISA"), edi.seg("GS")
    return {
        "sender": _from_element(isa, 6, traces, "ISA"),
        "receiver": _from_element(isa, 8, traces, "ISA"),
        "interchangeControl": _from_element(isa, 13, traces, "ISA"),
        "groupControl": _from_element(gs, 6, traces, "GS"),
        "transactionCount": len(edi.claims),
    }


def interpret(edi, detection):
    traces = TraceIndex()
    result = {
        "envelope": _envelope(edi, traces),
        "claims": [_claim(claim, detection.workflow, traces, index)
                   for index, claim in enumerate(edi.claims, start=1)],
        "traces": traces.rows,
    }
    return result
