"""Execute the production options-pane callbacks with Android geometry doubles.

These tests cover pane ownership, insets, layout feedback, and dim clipping.
Actual PopupWindow rendering and gestures still require the emulator test.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = ROOT / "app/src/main/java/org/thunderdog/challegram/navigation/OptionsLayout.java"
POPUP = ROOT / "app/src/main/java/org/thunderdog/challegram/widget/PopupLayout.java"
CONTROLLER = ROOT / "app/src/main/java/org/thunderdog/challegram/navigation/ViewController.java"
DRAWER = ROOT / "app/src/main/java/org/thunderdog/challegram/navigation/DrawerController.java"
BOUNDS = ROOT / "app/src/main/java/org/thunderdog/challegram/navigation/PopupPaneBounds.java"


def source_for(broken=False, stale_dim=False, missing_drawer=False):
    helper = block(BOUNDS, "public final class PopupPaneBounds").replace("public final class PopupPaneBounds", "static final class PopupPaneBounds")
    signatures = (
        "public void setConstrainToSourcePane (", "public @Nullable PopupPaneBounds getPopupPaneBounds (",
        "protected void onAttachedToWindow (", "protected void onDetachedFromWindow (",
        "public void onApplyMarginInsets (",
    )
    methods = "\n".join(block(OPTIONS, signature) for signature in signatures)
    if missing_drawer:
        helper = helper.replace("parent.getOptionsSourceController()", "parent.getParentOrSelf()")
    if broken:
        helper = helper.replace("Math.max(insets.left, sourcePaneLeft)", "insets.left").replace("Math.max(insets.right, sourcePaneRight)", "insets.right")
    layout = block(POPUP, "protected void onLayout (")
    if stale_dim:
        layout = layout.replace("backgroundView.invalidate();", "")
    settings = block(CONTROLLER, "public void onApplyMarginInsets (View child, LayoutParams params").replace("LayoutParams params", "FrameLayout.LayoutParams params")
    replacements = {
        "HELPER": helper, "METHODS": methods, "DRAW": block(POPUP, "public void draw (Canvas c)"),
        "POPUP_LAYOUT": layout,
        "SOURCE_CONTROLLER": block(CONTROLLER, "public @Nullable ViewController<?> getOptionsSourceController ("),
        "DRAWER_SOURCE": block(DRAWER, "public @Nullable ViewController<?> getOptionsSourceController ("),
        "SETTINGS_INSETS": settings,
    }
    source = (ROOT / "tests/TwoPaneOptionsHarness.java").read_text()
    for marker, text in replacements.items(): source = source.replace("/* " + marker + " */", text)
    return source


class TwoPaneOptionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moex-options-")
        cls.compile(cls.temp.name, source_for())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def compile(directory, source):
        path = Path(directory) / "TwoPaneOptionsHarness.java"
        path.write_text(source)
        subprocess.run(["javac", "-d", directory, str(path)], check=True)

    def run_case(self, case):
        subprocess.run(["java", "-cp", self.temp.name, "TwoPaneOptionsHarness", case], check=True, timeout=15)

    def test_right_left_rtl_and_screen_origin(self): self.run_case("bounds")
    def test_single_pane_and_fullscreen_overlay_scope(self): self.run_case("scope")
    def test_resize_fold_unfold_and_no_layout_feedback(self): self.run_case("lifecycle")
    def test_settings_sheet_uses_source_pane_and_preserves_bottom_inset(self): self.run_case("settings")
    def test_drawer_source_tracks_left_pane_and_fold_unfold(self): self.run_case("drawer")
    def test_negative_control_reproduces_unscoped_drawer_menu(self):
        with tempfile.TemporaryDirectory(prefix="moex-options-no-drawer-") as directory:
            self.compile(directory, source_for(missing_drawer=True))
            result = subprocess.run(["java", "-cp", directory, "TwoPaneOptionsHarness", "drawer"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("menu follows source pane", result.stderr)

    def test_dim_display_list_refreshes_after_fold_and_unfold(self): self.run_case("dim_cache")
    def test_negative_control_reproduces_stale_dim_clip(self):
        with tempfile.TemporaryDirectory(prefix="moex-options-stale-dim-") as directory:
            self.compile(directory, source_for(stale_dim=True))
            result = subprocess.run(["java", "-cp", directory, "TwoPaneOptionsHarness", "dim_cache"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dim cache refreshed", result.stderr)

    def test_negative_control_reproduces_full_width_menu(self):
        with tempfile.TemporaryDirectory(prefix="moex-options-old-") as directory:
            self.compile(directory, source_for(broken=True))
            result = subprocess.run(["java", "-cp", directory, "TwoPaneOptionsHarness", "bounds"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("menu follows source pane", result.stderr)


if __name__ == "__main__": unittest.main()
