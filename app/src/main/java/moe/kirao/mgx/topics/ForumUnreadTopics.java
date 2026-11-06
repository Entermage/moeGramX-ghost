package moe.kirao.mgx.topics;

import org.drinkless.tdlib.TdApi;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Which topics of one forum have unread messages, for its chat list badge. Taken from a page of the newest topics
 * and the topics the topic list loaded, then kept from new messages and topic read updates on this device. Unread
 * means as in the topic list: see {@link XgramForums#normalizeUnread}.
 */
final class ForumUnreadTopics {
  private static final class Topic {
    long lastReadInboxMessageId, lastMessageId;
    boolean unread;
    /** Its last message was deleted: what it has instead is known from the server only. Counted as before until then. */
    boolean lastDeleted;
    /** Fetched by itself with this last message: missing from a page, it is where the server lists it. */
    boolean fetched;
    TdApi.ChatNotificationSettings notificationSettings;
  }

  private final HashMap<Integer, Topic> topics = new HashMap<>();
  private boolean loaded;

  boolean isLoaded () {
    return loaded;
  }

  /**
   * The first page of the newest topics, newer than anything counted before it (messages that came while it loaded
   * are applied after it). Complete, it is all the topics: it replaces what was known. Otherwise it tells only about
   * the topics in it: a known topic missing from it isn't read, so it is kept as it was.
   *
   * @return the kept unread topics it leaves unsure, to fetch by themselves: their last message was deleted, or by it
   * they would be on the page (deleted elsewhere, or the forum lists its topics by creation date)
   */
  List<Integer> setTopics (TdApi.ForumTopic[] page, boolean complete) {
    HashMap<Integer, Topic> known = complete || topics.isEmpty() ? null : new HashMap<>(topics);
    topics.clear();
    long oldestShown = Long.MAX_VALUE;
    for (TdApi.ForumTopic forumTopic : page) {
      Topic topic = new Topic();
      topics.put(forumTopic.info.forumTopicId, topic);
      set(topic, forumTopic, forumTopic.lastReadInboxMessageId);
      if (!forumTopic.isPinned && forumTopic.lastMessage != null) {
        // Pinned topics come first whatever their last message: the others are the newest by it.
        oldestShown = Math.min(oldestShown, topic.lastMessageId);
      }
    }
    List<Integer> unsure = new ArrayList<>();
    if (known != null) {
      for (Map.Entry<Integer, Topic> entry : known.entrySet()) {
        Topic topic = entry.getValue();
        if (topics.containsKey(entry.getKey())) {
          continue;
        }
        topics.put(entry.getKey(), topic);
        if (topic.unread && (topic.lastDeleted || (topic.lastMessageId >= oldestShown && !topic.fetched))) {
          unsure.add(entry.getKey());
        }
      }
    }
    loaded = true;
    return unsure;
  }

  /**
   * A topic as the server has it, from the topic list loading or refreshing it, or fetched by itself: possibly older
   * than what came since.
   */
  boolean putTopic (TdApi.ForumTopic forumTopic) {
    TdApi.Message last = forumTopic.lastMessage;
    long lastMessageId = last != null ? last.id : 0;
    long readInboxMessageId = forumTopic.lastReadInboxMessageId;
    Topic topic = topics.get(forumTopic.info.forumTopicId);
    if (topic == null) {
      topic = new Topic();
      topics.put(forumTopic.info.forumTopicId, topic);
    } else if (topic.lastDeleted ? lastMessageId == topic.lastMessageId : lastMessageId < topic.lastMessageId) {
      // Older than a message counted since, or still with the deleted last message: it tells nothing newer.
      return false;
    } else if (lastMessageId == topic.lastMessageId) {
      // An older snapshot of the same messages doesn't unread what was read since.
      readInboxMessageId = Math.max(readInboxMessageId, topic.lastReadInboxMessageId);
    }
    return set(topic, forumTopic, readInboxMessageId);
  }

  /** {@link #putTopic}, for a topic a page left unsure, fetched by itself: until its last message changes, it is sure. */
  boolean putFetchedTopic (TdApi.ForumTopic forumTopic) {
    boolean changed = putTopic(forumTopic);
    Topic topic = topics.get(forumTopic.info.forumTopicId);
    TdApi.Message last = forumTopic.lastMessage;
    if (topic != null && !topic.lastDeleted && topic.lastMessageId == (last != null ? last.id : 0)) {
      topic.fetched = true;
    }
    return changed;
  }

  private static boolean set (Topic topic, TdApi.ForumTopic forumTopic, long readInboxMessageId) {
    TdApi.Message last = forumTopic.lastMessage;
    boolean unread = forumTopic.unreadCount > 0 &&
      !(last != null && (last.isOutgoing || readInboxMessageId >= last.id));
    boolean changed = topic.unread != unread ||
      isMuted(topic.notificationSettings) != isMuted(forumTopic.notificationSettings) ||
      inheritsMute(topic.notificationSettings) != inheritsMute(forumTopic.notificationSettings);
    topic.lastReadInboxMessageId = readInboxMessageId;
    long lastMessageId = last != null ? last.id : 0;
    if (topic.lastMessageId != lastMessageId) {
      topic.fetched = false;
    }
    topic.lastMessageId = lastMessageId;
    topic.lastDeleted = false;
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
    topic.lastDeleted = false;
    topic.fetched = false;
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

  /**
   * Deleting the last message of an unread topic may leave nothing unread in it: only the server tells, by a new page
   * or by the topic itself. Until then it is counted.
   */
  boolean needsReloadAfterDelete (long[] messageIds) {
    boolean reload = false;
    for (Topic topic : topics.values()) {
      if (topic.unread) {
        for (long messageId : messageIds) {
          if (messageId == topic.lastMessageId) {
            topic.lastDeleted = true;
            reload = true;
            break;
          }
        }
      }
    }
    return reload;
  }

  /** Whether the topic is known and counted as unread. */
  boolean isUnread (int forumTopicId) {
    Topic topic = topics.get(forumTopicId);
    return topic != null && topic.unread;
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
