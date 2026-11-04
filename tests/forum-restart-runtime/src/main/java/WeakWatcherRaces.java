import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.telegram.TdlibDataManager;
import org.thunderdog.challegram.telegram.TdlibForumTopicManager;

import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.lang.ref.Reference;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import me.vkryl.core.reference.ReferenceMap;

/**
 * A weak watcher registered right after a generation step (client restart, cancelled or answered
 * key) must belong to the next request: it is neither ended by the old generation nor fed its
 * answer. Each scenario stops the production step while it waits for the weak watcher map and
 * registers at the earliest point another thread can get in:
 * - the step still holds dataLock: the registration runs on a third thread and waits for dataLock;
 * - the step released dataLock first (the bug): the registration runs on the thread holding the
 *   map, which is reentrant, so it lands inside the gap deterministically.
 * Monitors are always taken in the production order (dataLock, then the map), every wait is
 * bounded, and helper threads are daemons: a regression fails, it never hangs.
 */
final class WeakWatcherRaces {
  private static final ThreadMXBean THREADS = ManagementFactory.getThreadMXBean();
  private static final long WAIT_NS = 5_000_000_000L;

  static int checks;

  static void check (boolean value, String message) {
    checks++;
    if (!value) throw new AssertionError(message);
  }

  /** Upstream-style manager that ends waits on restart, exposing the production result paths. */
  static final class EndingManager extends TdlibDataManager<Long, TdApi.Sticker, EndingManager.Entry> {
    static final class Entry extends TdlibDataManager.AbstractEntry<Long, TdApi.Sticker> {
      Entry (Long key, TdApi.Sticker value, TdApi.Error error) { super(key, value, error); }
    }
    final List<Long> requested = new ArrayList<>();
    final List<Integer> contexts = new ArrayList<>();
    EndingManager (Tdlib tdlib) { super(tdlib); }
    @Override protected boolean endsWaitsOnRestart () { return true; }
    @Override protected Entry newEntry (Long key, TdApi.Sticker value, TdApi.Error error) { return new Entry(key, value, error); }
    @Override protected void requestData (int contextId, Collection<Long> keys) { for (Long key : keys) { contexts.add(contextId); requested.add(key); } }
    void cancel (int contextId, long key) { processCancelled(contextId, key, new TdApi.Error(500, "Topic request ended: client closed")); }
    void answer (int contextId, long key) { processData(contextId, key, new TdApi.Sticker()); }
  }

  static final class Counter<K, V extends TdApi.Object, R extends TdlibDataManager.AbstractEntry<K, V>> implements TdlibDataManager.Watcher<K, V, R> {
    final AtomicInteger values = new AtomicInteger(), errors = new AtomicInteger();
    @Override public void onEntryLoaded (TdlibDataManager<K, V, R> context, R entry) {
      (entry.value != null ? values : errors).incrementAndGet();
    }
    int total () { return values.get() + errors.get(); }
  }

  private static Object field (Object manager, String name) throws ReflectiveOperationException {
    Field field = TdlibDataManager.class.getDeclaredField(name);
    field.setAccessible(true);
    return field.get(manager);
  }

  private static void awaitBlockedOn (Thread thread, Object monitor, String what) throws InterruptedException {
    long deadline = System.nanoTime() + WAIT_NS;
    int identity = System.identityHashCode(monitor);
    while (true) {
      ThreadInfo info = THREADS.getThreadInfo(thread.threadId());
      if (info != null && info.getThreadState() == Thread.State.BLOCKED && info.getLockInfo() != null &&
        info.getLockInfo().getIdentityHashCode() == identity) {
        return;
      }
      if (!thread.isAlive()) throw new AssertionError(what + ": thread ended before it reached the monitor");
      if (System.nanoTime() > deadline) throw new AssertionError(what + ": thread did not reach the monitor, state=" + thread.getState());
      Thread.sleep(1);
    }
  }

  private static boolean holds (Thread thread, Object monitor) {
    int identity = System.identityHashCode(monitor);
    ThreadInfo info = THREADS.getThreadInfo(new long[] {thread.threadId()}, true, false)[0];
    for (MonitorInfo locked : info.getLockedMonitors()) {
      if (locked.getIdentityHashCode() == identity) return true;
    }
    return false;
  }

  private static Thread daemon (Runnable runnable, String name, AtomicReference<Throwable> failure) {
    Thread thread = new Thread(runnable, name);
    thread.setDaemon(true);
    thread.setUncaughtExceptionHandler((t, e) -> failure.compareAndSet(null, e));
    return thread;
  }

  private static void join (Thread thread, String what) throws InterruptedException {
    if (thread == null) return;
    thread.join(WAIT_NS / 1_000_000L);
    if (thread.isAlive()) throw new AssertionError(what + ": " + thread.getName() + " is stuck (deadlock?)");
  }

  /** Returns whether the step left a gap (released dataLock before detaching weak watchers). */
  static boolean interleave (TdlibDataManager<?, ?, ?> manager, Runnable step, Runnable next, String what) throws Exception {
    Object dataLock = field(manager, "dataLock");
    Object map = ((ReferenceMap<?, ?>) field(manager, "watcherReferences")).mapUnchecked();
    AtomicReference<Throwable> failure = new AtomicReference<>();
    Thread stepThread = daemon(step, what + "-step", failure), nextThread = null;
    boolean gap;
    synchronized (map) {
      stepThread.start();
      awaitBlockedOn(stepThread, map, what);
      gap = !holds(stepThread, dataLock);
      if (gap) {
        next.run();
      } else {
        nextThread = daemon(next, what + "-next", failure);
        nextThread.start();
        awaitBlockedOn(nextThread, dataLock, what);
      }
    }
    join(stepThread, what);
    join(nextThread, what);
    if (failure.get() != null) throw new AssertionError(what + ": " + failure.get(), failure.get());
    return gap;
  }

  /** The coordinator's reproduction, with the production TdlibForumTopicManager. */
  static void restartKeepsNextGenerationWeakWatcher () throws Exception {
    Tdlib tdlib = new Tdlib(21);
    TdlibForumTopicManager topics = new TdlibForumTopicManager(tdlib);
    Counter<TdlibForumTopicManager.Key, TdApi.ForumTopic, TdlibForumTopicManager.Entry> old = new Counter<>(), fresh = new Counter<>();
    TdlibForumTopicManager.Key oldKey = new TdlibForumTopicManager.Key(-1001L, 1), freshKey = new TdlibForumTopicManager.Key(-1001L, 2);
    topics.findOrPostponeRequest(oldKey, old);
    boolean gap = interleave(topics, topics::onPerformRestart, () -> topics.findOrPostponeRequest(freshKey, fresh), "restart");
    tdlib.ui().flush();
    check(old.errors.get() == 1 && old.values.get() == 0, "weak watcher of the closed client must end exactly once, got " + old.total());
    check(fresh.total() == 0, "new-generation weak watcher was canceled by prior restart (gap=" + gap + ")");
    topics.performPostponedRequests();
    check(tdlib.sent.size() == 1, "registration after restart must be requested on the next client, sent=" + tdlib.sent.size());
    tdlib.sent.get(0).answer(ForumRestartRuntimeTest.topic(2), null);
    tdlib.ui().flush();
    check(fresh.values.get() == 1 && fresh.errors.get() == 0, "new-generation weak watcher receives the next client's answer");
    check(old.total() == 1, "old watcher is not called again");
    Reference.reachabilityFence(old);
    Reference.reachabilityFence(fresh);
  }

  /** processCancelled releases the key; a watcher registered right after it must get the next request. */
  static void cancelledKeyKeepsLaterWeakWatcher () throws Exception {
    Tdlib tdlib = new Tdlib(22);
    EndingManager manager = new EndingManager(tdlib);
    Counter<Long, TdApi.Sticker, EndingManager.Entry> first = new Counter<>(), later = new Counter<>();
    manager.findOrPostponeRequest(7L, first);
    manager.performPostponedRequests();
    check(manager.requested.size() == 1, "first request");
    int context = manager.contexts.get(0);
    boolean gap = interleave(manager, () -> manager.cancel(context, 7L), () -> manager.findOrPostponeRequest(7L, later), "cancelled");
    check(first.errors.get() == 1 && first.values.get() == 0, "cancelled request ends its own watcher once");
    check(later.total() == 0, "weak watcher registered after the cancellation was ended by it (gap=" + gap + ")");
    manager.performPostponedRequests();
    check(manager.requested.size() == 2, "the released key is requested again for the later watcher");
    manager.answer(manager.contexts.get(1), 7L);
    check(later.values.get() == 1 && first.total() == 1, "later watcher receives the new answer, the first is not called again");
    Reference.reachabilityFence(first);
    Reference.reachabilityFence(later);
  }

  /** An answer that passed its generation check must not reach a watcher registered after a restart. */
  static void answerDoesNotReachNextGeneration () throws Exception {
    Tdlib tdlib = new Tdlib(23);
    EndingManager manager = new EndingManager(tdlib);
    Counter<Long, TdApi.Sticker, EndingManager.Entry> first = new Counter<>(), fresh = new Counter<>();
    manager.findOrPostponeRequest(9L, first);
    manager.performPostponedRequests();
    int context = manager.contexts.get(0);
    boolean gap = interleave(manager, () -> manager.answer(context, 9L), () -> {
      manager.onPerformRestart();
      manager.findOrPostponeRequest(9L, fresh);
    }, "answer");
    tdlib.ui().flush();
    check(first.total() == 1, "the waiting watcher gets exactly one end state, got " + first.total());
    check(fresh.total() == 0, "new-generation weak watcher got the closed client's answer (gap=" + gap + ")");
    manager.performPostponedRequests();
    check(manager.requested.size() == 2 && manager.contexts.get(1) != context, "next generation requests the key again");
    manager.answer(manager.contexts.get(1), 9L);
    check(fresh.values.get() == 1, "new-generation watcher receives the next answer");
    Reference.reachabilityFence(first);
    Reference.reachabilityFence(fresh);
  }

  /**
   * Free-running restart vs registration: each weak watcher either belonged to the closed client
   * (ended once, key released) or to the next one (kept, key postponed and answered later).
   */
  static void freeRunningInvariant () throws Exception {
    for (int round = 0; round < 400; round++) {
      Tdlib tdlib = new Tdlib(1000 + round);
      EndingManager manager = new EndingManager(tdlib);
      Counter<Long, TdApi.Sticker, EndingManager.Entry> watcher = new Counter<>();
      CyclicBarrier start = new CyclicBarrier(2);
      AtomicReference<Throwable> failure = new AtomicReference<>();
      Thread restart = daemon(() -> { await(start); manager.onPerformRestart(); }, "free-restart", failure);
      Thread register = daemon(() -> { await(start); manager.findOrPostponeRequest(5L, watcher); }, "free-register", failure);
      restart.start();
      register.start();
      join(restart, "free-running");
      join(register, "free-running");
      if (failure.get() != null) throw new AssertionError(failure.get());
      tdlib.ui().flush();
      manager.performPostponedRequests();
      boolean ended = watcher.errors.get() == 1, requested = manager.requested.contains(5L);
      check(ended != requested && watcher.total() == (ended ? 1 : 0),
        "round " + round + ": watcher must be ended by the old client xor kept for the next (ended=" + ended + ", requested=" + requested + ")");
      if (requested) {
        manager.answer(manager.contexts.get(0), 5L);
        check(watcher.values.get() == 1, "round " + round + ": kept watcher receives the next answer");
      }
      Reference.reachabilityFence(watcher);
    }
  }

  private static void await (CyclicBarrier barrier) {
    try {
      barrier.await();
    } catch (Exception e) {
      throw new AssertionError(e);
    }
  }

  static void run () throws Exception {
    restartKeepsNextGenerationWeakWatcher();
    cancelledKeyKeepsLaterWeakWatcher();
    answerDoesNotReachNextGeneration();
    freeRunningInvariant();
  }
}
