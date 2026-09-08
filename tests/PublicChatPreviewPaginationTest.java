package org.thunderdog.challegram.telegram;

/** Standalone regression checks; requires only PublicChatPreviewPagination and a JDK. */
public final class PublicChatPreviewPaginationTest {
  private static int checks;

  private static void check (boolean value, String reason) {
    checks++;
    if (!value) throw new AssertionError(reason);
  }

  private static void equal (long actual, long expected, String reason) {
    check(actual == expected, reason + ": expected " + expected + ", got " + actual);
  }

  public static void main (String[] args) {
    for (String invalid : new String[] {null, "", "0", "-1", "+1", " 1", "1 ", "1.2", "2147483648", "9223372036854775808"}) {
      equal(PublicChatPreviewPagination.parseServerMessageId(invalid), 0, "invalid boundary " + invalid);
    }
    equal(PublicChatPreviewPagination.parseServerMessageId("1"), 1, "smallest server ID");
    equal(PublicChatPreviewPagination.parseServerMessageId("2147483647"), Integer.MAX_VALUE, "largest server ID");

    PublicChatPreviewPagination older = new PublicChatPreviewPagination(100, 0, false);
    check(older.beginRequest(), "older first request");
    equal(older.offset(), 0, "older excludes boundary in selection, not fabricated cursor");
    equal(older.fromMessageId, 100, "original boundary preserved");
    equal(older.findVisibleMessage(new long[] {95, 70}, new boolean[] {true, true}), 0,
      "deleted boundary and message-ID gaps select a returned message");
    equal(older.findVisibleMessage(new long[] {100, 99, 90}, new boolean[] {true, false, true}), 2,
      "boundary and filtered message excluded");
    check(older.advance(new long[] {100, 99, 90}, 0), "hidden raw page advances");
    equal(older.fromMessageId, 90, "cursor uses raw oldest ID");
    check(!older.advance(new long[] {90, 100}, 0), "history cursor cannot stall or reverse");

    PublicChatPreviewPagination newer = new PublicChatPreviewPagination(0, 100, false);
    check(newer.beginRequest(), "newer first request");
    check(newer.offset() < 0 && newer.limit() > -newer.offset(), "valid negative offset with anchor slot");
    equal(newer.findVisibleMessage(new long[] {150, 120, 100, 80}, new boolean[] {true, true, true, true}), 1,
      "nearest real newer message selected");
    equal(newer.findVisibleMessage(new long[] {170, 130}, new boolean[] {true, true}), 1,
      "newer page selects an existing ID when boundary and adjacent IDs are deleted");
    check(newer.advance(new long[] {150, 120, 100, 80}, 0), "newer raw page advances");
    equal(newer.fromMessageId, 150, "newer cursor uses raw maximum");
    check(!newer.advance(new long[] {150, 120}, 0), "newer cursor cannot stall");

    PublicChatPreviewPagination interval = new PublicChatPreviewPagination(200, 100, false);
    check(interval.beginRequest(), "bounded interval");
    equal(interval.findVisibleMessage(new long[] {210, 200, 180, 100, 90}, new boolean[] {true, true, true, true, true}), 2,
      "both bounds strictly applied");
    check(!interval.advance(new long[] {150, 100, 90}, 0), "stop after crossing lower bound");
    check(!new PublicChatPreviewPagination(100, 100, false).beginRequest(), "empty interval stops before request");
    check(!new PublicChatPreviewPagination(50, 100, false).beginRequest(), "reversed interval stops before request");

    PublicChatPreviewPagination search = new PublicChatPreviewPagination(100, 0, true);
    check(search.beginRequest(), "search first request");
    check(search.advance(new long[0], 70), "empty search page can use TDLib raw cursor");
    equal(search.fromMessageId, 70, "TDLib cursor preserved");
    check(!search.advance(new long[] {60}, 0), "zero search cursor ends pagination");
    check(!search.advance(new long[] {60}, 80), "search cursor cannot move backwards");
    check(!search.advance(new long[] {60}, 70), "repeated search cursor stops");

    PublicChatPreviewPagination newerSearch = new PublicChatPreviewPagination(0, 100, true);
    check(newerSearch.beginRequest(), "newer search first request");
    check(newerSearch.advance(new long[] {150, 120, 100}, 0), "newer search does not use the older-direction end cursor");
    equal(newerSearch.fromMessageId, 150, "newer search uses raw maximum");

    PublicChatPreviewPagination capped = new PublicChatPreviewPagination(1000, 0, false);
    for (int i = 0; i < PublicChatPreviewPagination.MAX_PAGES; i++) {
      check(capped.beginRequest(), "bounded page " + i);
      check(capped.findVisibleMessage(new long[] {900 - i}, new boolean[] {false}) == -1, "hidden page has no target");
      boolean advanced = capped.advance(new long[] {900 - i}, 0);
      check(advanced == (i + 1 < PublicChatPreviewPagination.MAX_PAGES), "stop at page budget");
    }
    check(!capped.beginRequest(), "no fifth request");
    System.out.println("PublicChatPreviewPagination: " + checks + " checks passed");
  }
}
