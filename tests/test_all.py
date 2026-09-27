"""
Aggregate test suite coordinator for Discord Game Utility Bot.
Maintains backward compatibility for `unittest tests/test_all.py`.
"""
import unittest

from tests.test_player_database import (
    TestPlayerDatabase,
    TestWyrDatabase,
)
from tests.test_player_manager import (
    TestPlayerSearchAndCallables,
    TestPlayerManagerCog,
)
from tests.test_code_redeem import (
    TestRedeemUtils,
    TestCodeDetector,
    TestAutoRedeemSystem,
    TestCodeRedeemCog,
)
from tests.test_views import (
    TestBattleSupport,
    TestMenuViews,
)

__all__ = [
    "TestPlayerDatabase",
    "TestWyrDatabase",
    "TestPlayerSearchAndCallables",
    "TestPlayerManagerCog",
    "TestRedeemUtils",
    "TestCodeDetector",
    "TestAutoRedeemSystem",
    "TestCodeRedeemCog",
    "TestBattleSupport",
    "TestMenuViews",
]


def load_tests(loader, standard_tests, pattern):
    """
    Avoid duplicating tests during discovery (`unittest discover tests`).
    When invoked directly (`unittest tests/test_all.py`), pattern is None,
    so we return standard_tests containing the imported test classes.
    """
    if pattern is not None:
        return loader.suiteClass()
    return standard_tests


if __name__ == "__main__":
    unittest.main()
