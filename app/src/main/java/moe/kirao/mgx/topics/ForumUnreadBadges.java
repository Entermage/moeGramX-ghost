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
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import me.vkryl.core.reference.ReferenceList;

/**
 * Chat list badges of forums shown as topics: the number of topics with unread messages, as the official apps show.
 * The chat's own unread_count isn't the sum of its topics and doesn't follow reading them (Ghost Mode included).
 * <p>
 * The newest {@link #PAGE_SIZE} topics are loaded once per session when a row of the forum is shown, one forum at a
 * time through {@link ForumRequests}, so screens keep the rest of its queue. Topics past that page are counted once the
 * topic list loaded them; a page keeps them as they were, as missing from it doesn't make them read. New messages and
 * topic read updates keep them on this device without requests. A read of the whole chat or a deleted last message
 * names no topic: the page is then loaded again, once and later, and again after a page that was already loading when
 * it happened. The chat's read position and unread_count don't read topics (TDLib reads none when the whole chat is
 * read), so only a topic's own update or as the server has it does. Unread topics the page leaves unsure are fetched by
 * themselves after it, a few, through the same queue.
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
  /** Unread topics a page left unsure that are fetched by themselves after it, at most. */
  private static final int MAX_TOPIC_CHECKS = 8;
  /** Topics deleted here that answers asked for before can't bring back, the latest ones per account. */
  private static final int MAX_DELETED_TOPICS = 64;
  private static final int NOT_LOADED = -1;

  private static final Map<Integer, ForumUnreadBadges> instances = new ConcurrentHashMap<>();

  private final Tdlib tdlib;
  // Read by badges on any thread, changed on the UI thread only.
  private final Map<Long, Forum> forums = new ConcurrentHashMap<>();
  private final ArrayDeque<Forum> queue = new ArrayDeque<>();
  /**
   * Topics deleted here while this client runs ("chatId:forumTopicId"). TDLib sends no update for it, and a page or topic
   * asked for before, even by another screen sharing its request, still has them. Topic IDs aren't used again.
   */
  private final LinkedHashSet<String> deletedTopics = new LinkedHashSet<>();
  private @Nullable Forum loading;
  private long shownCounter;
  private boolean closed;

  private ForumUnreadBadges (Tdlib tdlib) {
    this.tdlib = tdlib;
  }

  private static ForumUnreadBadges obtain (Tdlib tdlib) {
    ForumUnreadBadges badges = instances.get(tdlib.id());
    if (badges == null || badges.tdlib != tdlib) {
      badges = new ForumUnreadBadges(tdlib);
      instances.put(tdlib.id(), badges);
    }
    return badges;
  }

  @Nullable
  private static Forum find (Tdlib tdlib, long chatId) {
    ForumUnreadBadges badges = instances.get(tdlib.id());
    return badges != null && badges.tdlib == tdlib ? badges.forums.get(chatId) : null;
  }

  private static String deletedKey (long chatId, int forumTopicId) {
    return chatId + ":" + forumTopicId;
  }

  /** Whether the topic was deleted here while this client runs: an older answer with it must not bring it back. */
  @UiThread
  public static boolean isTopicDeleted (Tdlib tdlib, long chatId, int forumTopicId) {
    ForumUnreadBadges badges = instances.get(tdlib.id());
    return badges != null && badges.tdlib == tdlib && badges.deletedTopics.contains(deletedKey(chatId, forumTopicId));
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
    obtain(tdlib).attachImpl(chatId, listener);
  }

  @UiThread
  public static void detach (Tdlib tdlib, long chatId, Listener listener) {
    Forum forum = find(tdlib, chatId);
    if (forum != null) {
      forum.listeners.remove(listener);
    }
  }

  /**
   * A topic the topic list loaded or refreshed: counted too, as the official apps count every loaded topic. Before the
   * first page it is kept for it, which keeps topics past it.
   */
  @UiThread
  public static void onTopicLoaded (Tdlib tdlib, long chatId, TdApi.ForumTopic topic) {
    Forum forum = find(tdlib, chatId);
    if (forum != null && !forum.destroyed && !isTopicDeleted(tdlib, chatId, topic.info.forumTopicId) &&
        forum.topics.putTopic(topic) && forum.topics.isLoaded()) {
      forum.publish();
    }
  }

  /** A topic was deleted here, or the server said it is gone. TDLib sends no update for it. */
  @UiThread
  public static void onTopicDeleted (Tdlib tdlib, long chatId, int forumTopicId) {
    ForumUnreadBadges badges = obtain(tdlib);
    String key = deletedKey(chatId, forumTopicId);
    badges.deletedTopics.remove(key);
    badges.deletedTopics.add(key);
    while (badges.deletedTopics.size() > MAX_DELETED_TOPICS) {
      badges.deletedTopics.remove(badges.deletedTopics.iterator().next());
    }
    Forum forum = badges.forums.get(chatId);
    if (forum != null) {
      forum.checks.remove(forumTopicId);
      if (forum.topics.removeTopic(forumTopicId)) {
        forum.publish();
      }
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
    // The old client's answers end with it: nothing older can come.
    badges.deletedTopics.clear();
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
        (forum.topics.isLoaded() && !forum.stale && forum.checks.isEmpty()) || SystemClock.uptimeMillis() < forum.retryAfter) {
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
      if (!forum.topics.isLoaded() || forum.stale) {
        loading = forum;
        forum.loadingInvalidation = forum.invalidation;
        forum.clearPending();
        ForumRequests.send(tdlib, forum, new TdApi.GetForumTopics(forum.chatId, "", 0, 0, 0, PAGE_SIZE),
          (result, error) -> onPage(forum, result, error));
        continue;
      }
      // After its page: one unsure topic, then the forum goes to the end of the queue for the next.
      int forumTopicId = 0;
      while (forumTopicId == 0 && !forum.checks.isEmpty()) {
        int next = forum.checks.iterator().next();
        if (forum.topics.isUnread(next)) {
          forumTopicId = next;
        } else {
          // Read or gone meanwhile: nothing left to count.
          forum.checks.remove(next);
        }
      }
      if (forumTopicId == 0) {
        continue;
      }
      final int checked = forumTopicId;
      loading = forum;
      forum.clearPending();
      ForumRequests.send(tdlib, forum, new TdApi.GetForumTopic(forum.chatId, checked),
        (result, error) -> onTopic(forum, checked, result, error));
    }
  }

  /** Keeps the unread topics a page left unsure for fetching each by itself, a few at most. */
  private void addChecks (Forum forum, List<Integer> unsure) {
    for (int forumTopicId : unsure) {
      if (forum.checks.size() >= MAX_TOPIC_CHECKS) {
        // Past the bound a topic stays counted as it was, until the topic list or an update tells.
        break;
      }
      forum.checks.add(forumTopicId);
    }
  }

  /** The page without the topics deleted here since it was asked for. */
  private TdApi.ForumTopic[] withoutDeleted (long chatId, TdApi.ForumTopic[] page) {
    ArrayList<TdApi.ForumTopic> result = null;
    for (int i = 0; i < page.length; i++) {
      boolean deleted = deletedTopics.contains(deletedKey(chatId, page[i].info.forumTopicId));
      if (deleted && result == null) {
        result = new ArrayList<>(page.length);
        for (int j = 0; j < i; j++) {
          result.add(page[j]);
        }
      } else if (!deleted && result != null) {
        result.add(page[i]);
      }
    }
    return result != null ? result.toArray(new TdApi.ForumTopic[0]) : page;
  }

  private void onPage (Forum forum, @Nullable TdApi.ForumTopics result, @Nullable TdApi.Error error) {
    if (loading == forum) {
      loading = null;
    }
    if (!closed && !forum.destroyed) {
      if (result != null) {
        // As the topic list: a page with every topic of the forum is complete.
        boolean complete = result.topics.length == 0 || (result.totalCount > 0 && result.topics.length >= result.totalCount);
        // The page decides again which topics are unsure.
        forum.checks.clear();
        addChecks(forum, forum.topics.setTopics(withoutDeleted(forum.chatId, result.topics), complete));
        // The page may be older than messages that came while it loaded.
        for (TdApi.Message message : forum.pendingMessages) {
          forum.topics.onMessage(ForumTopicList.forumTopicId(message.topicId), message);
        }
        // Invalidated again while it loaded: the page may be older than that, ask once more after it.
        forum.stale = forum.invalidation != forum.loadingInvalidation;
        forum.retryAfter = 0;
        forum.publish();
        boolean deletedLast = false;
        for (long[] messageIds : forum.pendingDeletions) {
          deletedLast |= forum.topics.needsReloadAfterDelete(messageIds);
        }
        // Unless asked for again anyway, after these the page itself.
        if (!forum.stale && (forum.pendingOverflow || deletedLast)) {
          forum.scheduleReload();
        }
      } else if (error != null && !ForumRequests.isClientClosed(error)) {
        // Stays stale: asked for again once a row shows it after the wait, not in the background.
        forum.retryAfter = SystemClock.uptimeMillis() + XgramForums.retryAfterMs(error, RETRY_DELAY_MS);
      }
      forum.clearPending();
      if (result != null && (forum.stale || !forum.checks.isEmpty())) {
        request(forum);
      }
    }
    pump();
  }

  /** An unsure topic fetched by itself: as the server has it now, or gone. */
  private void onTopic (Forum forum, int forumTopicId, @Nullable TdApi.ForumTopic result, @Nullable TdApi.Error error) {
    if (loading == forum) {
      loading = null;
    }
    if (!closed && !forum.destroyed) {
      boolean answered = true;
      if (result != null) {
        forum.retryAfter = 0;
        if (!isTopicDeleted(tdlib, forum.chatId, forumTopicId) && forum.topics.putFetchedTopic(result)) {
          forum.publish();
        }
      } else if (error == null || XgramForums.isTopicGone(error)) {
        if (forum.topics.removeTopic(forumTopicId)) {
          forum.publish();
        }
      } else if (!ForumRequests.isClientClosed(error)) {
        // Stays unsure and counted: asked for again once a row shows the forum after the wait, not in the background.
        answered = false;
        forum.retryAfter = SystemClock.uptimeMillis() + XgramForums.retryAfterMs(error, RETRY_DELAY_MS);
      } else {
        answered = false;
      }
      if (answered) {
        forum.checks.remove(forumTopicId);
      }
      forum.clearPending();
      if (answered && (forum.stale || !forum.checks.isEmpty())) {
        request(forum);
      }
    }
    pump();
  }

  private final class Forum implements ChatListener, MessageListener {
    final long chatId;
    final ForumUnreadTopics topics = new ForumUnreadTopics();
    final ReferenceList<Listener> listeners = new ReferenceList<>();
    final ArrayList<TdApi.Message> pendingMessages = new ArrayList<>();
    /** Deleted message IDs that came while a page loaded, as received. */
    final ArrayList<long[]> pendingDeletions = new ArrayList<>();
    int pendingDeletedCount;
    /** Unread topics the last page left unsure, fetched one by one after it while a row shows the forum. */
    final LinkedHashSet<Integer> checks = new LinkedHashSet<>();
    // Read by badges on any thread.
    volatile int unreadCount = NOT_LOADED, unreadInheritingMute, unreadUnmuted;
    long lastShown, retryAfter, lastChatReadInboxMessageId;
    /** Counts the reloads asked for; a page answers those asked for before it was sent. */
    int invalidation, loadingInvalidation;
    boolean queued, stale, pendingOverflow, destroyed;
    final Runnable reload = () -> {
      invalidation++;
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

    void clearPending () {
      pendingMessages.clear();
      pendingDeletions.clear();
      pendingDeletedCount = 0;
      pendingOverflow = false;
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
      clearPending();
      checks.clear();
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
        if (destroyed) {
          return;
        }
        if (loading == this) {
          // The loading page may still have them as last messages.
          if (pendingDeletedCount + messageIds.length <= MAX_PENDING_MESSAGES) {
            pendingDeletions.add(messageIds);
            pendingDeletedCount += messageIds.length;
          } else {
            pendingOverflow = true;
          }
        }
        if (topics.isLoaded() && topics.needsReloadAfterDelete(messageIds)) {
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
        // Not a read of its topics, even with nothing unread left in the chat: TDLib reads none of them for a read of
        // the whole forum (MessagesManager::mark_dialog_as_read). The page tells about its own; topics past it are
        // read by their own update or once fetched.
        if (topics.isLoaded() || loading == this) {
          scheduleReload();
        }
      });
    }
  }
}
