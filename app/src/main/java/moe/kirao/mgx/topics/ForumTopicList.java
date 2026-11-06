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
import androidx.annotation.UiThread;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.ChatListener;
import org.thunderdog.challegram.telegram.MessageListener;
import org.thunderdog.challegram.telegram.Tdlib;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;

import me.vkryl.core.collection.IntList;
import me.vkryl.core.collection.IntSet;
import me.vkryl.core.lambda.Destroyable;
import me.vkryl.core.reference.ReferenceList;

/**
 * Live, sorted and paged list of topics of one forum chat.
 *
 * TDLib reports pin, read and notification changes through {@code updateForumTopic}, but not changes to
 * {@code order}, {@code last_message} or {@code unread_count}. Topics affected by new, sent or deleted
 * messages are therefore refreshed with {@code getForumTopic}, batched to one request per topic per
 * {@link #REFRESH_DELAY_MS}.
 */
public final class ForumTopicList implements ChatListener, MessageListener, Destroyable {
  public interface Listener {
    default void onTopicsLoaded (ForumTopicList list) { }
    default void onTopicInserted (ForumTopicList list, int index) { }
    default void onTopicRemoved (ForumTopicList list, int index) { }
    default void onTopicMoved (ForumTopicList list, int fromIndex, int toIndex) { }
    default void onTopicChanged (ForumTopicList list, int index) { }
    /** A page that failed or had to wait may be asked again: load it if the end of the list is on screen. */
    default void onLoadMoreAvailable (ForumTopicList list) { }
  }

  private static final int FIRST_PAGE_SIZE = 20;
  private static final int NEXT_PAGE_SIZE = 100;
  private static final long REFRESH_DELAY_MS = 300;
  /** More pending topics than this are refreshed with one page request. */
  private static final int BATCH_THRESHOLD = 5;
  /** At most this many single-topic requests after a page request. */
  private static final int MAX_SINGLE_FETCHES = 10;

  /** The first page is fetched again at most this often (uptime ms) to follow pin and order changes made elsewhere. */
  private static final long RESYNC_INTERVAL_MS = 30_000;

  /**
   * Pinned topics in their server order (ids). TDLib's {@code order} only follows the last message and the draft,
   * never pinning, so this list is what keeps pinned topics on top and in the order the user chose.
   */
  private final IntList pinnedOrder = new IntList(8);

  private final Comparator<TdApi.ForumTopic> comparator = (a, b) -> {
    // Hidden General goes first, like the official app's pull-down row.
    boolean aHidden = a.info.isHidden, bHidden = b.info.isHidden;
    if (aHidden != bHidden) {
      return aHidden ? -1 : 1;
    }
    if (a.isPinned != b.isPinned) {
      return a.isPinned ? -1 : 1;
    }
    if (a.isPinned) {
      int aIndex = pinnedIndex(a.info.forumTopicId), bIndex = pinnedIndex(b.info.forumTopicId);
      if (aIndex != bIndex) {
        return Integer.compare(aIndex, bIndex);
      }
    }
    if (a.order != b.order) {
      return Long.compare(b.order, a.order);
    }
    return Integer.compare(b.info.forumTopicId, a.info.forumTopicId);
  };

  /** Position of a pinned topic in {@link #pinnedOrder}; topics the order doesn't know go after the known ones. */
  private int pinnedIndex (int forumTopicId) {
    int index = pinnedOrder.indexOf(forumTopicId);
    return index == -1 ? Integer.MAX_VALUE : index;
  }

  // Visible controllers share a list. The last observer releases it and its subscriptions.
  private static final int CACHE_SIZE = 8;
  private static final LinkedHashMap<String, ForumTopicList> cache = new LinkedHashMap<>(16, .75f, true);

  /** Returns the cached topic list of the chat, or a new one. Call {@link #loadMore()} if it isn't loaded. */
  @UiThread
  public static ForumTopicList obtain (Tdlib tdlib, long chatId) {
    String key = tdlib.id() + "_" + chatId;
    ForumTopicList list = cache.get(key);
    if (list == null || list.isDestroyed) {
      list = new ForumTopicList(tdlib, chatId);
      cache.put(key, list);
      trimCache();
    } else if (list.loadFailed) {
      // Reset in place: screens still bound to this instance keep a list that loads and updates again. Replacing it
      // would leave them a dead, empty one, as they don't obtain the list again for the same chat.
      list.resetAfterFailure();
    }
    return list;
  }

  /** Restore only display data from a covered controller; requests and listeners never survive release. */
  @UiThread
  public void restoreFrom (ForumTopicList previous) {
    if (previous == null || previous == this || previous.tdlib != tdlib || previous.chatId != chatId ||
        !previous.isLoaded || previous.loadFailed || isLoaded || isLoading || isDestroyed) return;
    topics.addAll(previous.topics);
    nextOffsetDate = previous.nextOffsetDate;
    nextOffsetMessageId = previous.nextOffsetMessageId;
    nextOffsetForumTopicId = previous.nextOffsetForumTopicId;
    endReached = previous.endReached;
    isLoaded = true;
    generalChecked = previous.generalChecked;
    replacePinnedOrder(previous.pinnedTopicIds());
    localReorderVersion = previous.localReorderVersion;
    lastResyncAt = previous.lastResyncAt;
    lastReturnRefreshAt = previous.lastReturnRefreshAt;
    loadRetryAfter = previous.loadRetryAfter;
  }

  /** Lets a list whose first page failed try again: not loaded, nothing reached, offsets at the start. */
  @UiThread
  private void resetAfterFailure () {
    loadFailed = false;
    firstPageRetries = 0;
    endReached = false;
    isLoaded = false;
    isLoading = false;
    loadRetryAfter = 0;
    nextOffsetDate = 0;
    nextOffsetMessageId = 0;
    nextOffsetForumTopicId = 0;
  }

  /** A topic from the cached list of the chat, without creating or loading a list. */
  @UiThread
  @Nullable
  public static TdApi.ForumTopic peekTopic (Tdlib tdlib, long chatId, int forumTopicId) {
    ForumTopicList list = cache.get(tdlib.id() + "_" + chatId);
    return list != null && !list.isDestroyed ? list.find(forumTopicId) : null;
  }

  /** True while a cached, live list of the chat holds all of its topics: its sum is then the forum's badge. */
  @UiThread
  public static boolean isFullyLoaded (Tdlib tdlib, long chatId) {
    ForumTopicList list = cache.get(tdlib.id() + "_" + chatId);
    return list != null && !list.isDestroyed && list.isLoaded && list.endReached && !list.loadFailed;
  }

  /** A topic was deleted here. TDLib sends no update for it, so the cached list of the chat drops it now. */
  @UiThread
  public static void onTopicDeleted (Tdlib tdlib, long chatId, int forumTopicId) {
    ForumTopicList list = cache.get(tdlib.id() + "_" + chatId);
    if (list != null && !list.isDestroyed) {
      list.removeTopic(forumTopicId);
    }
  }

  @UiThread
  public static void forgetAccount (Tdlib tdlib) {
    Iterator<ForumTopicList> it = cache.values().iterator();
    while (it.hasNext()) {
      ForumTopicList list = it.next();
      if (list.tdlib == tdlib) {
        it.remove();
        list.performDestroy();
      }
    }
  }

  private static void trimCache () {
    Iterator<ForumTopicList> it = cache.values().iterator();
    while (cache.size() > CACHE_SIZE && it.hasNext()) {
      ForumTopicList eldest = it.next();
      if (eldest.listeners.isEmpty()) {
        it.remove();
        eldest.performDestroy();
      }
    }
  }

  private final Tdlib tdlib;
  private final long chatId;
  private final List<TdApi.ForumTopic> topics = new ArrayList<>();
  private final ReferenceList<Listener> listeners = new ReferenceList<>();

  private int nextOffsetDate;
  private long nextOffsetMessageId;
  private int nextOffsetForumTopicId;
  private boolean isLoading, endReached, isLoaded, isDestroyed, loadFailed;

  private final IntSet pendingRefresh = new IntSet();
  private boolean refreshScheduled;
  private final Runnable refreshTask = this::performRefresh;
  /** A page that failed to load isn't asked again before this (uptime ms), so scrolling can't hammer an offline server. */
  private long loadRetryAfter;
  private static final int MAX_FIRST_PAGE_RETRIES = 4;
  private int firstPageRetries;
  /** Topics whose fetch failed once (not as deleted): they get one more try. */
  private final java.util.Set<Integer> retriedOnce = new java.util.HashSet<>();
  /** A retry of a failed or postponed page is on its way ({@link #scheduleLoadRetry}). */
  private boolean loadRetryScheduled;

  // Updates of topics that aren't rows yet while a page is loading. TDLib sends them as it takes the page in (those
  // match the page) or for changes made meanwhile (those are newer): kept, they are applied once the page is in, as
  // dropping them lost read and pin changes made during the first load.
  private final java.util.Map<Integer, TdApi.UpdateForumTopic> updatesWhileLoading = new java.util.HashMap<>();
  private final java.util.Map<Integer, TdApi.ForumTopicInfo> infosWhileLoading = new java.util.HashMap<>();
  /** Topics fetched before the first page was in: fetched again after it, as the page may be older than them. */
  private final IntSet fetchedWhileLoading = new IntSet();
  /** The General topic was looked for once, as the hidden one goes first but may be on a later page. */
  private boolean generalChecked;

  public ForumTopicList (Tdlib tdlib, long chatId) {
    this.tdlib = tdlib;
    this.chatId = chatId;
    tdlib.listeners().subscribeToChatUpdates(chatId, this);
    tdlib.listeners().subscribeToMessageUpdates(chatId, this);
    TdApi.Chat chat = tdlib.chat(chatId);
    if (chat != null) {
      // The chat's read state when the list was made: the first read update compares with it (refreshing every unread topic otherwise).
      lastChatReadInboxMessageId = chat.lastReadInboxMessageId;
    }
  }

  public long chatId () {
    return chatId;
  }

  public void addListener (Listener listener) {
    listeners.add(listener);
  }

  public void removeListener (Listener listener) {
    listeners.remove(listener);
    if (listeners.isEmpty()) {
      performDestroy();
      cache.values().removeIf(value -> value == this);
    }
  }

  public int size () {
    return topics.size();
  }

  public TdApi.ForumTopic get (int index) {
    return topics.get(index);
  }

  public boolean isLoaded () {
    return isLoaded;
  }

  public boolean isEndReached () {
    return endReached;
  }

  public boolean canLoadMore () {
    return !endReached && !isLoading && !isDestroyed && android.os.SystemClock.uptimeMillis() >= loadRetryAfter;
  }

  public int indexOf (int forumTopicId) {
    for (int i = 0; i < topics.size(); i++) {
      if (topics.get(i).info.forumTopicId == forumTopicId) {
        return i;
      }
    }
    return -1;
  }

  @Nullable
  public TdApi.ForumTopic find (int forumTopicId) {
    int index = indexOf(forumTopicId);
    return index != -1 ? topics.get(index) : null;
  }

  // Loading

  static boolean endOfPage (int returned, int loaded, int total, int oldDate, long oldMessage, int oldTopic,
                            int nextDate, long nextMessage, int nextTopic) {
    return returned == 0 || (nextDate == 0 && nextMessage == 0 && nextTopic == 0) ||
      (oldDate == nextDate && oldMessage == nextMessage && oldTopic == nextTopic) ||
      (total > 0 && loaded >= total);
  }

  @UiThread
  public void loadMore () {
    if (!canLoadMore()) {
      return;
    }
    long floodWait = XgramTopicFlood.waitMs(tdlib);
    if (floodWait > 0) {
      // The server asked to wait: the page is asked for once it may be.
      loadRetryAfter = android.os.SystemClock.uptimeMillis() + floodWait;
      scheduleLoadRetry(floodWait);
      return;
    }
    isLoading = true;
    int limit = topics.isEmpty() ? FIRST_PAGE_SIZE : NEXT_PAGE_SIZE;
    // The server lists pinned topics first on the first page: that is the only place their order comes from.
    final boolean firstPage = nextOffsetDate == 0 && nextOffsetMessageId == 0 && nextOffsetForumTopicId == 0;
    final int oldDate = nextOffsetDate, oldTopic = nextOffsetForumTopicId;
    final long oldMessage = nextOffsetMessageId;
    ForumRequests.send(tdlib, this, new TdApi.GetForumTopics(chatId, "", nextOffsetDate, nextOffsetMessageId, nextOffsetForumTopicId, limit), (result, error) -> tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      isLoading = false;
      if (error != null) {
        long delay = XgramTopicFlood.onError(tdlib, error, topics.isEmpty() ? 3000 : 5000);
        if (topics.isEmpty() && !isLoaded && !listeners.isEmpty() && firstPageRetries < MAX_FIRST_PAGE_RETRIES) {
          // An open screen keeps its spinner and tries again (FLOOD_WAIT after a burst is common), instead of "No topics".
          firstPageRetries++;
          loadRetryAfter = android.os.SystemClock.uptimeMillis() + delay;
          scheduleLoadRetry(delay);
          return;
        }
        if (topics.isEmpty()) {
          endReached = true;
          loadFailed = true;
        } else {
          // Keep what's loaded and try the next page again a bit later, without waiting for the next scroll.
          loadRetryAfter = android.os.SystemClock.uptimeMillis() + delay;
          scheduleLoadRetry(delay);
        }
      } else {
        for (TdApi.ForumTopic topic : result.topics) {
          if (ForumUnreadBadges.isTopicDeleted(tdlib, chatId, topic.info.forumTopicId)) {
            continue; // Deleted here after the page was asked for: it doesn't come back.
          }
          XgramTopicReadOutbox.set(tdlib, chatId, topic);
          XgramTopicMute.onSettings(tdlib, chatId, topic);
          ForumUnreadBadges.onTopicLoaded(tdlib, chatId, topic);
          if (indexOf(topic.info.forumTopicId) == -1) {
            topics.add(XgramForums.normalizeUnread(tdlib, topic));
          }
        }
        if (firstPage) {
          replacePinnedOrder(serverPinnedIds(result.topics));
        }
        Collections.sort(topics, comparator);
        nextOffsetDate = result.nextOffsetDate;
        nextOffsetMessageId = result.nextOffsetMessageId;
        nextOffsetForumTopicId = result.nextOffsetForumTopicId;
        endReached = endOfPage(result.topics.length, topics.size(), result.totalCount,
          oldDate, oldMessage, oldTopic, nextOffsetDate, nextOffsetMessageId, nextOffsetForumTopicId);
      }
      isLoaded = true;
      for (Listener listener : listeners) {
        listener.onTopicsLoaded(this);
      }
      applyUpdatesWhileLoading();

      if (firstPage && error == null) {
        checkGeneral();
      }
    }));
  }

  /**
   * After a page failed or had to wait: once it may be asked again, a first page loads by itself and screens are told
   * the next one can (they load it if the end of the list is on screen), so no scroll is needed to try again.
   */
  private final Object retryToken = new Object();

  private void postRetry (Runnable task, long delay) {
    if (!isDestroyed) tdlib.ui().postAtTime(task, retryToken, android.os.SystemClock.uptimeMillis() + Math.max(0, delay));
  }

  @UiThread
  private void scheduleLoadRetry (long delay) {
    if (loadRetryScheduled) {
      return;
    }
    loadRetryScheduled = true;
    postRetry(() -> {
      loadRetryScheduled = false;
      if (isDestroyed || listeners.isEmpty()) {
        return;
      }
      long left = loadRetryAfter - android.os.SystemClock.uptimeMillis();
      if (left > 0) {
        scheduleLoadRetry(left); // the wait grew meanwhile
        return;
      }
      if (!isLoaded) {
        loadMore();
      } else {
        for (Listener listener : listeners) {
          listener.onLoadMoreAvailable(this);
        }
      }
    }, Math.max(0, delay));
  }

  /** Applies what TDLib said about topics that weren't rows while the page was loading, now that they may be. */
  @UiThread
  private void applyUpdatesWhileLoading () {
    if (!infosWhileLoading.isEmpty()) {
      List<TdApi.ForumTopicInfo> infos = new ArrayList<>(infosWhileLoading.values());
      infosWhileLoading.clear();
      for (TdApi.ForumTopicInfo info : infos) {
        applyTopicInfo(info);
      }
    }
    if (!updatesWhileLoading.isEmpty()) {
      List<TdApi.UpdateForumTopic> updates = new ArrayList<>(updatesWhileLoading.values());
      updatesWhileLoading.clear();
      for (TdApi.UpdateForumTopic update : updates) {
        applyTopicUpdate(update);
      }
    }
    if (!fetchedWhileLoading.isEmpty()) {
      int[] forumTopicIds = fetchedWhileLoading.toArray();
      fetchedWhileLoading.clear();
      for (int forumTopicId : forumTopicIds) {
        scheduleRefresh(forumTopicId);
      }
    }
  }

  /**
   * After the first page: the hidden General goes on top, but a quiet one sorts onto a later page on the server and
   * would only show up (and jump to the top) once the list is scrolled that far. Fetched once if it isn't a row.
   */
  @UiThread
  private void checkGeneral () {
    if (generalChecked || endReached || isDestroyed) {
      return;
    }
    generalChecked = true;
    if (indexOf(XgramForums.GENERAL_TOPIC_ID) == -1) {
      scheduleRefresh(XgramForums.GENERAL_TOPIC_ID); // a General that isn't hidden stays out: its page isn't loaded
    }
  }

  // Refreshing single topics

  private void scheduleRefresh (int forumTopicId) {
    if (forumTopicId == 0 || isDestroyed) {
      return;
    }
    pendingRefresh.add(forumTopicId);
    if (!refreshScheduled) {
      refreshScheduled = true;
      tdlib.ui().postDelayed(refreshTask, REFRESH_DELAY_MS);
    }
  }

  private void performRefresh () {
    refreshScheduled = false;
    if (isDestroyed || pendingRefresh.isEmpty()) {
      return;
    }
    long floodWait = XgramTopicFlood.waitMs(tdlib);
    if (floodWait > 0) {
      // The server asked to wait: the topics stay pending until then (more may join them meanwhile).
      refreshScheduled = true;
      tdlib.ui().postDelayed(refreshTask, floodWait);
      return;
    }
    int[] forumTopicIds = pendingRefresh.toArray();
    pendingRefresh.clear();
    if (forumTopicIds.length <= BATCH_THRESHOLD) {
      List<Integer> ids = new ArrayList<>(forumTopicIds.length);
      for (int forumTopicId : forumTopicIds) {
        ids.add(forumTopicId);
      }
      fetchSingles(ids);
      return;
    }
    // Many topics at once (a read in "All", a burst of messages): one page instead of one request per topic, which
    // ends in FLOOD_WAIT. Topics not on that page are fetched one by one, a few at a time.
    lastResyncAt = android.os.SystemClock.uptimeMillis();
    final int requestedReorderVersion = localReorderVersion;
    ForumRequests.send(tdlib, this, new TdApi.GetForumTopics(chatId, "", 0, 0, 0, firstPageLimit()), (result, error) -> tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      java.util.Set<Integer> left = new java.util.LinkedHashSet<>();
      for (int forumTopicId : forumTopicIds) {
        left.add(forumTopicId);
      }
      if (result != null) {
        applyFirstPage(result, requestedReorderVersion);
        for (TdApi.ForumTopic topic : result.topics) {
          left.remove(topic.info.forumTopicId);
        }
      } else {
        XgramTopicFlood.onError(tdlib, error, 0);
        if (XgramTopicFlood.waitMs(tdlib) > 0) {
          // A flood wait: one request per topic now would only fail too. All of them wait and go as one page again.
          for (int forumTopicId : forumTopicIds) {
            scheduleRefresh(forumTopicId);
          }
          return;
        }
      }
      // Topics further down than the page: one by one, a few at a time (as single fetches, not as another page).
      fetchSingles(new ArrayList<>(left));
    }));
  }

  /** Fetches topics one by one, {@link #MAX_SINGLE_FETCHES} a second, after any flood wait. */
  @UiThread
  private void fetchSingles (List<Integer> forumTopicIds) {
    if (isDestroyed || forumTopicIds.isEmpty()) {
      return;
    }
    long floodWait = XgramTopicFlood.waitMs(tdlib);
    if (floodWait > 0) {
      postRetry(() -> fetchSingles(forumTopicIds), floodWait);
      return;
    }
    int count = Math.min(MAX_SINGLE_FETCHES, forumTopicIds.size());
    for (int i = 0; i < count; i++) {
      fetchTopic(forumTopicIds.get(i));
    }
    if (count < forumTopicIds.size()) {
      List<Integer> later = new ArrayList<>(forumTopicIds.subList(count, forumTopicIds.size()));
      postRetry(() -> fetchSingles(later), 1000);
    }
  }

  private void fetchTopic (int forumTopicId) {
    ForumRequests.send(tdlib, this, new TdApi.GetForumTopic(chatId, forumTopicId), (topic, error) -> tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      if (error == null) {
        retriedOnce.remove(forumTopicId);
        putTopic(topic);
      } else if (XgramForums.isTopicGone(error)) {
        retriedOnce.remove(forumTopicId);
        removeTopic(forumTopicId);
        // Deleted elsewhere: the badge stops counting it too. General can't be deleted, so it isn't kept as deleted.
        if (forumTopicId != XgramForums.GENERAL_TOPIC_ID) {
          ForumUnreadBadges.onTopicDeleted(tdlib, chatId, forumTopicId);
        }

      } else {
        long delay = XgramTopicFlood.onError(tdlib, error, 5000);
        if (retriedOnce.add(forumTopicId)) {
          // Offline, flood wait, a server hiccup: the topic still exists. Try once more, later.
          postRetry(() -> scheduleRefresh(forumTopicId), delay);
        } else {
          retriedOnce.remove(forumTopicId); // gave up for now; the next update of this topic tries again
        }
      }
    }));
  }

  @UiThread
  private void putTopic (TdApi.ForumTopic topic) {
    putTopicImpl(topic);

  }

  @UiThread
  private void putTopicImpl (TdApi.ForumTopic topic) {
    if (ForumUnreadBadges.isTopicDeleted(tdlib, chatId, topic.info.forumTopicId)) {
      return; // Deleted here after it was asked for: an older answer doesn't bring it back.
    }
    XgramForums.normalizeUnread(tdlib, topic);
    XgramTopicReadOutbox.set(tdlib, chatId, topic);
    XgramTopicMute.onSettings(tdlib, chatId, topic);
    ForumUnreadBadges.onTopicLoaded(tdlib, chatId, topic);
    int oldIndex = indexOf(topic.info.forumTopicId);
    // A topic pinned or unpinned since the last fetch (or one not seen before): keep the pinned order in step before
    // the comparator places it. A fresh pin goes on top, as it does on the server.
    if (topic.isPinned) {
      if (!pinnedOrder.contains(topic.info.forumTopicId)) {
        prependPinned(topic.info.forumTopicId);
      }
    } else {
      pinnedOrder.remove(topic.info.forumTopicId);
    }
    if (oldIndex == -1) {
      if (!isLoaded) {
        if (isLoading) {
          // Fetched while the first page loads, which may be older: fetched again once the page is in.
          fetchedWhileLoading.add(topic.info.forumTopicId);
        }
        return;
      }
      int newIndex = insertionIndex(topic);
      if (newIndex == topics.size() && !endReached) {
        // Belongs to a page that hasn't been loaded yet.
        return;
      }
      topics.add(newIndex, topic);
      for (Listener listener : listeners) {
        listener.onTopicInserted(this, newIndex);
      }
      return;
    }
    TdApi.ForumTopic oldTopic = topics.remove(oldIndex);
    if (oldTopic.lastMessage != null && oldTopic.lastMessage.sendingState instanceof TdApi.MessageSendingStatePending &&
      (topic.lastMessage == null || topic.lastMessage.id < oldTopic.lastMessage.id)) {
      // Still sending: the server doesn't know the message yet. Keep its preview until it is sent or fails.
      topic.lastMessage = oldTopic.lastMessage;
    }
    int newIndex = insertionIndex(topic);
    topics.add(newIndex, topic);
    boolean changed = !sameVisibleState(oldTopic, topic);
    for (Listener listener : listeners) {
      if (oldIndex != newIndex) {
        listener.onTopicMoved(this, oldIndex, newIndex);
      }
      if (changed) {
        listener.onTopicChanged(this, newIndex);
      }
    }
  }

  private static boolean sameVisibleState (TdApi.ForumTopic a, TdApi.ForumTopic b) {
    return a.order == b.order &&
      a.isPinned == b.isPinned &&
      a.unreadCount == b.unreadCount &&
      a.unreadMentionCount == b.unreadMentionCount &&
      a.unreadReactionCount == b.unreadReactionCount &&
      a.lastReadOutboxMessageId == b.lastReadOutboxMessageId &&
      sameMessage(a.lastMessage, b.lastMessage) &&
      sameDraft(a.draftMessage, b.draftMessage) &&
      sameNotificationSettings(a.notificationSettings, b.notificationSettings) &&
      a.info.isClosed == b.info.isClosed &&
      a.info.isHidden == b.info.isHidden &&
      a.info.name.equals(b.info.name) &&
      sameIcon(a.info.icon, b.info.icon);
  }

  private static boolean sameMessage (@Nullable TdApi.Message a, @Nullable TdApi.Message b) {
    if (a == null || b == null) {
      return a == b;
    }
    return a.id == b.id && a.editDate == b.editDate && a.content.getConstructor() == b.content.getConstructor();
  }

  private static boolean sameDraft (@Nullable TdApi.DraftMessage a, @Nullable TdApi.DraftMessage b) {
    if (a == null || b == null) {
      return a == b;
    }
    return tgx.td.Td.equalsTo(a, b);
  }

  private static boolean sameIcon (@Nullable TdApi.ForumTopicIcon a, @Nullable TdApi.ForumTopicIcon b) {
    if (a == null || b == null) {
      return a == b;
    }
    return a.color == b.color && a.customEmojiId == b.customEmojiId;
  }

  private static boolean sameNotificationSettings (@Nullable TdApi.ChatNotificationSettings a, @Nullable TdApi.ChatNotificationSettings b) {
    if (a == null || b == null) {
      return a == b;
    }
    return a.useDefaultMuteFor == b.useDefaultMuteFor && a.muteFor == b.muteFor;
  }

  private int insertionIndex (TdApi.ForumTopic topic) {
    int index = Collections.binarySearch(topics, topic, comparator);
    return index >= 0 ? index : -index - 1;
  }

  // Pinned order

  /** Pinned topics, in their current order (the ids {@code SetPinnedForumTopics} takes). */
  public int[] pinnedTopicIds () {
    return pinnedOrder.get().clone(); // IntList.get() is its own array
  }

  /** Ids of the pinned topics of a server page, in the server's order. */
  private static int[] serverPinnedIds (TdApi.ForumTopic[] serverTopics) {
    IntList ids = new IntList(8);
    for (TdApi.ForumTopic topic : serverTopics) {
      if (topic.isPinned) {
        ids.append(topic.info.forumTopicId);
      }
    }
    return ids.get();
  }

  private void replacePinnedOrder (int[] ids) {
    pinnedOrder.clear();
    pinnedOrder.appendAll(ids);
  }

  private void prependPinned (int forumTopicId) {
    insertPinnedAt(0, forumTopicId);
  }

  /** Puts the id at {@code position} among the other ids (removing it first if it is already there). */
  private void insertPinnedAt (int position, int forumTopicId) {
    int[] rest = pinnedOrder.get().clone(); // IntList.get() is its own array, cleared and refilled below
    pinnedOrder.clear();
    int i = 0;
    boolean inserted = false;
    for (int id : rest) {
      if (id == forumTopicId) {
        continue;
      }
      if (i == position) {
        pinnedOrder.append(forumTopicId);
        inserted = true;
      }
      pinnedOrder.append(id);
      i++;
    }
    if (!inserted) {
      pinnedOrder.append(forumTopicId);
    }
  }

  /**
   * Makes the pinned order match the pinned rows as they are listed: every pinned row is in it, in list order, and
   * nothing else. Rows the order didn't know (sorted after the known ones) get their place that way.
   */
  private void normalizePinnedOrder () {
    IntList ids = new IntList(Math.max(8, pinnedOrder.size()));
    for (TdApi.ForumTopic topic : topics) {
      if (topic.isPinned) {
        ids.append(topic.info.forumTopicId);
      }
    }
    // Pinned topics that are known but not loaded as rows (a failed fetch) stay, so a reorder can't unpin them.
    for (int i = 0; i < pinnedOrder.size(); i++) {
      int id = pinnedOrder.get(i);
      if (!ids.contains(id)) {
        ids.append(id);
      }
    }
    replacePinnedOrder(ids.get());
  }

  /**
   * Sets the pinned order (e.g. the ids the server accepted in {@code SetPinnedForumTopics}) and moves the rows to
   * match it.
   */
  @UiThread
  public void setPinnedOrder (int[] ids) {
    if (isDestroyed) {
      return;
    }
    replacePinnedOrder(ids);
    resort();
  }

  /** Moves rows until the list is sorted by {@link #comparator} again, one {@code onTopicMoved} per moved row. */
  @UiThread
  private void resort () {
    List<TdApi.ForumTopic> sorted = new ArrayList<>(topics);
    Collections.sort(sorted, comparator);
    for (int i = 0; i < sorted.size(); i++) {
      TdApi.ForumTopic expected = sorted.get(i);
      if (topics.get(i) == expected) {
        continue;
      }
      int fromIndex = -1;
      for (int j = i + 1; j < topics.size(); j++) {
        if (topics.get(j) == expected) {
          fromIndex = j;
          break;
        }
      }
      if (fromIndex == -1) {
        continue;
      }
      topics.remove(fromIndex);
      topics.add(i, expected);
      for (Listener listener : listeners) {
        listener.onTopicMoved(this, fromIndex, i);
      }
    }
  }

  /**
   * Moves a pinned topic among the pinned ones before the server confirms it: the pinned order changes with it, so
   * the list stays sorted, and {@link #pinnedTopicIds()} gives the ids to send in {@code SetPinnedForumTopics}.
   */
  @UiThread
  public boolean movePinnedLocally (int fromIndex, int toIndex) {
    if (fromIndex == toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= topics.size() || toIndex >= topics.size()) {
      return false;
    }
    int step = toIndex > fromIndex ? 1 : -1;
    for (int i = fromIndex; ; i += step) {
      TdApi.ForumTopic topic = topics.get(i);
      if (!topic.isPinned || topic.info.isHidden) {
        // Only through pinned rows, and never across the hidden General, which stays first whatever its pin.
        return false;
      }
      if (i == toIndex) {
        break;
      }
    }
    normalizePinnedOrder();
    TdApi.ForumTopic moved = topics.get(fromIndex);
    int fromPosition = pinnedOrder.indexOf(moved.info.forumTopicId);
    int toPosition = pinnedOrder.indexOf(topics.get(toIndex).info.forumTopicId);
    if (fromPosition == -1 || toPosition == -1) {
      return false;
    }
    insertPinnedAt(toPosition, moved.info.forumTopicId);
    localReorderVersion++;
    topics.remove(fromIndex);
    topics.add(toIndex, moved);
    for (Listener listener : listeners) {
      listener.onTopicMoved(this, fromIndex, toIndex);
    }
    return true;
  }

  private long lastResyncAt;

  /**
   * Counts drag moves made here. A first page asked for before the latest move carries the old server order, so it
   * must not undo the move (mid-drag, or before {@code SetPinnedForumTopics} answers).
   */
  private int localReorderVersion;

  /** The current {@link #localReorderVersion}: pass it back to {@link #setPinnedOrder(int[], int)}. */
  public int localReorderVersion () {
    return localReorderVersion;
  }

  /** As {@link #setPinnedOrder(int[])}, unless the user moved a pinned topic again since {@code reorderVersion}. */
  @UiThread
  public void setPinnedOrder (int[] ids, int reorderVersion) {
    if (reorderVersion == localReorderVersion) {
      setPinnedOrder(ids);
    }
  }

  private int firstPageLimit () {
    return Math.min(100, Math.max(20, topics.size()));
  }

  /**
   * Fetches the first page again and takes its pin state and pinned order (at most once per
   * {@link #RESYNC_INTERVAL_MS}): the way to follow a reorder made on another device, which TDLib doesn't report.
   */
  @UiThread
  public boolean resyncFirstPage () {
    return resyncFirstPage(false);
  }

  /**
   * As {@link #resyncFirstPage()}; {@code force} skips the throttle, e.g. to undo a reorder the server refused.
   * Returns whether the page was asked for.
   */
  @UiThread
  public boolean resyncFirstPage (boolean force) {
    if (isDestroyed || !isLoaded || loadFailed) {
      return false;
    }
    long now = android.os.SystemClock.uptimeMillis();
    if (!force && lastResyncAt != 0 && now - lastResyncAt < RESYNC_INTERVAL_MS) {
      return false;
    }
    if (!force && XgramTopicFlood.waitMs(tdlib) > 0) {
      return false; // the server asked to wait; the next return or resume asks again
    }
    lastResyncAt = now;
    final int requestedReorderVersion = localReorderVersion;
    ForumRequests.send(tdlib, this, new TdApi.GetForumTopics(chatId, "", 0, 0, 0, firstPageLimit()), (result, error) -> tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      if (result == null) {
        XgramTopicFlood.onError(tdlib, error, 0);
        return;
      }
      applyFirstPage(result, requestedReorderVersion);
    }));
    return true;
  }

  /**
   * Puts the topics of a first page in and takes the server's pinned order from it, unless a pinned topic was moved
   * here after the page was asked for (its order is then older than the one shown).
   */
  @UiThread
  private void applyFirstPage (TdApi.ForumTopics result, int requestedReorderVersion) {
    for (TdApi.ForumTopic topic : result.topics) {
      putTopicImpl(topic);
    }
    setPinnedOrder(serverPinnedIds(result.topics), requestedReorderVersion);
    checkMissingRows(result);

  }

  /**
   * Rows listed among the topics of a fresh first page that the page doesn't have: deleted elsewhere (TDLib sends no
   * update for that, so they stayed for good) or out of place. Each is fetched: a deleted one goes, others move.
   */
  @UiThread
  private void checkMissingRows (TdApi.ForumTopics result) {
    if (result.topics.length == 0) {
      return;
    }
    java.util.Set<Integer> onPage = new java.util.HashSet<>();
    for (TdApi.ForumTopic topic : result.topics) {
      onPage.add(topic.info.forumTopicId);
    }
    // The page holds every topic: any other row is gone. Else only rows listed above its last one are suspect.
    int end = -1;
    if (result.topics.length >= result.totalCount) {
      end = topics.size();
    } else {
      for (int i = 0; i < topics.size(); i++) {
        if (onPage.contains(topics.get(i).info.forumTopicId)) {
          end = i;
        }
      }
    }
    List<Integer> missing = new ArrayList<>();
    // A few per page: more would be a burst of requests (the rest are seen at the next resync).
    for (int i = 0; i < end && missing.size() < MAX_SINGLE_FETCHES; i++) {
      TdApi.ForumTopic topic = topics.get(i);
      // General can't be deleted, and the hidden one is listed first here whatever its place on the server.
      if (!topic.info.isGeneral && !onPage.contains(topic.info.forumTopicId)) {
        missing.add(topic.info.forumTopicId);
      }
    }
    fetchSingles(missing);
  }

  /** Fetches topics again, e.g. after their pinned order changed on the server. */
  @UiThread
  public void refreshTopics (int[] forumTopicIds) {
    for (int forumTopicId : forumTopicIds) {
      scheduleRefresh(forumTopicId);
    }
  }

  @UiThread
  private void removeTopic (int forumTopicId) {
    pinnedOrder.remove(forumTopicId);
    int index = indexOf(forumTopicId);
    if (index != -1) {
      topics.remove(index);
      for (Listener listener : listeners) {
        listener.onTopicRemoved(this, index);
      }
    }
  }

  @UiThread
  private void notifyChanged (int index) {
    for (Listener listener : listeners) {
      listener.onTopicChanged(this, index);
    }
  }

  static int forumTopicId (@Nullable TdApi.MessageTopic topicId) {
    if (topicId == null) {
      // A message of this forum without a topic is one of General (messages sent there go without one), whose row
      // didn't follow them.
      return XgramForums.GENERAL_TOPIC_ID;
    }
    return topicId instanceof TdApi.MessageTopicForum ? ((TdApi.MessageTopicForum) topicId).forumTopicId : 0;
  }

  // ChatListener (TDLib thread)

  private long lastChatReadInboxMessageId = -1;

  @Override
  public void onChatReadInbox (long chatId, long lastReadInboxMessageId, int unreadCount, boolean availabilityChanged) {
    // Reading from the "All" tab, the merged view or another device marks messages read in their topics without
    // an update for each topic: fetch the topics that still look unread. Only when the chat's state changed, so a
    // refresh that makes TDLib resend the same state can't loop.
    // The server's position: ghost mode moves the one in the update up to each message viewed, nothing read on the
    // server, and refreshing every unread topic for each of them flooded the server while scrolling. Topics viewed
    // that way are refreshed through onLocalReadChanged.
    long serverReadId = lastReadInboxMessageId;
    tdlib.ui().post(() -> {
      // Only a moved read position: new messages change unreadCount too, and they arrive through onNewMessage.
      if (lastChatReadInboxMessageId == serverReadId) {
        return;
      }
      lastChatReadInboxMessageId = serverReadId;
      refreshUnreadTopics();
    });
  }

  /** Fetches the real counters of every topic that looks unread (batched with other refreshes). */
  @UiThread
  public void refreshUnreadTopics () {
    refreshUnreadTopics(0);
  }

  /** As {@link #refreshUnreadTopics()}, for the topics from {@code fromIndex} on. */
  @UiThread
  private void refreshUnreadTopics (int fromIndex) {
    if (isDestroyed) {
      return;
    }
    for (int i = Math.max(0, fromIndex); i < topics.size(); i++) {
      TdApi.ForumTopic topic = topics.get(i);
      if (topic.unreadCount > 0 || topic.unreadMentionCount > 0 || topic.unreadReactionCount > 0) {
        scheduleRefresh(topic.info.forumTopicId);
      }
    }
  }

  /**
   * A screen shows this list again (a cached list reused, or the topic list back in front): what changed meanwhile
   * without an update, such as the order, last messages and counters, is fetched again. The first page comes in one
   * request (throttled); unread topics below it are refreshed one by one.
   */
  @UiThread
  public void refreshOnReturn () {
    if (isDestroyed || !isLoaded) {
      return;
    }
    if (loadFailed) {
      // "No topics" after the first page failed (offline, flood wait): load it again, the screens show the spinner.
      resetAfterFailure();
      for (Listener listener : listeners) {
        listener.onTopicsLoaded(this);
      }
      loadMore();
      return;
    }
    int firstPage = firstPageLimit();
    boolean resynced = resyncFirstPage();
    long now = android.os.SystemClock.uptimeMillis();
    if (!resynced && lastReturnRefreshAt != 0 && now - lastReturnRefreshAt < RETURN_REFRESH_INTERVAL_MS) {
      // Back again right away (in and out of topics): what changed since the last time came through updates.
      return;
    }
    lastReturnRefreshAt = now;
    refreshUnreadTopics(resynced ? firstPage : 0);
  }

  /** The unread topics are refreshed on return at most this often (uptime ms), unless the first page is fetched. */
  private static final long RETURN_REFRESH_INTERVAL_MS = 10_000;
  private long lastReturnRefreshAt;

  @Override
  public void onChatTopMessageChanged (long chatId, @Nullable TdApi.Message topMessage) {
    // The chat's last message moved without a new message for this list, e.g. after a gap was filled on reconnect:
    // its topic's last message and order may be stale. (Deleted last messages are handled in onMessagesDeleted.)
    if (topMessage == null || topMessage.sendingState != null) {
      return; // messages being sent show at once through onNewMessage
    }
    int forumTopicId = forumTopicId(topMessage.topicId);
    long messageId = topMessage.id;
    tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      TdApi.ForumTopic topic = find(forumTopicId);
      if (topic != null && (topic.lastMessage == null || topic.lastMessage.id < messageId)) {
        scheduleRefresh(forumTopicId);
      }
    });
  }

  @Override
  public void onForumTopicInfoChanged (TdApi.ForumTopicInfo info) {
    tdlib.ui().post(() -> applyTopicInfo(info));
  }

  @UiThread
  private void applyTopicInfo (TdApi.ForumTopicInfo info) {
    if (isDestroyed) {
      return;
    }
    int index = indexOf(info.forumTopicId);
    if (index == -1) {
      if (isLoading) {
        infosWhileLoading.put(info.forumTopicId, info);
      }
      // Not loaded (yet). A new topic arrives with its "topic created" message through onNewMessage; fetching here
      // too would request every topic TDLib tells about while pages are loading.
      return;
    }
    TdApi.ForumTopic topic = topics.get(index);
    boolean hiddenChanged = topic.info.isHidden != info.isHidden;
    boolean changed = !sameInfo(topic.info, info);
    topic.info = info;
    if (hiddenChanged) {
      // The hidden General goes first: it moves now, as a row out of order misplaces the rows put in after it too.
      index = reposition(index);
      scheduleRefresh(info.forumTopicId);
    }
    if (changed) {
      notifyChanged(index);
    }
  }

  private static boolean sameInfo (TdApi.ForumTopicInfo a, TdApi.ForumTopicInfo b) {
    return a.isClosed == b.isClosed &&
      a.isHidden == b.isHidden &&
      a.name.equals(b.name) &&
      sameIcon(a.icon, b.icon);
  }

  /** Moves the row at {@code index} to where the comparator puts it now. Returns its new index. */
  @UiThread
  private int reposition (int index) {
    TdApi.ForumTopic topic = topics.remove(index);
    int newIndex = insertionIndex(topic);
    topics.add(newIndex, topic);
    if (newIndex != index) {
      for (Listener listener : listeners) {
        listener.onTopicMoved(this, index, newIndex);
      }
    }
    return newIndex;
  }

  @Override
  public void onForumTopicUpdated (TdApi.UpdateForumTopic update) {
    tdlib.ui().post(() -> applyTopicUpdate(update));
  }

  @UiThread
  private void applyTopicUpdate (TdApi.UpdateForumTopic update) {
    if (isDestroyed) {
      return;
    }
    int index = indexOf(update.forumTopicId);
    if (index == -1) {
      if (isLoading) {
        // It may be a row once the page is in: applied then (the last one of each topic).
        updatesWhileLoading.put(update.forumTopicId, update);
        return;
      }
      if (!update.isPinned) {
        // Known as pinned but not loaded as a row: forget it, or the next reorder would pin it again.
        pinnedOrder.remove(update.forumTopicId);
      }
      return;
    }
    TdApi.ForumTopic topic = topics.get(index);
    // Ghost mode: mentions viewed without reading them count as read here.
    int mentions = update.unreadMentionCount;
    boolean readChanged = topic.lastReadInboxMessageId != update.lastReadInboxMessageId;
    boolean pinChanged = topic.isPinned != update.isPinned;
    boolean draftChanged = !sameDraft(topic.draftMessage, update.draftMessage);
    boolean changed = readChanged || pinChanged || draftChanged ||
      topic.lastReadOutboxMessageId != update.lastReadOutboxMessageId ||
      topic.unreadMentionCount != mentions ||
      topic.unreadReactionCount != update.unreadReactionCount ||
      topic.unreadPollVoteCount != update.unreadPollVoteCount ||
      !sameNotificationSettings(topic.notificationSettings, update.notificationSettings);
    topic.isPinned = update.isPinned;
    topic.lastReadInboxMessageId = update.lastReadInboxMessageId;
    topic.lastReadOutboxMessageId = update.lastReadOutboxMessageId;
    topic.unreadMentionCount = mentions;
    topic.unreadReactionCount = update.unreadReactionCount;
    topic.unreadPollVoteCount = update.unreadPollVoteCount;
    topic.notificationSettings = update.notificationSettings;
    topic.draftMessage = update.draftMessage;
    // unread_count isn't part of this update. Reading up to the last message means nothing is left.
    boolean readFully = topic.lastMessage != null && topic.lastReadInboxMessageId >= topic.lastMessage.id;
    if (readFully && topic.unreadCount != 0) {
      topic.unreadCount = 0;
      changed = true;
    }
    if (pinChanged) {
      // Pinned here or elsewhere: it goes on top of the pinned ones (as on the server); unpinned, it falls back to
      // its place by date. No fetch is needed, as order doesn't follow pinning.
      if (update.isPinned) {
        prependPinned(update.forumTopicId);
      } else {
        pinnedOrder.remove(update.forumTopicId);
      }
      index = reposition(index);
    }
    if (changed) {
      notifyChanged(index);

    }
    // Partial reads change the unread count, and a draft the order (which this update doesn't carry): fetch the
    // exact values. Fetching on every update can loop, as fetching a topic may emit this update again.
    if ((readChanged && !readFully) || draftChanged) {
      scheduleRefresh(update.forumTopicId);
    }
  }

  // MessageListener (TDLib thread)

  @Override
  public void onNewMessage (TdApi.Message message) {
    int forumTopicId = forumTopicId(message.topicId);
    tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      if (message.sendingState != null && message.schedulingState == null) {
        // Scheduled messages also arrive here, but they aren't the topic's last message.
        int index = indexOf(forumTopicId);
        if (index != -1) {
          // A message being sent: TDLib's topic last_message only comes from the server, which doesn't know it yet, so
          // a fetch would return the previous message. Show the clock and the new preview now; the server order is
          // fetched once it is sent.
          topics.get(index).lastMessage = message;
          notifyChanged(index);
          return;
        }
      }
      scheduleRefresh(forumTopicId);
    });
  }

  @Override
  public void onMessageSendSucceeded (TdApi.Message message, long oldMessageId) {
    int forumTopicId = forumTopicId(message.topicId);
    tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      int index = indexOf(forumTopicId);
      if (index != -1) {
        TdApi.ForumTopic topic = topics.get(index);
        if (topic.lastMessage != null && topic.lastMessage.id == oldMessageId) {
          // The clock goes away at once; the fetch below brings the server order.
          topic.lastMessage = message;
          notifyChanged(index);
        }
      }
      scheduleRefresh(forumTopicId);
    });
  }

  @Override
  public void onMessageSendFailed (TdApi.Message message, long oldMessageId, TdApi.Error error) {
    int forumTopicId = forumTopicId(message.topicId);
    tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      int index = indexOf(forumTopicId);
      if (index != -1) {
        TdApi.ForumTopic topic = topics.get(index);
        if (topic.lastMessage != null && topic.lastMessage.id == oldMessageId) {
          // Not pending any more: left as it was, putTopicImpl would keep the pending preview over the server's for good.
          topic.lastMessage = message;
          notifyChanged(index);
        }
      }
      scheduleRefresh(forumTopicId);
    });
  }

  @Override
  public void onMessageContentChanged (long chatId, long messageId, TdApi.MessageContent newContent) {
    tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      for (int i = 0; i < topics.size(); i++) {
        TdApi.Message lastMessage = topics.get(i).lastMessage;
        if (lastMessage != null && lastMessage.id == messageId) {
          lastMessage.content = newContent;
          notifyChanged(i);
          break;
        }
      }
    });
  }

  @Override
  public void onMessagesDeleted (long chatId, long[] messageIds) {
    tdlib.ui().post(() -> {
      if (isDestroyed) {
        return;
      }
      for (int i = 0; i < topics.size(); i++) {
        TdApi.ForumTopic topic = topics.get(i);
        if (topic.lastMessage != null) {
          for (long messageId : messageIds) {
            if (topic.lastMessage.id == messageId) {
              if (topic.lastMessage.sendingState != null) {
                // Deleted before it was sent (or after it failed): only this list knows it. Drop it, or
                // putTopicImpl would keep its preview over the server's last message.
                topic.lastMessage = null;
                notifyChanged(i);
              }
              scheduleRefresh(topic.info.forumTopicId);
              break;
            }
          }
        }
      }
    });
  }

  @Override
  public void performDestroy () {
    if (!isDestroyed) {
      isDestroyed = true;
      ForumRequests.cancel(tdlib, this);
      tdlib.ui().removeCallbacks(refreshTask);
      tdlib.ui().removeCallbacksAndMessages(retryToken);
      pendingRefresh.clear();
      updatesWhileLoading.clear();
      infosWhileLoading.clear();
      fetchedWhileLoading.clear();
      tdlib.listeners().unsubscribeFromChatUpdates(chatId, this);
      tdlib.listeners().unsubscribeFromMessageUpdates(chatId, this);
      listeners.clear();
    }
  }
}
