import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.telegram.TdlibDataManager;
import org.thunderdog.challegram.telegram.TdlibForumTopicManager;

import java.util.ArrayList;
import java.util.List;

import moe.kirao.mgx.topics.ForumRequests;

/**
 * Same-instance TDLib client restart with topic metadata requests in flight or queued.
 * The order of events follows Tdlib.updateAuthState on AuthorizationStateClosed: TDLib aborts
 * live requests, XgramForums posts ForumRequests.onClientClosed, then listeners().performRestart()
 * runs synchronously. NOT a device test: no TDLib client is started or closed.
 */
public class ForumRestartRuntimeTest {
  static int checks;

  static void check (boolean value, String message) {
    checks++;
    if (!value) throw new AssertionError(message);
  }

  static TdlibForumTopicManager.Key key (int topic) {
    return new TdlibForumTopicManager.Key(-1001L, topic);
  }

  static TdApi.ForumTopic topic (int id) {
    TdApi.ForumTopic topic = new TdApi.ForumTopic();
    topic.info = new TdApi.ForumTopicInfo();
    topic.info.chatId = -1001L;
    topic.info.forumTopicId = id;
    return topic;
  }

  static void closeClient (Tdlib tdlib, boolean abortLive) {
    if (abortLive) {
      for (Tdlib.Sent sent : tdlib.unanswered()) sent.answer(null, new TdApi.Error(500, "Request aborted"));
    }
    tdlib.ui().post(() -> ForumRequests.onClientClosed(tdlib));
    tdlib.listeners().performRestart();
  }

  static final class Calls {
    final List<TdlibForumTopicManager.Entry> entries = new ArrayList<>();
    void add (TdlibForumTopicManager.Entry entry, boolean inPlace) { entries.add(entry); }
  }

  static void restartWithLiveRequest () {
    Tdlib tdlib = new Tdlib(1);
    TdlibForumTopicManager topics = new TdlibForumTopicManager(tdlib);
    Calls first = new Calls();
    topics.findOrRequest(key(5), first::add);
    check(tdlib.sent.size() == 1, "first request is sent");
    closeClient(tdlib, true);
    tdlib.ui().flush();
    check(first.entries.size() == 1 && first.entries.get(0).error != null, "caller of the closed client must get one end state");
    check(topics.find(key(5)) == null, "restart must not cache a topic error");
    Calls second = new Calls();
    topics.findOrRequest(key(5), second::add);
    check(tdlib.sent.size() == 2, "same Tdlib instance must request the topic again after restart");
    tdlib.sent.get(1).answer(topic(5), null);
    tdlib.ui().flush();
    check(second.entries.size() == 1 && second.entries.get(0).value != null, "new client's answer reaches the new caller");
    check(first.entries.size() == 1, "old caller is not called again");
    check(topics.find(key(5)) != null && topics.find(key(5)).value != null, "new answer is cached");
    // A second restart of the same instance behaves the same way.
    closeClient(tdlib, true);
    tdlib.ui().flush();
    Calls third = new Calls();
    topics.findOrRequest(key(5), third::add);
    check(tdlib.sent.size() == 3, "repeated restarts keep requests possible");
  }

  static void queuedWaitersGetEndState () {
    for (boolean abortLive : new boolean[] {true, false}) {
      Tdlib tdlib = new Tdlib(abortLive ? 2 : 5);
      List<String> results = new ArrayList<>();
      Object screen = new Object(); // e.g. MessagesController#xgramLoadTopic, which waits on xgramTopicLoading
      for (int id = 1; id <= 3; id++) {
        final int topic = id;
        ForumRequests.send(tdlib, screen, new TdApi.GetForumTopic(-1001L, id), (result, error) ->
          results.add(topic + ":" + (error != null ? error.code : 0)));
      }
      check(tdlib.sent.size() == 2 && ForumRequests.snapshot(tdlib)[1] == 1, "two native slots, one queued");
      closeClient(tdlib, abortLive);
      tdlib.ui().flush();
      check(results.size() == 3, "queued waiter must get an end state when its client closes, got " + results);
      for (Tdlib.Sent sent : tdlib.unanswered()) sent.answer(null, new TdApi.Error(500, "Request aborted"));
      tdlib.ui().flush();
      check(results.size() == 3, "late answers after closing are dropped");
      int sentBefore = tdlib.sent.size();
      ForumRequests.send(tdlib, screen, new TdApi.GetForumTopic(-1001L, 3), (result, error) -> results.add("again"));
      check(tdlib.sent.size() == sentBefore + 1, "next client starts with a fresh queue");
    }
    check(ForumRequests.isClientClosed(new TdApi.Error(500, "Topic request ended: client closed")) &&
      !ForumRequests.isClientClosed(new TdApi.Error(500, "Request aborted")), "client-closed end state is distinguishable");
  }

  static void currentGenerationRace () {
    Tdlib tdlib = new Tdlib(3);
    TdlibForumTopicManager topics = new TdlibForumTopicManager(tdlib);
    topics.findOrRequest(key(7), (entry, inPlace) -> { });
    for (Tdlib.Sent sent : tdlib.unanswered()) sent.answer(null, new TdApi.Error(500, "Request aborted"));
    tdlib.ui().post(() -> ForumRequests.onClientClosed(tdlib));
    tdlib.listeners().performRestart();
    // A UI task that was already running asks for another topic before onClientClosed is dequeued.
    Calls calls = new Calls();
    topics.findOrRequest(key(8), calls::add);
    check(tdlib.sent.size() == 2, "the racing request entered the old queue");
    tdlib.ui().flush();
    check(calls.entries.size() == 1 && calls.entries.get(0).error != null, "racing caller gets an end state");
    check(topics.find(key(8)) == null, "client-closed error must not be cached as topic state");
    tdlib.sent.get(1).answer(null, new TdApi.Error(500, "Request aborted"));
    tdlib.ui().flush();
    check(calls.entries.size() == 1, "late answer of the closed queue is dropped");
    topics.findOrRequest(key(8), calls::add);
    check(tdlib.sent.size() == 3, "the topic is requested again at once");
  }

  static void timeoutKeepsNativeSlots () {
    Tdlib tdlib = new Tdlib(4);
    TdlibForumTopicManager topics = new TdlibForumTopicManager(tdlib);
    for (int id = 1; id <= 3; id++) topics.findOrRequest(key(id), (entry, inPlace) -> { });
    check(tdlib.sent.size() == 2, "bounded native requests");
    tdlib.ui().runDelayed(); // 30 s UI timeout
    long[] counters = ForumRequests.snapshot(tdlib);
    check(counters[0] == 2 && tdlib.sent.size() == 2, "UI timeout must not release live native slots");
    topics.findOrRequest(key(9), (entry, inPlace) -> { });
    check(tdlib.sent.size() == 2, "no extra native request while slots are held");
    tdlib.sent.get(0).answer(topic(1), null);
    tdlib.ui().flush();
    check(tdlib.sent.size() == 3 && ForumRequests.snapshot(tdlib)[0] == 2, "only the real callback frees a slot");
    closeClient(tdlib, false);
    tdlib.ui().flush();
    check(ForumRequests.snapshot(tdlib)[0] == 0, "AuthorizationStateClosed frees the remaining slots");
    topics.findOrRequest(key(2), (entry, inPlace) -> { });
    check(tdlib.sent.size() == 4, "after closing, a timed-out topic can be asked of the new client");
  }

  /** Upstream managers (custom emoji, reactions, outlines) keep the default restart behavior. */
  static final class PlainManager extends TdlibDataManager<Long, TdApi.Sticker, PlainManager.Entry> {
    static final class Entry extends TdlibDataManager.AbstractEntry<Long, TdApi.Sticker> {
      Entry (Long key, TdApi.Sticker value, TdApi.Error error) { super(key, value, error); }
    }
    final List<Integer> requested = new ArrayList<>();
    final List<Integer> contexts = new ArrayList<>();
    PlainManager (Tdlib tdlib) { super(tdlib); }
    @Override protected Entry newEntry (Long key, TdApi.Sticker value, TdApi.Error error) { return new Entry(key, value, error); }
    @Override protected void requestData (int contextId, java.util.Collection<Long> keys) { contexts.add(contextId); requested.add(keys.size()); }
    void answer (int contextId, long key) { if (!isCancelled(contextId)) processData(contextId, key, new TdApi.Sticker()); }
  }

  static void defaultManagersKeepWatchers () {
    Tdlib tdlib = new Tdlib(6);
    PlainManager manager = new PlainManager(tdlib);
    List<PlainManager.Entry> calls = new ArrayList<>();
    manager.findOrRequest(42L, (entry, inPlace) -> calls.add(entry));
    check(manager.requested.size() == 1, "default manager requests");
    tdlib.listeners().performRestart();
    tdlib.ui().flush();
    manager.answer(manager.contexts.get(0), 42L);
    check(calls.isEmpty(), "a default manager's watcher is neither ended nor fed the old client's answer");
    manager.findOrRequest(42L, (entry, inPlace) -> calls.add(entry));
    check(manager.requested.size() == 2, "a released key is requested again on the new client");
    manager.answer(manager.contexts.get(1), 42L);
    check(calls.size() == 2 && calls.get(0).value != null && calls.get(1).value != null,
      "the waiting watcher receives the new client's answer instead of an error");
  }

  public static void main (String[] args) throws Exception {
    restartWithLiveRequest();
    defaultManagersKeepWatchers();
    queuedWaitersGetEndState();
    currentGenerationRace();
    timeoutKeepsNativeSlots();
    WeakWatcherRaces.run();
    checks += WeakWatcherRaces.checks;
    System.out.println("Forum restart runtime: " + checks + " checks passed (JVM doubles, no TDLib client)");
  }
}
