"""Run production proxy entry methods with controller doubles; this is not Android E2E."""
from pathlib import Path
import unittest

from test_chat_navigation import block
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/src/main/java/org/thunderdog/challegram/telegram/TdlibUi.java"


class TwoPaneProxySourceTest(unittest.TestCase):
    def test_choice_menu_source_preserves_edit_navigation(self):
        methods = "\n".join(block(SOURCE, signature) for signature in (
            "public void openProxySettings (", "public void addNewProxy (",
        ))
        harness = (ROOT / "tests/TwoPaneProxySourceHarness.java").read_text().replace("__METHODS__", methods)
        run_java({"TwoPaneProxySourceHarness.java": harness}, "TwoPaneProxySourceHarness")


if __name__ == "__main__":
    unittest.main()
