package moe.kirao.mgx.topics;

import org.drinkless.tdlib.TdApi;

/** Screen-local read progress. No server read requests or separate persistent read database. */
public final class ForumTopicCounters {
  private ForumTopicCounters () { }

  public static TdApi.ForumTopic copy (TdApi.ForumTopic topic) {
    return new TdApi.ForumTopic(topic.info, topic.lastMessage, topic.order, topic.isPinned,
      topic.unreadCount, topic.lastReadInboxMessageId, topic.lastReadOutboxMessageId,
      topic.unreadMentionCount, topic.unreadReactionCount, topic.unreadPollVoteCount,
      topic.notificationSettings, topic.draftMessage);
  }

  /** A delayed/server snapshot must not undo a newer read on this screen (including Ghost Mode). */
  public static TdApi.ForumTopic mergeSnapshot (TdApi.ForumTopic current, TdApi.ForumTopic received, boolean changedWhileLoading) {
    TdApi.ForumTopic result = copy(received);
    if (current != null && current.info.chatId == received.info.chatId &&
        current.info.forumTopicId == received.info.forumTopicId) {
      if (received.lastReadInboxMessageId < current.lastReadInboxMessageId ||
          (changedWhileLoading && received.lastReadInboxMessageId == current.lastReadInboxMessageId)) {
        result.lastReadInboxMessageId = current.lastReadInboxMessageId;
        result.unreadCount = current.unreadCount;
      }
      if (changedWhileLoading && current.lastMessage != null &&
          (received.lastMessage == null || current.lastMessage.id > received.lastMessage.id)) {
        result.lastMessage = current.lastMessage;
      }
    }
    return result;
  }

  /** Counts individual incoming messages, including each album item; IDs are not contiguous within a topic. */
  public static boolean isIncomingAfter (TdApi.Message message, long chatId, int topicId, long readId) {
    return message.chatId == chatId && !message.isOutgoing && message.schedulingState == null &&
      message.id > readId && XgramForums.isInTopic(message, topicId);
  }
}
