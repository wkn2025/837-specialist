"""Detect the UHCG 837 workflow from authoritative X12 version evidence."""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

VERSION_837I = "005010X223A2"
VERSION_837P = "005010X222A1"
VERSION_TO_WORKFLOW = {VERSION_837I: "I", VERSION_837P: "P"}
WORKFLOW_TO_VERSION = {value: key for key, value in VERSION_TO_WORKFLOW.items()}


@dataclass
class Detection:
    workflow: str
    version: str
    confidence: str
    evidence: list[dict] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _version_evidence(edi):
    rows = []
    for seg in edi.segs("GS"):
        if seg.el(8):
            rows.append({"source": "GS08", "value": seg.el(8),
                         "segmentIndex": seg.index})
    for seg in edi.segs("ST"):
        if seg.el(3):
            rows.append({"source": "ST03", "value": seg.el(3),
                         "segmentIndex": seg.index})
    return rows


def _supporting_evidence(edi, filename):
    rows = []
    for sid in ("SV1", "SV2", "CL1"):
        for seg in edi.segs(sid):
            rows.append({"source": "segment", "value": sid,
                         "segmentIndex": seg.index})
            break
    match = re.search(r"_([IP])_\d{14}\.x12$",
                      os.path.basename(filename or ""), re.IGNORECASE)
    if match:
        rows.append({"source": "filename", "value": match.group(1).upper(),
                     "segmentIndex": None})
    return rows


def detect(edi, filename=""):
    version_rows = _version_evidence(edi)
    authoritative = {
        VERSION_TO_WORKFLOW[row["value"]]
        for row in version_rows if row["value"] in VERSION_TO_WORKFLOW
    }
    evidence = version_rows + _supporting_evidence(edi, filename)

    if len(authoritative) > 1:
        return Detection(
            workflow="unknown", version="", confidence="conflict",
            evidence=evidence,
            conflicts=["GS08/ST03 identify different implementation guides"])

    if authoritative:
        selected = next(iter(authoritative))
        gs_has_selected = any(
            row["source"] == "GS08"
            and VERSION_TO_WORKFLOW.get(row["value"]) == selected
            for row in version_rows)
        st_has_selected = any(
            row["source"] == "ST03"
            and VERSION_TO_WORKFLOW.get(row["value"]) == selected
            for row in version_rows)
        return Detection(
            workflow=selected,
            version=WORKFLOW_TO_VERSION[selected],
            confidence="high" if gs_has_selected and st_has_selected else "medium",
            evidence=evidence)

    return Detection(workflow="unknown", version="", confidence="unknown",
                     evidence=evidence)
