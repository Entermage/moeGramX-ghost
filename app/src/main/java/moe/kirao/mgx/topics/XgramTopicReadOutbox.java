/*
 * This file is a part of XGram, a fork of Telegram X
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
package moe.kirao.mgx.topics;

import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * How far others have read each forum topic (its lastReadOutboxMessageId). In a forum TDLib keeps the read state
 * per topic and doesn't move the chat's own lastReadOutboxMessageId, so bubbles inside a topic would show one tick
 * for messages the topic list already shows as read. Fed by updateForumTopic and loaded topics.
 */
public final class XgramTopicReadOutbox {
  private XgramTopicReadOutbox () { }

  private static final Map<String, Long> readOutbox = new ConcurrentHashMap<>();

  private static String key (Tdlib tdlib, long chatId, int forumTopicId) {
    return tdlib.id() + "_" + chatId + "_" + forumTopicId;
  }

  /** Remembers the topic's read position; returns true if it moved forward. */
  public static boolean set (Tdlib tdlib, long chatId, int forumTopicId, long lastReadOutboxMessageId) {
    if (lastReadOutboxMessageId == 0) {
      return false;
    }
    String key = key(tdlib, chatId, forumTopicId);
    boolean[] advanced = {false};
    readOutbox.compute(key, (ignored, old) -> {
      if (old != null && old >= lastReadOutboxMessageId) return old;
      advanced[0] = true;
      return lastReadOutboxMessageId;
    });
    return advanced[0];
  }

  public static void set (Tdlib tdlib, long chatId, @Nullable TdApi.ForumTopic topic) {
    if (topic != null && topic.info != null) {
      set(tdlib, chatId, topic.info.forumTopicId, topic.lastReadOutboxMessageId);
    }
  }

  public static long get (Tdlib tdlib, long chatId, int forumTopicId) {
    Long value = readOutbox.get(key(tdlib, chatId, forumTopicId));
    return value != null ? value : 0;
  }

  public static void forgetAccount (int accountId) {
    readOutbox.keySet().removeIf(key -> key.startsWith(accountId + "_"));
  }

  /** The read position that applies to a message: its topic's, in a forum (General when the message names none). */
  public static long forMessage (Tdlib tdlib, TdApi.Message message) {
    if (message == null || !tdlib.isForum(message.chatId)) {
      return 0;
    }
    int forumTopicId = message.topicId instanceof TdApi.MessageTopicForum ? ((TdApi.MessageTopicForum) message.topicId).forumTopicId : XgramForums.GENERAL_TOPIC_ID;
    return get(tdlib, message.chatId, forumTopicId);
  }
}
