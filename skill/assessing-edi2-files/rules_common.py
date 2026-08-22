"""Conservative registry of checks proven reusable across 837I and 837P.

The original Institutional validator registered all rules in one ordered list.
This module deliberately selects only syntax and identifier checks whose
meaning is shared. Workflow-specific structure, adjudication math, scenarios,
and source immutability remain in their workflow modules.
"""
from __future__ import annotations

from dataclasses import replace

import rules


COMMON_RULE_IDS = frozenset({
    "ENV-ISA-LEN",
    "ENV-ISA13-LEN",
    "ENV-ISA13-IEA02",
    "ENV-ISA15",
    "ENV-ONE-GROUP",
    "ENV-GE01-COUNT",
    "ENV-GE02-GS06",
    "ENV-SE01-COUNT",
    "ENV-SE02-ST02",
    "ENV-ST02-UNIQUE",
    "ENV-CLAIM-LIMIT",
    "ENV-FILENAME",
    "STR-ONE-CLAIM-PER-SET",
    "STR-HL-SEQUENCE",
    "STR-EMPTY-SEGMENT",
    "FMT-BHT03-LEN",
    "FMT-MONEY-FORM",
    "FMT-MONEY-NEGATIVE",
    "FMT-NTE-DELIMITER",
    "FMT-NTE-LENGTH",
    "FMT-COVERAGE-PCT",
    "ID-REF-F8",
    "ID-REF-9A",
    "ID-REF-D9",
    "ID-SVD01-PAYER",
    "NTE-NO-ECHO",
    "ADJ-CLM20-VALUE",
    "ADJ-CLM20-FILE-PREFIX",
    "ADV-2320-OTHER-PAYER-LOOPS",
    "ADV-ISA14",
})


def registry(source=None):
    """Return shared checks in source order, tagged for both workflows."""
    available = rules.RULES if source is None else source
    return [replace(item, workflow="common")
            for item in available if item.id in COMMON_RULE_IDS]

