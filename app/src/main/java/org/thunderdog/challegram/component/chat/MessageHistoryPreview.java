package org.thunderdog.challegram.component.chat;

import android.os.SystemClock;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.MessageListener;
import org.thunderdog.challegram.telegram.Tdlib;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.ArrayList;
import tgx.td.Td;

/** Bounded, process-local display snapshots. Never an authoritative history/page cache. */
public final class MessageHistoryPreview {
  public static final int MAX_MESSAGES = 80;
  /** Window offset placing its anchor row at the top, where an unread entry puts the first unread row. */
  public static final int OFFSET_TOP = Integer.MIN_VALUE;
  private static final int MAX_WINDOWS = 6;
  private static final long TTL_MS = 5 * 60_000L;
  /** Local scans followed at once; past it a topic opens with the normal loading state. */
  private static final int MAX_TRACKERS = 8;
  /** Changed message IDs kept for one scan; past it the scan is not published. */
  private static final int MAX_TRACKED_CHANGES = 512;
  private static final IdentityHashMap<Tdlib, State> states = new IdentityHashMap<>();

  public static final class Window {
    public final TdApi.Message[] messages;
    public final long anchorId;
    public final int offset;
    private final long created, revision;
    private final String key;
    private final boolean tail;
    private Window(TdApi.Message[] messages, long anchorId, int offset, boolean tail, String key, long revision, long created) {
      this.messages = messages; this.anchorId = anchorId; this.offset = offset;
      this.tail = tail; this.key = key; this.revision = revision; this.created = created;
    }
  }

  /**
   * Message changes of one chat while a window is built from its stored history, before it is stored:
   * a stored window is invalidated by them, messages not stored yet must be too.
   */
  public static final class Tracker {
    final long chatId, created;
    final HashSet<Long> deleted = new HashSet<>(), changed = new HashSet<>();
    boolean overflow;
    private Tracker(long chatId, long created) { this.chatId = chatId; this.created = created; }
    private void record(HashSet<Long> target, long... messageIds) {
      if (overflow) return;
      for (long id : messageIds) target.add(id);
      if (deleted.size() + changed.size() > MAX_TRACKED_CHANGES) {
        overflow = true; deleted.clear(); changed.clear();
      }
    }
    /** Under the lock: whether one of the messages changed or the changes weren't all kept. */
    private boolean isStale(TdApi.Message[] messages) {
      if (overflow) return true;
      for (TdApi.Message message : messages) {
        if (deleted.contains(message.id) || changed.contains(message.id)) return true;
      }
      return false;
    }
  }

  private static final class State implements MessageListener {
    final LinkedHashMap<String, Window> windows = new LinkedHashMap<>(8, .75f, true);
    final ArrayList<Tracker> trackers = new ArrayList<>();
    long revision;
    private void changed(long chatId, long... messageIds) { changed(chatId, false, messageIds); }
    private void changed(long chatId, boolean deletion, long... messageIds) {
      synchronized (states) {
        for (Tracker tracker : trackers) {
          if (tracker.chatId == chatId) tracker.record(deletion ? tracker.deleted : tracker.changed, messageIds);
        }
        // Forum topics share a chat ID. An edit elsewhere must not erase this window.
        windows.entrySet().removeIf(entry -> {
          if (!entry.getKey().startsWith(chatId + ":")) return false;
          for (TdApi.Message message : entry.getValue().messages) {
            for (long id : messageIds) if (message.id == id) return true;
          }
          return false;
        });
      }
    }
    @Override public void onMessageContentChanged(long c, long id, TdApi.MessageContent content) { changed(c, id); }
    @Override public void onMessageEphemeralContentChanged(long c, long id, TdApi.EphemeralMessageContent content) { changed(c, id); }
    @Override public void onMessageEdited(long c, long id, int date, TdApi.ReplyMarkup markup) { changed(c, id); }
    @Override public void onMessagesDeleted(long c, long[] ids) { changed(c, true, ids); }
    @Override public void onMessageSendSucceeded(TdApi.Message m, long old) { changed(m.chatId, old, m.id); }
    @Override public void onMessageSendFailed(TdApi.Message m, long old, TdApi.Error e) { changed(m.chatId, old, m.id); }
  }

  private static State state(Tdlib tdlib) {
    State state = states.get(tdlib);
    if (state == null) {
      state = new State(); states.put(tdlib, state);
      tdlib.listeners().subscribeForGlobalUpdates(state);
    }
    return state;
  }

  /** Starts following the chat's message changes for a window being built; null when it can't be followed. */
  public static Tracker track(Tdlib tdlib, long chatId) {
    if (!tdlib.isAuthorized()) return null;
    synchronized (states) {
      State state = state(tdlib);
      // A scan ends with its last page; one older than a window's lifetime lost its callbacks.
      state.trackers.removeIf(t -> SystemClock.uptimeMillis() - t.created >= TTL_MS);
      if (state.trackers.size() >= MAX_TRACKERS) return null;
      Tracker tracker = new Tracker(chatId, SystemClock.uptimeMillis());
      state.trackers.add(tracker);
      return tracker;
    }
  }

  public static void untrack(Tdlib tdlib, Tracker tracker) {
    State idle;
    synchronized (states) {
      State state = states.get(tdlib);
      idle = state != null && state.trackers.remove(tracker) ? removeIfIdle(tdlib, state) : null;
    }
    if (idle != null) tdlib.listeners().unsubscribeFromGlobalUpdates(idle);
  }

  /** Under the lock: with no window and no scan left, the account stops listening until one needs it again. */
  private static State removeIfIdle(Tdlib tdlib, State state) {
    if (!state.trackers.isEmpty() || !state.windows.isEmpty() || states.get(tdlib) != state) return null;
    states.remove(tdlib);
    return state;
  }

  /** Whether the message was deleted since tracking began. */
  public static boolean isDeleted(Tracker tracker, long messageId) {
    synchronized (states) { return tracker.deleted.contains(messageId); }
  }

  public static void put(Tdlib tdlib, long chatId, long topicId, TdApi.Message[] messages,
                         long anchorId, int offset, boolean tail) {
    put(tdlib, chatId, topicId, messages, anchorId, offset, tail, null);
  }

  /**
   * Stores a window. With a tracker, it ends tracking and stores nothing if one of the messages changed since it
   * began, or tracking was lost: afterwards the stored window is invalidated by the changes instead.
   * @return whether the window was stored
   */
  public static boolean put(Tdlib tdlib, long chatId, long topicId, TdApi.Message[] messages,
                            long anchorId, int offset, boolean tail, Tracker tracker) {
    boolean stored;
    State idle = null;
    synchronized (states) {
      stored = putLocked(tdlib, chatId, topicId, messages, anchorId, offset, tail, tracker);
      State state = states.get(tdlib);
      if (!stored && tracker != null && state != null) idle = removeIfIdle(tdlib, state);
    }
    if (idle != null) tdlib.listeners().unsubscribeFromGlobalUpdates(idle);
    return stored;
  }

  // Under the lock.
  private static boolean putLocked(Tdlib tdlib, long chatId, long topicId, TdApi.Message[] messages,
                                   long anchorId, int offset, boolean tail, Tracker tracker) {
    if (tracker != null) {
      State tracked = states.get(tdlib);
      if (tracked == null || !tracked.trackers.remove(tracker) || tracker.chatId != chatId || tracker.isStale(messages)) return false;
    }
    if (!tdlib.isAuthorized() || messages.length == 0 || messages.length > MAX_MESSAGES) return false;
    State state = state(tdlib);
    ArrayList<TdApi.Message> copy = new ArrayList<>(messages.length);
    for (TdApi.Message message : messages) {
      // Exclude expiring, pending and synthetic rows; media files stay TDLib-owned.
      if (message == null || message.chatId != chatId || message.id <= 0 ||
          message.sendingState != null || message.schedulingState != null ||
          message.selfDestructType != null || message.autoDeleteIn > 0) return false;
      long actualTopic = message.topicId instanceof TdApi.MessageTopicForum ?
        ((TdApi.MessageTopicForum) message.topicId).forumTopicId : 0;
      if (topicId != 0 && actualTopic != topicId && !(topicId == 1 && actualTopic == 0)) return false;
      copy.add(Td.copyOf(message));
    }
    state.windows.values().removeIf(w -> SystemClock.uptimeMillis() - w.created >= TTL_MS);
    String key = chatId + ":" + topicId;
    state.windows.put(key, new Window(copy.toArray(new TdApi.Message[0]), anchorId, offset, tail,
      key, ++state.revision, SystemClock.uptimeMillis()));
    while (state.windows.size() > MAX_WINDOWS) state.windows.remove(state.windows.keySet().iterator().next());
    return true;
  }

  public static Window get(Tdlib tdlib, long chatId, long topicId, long requestedId, boolean latest) {
    return get(tdlib, chatId, topicId, requestedId, latest, false);
  }

  public static Window get(Tdlib tdlib, long chatId, long topicId, long requestedId, boolean latest,
                           boolean allowPreviousPosition) {
    synchronized (states) {
      State state = states.get(tdlib);
      if (!tdlib.isAuthorized() || state == null) return null;
      Window w = state.windows.get(chatId + ":" + topicId);
      if (w == null) return null;
      if (SystemClock.uptimeMillis() - w.created >= TTL_MS) {
        state.windows.remove(chatId + ":" + topicId); return null;
      }
      // Unread lookup may target a new message outside the last visible window. Show that
      // window only as a temporary preview; the authoritative request still resolves unread.
      if (!allowPreviousPosition && (latest ? !w.tail :
          requestedId < w.messages[w.messages.length - 1].id || requestedId > w.messages[0].id)) return null;
      TdApi.Message[] copy = new TdApi.Message[w.messages.length];
      for (int i=0; i<copy.length; i++) copy[i] = Td.copyOf(w.messages[i]);
      Window result = new Window(copy, w.anchorId, w.offset, w.tail, w.key, w.revision, w.created);
      return result;
    }
  }

  public static boolean isValid(Tdlib tdlib, Window window) {
    synchronized (states) {
      State state = states.get(tdlib);
      Window current = state != null ? state.windows.get(window.key) : null;
      return current != null && current.revision == window.revision &&
        SystemClock.uptimeMillis() - window.created < TTL_MS;
    }
  }

  public static void clear(Tdlib tdlib) {
    State state;
    synchronized (states) { state = states.remove(tdlib); }
    if (state != null) tdlib.listeners().unsubscribeFromGlobalUpdates(state);
  }
}
