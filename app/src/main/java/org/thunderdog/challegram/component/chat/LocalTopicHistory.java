package org.thunderdog.challegram.component.chat;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import java.util.ArrayList;

/**
 * A forum topic's newest messages found in its chat's local history, shown as a display-only
 * {@link MessageHistoryPreview} window while the topic's own history (always a server query) loads.
 * Pages arrive newest first, from the end of the chat's stored history; the scan is bounded.
 * Forums read as topics often store little chat history, so the window is only used where the
 * loading history will open at the same place.
 */
public final class LocalTopicHistory {
  public static final int PAGE_SIZE = 100, MAX_PAGES = 3, MAX_MESSAGES = MessageHistoryPreview.MAX_MESSAGES;
  /** Fewer rows would show the topic's last message alone, then a page replacing it. */
  public static final int MIN_MESSAGES = 5;

  public final long chatId, topicId;
  private final long requestedId;
  private final boolean unreadEntry;
  private final ArrayList<TdApi.Message> found = new ArrayList<>();
  private long nextFromId;
  private int pages;
  private boolean tail, truncated;

  /** @param requestedId the read boundary of an unread entry, else the message to restore */
  public LocalTopicHistory (long chatId, long topicId, long requestedId, boolean unreadEntry) {
    this.chatId = chatId;
    this.topicId = topicId;
    this.requestedId = requestedId;
    this.unreadEntry = unreadEntry;
  }

  /** Where the next local page starts: the chat's last message, then the oldest message seen. */
  public long nextFromMessageId () {
    return nextFromId;
  }

  /**
   * Takes one page of the chat's local history and returns whether another page is needed.
   * A scan that begins at the chat's last message has seen every newer message of the topic,
   * so its newest match is the topic's tail.
   */
  public boolean accept (TdApi.Message[] page, long chatLastMessageId) {
    boolean first = pages++ == 0;
    long oldest = nextFromId;
    int added = 0;
    for (TdApi.Message message : page) {
      // With offset 0 a page repeats its starting message.
      if (message == null || (!first && message.id >= nextFromId)) continue;
      if (first && added == 0) tail = chatLastMessageId != 0 && message.id == chatLastMessageId;
      oldest = message.id;
      added++;
      if (found.size() < MAX_MESSAGES && belongs(message)) found.add(message);
    }
    if (added == 0) return false; // the stored history ends here
    nextFromId = oldest;
    truncated = found.size() >= MAX_MESSAGES || pages >= MAX_PAGES;
    return !truncated;
  }

  private boolean belongs (TdApi.Message message) {
    // Same exclusions as a remembered window: expiring, pending and scheduled rows never enter it.
    if (message.chatId != chatId || message.id <= 0 || message.sendingState != null ||
        message.schedulingState != null || message.selfDestructType != null || message.autoDeleteIn > 0) return false;
    long actual = message.topicId instanceof TdApi.MessageTopicForum ? ((TdApi.MessageTopicForum) message.topicId).forumTopicId : 0;
    return actual == topicId || (topicId == 1 && actual == 0);
  }

  /** Messages for the window, newest first; an album cut by the scan bound is left out. */
  public TdApi.Message[] messages () {
    ArrayList<TdApi.Message> result = new ArrayList<>(found);
    if (truncated && !result.isEmpty()) {
      long album = result.get(result.size() - 1).mediaAlbumId;
      if (album != 0) result.removeIf(message -> message.mediaAlbumId == album);
    }
    return result.toArray(new TdApi.Message[0]);
  }

  /**
   * Whether these rows can stand in for the loading history: a few rows at least and, for an unread
   * entry, both sides of the read boundary, as the history opens at the first unread row.
   */
  public boolean isUsable (TdApi.Message[] messages) {
    if (messages.length < MIN_MESSAGES) return false;
    return !unreadEntry || (messages[messages.length - 1].id <= requestedId && requestedId < messages[0].id);
  }

  /** The row to keep in view: the first unread row, else the last at or before the position, else the newest. */
  public long anchorId (TdApi.Message[] messages) {
    if (messages.length == 0) return 0;
    if (unreadEntry) {
      for (int i = messages.length - 1; i >= 0; i--) {
        if (messages[i].id > requestedId) return messages[i].id;
      }
    } else if (requestedId > 0 && requestedId < messages[0].id) {
      for (TdApi.Message message : messages) {
        if (message.id <= requestedId) return message.id;
      }
    }
    return messages[0].id;
  }

  public int anchorOffset () {
    return unreadEntry ? MessageHistoryPreview.OFFSET_TOP : 0;
  }

  public boolean isTail () {
    return tail;
  }

  /** Stores the result as the topic's preview window; false when it cannot stand in for the history. */
  public boolean publish (Tdlib tdlib) {
    TdApi.Message[] messages = messages();
    if (!isUsable(messages)) return false;
    MessageHistoryPreview.put(tdlib, chatId, topicId, messages, anchorId(messages), anchorOffset(), tail);
    return true;
  }
}
