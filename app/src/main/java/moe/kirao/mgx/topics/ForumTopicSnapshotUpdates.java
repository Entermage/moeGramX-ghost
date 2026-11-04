package moe.kirao.mgx.topics;

import org.drinkless.tdlib.TdApi;
import java.util.HashMap;
import java.util.Map;

/** Updates observed after a metadata request started must survive its older response. UI thread only. */
final class ForumTopicSnapshotUpdates {
  private static final int MAX_TOPICS = 256;
  private static final class Delta {
    TdApi.ForumTopicInfo info;
    TdApi.UpdateForumTopic update;
  }
  private final Map<Integer, Delta> topics = new HashMap<>();
  private boolean overflow;

  private Delta topic (int id) {
    Delta delta = topics.get(id);
    if (delta == null) {
      if (topics.size() >= MAX_TOPICS) { overflow = true; return null; }
      delta = new Delta();
      topics.put(id, delta);
    }
    return delta;
  }

  void record (TdApi.ForumTopicInfo info) {
    Delta delta = topic(info.forumTopicId);
    if (delta != null) delta.info = info;
  }

  void record (TdApi.UpdateForumTopic update) {
    Delta delta = topic(update.forumTopicId);
    if (delta != null) delta.update = update;
  }

  boolean overflowed () { return overflow; }

  private TdApi.ForumTopic apply (TdApi.ForumTopic value) {
    if (value == null || value.info == null) return value;
    Delta delta = topics.get(value.info.forumTopicId);
    if (delta == null) return value;
    TdApi.UpdateForumTopic update = delta.update;
    long readInbox = update != null ? Math.max(value.lastReadInboxMessageId, update.lastReadInboxMessageId) : value.lastReadInboxMessageId;
    int unread = update != null && value.lastMessage != null && readInbox >= value.lastMessage.id ? 0 : value.unreadCount;
    return new TdApi.ForumTopic(delta.info != null ? delta.info : value.info, value.lastMessage, value.order,
      update != null ? update.isPinned : value.isPinned, unread, readInbox,
      update != null ? Math.max(value.lastReadOutboxMessageId, update.lastReadOutboxMessageId) : value.lastReadOutboxMessageId,
      update != null ? update.unreadMentionCount : value.unreadMentionCount,
      update != null ? update.unreadReactionCount : value.unreadReactionCount,
      update != null ? update.unreadPollVoteCount : value.unreadPollVoteCount,
      update != null ? update.notificationSettings : value.notificationSettings,
      update != null ? update.draftMessage : value.draftMessage);
  }

  TdApi.Object apply (TdApi.Object value) {
    if (value instanceof TdApi.ForumTopic) return apply((TdApi.ForumTopic) value);
    if (value instanceof TdApi.ForumTopics && !topics.isEmpty()) {
      TdApi.ForumTopics page = (TdApi.ForumTopics) value;
      TdApi.ForumTopic[] merged = page.topics.clone();
      for (int i = 0; i < merged.length; i++) merged[i] = apply(merged[i]);
      return new TdApi.ForumTopics(page.totalCount, merged, page.nextOffsetDate, page.nextOffsetMessageId, page.nextOffsetForumTopicId);
    }
    return value;
  }
}
