"""Findings and fixes - the interface between the rules, the fixer and the report."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field

BLOCKER = "blocker"
ADVISORY = "advisory"

REPLACE = "replace"
INSERT_BEFORE = "insert_before"


@dataclass
class Fix:
    segment_index: int
    old_text: str
    new_text: str
    kind: str = REPLACE
    uncertain: bool = False
    reason: str = ""


@dataclass
class Finding:
    rule_id: str
    severity: str
    message: str
    citation: str = ""
    claim: str = ""
    lx: int = None
    segment_index: int = None
    fix: Fix = None


def to_json(items, meta):
    payload = {"meta": meta, "findings": []}
    for f in items:
        row = asdict(f)
        payload["findings"].append(row)
    return json.dumps(payload, indent=2, sort_keys=False)


def from_json(text):
    payload = json.loads(text)
    items = []
    for row in payload["findings"]:
        fix_row = row.pop("fix", None)
        fix = Fix(**fix_row) if fix_row else None
        items.append(Finding(fix=fix, **row))
    return items, payload["meta"]
