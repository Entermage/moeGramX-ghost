"""Run real overlay layout callbacks with small Android view-tree doubles.

This checks layout scheduling, bounds, RTL and detach cleanup. It does not prove
Android rendering, memory pressure or the cause of an emulator-wide black screen.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "app/src/main/java/org/thunderdog/challegram/component"
INLINE = COMPONENT / "chat/InlineResultsWrap.java"
MEDIA = COMPONENT / "attach/MediaLayout.java"


def source_for(broken=None):
    inline = INLINE.read_text()
    media = MEDIA.read_text()
    inline_fields = inline[inline.index("  private int moexPaneLeft, moexPaneRight;"):inline.index("  /** The room left and right of the chat pane")]
    media_fields = "PopupPaneBounds paneBounds;"
    helper = block(ROOT / "app/src/main/java/org/thunderdog/challegram/navigation/PopupPaneBounds.java", "public final class PopupPaneBounds").replace("public final class PopupPaneBounds", "static final class PopupPaneBounds").replace("FrameLayout.LayoutParams", "LayoutParams")
    inline_methods = "\n".join(block(INLINE, signature) for signature in (
        "public void updatePosition (", "private boolean moexUpdatePaneMargins (",
        "public void onApplyMarginInsets (", "protected void onAttachedToWindow (",
        "protected void onDetachedFromWindow (",
    ))
    media_methods = "\n".join(block(MEDIA, signature) for signature in (
        "public void onApplyMarginInsets (", "public PopupPaneBounds getPopupPaneBounds (",
        "protected void onAttachedToWindow (",
        "protected void onDetachedFromWindow (",
    ))
    if broken == "inline":
        inline_fields = inline_fields.replace("updatePosition(false);", "updatePosition(false); requestLayout();", 1)
    if broken == "media":
        helper = helper.replace("if (popup != null && update())", "if (popup != null)", 1)
    source = (ROOT / "tests/TwoPaneOverlayLayoutHarness.java").read_text()
    for marker, code in (("PANE_HELPER", helper), ("INLINE_FIELDS", inline_fields), ("INLINE_METHODS", inline_methods), ("MEDIA_FIELDS", media_fields), ("MEDIA_METHODS", media_methods)):
        source = source.replace("/* " + marker + " */", code)
    return source.replace("org.thunderdog.challegram.BaseActivity", "BaseActivity").replace("android.view.ViewParent", "View")


def compile_harness(directory, source):
    path = Path(directory) / "TwoPaneOverlayLayoutHarness.java"
    path.write_text(source)
    subprocess.run(["javac", "-d", directory, str(path)], check=True)


class TwoPaneOverlayLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moex-overlay-layout-")
        compile_harness(cls.temp.name, source_for())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, overlay, name):
        subprocess.run(["java", "-cp", self.temp.name, "TwoPaneOverlayLayoutHarness", overlay, name], check=True, timeout=15)

    def test_inline_stable_geometry_has_no_layout_feedback(self): self.run_case("inline", "steady")
    def test_media_stable_geometry_has_no_layout_feedback(self): self.run_case("media", "steady")
    def test_inline_drag_fold_unfold_and_rtl_update_margins(self): self.run_case("inline", "changes")
    def test_media_drag_fold_unfold_and_rtl_update_margins(self): self.run_case("media", "changes")
    def test_inline_detach_cancels_callbacks_and_listener(self): self.run_case("inline", "detach")
    def test_media_detach_cancels_callbacks_and_listener(self): self.run_case("media", "detach")

    def test_negative_controls_reproduce_original_feedback(self):
        for overlay in ("inline", "media"):
            with self.subTest(overlay=overlay), tempfile.TemporaryDirectory(prefix="moex-overlay-broken-") as directory:
                compile_harness(directory, source_for(broken=overlay))
                result = subprocess.run(["java", "-cp", directory, "TwoPaneOverlayLayoutHarness", overlay, "steady"], text=True, capture_output=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("overlay layout feedback did not settle", result.stderr)


if __name__ == "__main__":
    unittest.main()
