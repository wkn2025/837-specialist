import os
import unittest

from tests import fixtures


class FixtureResolution(unittest.TestCase):
    def test_root_is_none_when_env_unset(self):
        old = os.environ.pop("EDI2_FIXTURES", None)
        try:
            self.assertIsNone(fixtures.fixture_root())
        finally:
            if old is not None:
                os.environ["EDI2_FIXTURES"] = old

    def test_root_is_none_when_path_missing(self):
        old = os.environ.get("EDI2_FIXTURES")
        os.environ["EDI2_FIXTURES"] = os.path.join(os.sep, "no", "such", "dir")
        try:
            self.assertIsNone(fixtures.fixture_root())
        finally:
            if old is None:
                del os.environ["EDI2_FIXTURES"]
            else:
                os.environ["EDI2_FIXTURES"] = old

    def test_fixture_joins_under_root(self):
        old = os.environ.get("EDI2_FIXTURES")
        os.environ["EDI2_FIXTURES"] = os.path.dirname(os.path.abspath(__file__))
        try:
            got = fixtures.fixture("test_fixtures_helper.py")
            self.assertTrue(os.path.isfile(got))
        finally:
            if old is None:
                del os.environ["EDI2_FIXTURES"]
            else:
                os.environ["EDI2_FIXTURES"] = old


if __name__ == "__main__":
    unittest.main()
