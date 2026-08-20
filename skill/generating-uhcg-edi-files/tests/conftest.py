import os
import sys
import pytest

# Add scripts/ to sys.path so tests can import modules like seeds, x12_parse, etc.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))


@pytest.fixture
def repo():
    """Return the EDI repository root path."""
    return os.environ.get(
        "EDI_REPO",
        r"C:\Users\wkn\837-specialist\.claude\worktrees\837-generator-ui"
    )
