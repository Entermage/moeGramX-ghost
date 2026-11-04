package moe.kirao.mgx.topics;

import org.drinkless.tdlib.TdApi;

import java.util.HashMap;

/**
 * Which topics of one forum have unread messages, for its chat list badge. Taken from a page of the newest topics,
 * then kept from new messages and topic read updates on this device. Unread means as in the topic list: see
 * {@link XgramForums#normalizeUnread}.
 */
final class ForumUnreadTopics {
  private static final class Topic {
    long lastReadInboxMessageId, lastMessageId;
    boolean unread;
    TdApi.ChatNotificationSettings notificationSettings;
  }

  private final HashMap<Integer, Topic> topics = new HashMap<>();
  private boolean loaded;

  boolean isLoaded () {
    return loaded;
  }

  /** A loaded page replaces what was known: topics outside it aren't counted until loaded or active again. */
  void setTopics (TdApi.ForumTopic[] page) {
    topics.clear();
    for (TdApi.ForumTopic forumTopic : page) {
      putTopic(forumTopic);
    }
    loaded = true;
  }

  /** A topic as the server has it, from a page or from the topic list loading or refreshing it. */
  boolean putTopic (TdApi.ForumTopic forumTopic) {
    TdApi.Message last = forumTopic.lastMessage;
    long lastMessageId = last != null ? last.id : 0;
    Topic topic = topics.get(forumTopic.info.forumTopicId);
    if (topic == null) {
      topic = new Topic();
      topics.put(forumTopic.info.forumTopicId, topic);
    } else if (lastMessageId < topic.lastMessageId) {
      // Older than a message counted since: a deleted last message loads the page again instead.
      return false;
    }
    boolean unread = forumTopic.unreadCount > 0 &&
      !(last != null && (last.isOutgoing || forumTopic.lastReadInboxMessageId >= last.id));
    boolean changed = topic.unread != unread ||
      isMuted(topic.notificationSettings) != isMuted(forumTopic.notificationSettings) ||
      inheritsMute(topic.notificationSettings) != inheritsMute(forumTopic.notificationSettings);
    topic.lastReadInboxMessageId = forumTopic.lastReadInboxMessageId;
    topic.lastMessageId = lastMessageId;
    topic.unread = unread;
    topic.notificationSettings = forumTopic.notificationSettings;
    return changed;
  }

  /** A new or just sent message. Pending ones are left out: they don't have their place among the server's yet. */
  boolean onMessage (int forumTopicId, TdApi.Message message) {
    if (message.sendingState != null || message.schedulingState != null) {
      return false;
    }
    Topic topic = topics.get(forumTopicId);
    if (topic == null) {
      // A topic past the loaded page: with this message it is among the newest ones.
      topic = new Topic();
      topics.put(forumTopicId, topic);
    } else if (message.id <= topic.lastMessageId) {
      return false;
    }
    topic.lastMessageId = message.id;
    boolean unread = !message.isOutgoing && message.id > topic.lastReadInboxMessageId;
    boolean changed = topic.unread != unread;
    topic.unread = unread;
    return changed;
  }

  /** A read position or notification settings of a topic (updateForumTopic). */
  boolean onTopicUpdated (TdApi.UpdateForumTopic update) {
    Topic topic = topics.get(update.forumTopicId);
    if (topic == null) {
      // Kept for a message that may come later: compared with this position, not with none.
      topic = new Topic();
      topics.put(update.forumTopicId, topic);
    }
    boolean changed = isMuted(topic.notificationSettings) != isMuted(update.notificationSettings) ||
      inheritsMute(topic.notificationSettings) != inheritsMute(update.notificationSettings);
    topic.lastReadInboxMessageId = update.lastReadInboxMessageId;
    topic.notificationSettings = update.notificationSettings;
    // The update carries no counter: read up to the last message, nothing is left; read partly, something is.
    if (topic.unread && update.lastReadInboxMessageId >= topic.lastMessageId) {
      topic.unread = false;
      changed = true;
    }
    return changed;
  }

  boolean removeTopic (int forumTopicId) {
    Topic topic = topics.remove(forumTopicId);
    return topic != null && topic.unread;
  }

  /** Deleting the last message of an unread topic may leave nothing unread in it: only a new page tells. */
  boolean needsReloadAfterDelete (long[] messageIds) {
    for (Topic topic : topics.values()) {
      if (topic.unread) {
        for (long messageId : messageIds) {
          if (messageId == topic.lastMessageId) {
            return true;
          }
        }
      }
    }
    return false;
  }

  int unreadCount () {
    int count = 0;
    for (Topic topic : topics.values()) {
      if (topic.unread) {
        count++;
      }
    }
    return count;
  }

  /** Unread topics that follow the chat's mute setting. */
  int unreadInheritingMuteCount () {
    int count = 0;
    for (Topic topic : topics.values()) {
      if (topic.unread && inheritsMute(topic.notificationSettings)) {
        count++;
      }
    }
    return count;
  }

  /** Unread topics unmuted by their own setting. */
  int unreadUnmutedCount () {
    int count = 0;
    for (Topic topic : topics.values()) {
      if (topic.unread && !inheritsMute(topic.notificationSettings) && !isMuted(topic.notificationSettings)) {
        count++;
      }
    }
    return count;
  }

  // As XgramForums.isTopicMuted, without the chat's setting.

  private static boolean inheritsMute (TdApi.ChatNotificationSettings settings) {
    return settings == null || settings.useDefaultMuteFor;
  }

  private static boolean isMuted (TdApi.ChatNotificationSettings settings) {
    return settings != null && !settings.useDefaultMuteFor && settings.muteFor > 0;
  }
}
