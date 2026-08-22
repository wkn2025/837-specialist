"""Rule registry plumbing. Rules themselves live in rules_837i.py."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field

import findings as F

RULES = []


class DuplicateRuleId(Exception):
    pass


class RuleExecutionError(Exception):
    """Safe signal that a validator rule could not evaluate the input."""
    def __init__(self, rule_id):
        self.rule_id = rule_id
        super().__init__("rule %s could not be evaluated" % rule_id)


@dataclass
class Rule:
    id: str
    severity: str
    citation: str
    func: object
    label: str = ""
    workflow: str = "I"
    skip: object = None


@dataclass
class CheckResult:
    id: str
    family: str
    label: str
    workflow: str
    status: str
    severity: str
    citation: str
    findings: list = field(default_factory=list)
    skipped_reason: str = ""

    def to_dict(self):
        return {
            "id": self.id,
            "family": self.family,
            "label": self.label,
            "workflow": self.workflow,
            "status": self.status,
            "severity": self.severity,
            "citation": self.citation,
            "findings": [asdict(item) for item in self.findings],
            "skippedReason": self.skipped_reason,
        }


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


def rule(rule_id, severity, citation, registry=None, label="", workflow="I",
         skip=None):
    target = RULES if registry is None else registry

    def wrap(func):
        if any(r.id == rule_id for r in target):
            raise DuplicateRuleId(rule_id)
        target.append(Rule(
            id=rule_id,
            severity=severity,
            citation=citation,
            func=func,
            label=label or rule_id,
            workflow=workflow,
            skip=skip,
        ))
        return func

    return wrap


def registered_ids(registry=None):
    target = RULES if registry is None else registry
    return [r.id for r in target]


def _execute(registered, ctx, fail_on_rule_error=False):
    try:
        produced = list(registered.func(ctx) or [])
    except Exception:
        if fail_on_rule_error:
            raise RuleExecutionError(registered.id) from None
        return [F.Finding(
            rule_id=registered.id,
            severity=F.BLOCKER,
            citation=registered.citation,
            message="rule could not be evaluated",
        )]
    for item in produced:
        item.severity = registered.severity
        item.citation = item.citation or registered.citation
    return produced


def run_checks(ctx, registry=None, fail_on_rule_error=False):
    target = RULES if registry is None else registry
    out = []
    for registered in target:
        reason = registered.skip(ctx) if registered.skip else ""
        if reason:
            out.append(CheckResult(
                id=registered.id,
                family=registered.id.split("-", 1)[0],
                label=registered.label,
                workflow=registered.workflow,
                status="skipped",
                severity=registered.severity,
                citation=registered.citation,
                skipped_reason=reason,
            ))
            continue
        produced = _execute(registered, ctx, fail_on_rule_error)
        if any(item.severity == F.BLOCKER for item in produced):
            status = "fail"
        elif produced:
            status = "warning"
        else:
            status = "pass"
        out.append(CheckResult(
            id=registered.id,
            family=registered.id.split("-", 1)[0],
            label=registered.label,
            workflow=registered.workflow,
            status=status,
            severity=registered.severity,
            citation=registered.citation,
            findings=produced,
        ))
    return out


def run_all(ctx, registry=None):
    """Compatibility projection containing only emitted findings."""
    return [
        finding
        for result in run_checks(ctx, registry=registry)
        for finding in result.findings
    ]
