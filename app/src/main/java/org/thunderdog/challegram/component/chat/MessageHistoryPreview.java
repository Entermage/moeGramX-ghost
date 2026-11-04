package org.thunderdog.challegram.component.chat;

import android.os.SystemClock;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.MessageListener;
import org.thunderdog.challegram.telegram.Tdlib;
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

  private static final class State implements MessageListener {
    final LinkedHashMap<String, Window> windows = new LinkedHashMap<>(8, .75f, true);
    long revision;
    private void changed(long chatId, long... messageIds) {
      synchronized (states) {
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
    @Override public void onMessagesDeleted(long c, long[] ids) { changed(c, ids); }
    @Override public void onMessageSendSucceeded(TdApi.Message m, long old) { changed(m.chatId, old, m.id); }
    @Override public void onMessageSendFailed(TdApi.Message m, long old, TdApi.Error e) { changed(m.chatId, old, m.id); }
  }

  public static void put(Tdlib tdlib, long chatId, long topicId, TdApi.Message[] messages,
                         long anchorId, int offset, boolean tail) {
    if (!tdlib.isAuthorized() || messages.length == 0 || messages.length > MAX_MESSAGES) return;
    synchronized (states) {
      State state = states.get(tdlib);
      if (state == null) {
        state = new State(); states.put(tdlib, state);
        tdlib.listeners().subscribeForGlobalUpdates(state);
      }
      ArrayList<TdApi.Message> copy = new ArrayList<>(messages.length);
      for (TdApi.Message message : messages) {
        // Exclude expiring, pending and synthetic rows; media files stay TDLib-owned.
        if (message == null || message.chatId != chatId || message.id <= 0 ||
            message.sendingState != null || message.schedulingState != null ||
            message.selfDestructType != null || message.autoDeleteIn > 0) return;
        long actualTopic = message.topicId instanceof TdApi.MessageTopicForum ?
          ((TdApi.MessageTopicForum) message.topicId).forumTopicId : 0;
        if (topicId != 0 && actualTopic != topicId && !(topicId == 1 && actualTopic == 0)) return;
        copy.add(Td.copyOf(message));
      }
      state.windows.values().removeIf(w -> SystemClock.uptimeMillis() - w.created >= TTL_MS);
      String key = chatId + ":" + topicId;
      state.windows.put(key, new Window(copy.toArray(new TdApi.Message[0]), anchorId, offset, tail,
        key, ++state.revision, SystemClock.uptimeMillis()));
      while (state.windows.size() > MAX_WINDOWS) state.windows.remove(state.windows.keySet().iterator().next());
    }
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
