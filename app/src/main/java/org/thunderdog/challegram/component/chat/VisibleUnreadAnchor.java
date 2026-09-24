package org.thunderdog.challegram.component.chat;

/** Bounded forward search in raw history; a read cursor need not itself be visible. */
public final class VisibleUnreadAnchor {
  public static final int PAGE_LIMIT = 100;
  public static final int MAX_PAGES = 5;

  public enum Result { FOUND, CONTINUE, STOP }

  private final long boundary;
  private long cursor, targetMessageId;
  private int pages;
  private Result terminal;

  public VisibleUnreadAnchor (long readBoundary) {
    boundary = cursor = readBoundary;
  }

  public Result acceptPage (long[] ids, boolean[] visibleIncoming, long knownLastMessageId) {
    if (ids.length != visibleIncoming.length) throw new IllegalArgumentException("Mismatched page flags");
    if (terminal != null) return terminal;
    pages++;
    long nextCursor = cursor;
    for (int i = 0; i < ids.length; i++) {
      long id = ids[i];
      nextCursor = Math.max(nextCursor, id);
      if (id > boundary && visibleIncoming[i] && (targetMessageId == 0 || id < targetMessageId)) {
        targetMessageId = id;
      }
    }
    if (targetMessageId != 0) return terminal = Result.FOUND;
    boolean advanced = nextCursor > cursor;
    cursor = nextCursor;
    if (ids.length == 0 || pages >= MAX_PAGES ||
        knownLastMessageId != 0 && cursor >= knownLastMessageId) {
      return terminal = Result.STOP;
    }
    // TDLib can initially return only a cached anchor. Retry once with a forward
    // window, but never loop on the same cursor. A short page alone is not EOF.
    if (!advanced && !(pages == 1 && knownLastMessageId > cursor)) {
      return terminal = Result.STOP;
    }
    return Result.CONTINUE;
  }

  public long boundary () { return boundary; }
  public long cursor () { return cursor; }
  public long targetMessageId () { return targetMessageId; }
  public int pages () { return pages; }
  public long delayMillis () { return Math.min(1000L, 200L * pages); }
}
