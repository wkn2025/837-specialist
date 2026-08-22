"""Read-only JSON interface for EDI2 workflow detection and validation."""
from __future__ import annotations

import argparse
import json
import os
import sys

import adjudication
import rules
import rules_837i
import rules_837p
import workflow
import x12_model as M


SCHEMA_VERSION = "1.0"


def _file_info(path, filename):
    return {
        "filename": os.path.basename(filename or path),
        "sizeBytes": os.path.getsize(path),
    }


def _counts(edi):
    return {
        "claims": len(edi.claims),
        "lines": sum(len(claim.lines) for claim in edi.claims),
    }


def _coverage(workflow_code, standalone="performed"):
    return {
        "standaloneValidation": standalone,
        "sourceComparison": "skipped",
        "original837Comparison": "not-performed",
        "professionalGolden": (
            "not-performed" if workflow_code == "P" else "not-applicable"),
    }


def _limitations(workflow_code):
    if workflow_code != "P":
        return []
    return [rules_837p.PROFESSIONAL_VALIDATION_NOTE]


def _summary(checks, edi):
    statuses = {status: 0 for status in ("pass", "fail", "warning", "skipped")}
    for check in checks:
        statuses[check.status] += 1
    return {
        **_counts(edi),
        "checks": len(checks),
        "passed": statuses["pass"],
        "failed": statuses["fail"],
        "warnings": statuses["warning"],
        "skipped": statuses["skipped"],
        "blockers": sum(
            1 for check in checks for item in check.findings
            if item.severity == "blocker"),
        "advisories": sum(
            1 for check in checks for item in check.findings
            if item.severity == "advisory"),
    }


def _trace_ids_by_segment(normalized):
    result = {}
    for trace_id, trace in normalized["traces"].items():
        result.setdefault(trace["segmentIndex"], []).append(trace_id)
    return result


def _serialize_checks(checks, normalized):
    traces = _trace_ids_by_segment(normalized)
    rows = []
    for check in checks:
        row = check.to_dict()
        row["findings"] = [{
            "ruleId": item.rule_id,
            "severity": item.severity,
            "message": item.message,
            "citation": item.citation,
            "claim": item.claim or None,
            "lineNumber": item.lx,
            "segmentIndex": item.segment_index,
            "traceIds": traces.get(item.segment_index, []),
        } for item in check.findings]
        rows.append(row)
    return rows


def _registry(workflow_code):
    if workflow_code == "I":
        return rules_837i.registry()
    if workflow_code == "P":
        return rules_837p.registry()
    return []


def _indeterminate(path, filename, edi, detected):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "indeterminate",
        "file": _file_info(path, filename),
        "workflow": detected.to_dict(),
        "summary": {**_counts(edi), "checks": 0, "passed": 0, "failed": 0,
                    "warnings": 0, "skipped": 0, "blockers": 0,
                    "advisories": 0},
        "coverage": _coverage("unknown", standalone="not-performed"),
        "limitations": [
            "Workflow-specific validation was not performed because the X12 "
            "version evidence is missing or conflicting."],
        "checks": [],
        "adjudication": None,
    }


def _unparseable(path, filename, error):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        raw = fh.read()
    offset = max(0, min(error.offset, len(raw)))
    context = raw[max(0, offset - 20):min(len(raw), offset + 40)]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "unparseable",
        "file": _file_info(path, filename),
        "workflow": None,
        "summary": {"claims": 0, "lines": 0, "checks": 0, "passed": 0,
                    "failed": 0, "warnings": 0, "skipped": 0,
                    "blockers": 0, "advisories": 0},
        "coverage": _coverage("unknown", standalone="not-performed"),
        "limitations": ["Structural validation and adjudication interpretation were not performed."],
        "checks": [],
        "adjudication": None,
        "parseError": {
            "message": str(error),
            "offset": offset,
            "context": context,
        },
    }


def validate(path, filename=None):
    """Analyze one EDI2 file without modifying it or producing side effects."""
    safe_filename = os.path.basename(filename or path)
    try:
        edi = M.parse(path)
    except M.ParseError as error:
        return _unparseable(path, safe_filename, error)

    detected = workflow.detect(edi, safe_filename)
    if detected.workflow == "unknown":
        return _indeterminate(path, safe_filename, edi, detected)

    context = rules.Context(edi=edi, filename=safe_filename)
    checks = rules.run_checks(context, _registry(detected.workflow))
    normalized = adjudication.interpret(edi, detected)
    summary = _summary(checks, edi)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "invalid" if summary["blockers"] else "valid",
        "file": _file_info(path, safe_filename),
        "workflow": detected.to_dict(),
        "summary": summary,
        "coverage": _coverage(detected.workflow),
        "limitations": _limitations(detected.workflow),
        "checks": _serialize_checks(checks, normalized),
        "adjudication": normalized,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--filename")
    args = parser.parse_args(argv)
    try:
        result = validate(args.file, filename=args.filename)
    except (OSError, UnicodeError) as error:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "status": "error",
            "error": "unable to read the uploaded EDI2 file: %s"
                     % error.__class__.__name__,
        }
        print(json.dumps(result, separators=(",", ":")))
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
