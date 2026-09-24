package org.thunderdog.challegram.component.chat;

import java.util.Arrays;

/** Runs the production pagination policy without an Android device. */
public final class VisibleUnreadAnchorTest {
  private static int checks;

  private static void check (boolean condition, String description) {
    checks++;
    if (!condition) throw new AssertionError(description);
  }

  private static VisibleUnreadAnchor.Result page (VisibleUnreadAnchor anchor, long end, long[] ids, long... visible) {
    boolean[] flags = new boolean[ids.length];
    for (int i = 0; i < ids.length; i++) {
      for (long id : visible) if (ids[i] == id) flags[i] = true;
    }
    return anchor.acceptPage(ids, flags, end);
  }

  public static void main (String[] args) {
    VisibleUnreadAnchor hidden = new VisibleUnreadAnchor(100);
    long[] initial = new long[33];
    for (int i = 0; i < initial.length; i++) initial[i] = 119 - i;
    check(page(hidden, 150, initial, 100, 99) == VisibleUnreadAnchor.Result.CONTINUE,
      "visible old messages do not make a hidden unread window a valid target");
    check(hidden.cursor() == 119 && hidden.boundary() == 100, "advance raw cursor, freeze read boundary");
    check(page(hidden, 150, new long[] {150, 130, 120, 119}, 130, 120) == VisibleUnreadAnchor.Result.FOUND,
      "seek newer, not older, after hidden 101..119");
    check(hidden.targetMessageId() == 120, "select first visible incoming, not newest message");
    check(hidden.pages() == 2, "exact request count");
    check(page(hidden, 151, new long[] {151}, 151) == VisibleUnreadAnchor.Result.FOUND && hidden.pages() == 2,
      "completed search cannot be revived by late pages");

    VisibleUnreadAnchor sparse = new VisibleUnreadAnchor(100L << 20);
    check(page(sparse, 1000L << 20, new long[] {900L << 20, 300L << 20, 200L << 20, 99L << 20},
      900L << 20, 300L << 20, 99L << 20) == VisibleUnreadAnchor.Result.FOUND, "sparse TDLib IDs supported");
    check(sparse.targetMessageId() == 300L << 20, "deleted IDs and hidden album member skipped without ID arithmetic");

    VisibleUnreadAnchor outgoing = new VisibleUnreadAnchor(100);
    check(page(outgoing, 130, new long[] {125, 120, 110, 100}, 120, 100) == VisibleUnreadAnchor.Result.FOUND,
      "outgoing and pending messages have ineligible flags");
    check(outgoing.targetMessageId() == 120, "outgoing 110 is not an unread anchor");

    VisibleUnreadAnchor shortPage = new VisibleUnreadAnchor(100);
    check(page(shortPage, 500, new long[] {101}) == VisibleUnreadAnchor.Result.CONTINUE, "short page is not EOF");
    check(page(shortPage, 500, new long[] {120, 101}, 120) == VisibleUnreadAnchor.Result.FOUND, "short first cache page can continue");

    VisibleUnreadAnchor stalled = new VisibleUnreadAnchor(100);
    check(page(stalled, 500, new long[] {100, 90}, 90) == VisibleUnreadAnchor.Result.CONTINUE, "anchor-only initial page gets one forward retry");
    check(stalled.cursor() == 100, "retry does not manufacture an ID");
    check(page(stalled, 500, new long[] {100}) == VisibleUnreadAnchor.Result.STOP, "repeated cursor stops");
    check(page(stalled, 500, new long[] {200}, 200) == VisibleUnreadAnchor.Result.STOP, "stopped search stays stopped");

    VisibleUnreadAnchor repeated = new VisibleUnreadAnchor(100);
    check(page(repeated, 1000, new long[] {200, 100}) == VisibleUnreadAnchor.Result.CONTINUE, "first cursor advance");
    check(page(repeated, 1000, new long[] {199, 150}) == VisibleUnreadAnchor.Result.STOP, "cursor regression stops");
    check(repeated.cursor() == 200, "cursor never goes backwards");

    VisibleUnreadAnchor end = new VisibleUnreadAnchor(100);
    check(page(end, 200, new long[] {200, 150, 100}) == VisibleUnreadAnchor.Result.STOP, "hidden known tail ends search");
    check(new VisibleUnreadAnchor(100).acceptPage(new long[0], new boolean[0], 500) == VisibleUnreadAnchor.Result.STOP,
      "empty network result stops without assuming chat is empty");
    check(page(new VisibleUnreadAnchor(100), 0, new long[] {100}) == VisibleUnreadAnchor.Result.STOP,
      "unknown tail does not allow an unproductive retry");

    for (boolean foundAtLimit : new boolean[] {false, true}) {
      VisibleUnreadAnchor capped = new VisibleUnreadAnchor(100);
      for (int p = 1; p <= VisibleUnreadAnchor.MAX_PAGES; p++) {
        long id = 100 + p * 100L;
        VisibleUnreadAnchor.Result result = page(capped, 10000, new long[] {id},
          foundAtLimit && p == VisibleUnreadAnchor.MAX_PAGES ? new long[] {id} : new long[0]);
        check(result == (p < VisibleUnreadAnchor.MAX_PAGES ? VisibleUnreadAnchor.Result.CONTINUE :
          foundAtLimit ? VisibleUnreadAnchor.Result.FOUND : VisibleUnreadAnchor.Result.STOP), "five-page request cap, page " + p);
        check(capped.pages() == p, "count includes initial page");
        check(capped.delayMillis() == Math.min(1000, 200 * p), "bounded incremental delay");
      }
      check(capped.pages() == 5, "at most initial 33 + four 100-message pages");
    }

    VisibleUnreadAnchor large = new VisibleUnreadAnchor(Long.MAX_VALUE - 1000);
    check(page(large, Long.MAX_VALUE, new long[] {Long.MAX_VALUE, Long.MAX_VALUE - 5}, Long.MAX_VALUE - 5) == VisibleUnreadAnchor.Result.FOUND,
      "64-bit IDs do not overflow");
    check(large.targetMessageId() == Long.MAX_VALUE - 5, "large ID preserved");
    check(VisibleUnreadAnchor.PAGE_LIMIT == 100, "TDLib page limit respected");
    check(-(VisibleUnreadAnchor.PAGE_LIMIT - 1) > -VisibleUnreadAnchor.PAGE_LIMIT, "negative offset leaves an anchor slot");

    // Exhaustively compare selection against the minimum eligible real ID in an
    // album-like window, including a read boundary inside that album.
    long[] album = {105, 104, 103, 102, 101, 100, 99};
    for (int mask = 0; mask < (1 << album.length); mask++) {
      boolean[] flags = new boolean[album.length];
      long expected = 0;
      for (int i = 0; i < album.length; i++) {
        flags[i] = (mask & (1 << i)) != 0;
        if (flags[i] && album[i] > 102 && (expected == 0 || album[i] < expected)) expected = album[i];
      }
      VisibleUnreadAnchor anchor = new VisibleUnreadAnchor(102);
      VisibleUnreadAnchor.Result result = anchor.acceptPage(album, flags, 105);
      check(anchor.targetMessageId() == expected, "album target " + Arrays.toString(flags));
      check(result == (expected == 0 ? VisibleUnreadAnchor.Result.STOP : VisibleUnreadAnchor.Result.FOUND), "album result " + mask);
    }
    System.out.println("VisibleUnreadAnchor: " + checks + " checks passed");
  }
}
