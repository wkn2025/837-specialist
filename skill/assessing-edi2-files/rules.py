"""Rule registry plumbing. Rules themselves live in rules_837i.py."""
from __future__ import annotations
import traceback
from dataclasses import dataclass, field

import findings as F

RULES = []


class DuplicateRuleId(Exception):
    pass


@dataclass
class Rule:
    id: str
    severity: str
    citation: str
    func: object


@dataclass
class Context:
    edi: object
    source: object = None
    matrix: object = None
    filename: str = ""
    # Recorded judgment, keyed by UHAP claim id, e.g.
    # {"E2E...704": {"benefit_decision": "4", "reason": "test plan MRR scenario"}}.
    # The expected-results matrix is never a rule source; this is the decision
    # a human or the model already took, handed to the script so the corrected
    # file stays reproducible.
    scenarios: dict = field(default_factory=dict)


def rule(rule_id, severity, citation, registry=None):
    target = RULES if registry is None else registry

    def wrap(func):
        if any(r.id == rule_id for r in target):
            raise DuplicateRuleId(rule_id)
        target.append(Rule(rule_id, severity, citation, func))
        return func

    return wrap


def registered_ids(registry=None):
    target = RULES if registry is None else registry
    return [r.id for r in target]


def run_all(ctx, registry=None):
    target = RULES if registry is None else registry
    out = []
    for r in target:
        try:
            produced = list(r.func(ctx) or [])
        except Exception:
            out.append(F.Finding(
                rule_id=r.id, severity=F.BLOCKER, citation=r.citation,
                message="rule raised: %s" % traceback.format_exc(limit=2).strip()))
            continue
        for item in produced:
            item.severity = r.severity
            item.citation = item.citation or r.citation
            out.append(item)
    return out
