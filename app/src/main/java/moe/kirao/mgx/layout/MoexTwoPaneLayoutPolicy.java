/*
 * moeGramX wide-window layout policy.
 * Derived from XGram's XgramTwoPane layout (GPL-3.0-or-later).
 */
package moe.kirao.mgx.layout;

/** Pure geometry shared by layout and regression tests; no physical-display assumptions. */
public final class MoexTwoPaneLayoutPolicy {
  private MoexTwoPaneLayoutPolicy () { }

  public static boolean shouldUseTwoPanes (int widthDp, int heightDp, boolean active) {
    int slack = active ? 20 : 0;
    return widthDp >= 1200 - slack || (widthDp >= 600 - slack && heightDp >= 480 - slack);
  }

  public static int defaultListWidthDp (int widthDp) {
    return Math.max(320, Math.min(420, Math.round(widthDp * .38f)));
  }

  public static final class Split {
    public final int listStart, listEnd, chatStart, chatEnd, gutterStart, gutterEnd;

    private Split (int listStart, int listEnd, int chatStart, int chatEnd, int gutterStart, int gutterEnd) {
      this.listStart = listStart;
      this.listEnd = listEnd;
      this.chatStart = chatStart;
      this.chatEnd = chatEnd;
      this.gutterStart = gutterStart;
      this.gutterEnd = gutterEnd;
    }
  }

  public static Split split (int width, int insetLeft, int insetRight, int gutterWidth,
                             int desiredListWidth, int minListWidth, int minChatWidth, boolean rtl) {
    width = Math.max(0, width);
    int start = Math.min(width, Math.max(0, insetLeft));
    int end = Math.max(start, width - Math.max(0, insetRight));
    int gutter = Math.max(0, Math.min(end - start, gutterWidth));
    int total = end - start - gutter;
    // The 20dp hysteresis can temporarily leave less than both minimum widths; protect the chat first.
    int maxList = Math.max(0, total - Math.max(0, minChatWidth));
    int minList = Math.min(Math.max(0, minListWidth), maxList);
    int list = Math.max(minList, Math.min(maxList, desiredListWidth));
    if (rtl) {
      int listStart = end - list;
      int chatEnd = listStart - gutter;
      return new Split(listStart, end, start, chatEnd, chatEnd, listStart);
    }
    int listEnd = start + list;
    int chatStart = listEnd + gutter;
    return new Split(start, listEnd, chatStart, end, listEnd, chatStart);
  }
}
