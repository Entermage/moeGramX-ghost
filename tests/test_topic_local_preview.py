"""Run the production local-history window for forum topics and the loader's paging around it."""
import unittest
import test_history_preview as base

CHAT = base.SRC / 'component/chat'


class TopicLocalPreviewTest(unittest.TestCase):
    run_java = base.HistoryPreviewTest.run_java

    def sources(self, scan_edit=None, loader_edit=None, preview_edit=None):
        scan = (CHAT / 'LocalTopicHistory.java').read_text()
        if scan_edit:
            self.assertIn(scan_edit[0], scan)
            scan = scan.replace(*scan_edit)
        loader = (CHAT / 'MessagesLoader.java').read_text()
        field = next(line for line in loader.splitlines() if 'LocalTopicHistory> localTopicScan' in line)
        methods = '\n'.join([field] + [base.method(loader, signature) for signature in [
            '  private void tryLocalTopicPreview (', '  private void endLocalTopicPreview (',
            '  private void requestLocalTopicPage (', '  public void pauseHistoryPreview (', '  public void reuse () {']])
        if loader_edit:
            self.assertIn(loader_edit[0], methods)
            methods = methods.replace(*loader_edit)
        preview = (CHAT / 'MessageHistoryPreview.java').read_text()
        if preview_edit:
            self.assertIn(preview_edit[0], preview)
            preview = preview.replace(*preview_edit)
        return {
          'org/thunderdog/challegram/component/chat/MessageHistoryPreview.java': preview,
          'org/thunderdog/challegram/component/chat/LocalTopicHistory.java': scan,
          'android/os/SystemClock.java': 'package android.os; public class SystemClock {public static long uptimeMillis(){return 0;}}',
          'org/drinkless/tdlib/TdApi.java': '''package org.drinkless.tdlib; public class TdApi {
            public static class MessageTopic {}
            public static class MessageTopicForum extends MessageTopic {public long forumTopicId; public MessageTopicForum(long id){forumTopicId=id;}}
            public static class Message {public long id,chatId,mediaAlbumId; public MessageTopic topicId; public Object sendingState,schedulingState,selfDestructType; public double autoDeleteIn;}
            public static class Messages {public Message[] messages; public Messages(Message... m){messages=m;}}
            public static class Chat {public long id; public Message lastMessage;}
            public static class GetChatHistory {public long chatId,fromMessageId; public int offset,limit; public boolean onlyLocal;
              public GetChatHistory(long c,long f,int o,int l,boolean local){chatId=c;fromMessageId=f;offset=o;limit=l;onlyLocal=local;}}
            public static class MessageContent{} public static class EphemeralMessageContent{} public static class ReplyMarkup{} public static class Error{}}''',
          'org/thunderdog/challegram/telegram/MessageListener.java': '''package org.thunderdog.challegram.telegram; import org.drinkless.tdlib.TdApi;
            public interface MessageListener {
            default void onMessageContentChanged(long c,long id,TdApi.MessageContent content){}
            default void onMessageEphemeralContentChanged(long c,long id,TdApi.EphemeralMessageContent content){}
            default void onMessageEdited(long c,long id,int d,TdApi.ReplyMarkup r){}
            default void onMessagesDeleted(long c,long[] ids){}
            default void onMessageSendSucceeded(TdApi.Message m,long old){}
            default void onMessageSendFailed(TdApi.Message m,long old,TdApi.Error e){} }''',
          'org/thunderdog/challegram/telegram/Tdlib.java': '''package org.thunderdog.challegram.telegram; import org.drinkless.tdlib.TdApi; import java.util.*;
            public class Tdlib {public boolean isAuthorized(){return true;}public final Listeners l=new Listeners(); public Listeners listeners(){return l;}
            public static class Listeners {public MessageListener listener; public void subscribeForGlobalUpdates(Object o){listener=(MessageListener)o;} public void unsubscribeFromGlobalUpdates(Object o){if(listener==o)listener=null;}}
            public interface ResultHandler<T> {void onResult(T result, TdApi.Error error);}
            public final ArrayList<TdApi.GetChatHistory> sent=new ArrayList<>(); public final ArrayDeque<ResultHandler<TdApi.Messages>> pending=new ArrayDeque<>();
            public void send(TdApi.GetChatHistory f, ResultHandler<TdApi.Messages> h){sent.add(f);pending.add(h);}
            public boolean reply(TdApi.Messages m){ResultHandler<TdApi.Messages> h=pending.poll();if(h==null)return false;h.onResult(m,m==null?new TdApi.Error():null);return true;}}''',
          'tgx/td/Td.java': '''package tgx.td; import org.drinkless.tdlib.TdApi; public class Td {
            public static TdApi.Message copyOf(TdApi.Message m){TdApi.Message c=new TdApi.Message();c.id=m.id;c.chatId=m.chatId;c.topicId=m.topicId;c.mediaAlbumId=m.mediaAlbumId;return c;}}''',
          'Harness.java': HARNESS.replace('LOADER_METHODS', methods),
        }

    def run_harness(self, **edits):
        return self.run_java(self.sources(**edits))

    def rejected(self, message, **edits):
        r = self.run_harness(**edits)
        self.assertNotEqual(r.returncode, 0)
        self.assertRegex(r.stderr, message)

    def test_production_scan_and_loader(self):
        r = self.run_harness()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('local topic preview checks passed', r.stdout)

    def test_stale_scan_as_tail_rejected(self):
        self.rejected('stale local history shown as the topic tail',
                      scan_edit=('tail = chatLastMessageId != 0 && message.id == chatLastMessageId', 'tail = true'))

    def test_repeated_page_start_rejected(self):
        self.rejected('page start repeated', scan_edit=('(!first && message.id >= nextFromId)', '(false)'))

    def test_cut_album_rejected(self):
        self.rejected('album cut by the scan bound',
                      scan_edit=('if (album != 0) result.removeIf(message -> message.mediaAlbumId == album);', ''))

    def test_lone_message_rejected(self):
        self.rejected('lone message', scan_edit=('if (messages.length < MIN_MESSAGES) return false;', ''))

    def test_unread_boundary_rejected(self):
        self.rejected('read boundary', scan_edit=(
            'return !unreadEntry || (messages[messages.length - 1].id <= requestedId && requestedId < messages[0].id);',
            'return true;'))

    def test_stale_generation_rejected(self):
        self.rejected('left page|published page', loader_edit=(
            'if (contextId != context || historyPublished || localTopicScan.get() != scan) {\n        scan.untrack(tdlib);\n        return;\n      }', ''))

    def test_scan_deletion_untracked_rejected(self):
        self.rejected('deleted message 280 was published', preview_edit=(
            'if (tracker.chatId == chatId) tracker.record(deletion ? tracker.deleted : tracker.changed, messageIds);', ''))

    def test_deleted_row_kept_rejected(self):
        self.rejected('scan with a deleted message not published without it', scan_edit=(
            'result.removeIf(message -> MessageHistoryPreview.isDeleted(changes, message.id));', ''))

    def test_scan_edit_untracked_rejected(self):
        self.rejected('edited message published', preview_edit=(
            'if (deleted.contains(message.id) || changed.contains(message.id)) return true;',
            'if (deleted.contains(message.id)) return true;'))

    def test_left_scan_leak_rejected(self):
        self.rejected('ended local scans kept following', loader_edit=('        scan.untrack(tdlib);\n', ''))

    def test_unusable_scan_leak_rejected(self):
        self.rejected('ended local scans kept following', scan_edit=(
            '    if (!isUsable(messages)) {\n      MessageHistoryPreview.untrack(tdlib, changes);\n', '    if (!isUsable(messages)) {\n'))

    def test_unbounded_scans_rejected(self):
        self.rejected('local scans followed without a bound', preview_edit=('MAX_TRACKERS = 8', 'MAX_TRACKERS = 100'))

    def test_blur_keeps_scan_rejected(self):
        # Round 1: blur only dropped the reload; the scan was released by its callback, if it came.
        self.rejected('blur left scan tracking active until a TDLib callback arrives',
                      loader_edit=('    cancelHistoryPreviewRetry();\n    endLocalTopicPreview();\n', '    cancelHistoryPreviewRetry();\n'))

    def test_blur_slots_kept_rejected(self):
        r = self.run_harness(loader_edit=('    cancelHistoryPreviewRetry();\n    endLocalTopicPreview();\n', '    cancelHistoryPreviewRetry();\n'))
        self.assertNotEqual(r.returncode, 0)
        # The first blur check already fails; the slot check is the same release seen from the bound.
        self.assertRegex(r.stderr, 'blur left scan tracking|blurred pages kept their tracking slots')

    def test_reuse_keeps_scan_rejected(self):
        self.rejected('reused page left its scan tracking', loader_edit=('    restoreRetainedHistory();\n    endLocalTopicPreview();\n', '    restoreRetainedHistory();\n'))

    def test_owner_check_missing_rejected(self):
        self.rejected('blurred scan read on or published', loader_edit=(' || localTopicScan.get() != scan) {', ') {'))

    def test_ended_scan_published_rejected(self):
        # A cancel that only drops the tracker must not turn a late scan into an unprotected publish.
        self.rejected('ended scan published without following changes', scan_edit=('    if (changes == null) return false;\n', ''))

    def test_idle_state_kept_listening_rejected(self):
        self.rejected('blurred scan kept the account listening', preview_edit=(
            '      idle = state != null && state.trackers.remove(tracker) ? removeIfIdle(tdlib, state) : null;',
            '      idle = null; if (state != null) state.trackers.remove(tracker);'))

    def test_history_arrival_ends_scan(self):
        # processMessages is too large to run here: the authoritative publication ends the scan where it is set.
        loader = (CHAT / 'MessagesLoader.java').read_text()
        self.assertIn('      historyPublished = true;\n      endLocalTopicPreview();', loader)

    def test_change_overflow_rejected(self):
        self.rejected('changes passed the bound', preview_edit=('overflow = true; deleted.clear(); changed.clear();', ''))


HARNESS = r'''
import org.thunderdog.challegram.component.chat.*;
import org.thunderdog.challegram.telegram.Tdlib;
import org.drinkless.tdlib.TdApi;
import java.util.*;

public class Harness {
  static int checks;
  static void check(boolean ok, String reason) { checks++; if (!ok) throw new AssertionError(reason); }
  static TdApi.Message m(long chat, long topic, long id) {
    TdApi.Message m = new TdApi.Message(); m.chatId = chat; m.id = id;
    if (topic != 0) m.topicId = new TdApi.MessageTopicForum(topic);
    return m;
  }
  /** Chat history page newest first: ids from..to, topic 5 at the given ids, topic 9 elsewhere. */
  static TdApi.Message[] page(long from, long to, long... topicIds) {
    ArrayList<TdApi.Message> list = new ArrayList<>();
    for (long id = from; id >= to; id--) {
      boolean mine = false; for (long t : topicIds) mine |= t == id;
      list.add(m(100, mine ? 5 : 9, id));
    }
    return list.toArray(new TdApi.Message[0]);
  }
  static long[] ids(TdApi.Message[] messages) { return Arrays.stream(messages).mapToLong(x -> x.id).toArray(); }
  static long[] range(long from, long to, long step) { ArrayList<Long> l = new ArrayList<>(); for (long i = from; i >= to; i -= step) l.add(i); return l.stream().mapToLong(Long::longValue).toArray(); }

  // ---- loader doubles around the production methods ----
  static class MessageId {
    final long id; final boolean end;
    MessageId(long id, boolean end) { this.id = id; this.end = end; }
    long getMessageId() { return id; } boolean isHistoryEnd() { return end; }
  }
  static class Background {
    static final Background b = new Background(); final ArrayList<Runnable> tasks = new ArrayList<>();
    static Background instance() { return b; } void post(Runnable r) { tasks.add(r); }
    void flush() { ArrayList<Runnable> copy = new ArrayList<>(tasks); tasks.clear(); copy.forEach(Runnable::run); }
  }
  // The rest of reuse() and pauseHistoryPreview(): what they touch besides the scan.
  static final boolean DEBUG_HANDLER = false;
  static final int MERGE_MODE_NONE = 0;
  static class Log { static void w(String s, Object o) {} static Object generateException(int i) { return null; } }
  static class MoexShadowUnreadManager { interface HiddenUsersCallback {} static void cancelHiddenUsers(Tdlib t, HiddenUsersCallback c) {} }
  static class Controller { void setHistoryLoading(boolean loading, boolean hasRows) {} }
  static class Manager { final Controller c = new Controller(); Controller controller() { return c; } }
  static class Cancellable { void cancel() {} }
  final Manager manager = new Manager();
  final Object lock = new Object();
  boolean historyPreviewShown, historyPreviewAttempted, historyPreviewToEnd, unreadNavigationPending, resolvedUnreadTarget,
    unreadNavigationStopped, unreadAnchorUnavailable, resumeUnreadOnFocus, foundUnreadAtLeastOnce,
    loadingSupportsFilteredContinuation, loadingLocal, loadingAllowMoreTop, loadingAllowMoreBottom, canLoadTop, canLoadBottom, isLoading;
  MoexShadowUnreadManager.HiddenUsersCallback hiddenUsersCallback; Runnable retryHiddenUsersLoad;
  Object visibleUnreadAnchor, scrollMessageId, lastFromMessageId, mergeChunk, lastHandler;
  final TreeMap<Long, Object> unreadAnchorMessages = new TreeMap<>();
  int scrollHighlightMode, knownTotalMessageCount, filteredPageContinuationCount, mergeMode, retryCancels;
  Cancellable sponsoredResultHandler;
  void restoreRetainedHistory() {}
  void cancelHistoryPreviewRetry() { retryCancels++; }

  /** Scans followed for the account now. */
  static int trackers(Tdlib t) {
    try {
      java.lang.reflect.Field f = MessageHistoryPreview.class.getDeclaredField("states"); f.setAccessible(true);
      Object state = ((Map<?, ?>) f.get(null)).get(t);
      if (state == null) return 0;
      java.lang.reflect.Field tf = state.getClass().getDeclaredField("trackers"); tf.setAccessible(true);
      return ((List<?>) tf.get(state)).size();
    } catch (ReflectiveOperationException x) { throw new AssertionError(x); }
  }
  static TdApi.Messages full() { return new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)); }

  Tdlib tdlib = new Tdlib();
  TdApi.MessageTopic topicId = new TdApi.MessageTopicForum(5);
  TdApi.Chat chat = new TdApi.Chat();
  long contextId = 1; boolean historyPublished; int parsed; TdApi.Message[] parsedMessages; MessageHistoryPreview.Window parsedWindow;
  Harness() { chat.id = 100; chat.lastMessage = m(100, 9, 300); }
  long historyPreviewTopic() { return 5; }
  void processMessages(long c, TdApi.Message[] messages, int count, String next, long nextFrom, boolean find,
                       Object missing, MessageHistoryPreview.Window w) { parsed++; parsedMessages = messages; parsedWindow = w; }

  LOADER_METHODS

  public static void main(String[] args) {
    // ---- scan: paging, tail and duplicates ----
    LocalTopicHistory scan = new LocalTopicHistory(100, 5, 0, false);
    check(scan.nextFromMessageId() == 0, "scan starts at the chat's last message");
    check(scan.accept(page(300, 201, 300, 290, 250, 201), 300), "few matches must read another page");
    check(scan.isTail() && scan.nextFromMessageId() == 201, "tail and cursor after first page");
    check(scan.accept(page(201, 102, 201, 150), 300), "second page continues");
    check(Arrays.equals(ids(scan.messages()), new long[] {300, 290, 250, 201, 150}), "page start repeated in the window");
    check(!scan.accept(page(102, 3, 102, 60), 300), "page bound stops the scan");
    check(scan.messages().length == 6, "third page matches kept");

    // A scan that does not start at the chat's last message has not seen the topic's newest rows.
    LocalTopicHistory stale = new LocalTopicHistory(100, 5, 265, false);
    stale.accept(page(280, 181, 280, 270, 260, 250, 240), 300);
    stale.accept(new TdApi.Message[] {m(100, 5, 181)}, 300); // only the repeated start: stored history ends
    check(!stale.isTail(), "stale local history shown as the topic tail");
    Tdlib d = new Tdlib();
    check(stale.track(d) && stale.publish(d), "stale scan still usable for its own rows");
    check(MessageHistoryPreview.get(d, 100, 5, 0, true) == null, "stale local history shown as the topic tail (end entry)");
    MessageHistoryPreview.Window restored = MessageHistoryPreview.get(d, 100, 5, 265, false);
    check(restored != null && restored.anchorId == 260 && restored.offset == 0, "position inside the window anchors at or before it");

    // ---- only rows that open where the history will ----
    LocalTopicHistory lone = new LocalTopicHistory(100, 5, 0, false);
    lone.accept(page(300, 201, 300), 300); lone.accept(new TdApi.Message[0], 300);
    Tdlib e = new Tdlib();
    check(lone.track(e) && !lone.publish(e) && MessageHistoryPreview.get(e, 100, 5, 0, true) == null, "lone message shown before the history");
    LocalTopicHistory unread = new LocalTopicHistory(100, 5, 250, true);
    unread.accept(page(300, 201, 300, 290, 280, 270, 260, 250, 240), 300);
    TdApi.Message[] u = unread.messages();
    check(unread.isUsable(u) && unread.anchorId(u) == 260 && unread.anchorOffset() == MessageHistoryPreview.OFFSET_TOP,
      "unread entry opens at its first unread row, at the top");
    Tdlib f = new Tdlib();
    check(unread.track(f) && unread.publish(f), "unread window across the read boundary is used");
    MessageHistoryPreview.Window w = MessageHistoryPreview.get(f, 100, 5, 250, false, true);
    check(w != null && w.anchorId == 260 && w.offset == MessageHistoryPreview.OFFSET_TOP, "unread placement kept in the window");
    LocalTopicHistory far = new LocalTopicHistory(100, 5, 100, true);
    far.accept(page(300, 201, 300, 290, 280, 270, 260, 250, 240), 300);
    check(!far.isUsable(far.messages()), "unread window must reach the read boundary");
    LocalTopicHistory read = new LocalTopicHistory(100, 5, 999, true);
    read.accept(page(300, 201, 300, 290, 280, 270, 260), 300);
    check(!read.isUsable(read.messages()), "unread entry without unread rows must not use the read boundary window");
    LocalTopicHistory never = new LocalTopicHistory(100, 5, 0, true);
    never.accept(page(300, 201, 300, 290, 280, 270, 260), 300);
    check(!never.isUsable(never.messages()), "never-read topic has no read boundary to reach");

    // ---- message bound, album cut and exclusions ----
    LocalTopicHistory full = new LocalTopicHistory(100, 5, 0, false);
    check(!full.accept(page(400, 301, range(400, 301, 1)), 400), "message bound stops the scan");
    check(full.messages().length == LocalTopicHistory.MAX_MESSAGES, "message bound");
    LocalTopicHistory album = new LocalTopicHistory(100, 5, 0, false);
    TdApi.Message[] p = page(500, 401, 500, 470, 403, 402);
    for (TdApi.Message x : p) if (x.id == 403 || x.id == 402) x.mediaAlbumId = 77;
    album.accept(p, 500); album.accept(page(401, 302), 500); album.accept(page(302, 203), 500);
    check(Arrays.equals(ids(album.messages()), new long[] {500, 470}), "album cut by the scan bound");
    LocalTopicHistory ended = new LocalTopicHistory(100, 5, 0, false);
    TdApi.Message[] q = page(500, 490, 500, 492, 491);
    for (TdApi.Message x : q) if (x.id < 493 && x.id > 490) x.mediaAlbumId = 78;
    check(ended.accept(q, 500), "short page continues");
    check(!ended.accept(new TdApi.Message[0], 500), "stored history end stops the scan");
    check(ended.messages().length == 3, "a complete album at the end of stored history is kept");

    TdApi.Message pending = m(100, 5, 600); pending.sendingState = new Object();
    TdApi.Message scheduled = m(100, 5, 599); scheduled.schedulingState = new Object();
    TdApi.Message secret = m(100, 5, 598); secret.selfDestructType = new Object();
    TdApi.Message expiring = m(100, 5, 597); expiring.autoDeleteIn = 5;
    TdApi.Message other = m(101, 5, 596), general = m(100, 0, 595), kept = m(100, 5, 594);
    LocalTopicHistory filtered = new LocalTopicHistory(100, 5, 0, false);
    filtered.accept(new TdApi.Message[] {pending, scheduled, secret, expiring, other, general, kept}, 600);
    check(Arrays.equals(ids(filtered.messages()), new long[] {594}), "pending, scheduled, expiring, other chat or topic excluded");
    check(filtered.isTail(), "an excluded newest row still proves the tail");
    LocalTopicHistory generalTopic = new LocalTopicHistory(100, 1, 0, false);
    generalTopic.accept(new TdApi.Message[] {general, kept}, 595);
    check(Arrays.equals(ids(generalTopic.messages()), new long[] {595}), "General topic rows have no topic id");

    TdApi.Message[] two = {m(100, 5, 30), m(100, 5, 20)};
    check(new LocalTopicHistory(100, 5, 999, false).anchorId(two) == 30, "position after the window anchors at its newest row");
    check(new LocalTopicHistory(100, 5, 10, false).anchorId(two) == 30, "position before the window anchors at its newest row");
    check(new LocalTopicHistory(100, 5, 25, false).anchorId(two) == 20, "position inside the window anchors at or before it");

    // ---- loader: chained local pages, then the remembered-window path ----
    Harness h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    check(h.tdlib.sent.size() == 1, "one local request at a time");
    TdApi.GetChatHistory first = h.tdlib.sent.get(0);
    check(first.onlyLocal && first.fromMessageId == 0 && first.offset == 0 && first.limit == LocalTopicHistory.PAGE_SIZE && first.chatId == 100,
      "local request from the end of the chat");
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 250)));
    check(h.tdlib.sent.size() == 2 && h.tdlib.sent.get(1).fromMessageId == 201, "next page continues from the oldest row");
    h.tdlib.reply(new TdApi.Messages(page(201, 102, 120)));
    h.tdlib.reply(new TdApi.Messages(page(102, 3)));
    check(h.tdlib.sent.size() == 3 && h.parsed == 0, "bounded pages; parsing waits for the background");
    Background.b.flush();
    check(h.parsed == 1 && Arrays.equals(ids(h.parsedMessages), new long[] {300, 290, 280, 250, 120}), "topic window parsed once");
    check(h.parsedWindow.anchorId == 300 && h.parsedWindow.offset == 0, "end entry opens at the newest row");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(250, false), true);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250, 240)));
    h.tdlib.reply(new TdApi.Messages(page(201, 102)));
    h.tdlib.reply(new TdApi.Messages(page(102, 3)));
    Background.b.flush();
    check(h.parsed == 1 && h.parsedWindow.anchorId == 260 && h.parsedWindow.offset == MessageHistoryPreview.OFFSET_TOP,
      "unread entry parsed at its first unread row");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.contextId++;
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300)));
    check(h.tdlib.sent.size() == 1, "left page keeps reading local history");
    Background.b.flush();
    check(h.parsed == 0, "left page parsed a local window");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300)));
    h.historyPublished = true;
    h.tdlib.reply(new TdApi.Messages(page(201, 102)));
    check(h.tdlib.sent.size() == 2, "published page keeps reading local history");
    Background.b.flush();
    check(h.parsed == 0, "published page replaced by a local window");

    h = new Harness();
    h.chat.lastMessage = m(100, 9, 301);
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260)));
    h.tdlib.reply(new TdApi.Messages(page(201, 102)));
    h.tdlib.reply(new TdApi.Messages(page(102, 3)));
    Background.b.flush();
    check(h.parsed == 0, "stale local history shown as the topic tail (loader)");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(null);
    Background.b.flush();
    check(h.tdlib.sent.size() == 1 && h.parsed == 0, "failed local query shows nothing");

    h = new Harness();
    h.topicId = null;
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    check(h.tdlib.sent.isEmpty(), "ordinary chats never scan for a topic");

    // ---- message changes while the scan reads: nothing shown or stored yet to invalidate ----
    h = new Harness();
    check(h.tdlib.l.listener == null, "setup: no window stored for the account");
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    check(h.tdlib.l.listener != null, "scan without a stored window follows no message changes");
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)));
    h.tdlib.l.listener.onMessagesDeleted(100, new long[] {280});
    h.tdlib.l.listener.onMessagesDeleted(101, new long[] {290});                // another chat
    h.tdlib.l.listener.onMessageContentChanged(100, 299, new TdApi.MessageContent()); // another topic's row
    h.tdlib.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsedMessages == null || Arrays.stream(h.parsedMessages).noneMatch(x -> x.id == 280),
      "deleted message 280 was published from an in-progress local scan");
    check(h.parsed == 1 && Arrays.equals(ids(h.parsedMessages), new long[] {300, 290, 270, 260, 250}),
      "scan with a deleted message not published without it");

    // As the review found it: another topic's window exists, this one has none.
    h = new Harness();
    MessageHistoryPreview.put(h.tdlib, 100, 9, new TdApi.Message[] {m(100, 9, 800)}, 800, 0, true);
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)));
    h.tdlib.l.listener.onMessagesDeleted(100, new long[] {280});
    h.tdlib.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsedMessages == null || Arrays.stream(h.parsedMessages).noneMatch(x -> x.id == 280),
      "deleted message 280 was published from an in-progress local scan (other window)");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)));
    h.tdlib.l.listener.onMessageEdited(100, 270, 0, new TdApi.ReplyMarkup());
    h.tdlib.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 0, "edited message published from an in-progress local scan");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260)));
    h.tdlib.l.listener.onMessagesDeleted(100, new long[] {260});
    h.tdlib.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 0, "scan left with too few rows by a deletion published");

    // Control: a deletion after the window is stored invalidates it, as before.
    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)));
    h.tdlib.reply(new TdApi.Messages());
    h.tdlib.l.listener.onMessagesDeleted(100, new long[] {280});
    Background.b.flush();
    check(h.parsed == 0, "deleted message of a stored window parsed");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)));
    long[] many = new long[600];
    for (int i = 0; i < many.length; i++) many[i] = 10_000 + i;
    h.tdlib.l.listener.onMessagesDeleted(100, many);
    h.tdlib.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 0, "scan published after its changes passed the bound");

    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)));
    MessageHistoryPreview.clear(h.tdlib);
    check(h.tdlib.l.listener == null, "closed account kept its listener");
    h.tdlib.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 0 && h.tdlib.l.listener == null, "scan published after the account closed");

    // ---- every way a scan ends stops following; at most a few at once ----
    Tdlib shared = new Tdlib();
    for (int i = 0; i < 10; i++) {
      h = new Harness(); h.tdlib = shared;                      // published
      h.tryLocalTopicPreview(new MessageId(0, true), false);
      shared.reply(new TdApi.Messages(page(300, 201, 300, 290, 280, 270, 260, 250)));
      shared.reply(new TdApi.Messages());
      h = new Harness(); h.tdlib = shared;                      // too few rows
      h.tryLocalTopicPreview(new MessageId(0, true), false);
      shared.reply(new TdApi.Messages(page(300, 201, 300)));
      shared.reply(new TdApi.Messages());
      h = new Harness(); h.tdlib = shared;                      // left
      h.tryLocalTopicPreview(new MessageId(0, true), false);
      h.contextId++;
      shared.reply(new TdApi.Messages(page(300, 201, 300)));
      h = new Harness(); h.tdlib = shared;                      // history arrived
      h.tryLocalTopicPreview(new MessageId(0, true), false);
      h.historyPublished = true;
      shared.reply(new TdApi.Messages(page(300, 201, 300)));
      h = new Harness(); h.tdlib = shared;                      // failed
      h.tryLocalTopicPreview(new MessageId(0, true), false);
      shared.reply(null);
    }
    check(shared.pending.isEmpty(), "setup: every scan ended");
    int before = shared.sent.size();
    h = new Harness(); h.tdlib = shared;
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    check(shared.sent.size() == before + 1, "ended local scans kept following message changes");
    shared.reply(null);
    Background.b.flush();

    Tdlib busy = new Tdlib();
    for (int i = 0; i < 9; i++) {
      h = new Harness(); h.tdlib = busy;
      h.tryLocalTopicPreview(new MessageId(0, true), false);
    }
    check(busy.sent.size() == 8, "local scans followed without a bound: " + busy.sent.size());

    // ---- the page owns its scan: blur, reuse and close end it although its callback never returns ----
    Tdlib owner = new Tdlib();
    h = new Harness(); h.tdlib = owner;
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    check(trackers(owner) == 1, "setup: scan followed");
    h.pauseHistoryPreview(); // MessagesManager.onBlur; an end entry has no unread navigation to cancel
    check(h.retryCancels == 1, "blur no longer drops the pending reload");
    check(trackers(owner) == 0, "blur left scan tracking active until a TDLib callback arrives");
    check(owner.l.listener == null, "blurred scan kept the account listening");
    owner.reply(full()); // the callback comes after all
    Background.b.flush();
    check(owner.sent.size() == 1 && h.parsed == 0 && MessageHistoryPreview.get(owner, 100, 5, 0, true) == null,
      "blurred scan read on or published");
    check(owner.l.listener == null && trackers(owner) == 0, "late callback of a blurred scan followed changes again");

    h = new Harness(); h.tdlib = owner;
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    owner.reply(full());
    check(owner.sent.size() == 3, "setup: second page asked for");
    h.pauseHistoryPreview(); // blurred between pages
    owner.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 0 && MessageHistoryPreview.get(owner, 100, 5, 0, true) == null, "scan blurred between pages published");

    h = new Harness(); h.tdlib = owner;
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.reuse(); // left, another topic, or MessagesManager.destroy
    check(trackers(owner) == 0, "reused page left its scan tracking until a TDLib callback arrives");
    owner.reply(full()); owner.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 0 && owner.l.listener == null, "late callback of a reused page published or listened");
    h.tryLocalTopicPreview(new MessageId(0, true), false); // the reused loader opens a topic again
    check(trackers(owner) == 1, "reused loader can't scan again");
    MessageHistoryPreview.clear(owner); // the client closed with the callback pending
    h.pauseHistoryPreview();
    check(owner.l.listener == null && trackers(owner) == 0, "ending a scan after close listened again");
    owner.reply(full()); owner.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 0 && owner.l.listener == null, "scan published after the client closed");

    // A published window stays: blur after it is only the snapshot being kept.
    h = new Harness();
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    h.tdlib.reply(full()); h.tdlib.reply(new TdApi.Messages());
    h.pauseHistoryPreview();
    Background.b.flush();
    check(h.parsed == 1, "blur after the window was stored dropped the snapshot");

    // An ended scan is never stored: without its tracker it doesn't know what changed meanwhile.
    Tdlib g = new Tdlib();
    LocalTopicHistory cancelled = new LocalTopicHistory(100, 5, 0, false);
    check(cancelled.track(g), "setup: scan followed");
    cancelled.accept(page(300, 201, 300, 290, 280, 270, 260, 250), 300); cancelled.accept(new TdApi.Message[0], 300);
    cancelled.untrack(g);
    check(!cancelled.publish(g) && MessageHistoryPreview.get(g, 100, 5, 0, true) == null, "ended scan published without following changes");
    check(g.l.listener == null, "ended scan listened again");
    LocalTopicHistory untracked = new LocalTopicHistory(100, 5, 0, false);
    untracked.accept(page(300, 201, 300, 290, 280, 270, 260, 250), 300); untracked.accept(new TdApi.Message[0], 300);
    check(!untracked.publish(g) && MessageHistoryPreview.get(g, 100, 5, 0, true) == null, "scan never followed published");

    // Every slot taken by pages whose callbacks never return: blurring them frees the slots at once.
    Tdlib slots = new Tdlib();
    Harness[] open = new Harness[8];
    for (int i = 0; i < open.length; i++) {
      open[i] = new Harness(); open[i].tdlib = slots;
      open[i].tryLocalTopicPreview(new MessageId(0, true), false);
    }
    check(slots.sent.size() == 8 && trackers(slots) == 8, "setup: every slot taken");
    h = new Harness(); h.tdlib = slots;
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    check(slots.sent.size() == 8, "a ninth scan started past the bound");
    for (Harness x : open) x.pauseHistoryPreview();
    check(trackers(slots) == 0, "blurred pages kept their tracking slots");
    h = new Harness(); h.tdlib = slots;
    h.tryLocalTopicPreview(new MessageId(0, true), false);
    check(slots.sent.size() == 9 && trackers(slots) == 1, "new topic can't scan while blurred pages' callbacks are pending");
    for (int i = 0; i < open.length; i++) slots.reply(full());
    check(slots.sent.size() == 9 && trackers(slots) == 1, "late callbacks of ended scans read on or ended another scan");
    slots.reply(full()); slots.reply(new TdApi.Messages());
    Background.b.flush();
    check(h.parsed == 1 && trackers(slots) == 0, "the new scan didn't publish from its own pages");
    for (Harness x : open) check(x.parsed == 0, "an ended scan published");
    System.out.println(checks + " local topic preview checks passed");
  }
}
'''


if __name__ == '__main__':
    unittest.main()
