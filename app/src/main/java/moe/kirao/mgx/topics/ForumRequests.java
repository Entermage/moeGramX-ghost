package moe.kirao.mgx.topics;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.tool.UI;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/** Bounded, coalesced metadata reads. Mutating topic operations never enter this queue. */
public final class ForumRequests {
  private ForumRequests () { }
  private static final int MAX_NATIVE = 2;
  private static final int MAX_QUEUED = 24;
  private static final int MAX_WAITERS = 16;
  private static final long TIMEOUT_MS = 30_000;
  private static final Map<Tdlib, State> states = new IdentityHashMap<>();

  private static final class Waiter {
    final Object owner;
    final Tdlib.ResultHandler<TdApi.Object> handler;
    Waiter (Object owner, Tdlib.ResultHandler<TdApi.Object> handler) {
      this.owner = owner;
      this.handler = handler;
    }
  }

  private static final class Entry {
    final String key;
    final TdApi.Function<TdApi.Object> query;
    final ArrayList<Waiter> waiters = new ArrayList<>();
    boolean active, expired;
    Runnable timeout;
    ForumTopicSnapshotUpdates updates;
    Entry (String key, TdApi.Function<TdApi.Object> query) {
      this.key = key;
      this.query = query;
    }
  }

  private static final class State {
    final Tdlib tdlib;
    final LinkedHashMap<String, Entry> entries = new LinkedHashMap<>();
    final Runnable resume = () -> pump(this);
    int nativeCount, peakNative, peakQueued;
    long sent, completed, timedOut, merged, rejected;
    boolean closed;
    State (Tdlib tdlib) { this.tdlib = tdlib; }
  }

  private static String key (TdApi.Function<?> query) {
    if (query instanceof TdApi.GetForumTopic) {
      TdApi.GetForumTopic q = (TdApi.GetForumTopic) query;
      return "topic:" + q.chatId + ":" + q.forumTopicId;
    }
    if (query instanceof TdApi.GetForumTopics) {
      TdApi.GetForumTopics q = (TdApi.GetForumTopics) query;
      return "page:" + q.chatId + ":" + q.offsetDate + ":" + q.offsetMessageId + ":" + q.offsetForumTopicId + ":" + q.limit + ":" + q.query;
    }
    throw new IllegalArgumentException("Only forum metadata reads may be queued");
  }

  private static boolean matches (Entry entry, long chatId, int topicId) {
    if (!entry.active || entry.expired) return false;
    TdApi.Function<?> function = entry.query;
    if (function instanceof TdApi.GetForumTopic) {
      TdApi.GetForumTopic query = (TdApi.GetForumTopic) function;
      return query.chatId == chatId && query.forumTopicId == topicId;
    }
    return ((TdApi.GetForumTopics) function).chatId == chatId;
  }

  public static void onTopicInfo (Tdlib tdlib, TdApi.ForumTopicInfo info) {
    if (!UI.inUiThread()) { tdlib.ui().post(() -> onTopicInfo(tdlib, info)); return; }
    State state = states.get(tdlib);
    if (state == null) return;
    for (Entry entry : state.entries.values()) if (matches(entry, info.chatId, info.forumTopicId)) {
      if (entry.updates == null) entry.updates = new ForumTopicSnapshotUpdates();
      entry.updates.record(info);
    }
  }

  public static void onTopicUpdate (Tdlib tdlib, TdApi.UpdateForumTopic update) {
    if (!UI.inUiThread()) { tdlib.ui().post(() -> onTopicUpdate(tdlib, update)); return; }
    State state = states.get(tdlib);
    if (state == null) return;
    for (Entry entry : state.entries.values()) if (matches(entry, update.chatId, update.forumTopicId)) {
      if (entry.updates == null) entry.updates = new ForumTopicSnapshotUpdates();
      entry.updates.record(update);
    }
  }

  @SuppressWarnings("unchecked")
  public static <T extends TdApi.Object> void send (Tdlib tdlib, Object owner, TdApi.Function<T> query, Tdlib.ResultHandler<T> handler) {
    if (!UI.inUiThread()) {
      tdlib.ui().post(() -> send(tdlib, owner, query, handler));
      return;
    }
    State state = states.computeIfAbsent(tdlib, State::new);
    String key = key(query);
    Entry entry = state.entries.get(key);
    if (entry != null && entry.expired) {
      state.rejected++;
      handler.onResult(null, new TdApi.Error(504, "Previous topic request is still pending"));
      return;
    }
    if (entry == null) {
      if (state.entries.size() - state.nativeCount >= MAX_QUEUED) {
        state.rejected++;
        handler.onResult(null, new TdApi.Error(503, "Topic request queue is busy"));
        return;
      }
      entry = new Entry(key, (TdApi.Function<TdApi.Object>) (TdApi.Function<?>) query);
      state.entries.put(key, entry);
      Entry pending = entry;
      entry.timeout = () -> expire(state, pending);
      tdlib.ui().postDelayed(entry.timeout, TIMEOUT_MS);
    } else {
      state.merged++;
    }
    // A screen's newer request for the same key supersedes its previous callback.
    entry.waiters.removeIf(waiter -> waiter.owner == owner);
    if (entry.waiters.size() >= MAX_WAITERS) {
      state.rejected++;
      handler.onResult(null, new TdApi.Error(503, "Topic request has too many observers"));
      return;
    }
    entry.waiters.add(new Waiter(owner, (Tdlib.ResultHandler<TdApi.Object>) (Tdlib.ResultHandler<?>) handler));
    pump(state);
    state.peakQueued = Math.max(state.peakQueued, state.entries.size() - state.nativeCount);
  }

  private static void pump (State state) {
    if (state.closed) return;
    state.tdlib.ui().removeCallbacks(state.resume);
    boolean queued = false;
    for (Entry entry : state.entries.values()) if (!entry.active) { queued = true; break; }
    if (!queued || state.nativeCount >= MAX_NATIVE) return;
    long floodWait = XgramTopicFlood.waitMs(state.tdlib);
    if (floodWait > 0) {
      state.tdlib.ui().postDelayed(state.resume, floodWait);
      return;
    }
    for (Entry entry : new ArrayList<>(state.entries.values())) {
      if (state.nativeCount >= MAX_NATIVE) break;
      if (entry.active || entry.expired || entry.waiters.isEmpty()) continue;
      entry.active = true;
      state.nativeCount++;
      state.peakNative = Math.max(state.peakNative, state.nativeCount);
      state.sent++;
      state.tdlib.send(entry.query, (result, error) -> state.tdlib.ui().post(() -> complete(state, entry, result, error)));
    }
  }

  private static void complete (State state, Entry entry, TdApi.Object result, TdApi.Error error) {
    if (state.closed || state.entries.get(entry.key) != entry) return;
    state.entries.remove(entry.key);
    state.tdlib.ui().removeCallbacks(entry.timeout);
    state.nativeCount--;
    state.completed++;
    if (error == null && entry.updates != null) {
      if (entry.updates.overflowed()) {
        result = null;
        error = new TdApi.Error(503, "Too many topic updates while loading");
      } else {
        result = entry.updates.apply(result);
      }
    }
    entry.updates = null;
    if (error != null) XgramTopicFlood.onError(state.tdlib, error, 0);
    ArrayList<Waiter> callbacks = new ArrayList<>(entry.waiters);
    entry.waiters.clear();
    for (Waiter waiter : callbacks) waiter.handler.onResult(result, error);
    pump(state);
  }

  private static void expire (State state, Entry entry) {
    if (state.closed || state.entries.get(entry.key) != entry) return;
    state.timedOut++;
    entry.expired = true;
    entry.updates = null;
    // A Java timeout cannot cancel TDLib's live request. Its native slot remains occupied
    // until the matching callback or AuthorizationStateClosed, including across reopening.
    if (!entry.active) state.entries.remove(entry.key);
    ArrayList<Waiter> callbacks = new ArrayList<>(entry.waiters);
    entry.waiters.clear();
    for (Waiter waiter : callbacks) waiter.handler.onResult(null, new TdApi.Error(504, "Topic request timed out"));
    pump(state);
  }

  /** Drop queued work and UI callbacks for a closed/superseded screen. Shared native work may finish. */
  public static void cancel (Tdlib tdlib, Object owner) {
    if (!UI.inUiThread()) { tdlib.ui().post(() -> cancel(tdlib, owner)); return; }
    State state = states.get(tdlib);
    if (state == null) return;
    Iterator<Entry> iterator = state.entries.values().iterator();
    while (iterator.hasNext()) {
      Entry entry = iterator.next();
      entry.waiters.removeIf(waiter -> waiter.owner == owner);
      if (entry.waiters.isEmpty() && !entry.active) {
        state.tdlib.ui().removeCallbacks(entry.timeout);
        iterator.remove();
      }
    }
    pump(state);
  }

  /** Called only once the old native TDLib client is closed, never on a network disconnect. */
  public static void onClientClosed (Tdlib tdlib) {
    if (!UI.inUiThread()) { tdlib.ui().post(() -> onClientClosed(tdlib)); return; }
    State state = states.remove(tdlib);
    if (state == null) return;
    state.closed = true;
    tdlib.ui().removeCallbacks(state.resume);
    ArrayList<Waiter> callbacks = new ArrayList<>();
    for (Entry entry : state.entries.values()) {
      tdlib.ui().removeCallbacks(entry.timeout);
      callbacks.addAll(entry.waiters);
      entry.waiters.clear();
      entry.updates = null;
    }
    state.entries.clear();
    // Every caller gets an end state; a new request goes to the next client's fresh queue.
    for (Waiter waiter : callbacks) waiter.handler.onResult(null, new TdApi.Error(CLIENT_CLOSED_CODE, CLIENT_CLOSED_MESSAGE));
  }

  private static final int CLIENT_CLOSED_CODE = 500;
  private static final String CLIENT_CLOSED_MESSAGE = "Topic request ended: client closed";

  /** The request got no answer because its client closed; it is not a fact about the topic. */
  public static boolean isClientClosed (TdApi.Error error) {
    return error != null && error.code == CLIENT_CLOSED_CODE && CLIENT_CLOSED_MESSAGE.equals(error.message);
  }

  /** UI-thread diagnostic counters; contains no account, chat, query or message content. */
  @androidx.annotation.Keep
  public static long[] snapshot (Tdlib tdlib) {
    State s = states.get(tdlib);
    return s == null ? new long[9] : new long[] {s.nativeCount, s.entries.size()-s.nativeCount,
      s.peakNative, s.peakQueued, s.sent, s.completed, s.timedOut, s.merged, s.rejected};
  }
}
