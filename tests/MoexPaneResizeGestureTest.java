import moe.kirao.mgx.layout.MoexPaneResizeGesture;

public final class MoexPaneResizeGestureTest {
  private static int checks;
  private static void check (boolean value, String message) {
    checks++;
    if (!value) throw new AssertionError(message);
  }

  public static void main (String[] args) {
    MoexPaneResizeGesture gesture = new MoexPaneResizeGesture();
    check(!gesture.move(100, 100, 8), "unstarted gesture cannot resize");
    gesture.begin(400, 300);
    check(!gesture.move(405, 302, 8) && gesture.isPending(), "small finger jitter remains a content click");
    check(!gesture.move(408, 300, 8), "slop itself does not take a click");
    check(gesture.move(409, 301, 8), "deliberate horizontal move starts resize");
    check(gesture.deltaX(430) == 30, "delta stays relative to the original down while divider moves");
    check(gesture.move(420, 500, 8), "claimed resize does not turn into content scroll mid-gesture");
    gesture.cancel();
    check(!gesture.isDragging() && !gesture.move(600, 300, 8), "cancel releases capture until a new down");

    for (float[] movement : new float[][] {{0, 9}, {5, 20}, {20, 20}, {15, 10}, {10, 12}}) {
      gesture.begin(200, 300);
      check(!gesture.move(200 + movement[0], 300 + movement[1], 8), "vertical/diagonal start must stay with the content");
      check(!gesture.isPending(), "content gesture is permanently released");
      check(!gesture.move(600, 310, 8), "later horizontal movement must not steal an already scrolling list");
    }
    gesture.begin(400, 300);
    check(gesture.move(380, 299, 8), "leftward drag works equally for RTL and LTR callers");
    check(gesture.deltaX(370) == -30, "signed delta lets caller mirror RTL width changes");
    gesture.begin(800, 200);
    check(!gesture.isDragging() && gesture.startX() == 800 && gesture.startY() == 200,
      "new down clears old capture and origin after cancellation or resizing");
    check(gesture.move(820, 210, 8), "horizontal-dominant diagonal drag remains practical");
    System.out.println("MoexPaneResizeGesture: " + checks + " assertions passed");
  }
}
