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
import org.thunderdog.challegram.telegram.TdlibForumTopicManager;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Which forum topics are muted, for notifications. TDLib builds local notifications from the chat's mute state only
 * and never looks at the topic's own notification settings, so a muted topic keeps notifying while the app is
 * connected. This remembers the time until which each topic is muted, fed by updateForumTopic, loaded topics and
 * the mute actions themselves. The time is stored, not the duration, because TDLib sends nothing when a topic
 * mute expires.
 * <p>
 * What stays as it is: an unmuted topic inside a muted forum never notifies, because TDLib does not create the
 * notification at all.
 */
public final class XgramTopicMute {
  private XgramTopicMute () { }

  /** A topic's own mention/pin setting: inherited from the chat (which TDLib applied already), or set on the topic. */
  static final int INHERITED = 0, ENABLED = 1, DISABLED = 2;

  private static final class Settings {
    /** Muted until this time (ms), 0 when the topic is not muted by its own settings. */
    final long mutedUntil;
    final int mentions, pinned;
    Settings (long mutedUntil, int mentions, int pinned) {
      this.mutedUntil = mutedUntil;
      this.mentions = mentions;
      this.pinned = pinned;
    }
  }

  /** Key: account, chat and topic. */
  private static final Map<String, Settings> settingsByTopic = new ConcurrentHashMap<>();
  private static final java.util.Set<String> pending = ConcurrentHashMap.newKeySet();

  private static String key (Tdlib tdlib, long chatId, int forumTopicId) {
    return tdlib.id() + "_" + chatId + "_" + forumTopicId;
  }

  private static int ownSetting (boolean useDefault, boolean disabled) {
    return useDefault ? INHERITED : disabled ? DISABLED : ENABLED;
  }

  /** Remembers the topic's notification settings; returns the time until which it is muted (0 when it is not). */
  public static long onSettings (Tdlib tdlib, long chatId, int forumTopicId, @Nullable TdApi.ChatNotificationSettings settings) {
    long until;
    if (settings == null || settings.useDefaultMuteFor || settings.muteFor <= 0) {
      until = 0;
    } else {
      until = System.currentTimeMillis() + settings.muteFor * 1000L;
    }
    int mentions = settings != null ? ownSetting(settings.useDefaultDisableMentionNotifications, settings.disableMentionNotifications) : INHERITED;
    int pinned = settings != null ? ownSetting(settings.useDefaultDisablePinnedMessageNotifications, settings.disablePinnedMessageNotifications) : INHERITED;
    settingsByTopic.put(key(tdlib, chatId, forumTopicId), new Settings(until, mentions, pinned));
    return until;
  }

  /**
   * TDLib already applied the chat's settings: a mention or pin the chat notifies about is in the Mentions
   * group, everything else in the Messages group. A topic's mute silences the Messages group only; its mentions
   * and pins still notify unless the topic itself disables them. In the Messages group a mention or pin means the
   * chat disabled that kind of notification, which the topic's own setting may enable again.
   */
  static boolean dropsNotification (long mutedUntil, int mentions, int pinned, boolean mentionGroup,
                                    boolean isPin, boolean containsMention, long now) {
    int own = isPin ? pinned : mentions;
    if (mentionGroup) {
      return own == DISABLED;
    }
    if (mutedUntil <= now) {
      return false;
    }
    return !((isPin || containsMention) && own == ENABLED);
  }

  public static void onSettings (Tdlib tdlib, long chatId, @Nullable TdApi.ForumTopic topic) {
    if (topic != null && topic.info != null) {
      onSettings(tdlib, chatId, topic.info.forumTopicId, topic.notificationSettings);
    }
  }

  /** Whether the topic's settings have been seen since the app started. */
  public static boolean isKnown (Tdlib tdlib, long chatId, int forumTopicId) {
    return settingsByTopic.containsKey(key(tdlib, chatId, forumTopicId));
  }

  /** Whether the topic is muted by its own settings. An unknown topic counts as not muted. */
  public static boolean isMuted (Tdlib tdlib, long chatId, int forumTopicId) {
    Settings settings = settingsByTopic.get(key(tdlib, chatId, forumTopicId));
    return settings != null && settings.mutedUntil > System.currentTimeMillis();
  }

  /**
   * Whether the local notification of this message must go, by its topic's own settings. Safe on any thread.
   * When the topic was never seen, its settings are asked for so that the next messages of that topic are
   * filtered; this one is let through.
   */
  public static boolean dropsNotification (Tdlib tdlib, @Nullable TdApi.Message message, boolean mentionGroup) {
    if (message == null || !(message.topicId instanceof TdApi.MessageTopicForum)) {
      return false;
    }
    final long chatId = message.chatId;
    final int forumTopicId = ((TdApi.MessageTopicForum) message.topicId).forumTopicId;
    Settings settings = settingsByTopic.get(key(tdlib, chatId, forumTopicId));
    if (settings == null) {
      TdlibForumTopicManager.Key key = new TdlibForumTopicManager.Key(chatId, forumTopicId);
      TdlibForumTopicManager.Entry entry = tdlib.topics().find(key); // synchronized, fine off the UI thread
      if (entry != null && entry.value != null) {
        onSettings(tdlib, chatId, forumTopicId, entry.value.notificationSettings);
        settings = settingsByTopic.get(key(tdlib, chatId, forumTopicId));
      } else {
        String pendingKey = key(tdlib, chatId, forumTopicId);
        if (pending.add(pendingKey)) {
          tdlib.ui().post(() -> tdlib.topics().findOrRequest(key, (loadedEntry, inPlace) -> {
            pending.remove(pendingKey);
            if (loadedEntry.value != null) {
              onSettings(tdlib, chatId, forumTopicId, loadedEntry.value.notificationSettings);
            }
          }));
        }
        return false;
      }
    }
    return settings != null && dropsNotification(settings.mutedUntil, settings.mentions, settings.pinned, mentionGroup,
      message.content instanceof TdApi.MessagePinMessage, message.containsUnreadMention, System.currentTimeMillis());
  }

  public static void forgetAccount (int accountId) {
    settingsByTopic.keySet().removeIf(key -> key.startsWith(accountId + "_"));
    pending.removeIf(key -> key.startsWith(accountId + "_"));
  }
}
