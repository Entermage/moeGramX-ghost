public final class TwoPaneResizeRoutingHarness {
  private static int checks;
  private static void check (boolean value, String message) {
    checks++;
    if (!value) throw new AssertionError(message);
  }
  private static MotionEvent event (int action, float x, float y) { return new MotionEvent(action, x, y, 1); }
  public static void main (String[] args) {
    ResizeHost h = new ResizeHost();
    check(!h.onExpandedResizeTouchEvent(event(0, 400, 300), false), "direct gutter down stays with handle");
    check(!h.onExpandedResizeTouchEvent(event(2, 450, 300), false), "observer does not duplicate direct handle drag");
    check(!h.onExpandedResizeTouchEvent(event(0, 412, 300), false), "expanded margin down reaches content");
    check(!h.onExpandedResizeTouchEvent(event(2, 414, 301), false), "margin click jitter reaches content");
    check(!h.onExpandedResizeTouchEvent(event(1, 414, 301), false), "margin click up reaches content");
    check(h.handle.starts == 0, "ordinary click creates no resize interaction");
    h.onExpandedResizeTouchEvent(event(0, 412, 300), false);
    check(!h.onExpandedResizeTouchEvent(event(2, 413, 320), false), "vertical list scroll is not captured");
    check(!h.onExpandedResizeTouchEvent(event(2, 460, 321), false), "later sideways motion cannot steal scrolling");
    h.onExpandedResizeTouchEvent(event(1, 460, 321), false);
    h.onExpandedResizeTouchEvent(event(0, 412, 300), false);
    check(h.onExpandedResizeTouchEvent(event(2, 432, 301), false), "horizontal margin drag is captured");
    check(h.isExpandedResizeCaptured() && h.handle.starts == 1 && h.handle.initialList == 394,
      "resize preserves initial list width and reports capture");
    h.handle.left = 414; h.handle.right = 426;
    check(h.onExpandedResizeTouchEvent(event(2, 452, 301), false), "moving handle bounds do not lose capture");
    check(h.handle.downX == 412 && h.handle.lastX == 452, "raw gesture origin survives moving layout");
    check(h.onExpandedResizeTouchEvent(event(1, 452, 301), false), "captured up is consumed");
    check(!h.isExpandedResizeCaptured() && h.handle.finishes == 1, "up commits exactly one resize and releases capture");

    h = new ResizeHost();
    h.context.popup = true;
    h.onExpandedResizeTouchEvent(event(0, 412, 300), false);
    check(!h.onExpandedResizeTouchEvent(event(2, 452, 300), false), "popup excludes hidden divider interaction");
    h.context.popup = false;
    h.context.drawer.visible = true;
    h.onExpandedResizeTouchEvent(event(0, 412, 300), false);
    check(!h.onExpandedResizeTouchEvent(event(2, 452, 300), false), "drawer excludes hidden divider interaction");
    h.context.drawer.visible = false;
    h.onExpandedResizeTouchEvent(event(0, 412, 400), false);
    check(!h.onExpandedResizeTouchEvent(event(2, 452, 400), false), "outside local handle height is not draggable");
    h.onExpandedResizeTouchEvent(event(0, 417, 300), false);
    check(!h.onExpandedResizeTouchEvent(event(2, 452, 300), false), "outside 32dp width is not draggable");
    h.onExpandedResizeTouchEvent(event(0, 388, 300), false);
    check(h.onExpandedResizeTouchEvent(event(2, 368, 300), false), "left margin also supports drag");
    check(h.onExpandedResizeTouchEvent(new MotionEvent(5, 368, 300, 2), false), "second finger cancels owned resize");
    check(h.handle.cancels == 1, "multi-touch cancellation rolls back once");
    check(h.onExpandedResizeTouchEvent(event(2, 340, 300), false), "cancelled capture consumes its remaining moves");
    check(h.onExpandedResizeTouchEvent(event(1, 340, 300), false), "cancelled capture consumes terminal up");
    check(!h.isExpandedResizeCaptured(), "terminal event releases cancelled stream");
    h.onExpandedResizeTouchEvent(event(0, 412, 300), false);
    h.onExpandedResizeTouchEvent(event(2, 432, 300), false);
    check(h.onExpandedResizeTouchEvent(event(2, 452, 300), true), "new animation block cancels and consumes owned move");
    check(h.onExpandedResizeTouchEvent(event(1, 452, 300), true), "blocked terminal event still clears ownership");
    check(!h.isExpandedResizeCaptured(), "block does not leave stale ownership");
    System.out.println("Two-pane resize routing: " + checks + " production checks passed (JVM state doubles)");
  }
}
