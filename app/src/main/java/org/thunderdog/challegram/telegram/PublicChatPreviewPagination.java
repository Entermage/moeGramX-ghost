package org.thunderdog.challegram.telegram;

/** Bounded, exclusive message-ID pagination for public chat preview links. */
final class PublicChatPreviewPagination {
  static final int PAGE_SIZE = 20;
  static final int MAX_PAGES = 4;

  final long beforeMessageId;
  final long afterMessageId;
  final boolean newer;
  final boolean searching;
  long fromMessageId;
  int requestedPages;

  PublicChatPreviewPagination (long beforeMessageId, long afterMessageId, boolean searching) {
    this.beforeMessageId = beforeMessageId;
    this.afterMessageId = afterMessageId;
    this.searching = searching;
    this.newer = beforeMessageId == 0 && afterMessageId != 0;
    this.fromMessageId = newer ? afterMessageId : beforeMessageId;
  }

  static int parseServerMessageId (String value) {
    if (value == null || value.isEmpty()) return 0;
    for (int i = 0; i < value.length(); i++) {
      if (value.charAt(i) < '0' || value.charAt(i) > '9') return 0;
    }
    try {
      int messageId = Integer.parseInt(value);
      return messageId > 0 ? messageId : 0;
    } catch (NumberFormatException ignored) {
      return 0;
    }
  }

  boolean beginRequest () {
    if (requestedPages >= MAX_PAGES || fromMessageId == 0 ||
        beforeMessageId != 0 && afterMessageId != 0 && beforeMessageId <= afterMessageId) {
      return false;
    }
    requestedPages++;
    return true;
  }

  int offset () {
    return newer ? -PAGE_SIZE : 0;
  }

  int limit () {
    // SearchChatMessages requires limit > -offset, including its anchor slot.
    return newer ? PAGE_SIZE + 1 : PAGE_SIZE;
  }

  int findVisibleMessage (long[] messageIds, boolean[] visible) {
    int candidate = -1;
    for (int i = 0; i < messageIds.length; i++) {
      long messageId = messageIds[i];
      if (!visible[i] || messageId <= 0 ||
          beforeMessageId != 0 && messageId >= beforeMessageId ||
          afterMessageId != 0 && messageId <= afterMessageId) {
        continue;
      }
      if (candidate == -1 || (newer ? messageId < messageIds[candidate] : messageId > messageIds[candidate])) {
        candidate = i;
      }
    }
    return candidate;
  }

  boolean advance (long[] rawMessageIds, long nextSearchFromMessageId) {
    if (requestedPages >= MAX_PAGES) return false;
    long nextMessageId = 0;
    for (long messageId : rawMessageIds) {
      if (messageId <= 0) continue;
      if (nextMessageId == 0 || (newer ? messageId > nextMessageId : messageId < nextMessageId)) {
        nextMessageId = messageId;
      }
    }
    if (searching && !newer) {
      // TDLib's search cursor can advance even if it returns an empty page.
      nextMessageId = nextSearchFromMessageId;
    }
    if (nextMessageId <= 0 || (newer ? nextMessageId <= fromMessageId : nextMessageId >= fromMessageId)) {
      return false;
    }
    if (!newer && afterMessageId != 0 && nextMessageId <= afterMessageId) return false;
    fromMessageId = nextMessageId;
    return true;
  }
}
