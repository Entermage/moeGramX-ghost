package moe.kirao.mgx.topics;

import android.os.SystemClock;

import androidx.annotation.Nullable;
import androidx.annotation.UiThread;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.ChatListener;
import org.thunderdog.challegram.telegram.MessageListener;
import org.thunderdog.challegram.telegram.Tdlib;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import me.vkryl.core.reference.ReferenceList;

/**
 * Chat list badges of forums shown as topics: the number of topics with unread messages, as the official apps show.
 * The chat's own unread_count isn't the sum of its topics and doesn't follow reading them (Ghost Mode included).
 * <p>
 * The newest {@link #PAGE_SIZE} topics are loaded once per session when a row of the forum is shown, one forum at a
 * time through {@link ForumRequests}, so screens keep the rest of its queue. New messages and topic read updates keep
 * them on this device without requests. A read of the whole chat or a deleted last message names no topic: the page
 * is then loaded again, once and later.
 */
public final class ForumUnreadBadges {
  public interface Listener {
    void onForumUnreadTopicsChanged (long chatId);
  }

  static final int PAGE_SIZE = 20;
  /** Forums followed at most: beyond it, the one shown least recently and without a row is dropped. */
  private static final int MAX_FORUMS = 64;
  /** Messages kept while a page loads, to apply after it; past this the page is loaded again. */
  private static final int MAX_PENDING_MESSAGES = 200;
  private static final long RELOAD_DELAY_MS = 2_000;
  private static final long RETRY_DELAY_MS = 30_000;
  private static final int NOT_LOADED = -1;

  private static final Map<Integer, ForumUnreadBadges> instances = new ConcurrentHashMap<>();

  private final Tdlib tdlib;
  // Read by badges on any thread, changed on the UI thread only.
  private final Map<Long, Forum> forums = new ConcurrentHashMap<>();
  private final ArrayDeque<Forum> queue = new ArrayDeque<>();
  private @Nullable Forum loading;
  private long shownCounter;
  private boolean closed;

  private ForumUnreadBadges (Tdlib tdlib) {
    this.tdlib = tdlib;
  }

  @Nullable
  private static Forum find (Tdlib tdlib, long chatId) {
    ForumUnreadBadges badges = instances.get(tdlib.id());
    return badges != null && badges.tdlib == tdlib ? badges.forums.get(chatId) : null;
  }

  /** Whether the chat's badge counts its topics: a forum opened as topics (list or tabs), not as merged messages. */
  public static boolean usesTopics (Tdlib tdlib, long chatId) {
    TdApi.Chat chat = tdlib.chat(chatId);
    return chat != null && tdlib.isForum(chatId) && (chat.viewAsTopics || XgramForums.hasForumTabs(tdlib, chat));
  }

  /** Topics with unread messages, or a dot while they aren't known yet and the chat has unread messages. */
  public static int badgeCount (Tdlib tdlib, TdApi.Chat chat) {
    Forum forum = find(tdlib, chat.id);
    int count = forum != null ? forum.unreadCount : NOT_LOADED;
    if (count > 0) {
      return count;
    }
    return chat.isMarkedAsUnread || (count == NOT_LOADED && chat.unreadCount > 0) ? Tdlib.CHAT_MARKED_AS_UNREAD : 0;
  }

  /** As in the official apps, the badge is muted unless one of the unread topics notifies. */
  public static boolean isBadgeMuted (Tdlib tdlib, long chatId, boolean chatMuted) {
    Forum forum = find(tdlib, chatId);
    if (forum == null || forum.unreadCount <= 0) {
      return chatMuted;
    }
    return forum.unreadUnmuted == 0 && (chatMuted || forum.unreadInheritingMute == 0);
  }

  /** A row of the forum is shown: its topics are loaded unless known, and changes reach the listener. */
  @UiThread
  public static void attach (Tdlib tdlib, long chatId, Listener listener) {
    ForumUnreadBadges badges = instances.get(tdlib.id());
    if (badges == null || badges.tdlib != tdlib) {
      badges = new ForumUnreadBadges(tdlib);
      instances.put(tdlib.id(), badges);
    }
    badges.attachImpl(chatId, listener);
  }

  @UiThread
  public static void detach (Tdlib tdlib, long chatId, Listener listener) {
    Forum forum = find(tdlib, chatId);
    if (forum != null) {
      forum.listeners.remove(listener);
    }
  }

  /** A topic the topic list loaded or refreshed: counted too, as the official apps count every loaded topic. */
  @UiThread
  public static void onTopicLoaded (Tdlib tdlib, long chatId, TdApi.ForumTopic topic) {
    Forum forum = find(tdlib, chatId);
    if (forum != null && forum.topics.isLoaded() && forum.topics.putTopic(topic)) {
      forum.publish();
    }
  }

  /** A topic was deleted here. TDLib sends no update for it. */
  @UiThread
  public static void onTopicDeleted (Tdlib tdlib, long chatId, int forumTopicId) {
    Forum forum = find(tdlib, chatId);
    if (forum != null && forum.topics.removeTopic(forumTopicId)) {
      forum.publish();
    }
  }

  /** The native client closed: what it told is dropped, a new one is asked again. */
  @UiThread
  public static void forgetAccount (Tdlib tdlib) {
    ForumUnreadBadges badges = instances.get(tdlib.id());
    if (badges == null || badges.tdlib != tdlib) {
      return;
    }
    instances.remove(tdlib.id());
    badges.closed = true;
    for (Forum forum : new ArrayList<>(badges.forums.values())) {
      forum.destroy();
    }
    badges.queue.clear();
    badges.loading = null;
  }

  @UiThread
  private void attachImpl (long chatId, Listener listener) {
    Forum forum = forums.get(chatId);
    if (forum == null) {
      forum = new Forum(chatId);
      forums.put(chatId, forum);
    }
    forum.lastShown = ++shownCounter;
    forum.listeners.add(listener);
    trim();
    request(forum);
  }

  private void trim () {
    while (forums.size() > MAX_FORUMS) {
      Forum eldest = null;
      for (Forum forum : forums.values()) {
        if (forum.listeners.isEmpty() && (eldest == null || forum.lastShown < eldest.lastShown)) {
          eldest = forum;
        }
      }
      if (eldest == null) {
        return;
      }
      eldest.destroy();
    }
  }

  private void request (Forum forum) {
    if (closed || forum.destroyed || forum.queued || loading == forum ||
        (forum.topics.isLoaded() && !forum.stale) || SystemClock.uptimeMillis() < forum.retryAfter) {
      return;
    }
    forum.queued = true;
    queue.add(forum);
    pump();
  }

  private void pump () {
    while (loading == null && !closed) {
      Forum forum = queue.poll();
      if (forum == null) {
        return;
      }
      forum.queued = false;
      if (forum.destroyed || forum.listeners.isEmpty()) {
        // No row shows it any more: asked for again when one does.
        continue;
      }
      loading = forum;
      forum.pendingMessages.clear();
      forum.pendingOverflow = false;
      ForumRequests.send(tdlib, forum, new TdApi.GetForumTopics(forum.chatId, "", 0, 0, 0, PAGE_SIZE),
        (result, error) -> onPage(forum, result, error));
    }
  }

  private void onPage (Forum forum, @Nullable TdApi.ForumTopics result, @Nullable TdApi.Error error) {
    if (loading == forum) {
      loading = null;
    }
    if (!closed && !forum.destroyed) {
      if (result != null) {
        forum.topics.setTopics(result.topics);
        // The page may be older than messages that came while it loaded.
        for (TdApi.Message message : forum.pendingMessages) {
          forum.topics.onMessage(ForumTopicList.forumTopicId(message.topicId), message);
        }
        forum.stale = false;
        forum.retryAfter = 0;
        forum.publish();
        if (forum.pendingOverflow) {
          forum.scheduleReload();
        }
      } else if (error != null && !ForumRequests.isClientClosed(error)) {
        forum.retryAfter = SystemClock.uptimeMillis() + XgramForums.retryAfterMs(error, RETRY_DELAY_MS);
      }
      forum.pendingMessages.clear();
      forum.pendingOverflow = false;
    }
    pump();
  }

  private final class Forum implements ChatListener, MessageListener {
    final long chatId;
    final ForumUnreadTopics topics = new ForumUnreadTopics();
    final ReferenceList<Listener> listeners = new ReferenceList<>();
    final ArrayList<TdApi.Message> pendingMessages = new ArrayList<>();
    // Read by badges on any thread.
    volatile int unreadCount = NOT_LOADED, unreadInheritingMute, unreadUnmuted;
    long lastShown, retryAfter, lastChatReadInboxMessageId;
    boolean queued, stale, pendingOverflow, destroyed;
    final Runnable reload = () -> {
      stale = true;
      request(this);
    };

    Forum (long chatId) {
      this.chatId = chatId;
      TdApi.Chat chat = tdlib.chat(chatId);
      if (chat != null) {
        lastChatReadInboxMessageId = chat.lastReadInboxMessageId;
      }
      tdlib.listeners().subscribeToChatUpdates(chatId, this);
      tdlib.listeners().subscribeToMessageUpdates(chatId, this);
    }

    void publish () {
      unreadInheritingMute = topics.unreadInheritingMuteCount();
      unreadUnmuted = topics.unreadUnmutedCount();
      unreadCount = topics.unreadCount();
      for (Listener listener : listeners) {
        listener.onForumUnreadTopicsChanged(chatId);
      }
    }

    void scheduleReload () {
      tdlib.ui().removeCallbacks(reload);
      tdlib.ui().postDelayed(reload, RELOAD_DELAY_MS);
    }

    void destroy () {
      if (destroyed) {
        return;
      }
      destroyed = true;
      forums.remove(chatId, this);
      queue.remove(this);
      boolean wasLoading = loading == this;
      if (wasLoading) {
        loading = null;
      }
      ForumRequests.cancel(tdlib, this);
      tdlib.ui().removeCallbacks(reload);
      tdlib.listeners().unsubscribeFromChatUpdates(chatId, this);
      tdlib.listeners().unsubscribeFromMessageUpdates(chatId, this);
      listeners.clear();
      pendingMessages.clear();
      if (wasLoading) {
        pump();
      }
    }

    @UiThread
    private void onMessage (TdApi.Message message) {
      if (destroyed) {
        return;
      }
      if (loading == this) {
        if (pendingMessages.size() < MAX_PENDING_MESSAGES) {
          pendingMessages.add(message);
        } else {
          pendingOverflow = true;
        }
      }
      if (topics.isLoaded() && topics.onMessage(ForumTopicList.forumTopicId(message.topicId), message)) {
        publish();
      }
    }

    // TDLib thread

    @Override
    public void onNewMessage (TdApi.Message message) {
      tdlib.ui().post(() -> onMessage(message));
    }

    @Override
    public void onMessageSendSucceeded (TdApi.Message message, long oldMessageId) {
      tdlib.ui().post(() -> onMessage(message));
    }

    @Override
    public void onMessagesDeleted (long chatId, long[] messageIds) {
      tdlib.ui().post(() -> {
        if (!destroyed && topics.isLoaded() && topics.needsReloadAfterDelete(messageIds)) {
          scheduleReload();
        }
      });
    }

    @Override
    public void onForumTopicUpdated (TdApi.UpdateForumTopic update) {
      tdlib.ui().post(() -> {
        if (!destroyed && topics.isLoaded() && topics.onTopicUpdated(update)) {
          publish();
        }
      });
    }

    @Override
    public void onChatReadInbox (long chatId, long lastReadInboxMessageId, int unreadCount, boolean availabilityChanged) {
      // Reading the merged view, the All tab or the whole chat moves this position without an update of each topic.
      // Only a moved position counts: new messages change unreadCount too.
      tdlib.ui().post(() -> {
        if (destroyed || lastChatReadInboxMessageId == lastReadInboxMessageId) {
          return;
        }
        lastChatReadInboxMessageId = lastReadInboxMessageId;
        if (topics.isLoaded()) {
          scheduleReload();
        }
      });
    }
  }
}
