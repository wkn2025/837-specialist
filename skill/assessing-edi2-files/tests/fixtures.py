"""Locate the 837-specialist repo that holds the test fixtures.

The skill itself never depends on the repo. Only this test suite does, so a
missing repo skips fixture-backed tests instead of failing them.
"""
from __future__ import annotations
import os

ENV = "EDI2_FIXTURES"
MESSAGE = (
    "%s is unset or does not point at a directory; "
    "set it to the 837-specialist repo root to run fixture-backed tests" % ENV
)


def fixture_root():
    """Return the fixture root, or None when it is unset or missing."""
    root = os.environ.get(ENV)
    if not root or not os.path.isdir(root):
        return None
    return root


def fixture(*parts):
    """Absolute path to a fixture. Raises if the root is unavailable."""
    root = fixture_root()
    if root is None:
        raise RuntimeError(MESSAGE)
    return os.path.join(root, *parts)


def requires_fixtures(test_case):
    """Call at the top of a test that needs fixtures; skips when absent."""
    if fixture_root() is None:
        test_case.skipTest(MESSAGE)
