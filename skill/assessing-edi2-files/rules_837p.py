"""837P (Professional) rules - not implemented.

Professional differs from Institutional in ways that matter to every family:
benefit decisions are accepted at claim AND line level, iCES reductions apply
(always line-level), and a denied line may be expressed against billed charges
because a line-level benefit decision exists. Adding it means filling this file
with the same rule shapes as rules_837i.py, sourced from
UHCG_837P_Companion_Guide_FULL.csv and UHCG_Validation_Rules_Professional.csv.
"""
from __future__ import annotations

VERSION_837P = "005010X222A1"

MESSAGE = ("837P rules are not implemented. This skill validates 837I "
           "(005010X223A2) only.")


def registry():
    raise NotImplementedError(MESSAGE)
