package org.thunderdog.challegram.telegram;

import org.drinkless.tdlib.TdApi;

public interface ForumTopicInfoListener {
  default void onForumTopicInfoChanged (TdApi.ForumTopicInfo info) { }
  default void onForumTopicUpdated (long chatId, long messageThreadId, boolean isPinned, long lastReadInboxMessageId, long lastReadOutboxMessageId, TdApi.ChatNotificationSettings notificationSettings) { }
  // XGram: the full update, including unread mention, reaction and poll vote counters and the draft.
  default void onForumTopicUpdated (TdApi.UpdateForumTopic update) { }
}
