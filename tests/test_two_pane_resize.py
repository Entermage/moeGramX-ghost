"""Exercise production direction arbitration for the divider's non-consuming side margins."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TwoPaneResizeTest(unittest.TestCase):
    def test_horizontal_capture_and_content_gesture_release(self):
        with tempfile.TemporaryDirectory(prefix="moex-pane-resize-") as output:
            subprocess.run([
                "javac", "-d", output,
                str(ROOT / "app/src/main/java/moe/kirao/mgx/layout/MoexPaneResizeGesture.java"),
                str(ROOT / "tests/MoexPaneResizeGestureTest.java"),
            ], check=True)
            subprocess.run(["java", "-cp", output, "MoexPaneResizeGestureTest"], check=True)

    def test_production_margin_event_routing(self):
        source = (ROOT / "app/src/main/java/moe/kirao/mgx/layout/MoexTwoPane.java").read_text()
        start = source.index("  public boolean onExpandedResizeTouchEvent (")
        end = source.index("  public static int chatPaneWidth (", start)
        routing = source[start:end]
        fixture = r"""
import moe.kirao.mgx.layout.MoexPaneResizeGesture;
class MotionEvent {
  static final int ACTION_DOWN=0, ACTION_UP=1, ACTION_MOVE=2, ACTION_CANCEL=3;
  final int action, pointers; final float x, y;
  MotionEvent(int a, float x, float y, int p) { action=a; this.x=x; this.y=y; pointers=p; }
  int getActionMasked() { return action; } int getPointerCount() { return pointers; }
  float getX() { return x; } float getY() { return y; }
  float getRawX() { return x; } float getRawY() { return y; }
}
class Screen { static float dpf(float value) { return value; } }
class Drawer { boolean visible; boolean isVisible() { return visible; } }
class Context {
  boolean passcode, popup; Drawer drawer = new Drawer();
  boolean isPasscodeShowing() { return passcode; } boolean isWindowPopupShowing() { return popup; }
  Drawer getDrawer() { return drawer; }
}
class Navigation { boolean animating; boolean isAnimating() { return animating; } }
class Handle {
  int left=394, right=406, touchSlop=8, starts, finishes, cancels, initialList;
  float downX, lastX;
  int getLeft() { return left; } int getRight() { return right; }
  int getTop() { return 264; } int getBottom() { return 336; }
  void startTouch(float x, float y, int width) { starts++; downX=x; initialList=width; }
  void moveTouch(float x, float y) { lastX=x; }
  void finishTouch() { finishes++; } void cancelDrag() { cancels++; }
}
class ResizeHost {
  static final float HANDLE_TOUCH_WIDTH_DP=32f;
  boolean isActive=true, destroyed, activityFocused=true, expandedResizeStreamOwned;
  int listStart=0, listEnd=394, expandedResizeListWidth;
  Context context=new Context(); Handle handle=new Handle(); Navigation leftNavigation=new Navigation();
  MoexPaneResizeGesture expandedResizeGesture=new MoexPaneResizeGesture();
""" + routing + "}"
        with tempfile.TemporaryDirectory(prefix="moex-pane-routing-") as output:
            generated = pathlib.Path(output) / "ResizeHost.java"
            generated.write_text(fixture)
            subprocess.run([
                "javac", "-d", output, str(generated),
                str(ROOT / "app/src/main/java/moe/kirao/mgx/layout/MoexPaneResizeGesture.java"),
                str(ROOT / "tests/TwoPaneResizeRoutingHarness.java"),
            ], check=True)
            subprocess.run(["java", "-cp", output, "TwoPaneResizeRoutingHarness"], check=True)


if __name__ == "__main__":
    unittest.main()
