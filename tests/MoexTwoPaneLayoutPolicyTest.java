import moe.kirao.mgx.layout.MoexTwoPaneLayoutPolicy;

public final class MoexTwoPaneLayoutPolicyTest {
  private static int checks;
  private static void check (boolean value, String message) {
    checks++;
    if (!value) throw new AssertionError(message);
  }

  private static void thresholds () {
    check(!MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(599, 800, false), "narrow portrait must stay single-pane");
    check(MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(600, 480, false), "fold/tablet minimum must open two panes");
    check(!MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(900, 479, false), "landscape phone must stay single-pane");
    check(MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(1200, 300, false), "wide desktop window can be short");
    check(MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(580, 460, true), "existing panes retain 20dp hysteresis");
    check(!MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(579, 800, true), "fold below hysteresis returns to one pane");
    check(!MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(900, 459, true), "shorter height leaves hysteresis");
    check(MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(1180, 300, true), "desktop hysteresis retained");
    check(!MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(1179, 300, true), "desktop hysteresis exit");
    check(!MoexTwoPaneLayoutPolicy.shouldUseTwoPanes(0, 0, false), "unmeasured window stays single-pane");
  }

  private static void checkBounds (MoexTwoPaneLayoutPolicy.Split split, int width, int left, int right, boolean rtl) {
    check(split.listStart >= left && split.listEnd <= width - right, "list avoids window side insets");
    check(split.chatStart >= left && split.chatEnd <= width - right, "chat avoids window side insets");
    check(split.listEnd >= split.listStart && split.chatEnd >= split.chatStart, "pane widths cannot be negative");
    check(split.gutterEnd >= split.gutterStart, "gutter width cannot be negative");
    if (rtl) {
      check(split.chatEnd == split.gutterStart && split.gutterEnd == split.listStart, "RTL has chat/gutter/list order");
    } else {
      check(split.listEnd == split.gutterStart && split.gutterEnd == split.chatStart, "LTR has list/gutter/chat order");
    }
    check(split.listEnd - split.listStart + split.chatEnd - split.chatStart + split.gutterEnd - split.gutterStart == width - left - right,
      "all usable width is accounted for without overlap");
  }

  private static void geometry () {
    check(MoexTwoPaneLayoutPolicy.defaultListWidthDp(600) == 320, "default lower bound");
    check(MoexTwoPaneLayoutPolicy.defaultListWidthDp(1000) == 380, "default proportional width");
    check(MoexTwoPaneLayoutPolicy.defaultListWidthDp(1800) == 420, "default upper bound");
    for (boolean rtl : new boolean[] {false, true}) {
      for (int requested : new int[] {-900, 0, 320, 420, 10000}) {
        MoexTwoPaneLayoutPolicy.Split split = MoexTwoPaneLayoutPolicy.split(1067, 23, 41, 24, requested, 260, 300, rtl);
        checkBounds(split, 1067, 23, 41, rtl);
        check(split.listEnd - split.listStart >= 260, "drag cannot crush the list");
        check(split.chatEnd - split.chatStart >= 300, "drag cannot crush chat");
      }
      MoexTwoPaneLayoutPolicy.Split slim = MoexTwoPaneLayoutPolicy.split(600, 0, 0, 12, 420, 260, 300, rtl);
      checkBounds(slim, 600, 0, 0, rtl);
      check(slim.chatEnd - slim.chatStart == 300 && slim.listEnd - slim.listStart == 288,
        "12dp divider returns the saved space to the panes at their minimum window width");
      MoexTwoPaneLayoutPolicy.Split slimSaved = MoexTwoPaneLayoutPolicy.split(1067, 23, 41, 12, 320, 260, 300, rtl);
      MoexTwoPaneLayoutPolicy.Split oldSaved = MoexTwoPaneLayoutPolicy.split(1067, 23, 41, 24, 320, 260, 300, rtl);
      check(slimSaved.listEnd - slimSaved.listStart == oldSaved.listEnd - oldSaved.listStart,
        "narrowing divider preserves saved list width");
      check(slimSaved.chatEnd - slimSaved.chatStart == oldSaved.chatEnd - oldSaved.chatStart + 12,
        "saved list gives the recovered gutter width to the chat");
      MoexTwoPaneLayoutPolicy.Split edge = MoexTwoPaneLayoutPolicy.split(600, 0, 0, 24, 420, 260, 300, rtl);
      checkBounds(edge, 600, 0, 0, rtl);
      check(edge.chatEnd - edge.chatStart == 300 && edge.listEnd - edge.listStart == 276, "minimum-wide screen protects both panes");
      MoexTwoPaneLayoutPolicy.Split slack = MoexTwoPaneLayoutPolicy.split(580, 0, 0, 24, 420, 260, 300, rtl);
      checkBounds(slack, 580, 0, 0, rtl);
      check(slack.chatEnd - slack.chatStart == 300 && slack.listEnd - slack.listStart == 256, "hysteresis gracefully clamps below combined minimum");
      for (int width : new int[] {0, 10, 100, 250}) {
        MoexTwoPaneLayoutPolicy.Split tiny = MoexTwoPaneLayoutPolicy.split(width, 0, 0, 24, 420, 260, 300, rtl);
        checkBounds(tiny, width, 0, 0, rtl);
      }
    }
    MoexTwoPaneLayoutPolicy.Split ltr = MoexTwoPaneLayoutPolicy.split(1600, 20, 40, 36, 570, 390, 450, false);
    MoexTwoPaneLayoutPolicy.Split rtl = MoexTwoPaneLayoutPolicy.split(1600, 40, 20, 36, 570, 390, 450, true);
    check(rtl.listStart == 1600 - ltr.listEnd && rtl.listEnd == 1600 - ltr.listStart, "RTL mirrors list with reversed insets");
    check(rtl.chatStart == 1600 - ltr.chatEnd && rtl.chatEnd == 1600 - ltr.chatStart, "RTL mirrors chat with reversed insets");
  }

  public static void main (String[] args) {
    thresholds();
    geometry();
    System.out.println("MoexTwoPaneLayoutPolicy: " + checks + " assertions passed");
  }
}
