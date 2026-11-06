"""Run the production snapshot exit paths on the JVM; NOT an Android or network E2E test.

The loader/manager methods that cancel, fail, retry, pause, resume and re-arm a displayed
history snapshot are extracted unchanged, together with the manager's real lifecycle and
gesture entry points (destroy, onBlur, onFocus, scrollToStart and the RecyclerView drag
callback). TDLib sends, the Android main-thread Handler and RecyclerView are doubles: a
request is recorded instead of sent, delayed callbacks sit in one process-wide queue (like
the main Looper, which outlives pages) and run in due order on a simulated elapsedRealtime
clock. The existing publication step (processMessages -> replaceHistoryPreview, covered by
test_history_preview) is applied explicitly when a test lets a request succeed.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_history_preview import method

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "app/src/main/java/org/thunderdog/challegram/component/chat"
LOADER = CHAT / "MessagesLoader.java"
MANAGER = CHAT / "MessagesManager.java"
FORUMS = ROOT / "app/src/main/java/moe/kirao/mgx/topics/XgramForums.java"

LOADER_METHODS = (
    "public boolean isShowingHistoryPreview ()",
    "public boolean isRetainingHistory ()",
    "private void restoreRetainedHistory ()",
    "static long historyPreviewRetryDelay (",
    "long historyPreviewWaitMs ()",
    "private void continueHistoryPreview (",
    "private void scheduleHistoryPreviewReload (",
    "private void cancelHistoryPreviewRetry ()",
    "public void pauseHistoryPreview ()",
    "public boolean resumeHistoryPreview ()",
    "public void onHistoryPreviewDragged ()",
    "public void showHistoryPreviewEnd ()",
    "private boolean canReloadHistoryPreview ()",
    "private boolean reloadHistoryPreview ()",
    "private boolean replaceHistoryPreviewRequest ()",
    "private void onHistoryError (",
    "public void reuse ()",
    "public void loadFromStart (MessageId startMessageId, boolean retain)",
    "public void loadFromMessage (",
    "public void cancelUnreadNavigation ()",
    "public void resumeUnreadNavigation ()",
    "private boolean loadMore (boolean fromTop, int count, boolean onlyLocal)",
    "public boolean canLoadTop ()",
)
MANAGER_METHODS = (
    "public @Nullable MessageId findHistoryPreviewAnchor ()",
    "public boolean readMessagesDisabled ()",
    "public void destroy (ViewController<?> context)",
    "private void onBlur ()",
    "private void onFocus ()",
    "public void scrollToStart (boolean force)",
    "public void loadFromStart ()",
    "private void loadFromStart (MessageId fromId, TGMessage startMessage)",
)
SCROLL_LISTENER = "public void onScrollStateChanged (RecyclerView recyclerView, int newState)"

HARNESS = r'''
import java.lang.ref.WeakReference;
import java.util.*;
public class Harness {
  @interface Nullable {}
  static final List<Runnable> uiQueue = new ArrayList<>();
  static final List<long[]> timerDelays = new ArrayList<>();
  static int errorsShown;
  static void flushUi () { while (!uiQueue.isEmpty()) uiQueue.remove(0).run(); }
  static class SystemClock { static long now = 1_000_000; static long elapsedRealtime () { return now; } }
  // The main Looper: one process-wide queue of delayed callbacks, run in due order.
  static final class Delayed { final Runnable r; final long due; Delayed (Runnable r, long due) { this.r = r; this.due = due; } }
  static final List<Delayed> looper = new ArrayList<>();
  static int pending () { return looper.size(); }
  static long nextDelay () { return looper.isEmpty() ? -1 : looper.get(0).due - SystemClock.now; }
  // Runs the callbacks already due at the current time (a zero-delay post, for example).
  static void runDue () {
    flushUi();
    while (!looper.isEmpty() && looper.stream().mapToLong(d -> d.due).min().getAsLong() <= SystemClock.now) runTimer();
  }
  static boolean runTimer () {
    flushUi(); if (looper.isEmpty()) return false;
    looper.sort(Comparator.comparingLong(d -> d.due));
    Delayed d = looper.remove(0); SystemClock.now = Math.max(SystemClock.now, d.due);
    d.r.run(); flushUi(); return true;
  }
  static class UI {
    static void post (Runnable r) { uiQueue.add(r); }
    static void showError (Object error) { errorsShown++; }
  }
  static class Handler {
    void postDelayed (Runnable r, long delay) { timerDelays.add(new long[] {delay}); looper.add(new Delayed(r, SystemClock.now + delay)); }
    void removeCallbacks (Runnable r) { looper.removeIf(d -> d.r == r); }
  }
  static class TdlibSettings { void removePinnedMessageDismissListener (Object listener) { } }
  static class Tdlib {
    final Handler ui = new Handler(); final TdlibSettings settings = new TdlibSettings(); int closed;
    Handler ui () { return ui; } TdlibSettings settings () { return settings; }
    void closeChat (long chatId, Object context, boolean force) { closed++; }
  }
  static class ViewController<T> { }
  static class Log {
    static final int TAG_MESSAGES_LOADER = 1;
    static boolean isEnabled (int tag) { return false; }
    static void i (int tag, String format, Object... args) { }
    static void w (String format, Object... args) { }
    static Throwable generateException (int skip) { return null; }
  }
  static class TdApi {
    static class Error { int code; String message; Error (int c, String m) { code = c; message = m; } }
    static class Message { long id; }
    static class SearchMessagesFilter { }
  }
  static class Client { interface ResultHandler { void onResult (Object object); } }
  static class MessageId {
    final long chatId, messageId;
    MessageId (long chatId, long messageId) { this.chatId = chatId; this.messageId = messageId; }
    long getChatId () { return chatId; } long getMessageId () { return messageId; }
  }
  static class ArrayUtils { static long[] removeElement (long[] array, int index) { return Arrays.copyOf(array, index); } }
  static class VisibleUnreadAnchor { VisibleUnreadAnchor (long boundary) { } }
  static class MoexShadowUnreadManager {
    interface HiddenUsersCallback { void onResult (boolean ready); }
    static void cancelHiddenUsers (Tdlib tdlib, HiddenUsersCallback callback) { }
  }
  static class Settings {
    static final Settings S = new Settings(); static Settings instance () { return S; }
    boolean dontReadMessages () { return false; } boolean needHideChatKeyboardOnScroll () { return false; }
  }
  static class Sponsored { void cancel () { } }
  static class RecyclerView { static final int SCROLL_STATE_IDLE = 0, SCROLL_STATE_DRAGGING = 1, SCROLL_STATE_SETTLING = 2; }
  static class MessagesRecyclerView extends RecyclerView { void setIsScrolling (boolean scrolling) { } }
  /* FORUMS */
  static class Controller {
    String subtitle; int errors;
    boolean inPreviewMode () { return false; } boolean isInForceTouchMode () { return false; }
    void setHistoryLoading (boolean loading, boolean updating) { subtitle = loading ? "updating" : null; }
    void setHistoryLoadingError () { subtitle = "failed"; errors++; }
    void collapsePinnedMessagesBar (boolean animated) { } void hideAllKeyboards () { }
  }
  static class TGMessage {
    final long id; TGMessage (long id) { this.id = id; }
    boolean isSponsoredMessage () { return false; } boolean isThreadHeader () { return false; }
    long getChatId () { return 100; } long getId () { return id; }
  }
  static class Adapter {
    final List<TGMessage> rows = new ArrayList<>(); int resets;
    int getMessageCount () { return rows.size(); }
    TGMessage getMessage (int i) { return i >= 0 && i < rows.size() ? rows.get(i) : null; }
    void reset (TGMessage start) { resets++; rows.clear(); if (start != null) rows.add(start); }
    void clear (boolean destroy) { rows.clear(); }
  }
  static class Layout { int first; int findFirstVisibleItemPosition () { return first; } }
  static class Destroyable { void performDestroy () { } }

  static class MessagesManager {
    static final int HIGHLIGHT_MODE_NONE = 0, HIGHLIGHT_MODE_NORMAL = 1, HIGHLIGHT_MODE_UNREAD = 2, HIGHLIGHT_MODE_POSITION_RESTORE = 3, HIGHLIGHT_MODE_UNREAD_NEXT = 4;
    final Controller controller = new Controller(); final Adapter adapter = new Adapter(); final Layout manager = new Layout();
    final Tdlib tdlib;
    MessagesLoader loader; boolean focused = true; int userScrollActionsCount, networkSent, unavailable, bottomScrolls;
    boolean wasScrollByUser, isScrolling, hasScrolled, pinnedMessagesAvailable, hasVisibleProtectedContent, awaitingForPinnedMessages;
    long[] returnToMessageIds; MessageId highlightMessageId; int highlightMode;
    long lastViewedMentionMessageId, lastViewedReactionMessageId;
    Object chatAdmins, mentionsHandler, reactionsHandler, closestMentions, closestUnreadReactions, messageViewer;
    Destroyable pinnedMessages;
    MessagesManager (Tdlib tdlib) { this.tdlib = tdlib; }
    Controller controller () { return controller; } Adapter getAdapter () { return adapter; }
    boolean isFocused () { return focused; } int getUserScrollActionsCount () { return userScrollActionsCount; }
    void onNetworkRequestSent () { networkSent++; } void onUnreadAnchorUnavailable () { unavailable++; }
    boolean inSpecialMode () { return false; } boolean hasReturnMessage () { return false; }
    void highlightMessage (MessageId id, int mode, long[] returnTo, boolean smooth) { }
    void revokeReturnMessages () { } void stopScroll () { }
    void scrollToBottom (boolean smooth) { bottomScrolls++; }
    void scrollToPositionWithOffsetImpl (int position, int offset) { }
    void rememberHistoryPreview () { } void clearMessageLinkTarget () { } void saveScrollPosition () { }
    void viewMessages (boolean byScroll) { } void checkSponsoredMessages () { } void scheduleMessageLinkTarget () { }
    void resetScroll () { } void unsubscribeFromUpdates () { } void resetSponsoredContext () { } void clearHeaderMessage () { }
    // RecyclerView.OnScrollListener of the constructor, with its production body.
    final class Listener { /* SCROLL_LISTENER */ }
    final Listener listener = new Listener();
    void drag () { listener.onScrollStateChanged(new MessagesRecyclerView(), RecyclerView.SCROLL_STATE_DRAGGING); }
    void blur () { focused = false; onBlur(); }
    void focus () { focused = true; onFocus(); }
    /* MANAGER_METHODS */
  }

  static class Request {
    final MessageId from; final int offset, limit, mode, highlight; final long context; final boolean onlyLocal;
    Request (MessageId from, int offset, int limit, int mode, int highlight, long context, boolean onlyLocal) {
      this.from = from; this.offset = offset; this.limit = limit; this.mode = mode; this.highlight = highlight; this.context = context; this.onlyLocal = onlyLocal;
    }
    boolean toEnd () { return from.getMessageId() == 0 && mode == MessagesLoader.MODE_REPEAT_INITIAL; }
  }

  static class MessagesLoader {
    static final int MODE_INITIAL = 0, MODE_MORE_TOP = 1, MODE_MORE_BOTTOM = 2, MODE_REPEAT_INITIAL = 3;
    static final int SPECIAL_MODE_NONE = 0;
    private static final boolean DEBUG_HANDLER = false;
    private static final int CHUNK_SIZE_SMALL = 15, CHUNK_SIZE_BIG = 50, CHUNK_SEARCH_OFFSET = -19, CHUNK_SIZE_SEARCH = 33, CHUNK_SIZE_BOTTOM = 31, CHUNK_BOTTOM_OFFSET = -30;
    private static final int MERGE_MODE_NONE = 0;
    /* MAX_RETRIES */
    final MessagesManager manager; final Tdlib tdlib; final Object lock = new Object();
    final List<Request> requests = new ArrayList<>(); final List<Long> processed = new ArrayList<>();
    TdApi.Message[] fallback = new TdApi.Message[0];
    boolean canLoadTop, canLoadBottom, isLoading, historyPreviewShown, historyPublished, historyPreviewAttempted;
    boolean retainingHistory, retainedCanLoadTop, retainedCanLoadBottom; int retainedScrollActions;
    boolean unreadNavigationPending, resolvedUnreadTarget, unreadNavigationStopped, unreadAnchorUnavailable;
    boolean unreadPreviousCanLoadTop, unreadPreviousCanLoadBottom, resumeUnreadOnFocus;
    boolean foundUnreadAtLeastOnce, loadingSupportsFilteredContinuation, loadingLocal, loadingAllowMoreTop, loadingAllowMoreBottom;
    int loadingMode, filteredPageContinuationCount, unreadNavigationScrollActions, scrollHighlightMode, knownTotalMessageCount, specialMode, mergeMode;
    long contextId = 1, unreadNavigationBoundary;
    Client.ResultHandler lastHandler; Object mergeChunk, visibleUnreadAnchor; Sponsored sponsoredResultHandler;
    int historyPreviewFailures; @Nullable Runnable historyPreviewRetry; long historyPreviewRetryContext, historyPreviewAllowedAt; boolean historyPreviewToEnd;
    boolean publishedToEnd;
    MessageId scrollMessageId, lastFromMessageId; TdApi.SearchMessagesFilter searchFilter;
    MoexShadowUnreadManager.HiddenUsersCallback hiddenUsersCallback; Runnable retryHiddenUsersLoad;
    final TreeMap<Long, TdApi.Message> unreadAnchorMessages = new TreeMap<>();
    MessagesLoader (MessagesManager manager) { this.manager = manager; this.tdlib = manager.tdlib; manager.loader = this; }
    long getChatId () { return 100; }
    boolean supportsHistoryPreview () { return true; }
    void retryHiddenUsersOnFocus () { }
    boolean canLoadBottom () { return retainingHistory ? retainedCanLoadBottom : canLoadBottom; }
    MessageId getStartTop () { return manager.adapter.rows.isEmpty() ? null : new MessageId(100, manager.adapter.rows.get(manager.adapter.rows.size() - 1).id); }
    MessageId getStartBottom () { return manager.adapter.rows.isEmpty() ? null : new MessageId(100, manager.adapter.rows.get(0).id); }
    TdApi.Message[] finishVisibleUnreadPage (boolean found) { visibleUnreadAnchor = null; return fallback; }
    void processMessages (long context, TdApi.Message[] messages, int count, String next, long nextId, boolean find, Object missing) { processed.add(context); }
    // TDLib transport double: records the function instead of sending it.
    void load (MessageId from, int offset, int limit, int mode, boolean onlyLocal, boolean top, boolean bottom) {
      synchronized (lock) {
        if (isLoading) return;
        isLoading = true; loadingMode = mode;
        lastHandler = object -> { };
        requests.add(new Request(from, offset, limit, mode, scrollHighlightMode, contextId, onlyLocal));
      }
    }
    Client.ResultHandler handler () { return lastHandler; }
    Request last () { return requests.get(requests.size() - 1); }
    void fail (TdApi.Error error) { onHistoryError(contextId, handler(), error); flushUi(); }
    // Applies the existing publication step of processMessages for a successful page.
    void publish () {
      publishedToEnd = historyPreviewShown && historyPreviewToEnd;
      historyPublished = true; historyPreviewShown = false; historyPreviewToEnd = false;
      lastHandler = null; isLoading = false; canLoadTop = true;
    }
    // The local topic scan pauseHistoryPreview() and reuse() end: run in test_topic_local_preview.
    private void endLocalTopicPreview () { }
    /* LOADER_METHODS */
  }

  static int checks;
  static void check (boolean value, String message) { checks++; if (!value) throw new AssertionError(message); }

  static MessagesLoader openedSnapshot () {
    uiQueue.clear(); looper.clear(); timerDelays.clear(); errorsShown = 0;
    MessagesManager manager = new MessagesManager(new Tdlib()); MessagesLoader loader = new MessagesLoader(manager);
    loader.loadFromMessage(new MessageId(100, 50), MessagesManager.HIGHLIGHT_MODE_UNREAD, true);
    // Arrange what the snapshot display step does once its rows are on screen.
    for (long id = 90; id > 60; id -= 10) manager.adapter.rows.add(new TGMessage(id));
    manager.manager.first = 1; loader.historyPreviewShown = true;
    check(loader.requests.size() == 1 && loader.unreadNavigationPending, "fixture opens with one unread request");
    return loader;
  }

  static void cancelledUnread () {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    Client.ResultHandler staleHandler = loader.handler(); long staleContext = loader.contextId;
    manager.userScrollActionsCount++; loader.cancelUnreadNavigation();
    check(manager.readMessagesDisabled() && !loader.loadMore(true, 50, false), "snapshot is read-only before its replacement");
    while (runTimer()) { }
    check(loader.requests.size() == 2, "cancelled unread navigation left the snapshot read-only");
    Request reload = loader.requests.get(1);
    check(reload.from.getMessageId() == 80 && reload.mode == MessagesLoader.MODE_REPEAT_INITIAL &&
      reload.highlight == MessagesManager.HIGHLIGHT_MODE_POSITION_RESTORE, "reload must keep the visible anchor");
    check(loader.historyPreviewShown && manager.adapter.rows.size() == 3, "visible snapshot rows must stay until replaced");
    loader.onHistoryError(staleContext, staleHandler, new TdApi.Error(500, "late"));
    while (runTimer()) { }
    check(loader.requests.size() == 2 && loader.isLoading && errorsShown == 0, "old generation must not touch the new request");
    manager.drag(); loader.cancelUnreadNavigation();
    check(loader.requests.size() == 2, "a drag during the reload must not restart it");
    loader.publish();
    check(!manager.readMessagesDisabled(), "authoritative page must end read-only state");
    check(loader.loadMore(true, 50, false) && loader.requests.get(2).mode == MessagesLoader.MODE_MORE_TOP, "pagination resumes after replacement");
  }

  static void boundedFailures () {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    loader.unreadNavigationPending = false; // A non-unread entry; its own request fails.
    loader.fail(new TdApi.Error(500, "Internal"));
    check(manager.controller.subtitle.equals("failed") && errorsShown == 1, "failure is reported");
    for (int i = 0; i < 20 && runTimer(); i++) {
      if (loader.isLoading) loader.fail(new TdApi.Error(500, "Internal"));
    }
    check(loader.requests.size() == 1 + MessagesLoader.MAX_HISTORY_PREVIEW_RETRIES, "retries must be bounded, got " + loader.requests.size());
    check(timerDelays.size() == 3 && timerDelays.get(0)[0] == 2000 && timerDelays.get(1)[0] == 4000 && timerDelays.get(2)[0] == 8000, "retry backoff");
    check(pending() == 0 && uiQueue.isEmpty() && !loader.isLoading, "exhausted retries leave no busy loop");
    for (Request r : loader.requests.subList(1, loader.requests.size()))
      check(r.from.getMessageId() == 80 && r.highlight == MessagesManager.HIGHLIGHT_MODE_POSITION_RESTORE, "retries keep the anchor");
    loader.resumeUnreadNavigation();
    check(loader.requests.size() == 5 && loader.isLoading, "focus re-arms a stalled snapshot");
    loader.fail(new TdApi.Error(429, "Too Many Requests: retry after 30"));
    check(timerDelays.get(timerDelays.size() - 1)[0] == 30000, "flood wait delays the retry");
    check(!loader.resumeHistoryPreview() && loader.requests.size() == 5, "a pending retry is not duplicated by user actions");
    runTimer();
    check(loader.requests.size() == 6, "the retry runs once the server's wait is over");
    loader.publish();
    check(!manager.readMessagesDisabled(), "a later success ends read-only state");
  }

  static void blurredAndStale () {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    manager.blur();
    while (runTimer()) { }
    check(loader.requests.size() == 1 && pending() == 0, "a blurred page waits for focus");
    manager.focus();
    check(loader.requests.size() == 2, "focus resumes the snapshot");
    loader.fail(new TdApi.Error(500, "x"));
    check(pending() == 1, "retry scheduled");
    loader.loadFromMessage(new MessageId(100, 7), MessagesManager.HIGHLIGHT_MODE_UNREAD, true);
    int afterNavigation = loader.requests.size();
    check(pending() == 0, "an explicit navigation removes the snapshot retry callback");
    while (runTimer()) { }
    check(loader.requests.size() == afterNavigation && !loader.historyPreviewShown, "an explicit navigation drops the snapshot retry");
  }

  static void staleRetry () {
    MessagesLoader loader = openedSnapshot();
    loader.unreadNavigationPending = false;
    loader.fail(new TdApi.Error(500, "x"));
    check(pending() == 1, "retry scheduled");
    // A filter refresh reloads the same snapshot in a newer generation, and fails too.
    loader.loadFromMessage(new MessageId(100, 80), MessagesManager.HIGHLIGHT_MODE_POSITION_RESTORE, false);
    check(pending() == 0, "a reused page must remove the old retry callback");
    loader.fail(new TdApi.Error(500, "x"));
    check(pending() == 1 && loader.requests.size() == 2 && loader.historyPreviewShown, "only the current generation is scheduled");
    check(timerDelays.get(1)[0] == 4000, "the newer generation keeps its backoff");
    runTimer();
    check(loader.requests.size() == 3, "the current generation retries");
  }

  static void pageErrors () {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    loader.unreadNavigationPending = false; loader.publish(); manager.controller.subtitle = null;
    check(loader.loadMore(true, 50, false), "page request");
    loader.fail(new TdApi.Error(500, "x"));
    check(manager.controller.subtitle == null && manager.controller.errors == 0, "a failed page must not mark the header as failed");
    check(pending() == 0 && loader.loadMore(true, 50, false), "page failures do not schedule snapshot reloads");
    loader.loadFromMessage(new MessageId(100, 5), MessagesManager.HIGHLIGHT_MODE_POSITION_RESTORE, true);
    loader.fail(new TdApi.Error(500, "x"));
    check("failed".equals(manager.controller.subtitle), "initial failures are still reported");
  }

  static void cancelWithoutSnapshot () {
    uiQueue.clear(); looper.clear(); timerDelays.clear();
    MessagesManager manager = new MessagesManager(new Tdlib()); MessagesLoader loader = new MessagesLoader(manager);
    for (long id = 90; id > 60; id -= 10) manager.adapter.rows.add(new TGMessage(id));
    // A repeat unread navigation over a normal page; its request shows "Updating messages".
    loader.loadFromMessage(new MessageId(100, 50), MessagesManager.HIGHLIGHT_MODE_UNREAD, false);
    manager.controller.setHistoryLoading(true, true);
    manager.userScrollActionsCount++; loader.cancelUnreadNavigation();
    while (runTimer()) { }
    check(manager.controller.subtitle == null, "cancelled navigation must clear the updating subtitle");
    check(loader.requests.size() == 1 && !loader.historyPreviewShown, "a normal page is not reloaded");
  }

  static void unreadFallback () {
    MessagesLoader loader = openedSnapshot();
    loader.fallback = new TdApi.Message[] {new TdApi.Message()};
    loader.fail(new TdApi.Error(429, "Too Many Requests: retry after 3"));
    while (runTimer()) { }
    check(loader.processed.size() == 1 && loader.requests.size() == 1, "unread fallback publishes without an extra reload");
  }

  /** A 24 h FLOOD_WAIT retry must not keep a closed page: destroy removes the real callback. */
  static void closeReleasesPage () {
    MessagesLoader loader = openedSnapshot();
    loader.unreadNavigationPending = false;
    loader.fail(new TdApi.Error(429, "Too Many Requests: retry after 86400"));
    check(pending() == 1 && nextDelay() == 86_400_000L, "a 24 h server wait schedules one reload, got " + nextDelay());
    WeakReference<MessagesManager> page = new WeakReference<>(loader.manager);
    WeakReference<MessagesLoader> pageLoader = new WeakReference<>(loader);
    loader.manager.destroy(new ViewController<Object>());
    check(pending() == 0 && loader.historyPreviewRetry == null, "closing the page must remove the pending snapshot reload");
    loader = null;
    for (int i = 0; i < 50 && (page.get() != null || pageLoader.get() != null); i++) {
      System.gc();
      try { Thread.sleep(10); } catch (InterruptedException e) { throw new AssertionError(e); }
    }
    check(page.get() == null && pageLoader.get() == null, "the main-thread queue must not keep a closed page alive");
  }

  /** Reusing the page for another chat removes the callback but keeps the server's wait. */
  static void reuseKeepsServerWait () {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    loader.unreadNavigationPending = false;
    loader.fail(new TdApi.Error(429, "Too Many Requests: retry after 600"));
    check(pending() == 1, "server wait scheduled");
    manager.destroy(new ViewController<Object>());
    check(pending() == 0, "reuse removes the pending reload");
    // The same controller shows a snapshot of the next chat, which also needs a reload.
    loader.loadFromMessage(new MessageId(100, 50), MessagesManager.HIGHLIGHT_MODE_UNREAD, true);
    for (long id = 90; id > 60; id -= 10) manager.adapter.rows.add(new TGMessage(id));
    loader.historyPreviewShown = true;
    int sent = loader.requests.size();
    manager.userScrollActionsCount++; loader.cancelUnreadNavigation();
    flushUi(); manager.drag(); runDue();
    check(loader.requests.size() == sent, "a reused page must not reload before the server's wait ends");
    check(pending() == 1 && nextDelay() == 600_000L, "one reload waits for the rest of the server's wait, got " + nextDelay());
    runTimer();
    check(loader.requests.size() == sent + 1 && SystemClock.now >= loader.historyPreviewAllowedAt, "the reload is sent when the wait ends");
  }

  /** Blur removes the callback; focus resumes it, without bypassing the server's wait. */
  static void focusKeepsServerWait () {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    loader.unreadNavigationPending = false;
    loader.fail(new TdApi.Error(429, "Too Many Requests: retry after 600"));
    long allowedAt = loader.historyPreviewAllowedAt;
    check(pending() == 1 && allowedAt == SystemClock.now + 600_000L, "server wait recorded");
    manager.blur();
    check(pending() == 0 && loader.historyPreviewRetry == null, "leaving the page must remove the pending reload");
    SystemClock.now += 10_000;
    manager.focus(); runDue();
    check(loader.requests.size() == 1, "focus must not bypass the server wait");
    check(pending() == 1 && nextDelay() == 590_000L, "focus waits for the rest of the server's wait, got " + nextDelay());
    manager.drag(); manager.scrollToStart(false); manager.scrollToStart(false); runDue();
    check(loader.requests.size() == 1 && pending() == 1, "drags and the arrow share the one pending reload during the wait");
    manager.blur(); manager.focus(); manager.blur(); manager.focus(); runDue();
    check(pending() == 1 && loader.requests.size() == 1, "repeated blur/focus keeps one callback");
    runTimer();
    check(loader.requests.size() == 2 && SystemClock.now >= allowedAt, "the reload is sent once the wait ends");
    check(loader.last().toEnd(), "the arrow tapped during the wait still asks for the history end");
    // A new wait on the end request: blur/focus or a drag still cannot send before it ends.
    loader.fail(new TdApi.Error(429, "Too Many Requests: retry after 60"));
    manager.blur(); manager.focus(); manager.drag(); runDue();
    check(loader.requests.size() == 2 && pending() == 1 && nextDelay() == 60_000L, "focus after a new wait must not send at once");
    runTimer();
    check(loader.requests.size() == 3 && loader.last().from.getMessageId() == 80,
      "after a drag during the wait, the one retry reloads around the visible row");
  }

  /** One tap on the arrow over a snapshot: keep the rows, ask for the history end once. */
  static void arrowLatest (boolean unreadPending) {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    if (!unreadPending) {
      loader.unreadNavigationPending = false; loader.fail(new TdApi.Error(500, "x"));
      runTimer(); check(loader.requests.size() == 2 && !loader.last().toEnd(), "a reload around the visible row is in flight");
    }
    Client.ResultHandler oldHandler = loader.handler(); long oldContext = loader.contextId;
    int sent = loader.requests.size(), errors = errorsShown;
    manager.scrollToStart(false);
    check(loader.requests.size() == sent + 1 && loader.last().toEnd(), "one tap on a snapshot must request the history end");
    check(loader.last().onlyLocal && loader.last().limit == MessagesLoader.CHUNK_SIZE_SMALL, "the same first request as opening a chat at its end");
    check(manager.bottomScrolls == 1 && manager.adapter.resets == 0 && manager.adapter.rows.size() == 3,
      "the tap keeps the snapshot rows on screen (no single seed, no blank list)");
    check(loader.historyPreviewShown && manager.readMessagesDisabled() && !loader.loadMore(true, 50, false), "rows stay read-only until replaced");
    loader.onHistoryError(oldContext, oldHandler, new TdApi.Error(500, "late"));
    flushUi();
    check(loader.isLoading && errorsShown == errors && pending() == 0, "the superseded request's late answer is ignored");
    manager.scrollToStart(false); manager.scrollToStart(false);
    check(loader.requests.size() == sent + 1 && manager.bottomScrolls == 3, "repeated taps must share the end request");
    check(!loader.resumeHistoryPreview(), "focus does not restart the end request");
    loader.fail(new TdApi.Error(500, "x"));
    runTimer();
    check(loader.requests.size() == sent + 2 && loader.last().toEnd(), "a failed end request retries the end");
    loader.publish();
    check(loader.publishedToEnd && !manager.readMessagesDisabled(), "the end page replaces the snapshot at the bottom");
    manager.scrollToStart(false);
    check(loader.requests.size() == sent + 2, "at the end of an authoritative page the arrow only scrolls");
  }

  static void arrowThenDrag () {
    MessagesLoader loader = openedSnapshot(); MessagesManager manager = loader.manager;
    manager.scrollToStart(false);
    Client.ResultHandler endHandler = loader.handler(); long endContext = loader.contextId;
    check(loader.last().toEnd(), "end request");
    manager.drag();
    check(loader.requests.size() == 3 && loader.last().from.getMessageId() == 80 &&
      loader.last().highlight == MessagesManager.HIGHLIGHT_MODE_POSITION_RESTORE, "a drag replaces the end request with one around the visible row");
    loader.onHistoryError(endContext, endHandler, new TdApi.Error(500, "late"));
    flushUi();
    check(errorsShown == 0 && loader.isLoading && pending() == 0, "the cancelled end request's answer is ignored");
    manager.drag();
    check(loader.requests.size() == 3, "further drags do not restart the reload");
  }

  /** A normal page keeps its existing arrow paths. */
  static void arrowNormalPage () {
    uiQueue.clear(); looper.clear(); timerDelays.clear();
    MessagesManager manager = new MessagesManager(new Tdlib()); MessagesLoader loader = new MessagesLoader(manager);
    for (long id = 90; id > 60; id -= 10) manager.adapter.rows.add(new TGMessage(id));
    loader.canLoadBottom = true;
    manager.scrollToStart(false);
    check(loader.requests.size() == 1 && loader.last().toEnd() && loader.retainingHistory && manager.adapter.resets == 0,
      "a page above the end keeps its rows while the end loads");
    manager.scrollToStart(false);
    check(loader.requests.size() == 1, "repeated taps share the retained end request");
    loader.retainingHistory = false; loader.isLoading = false; loader.lastHandler = null; loader.canLoadBottom = false;
    manager.scrollToStart(false);
    check(loader.requests.size() == 1 && manager.bottomScrolls == 1, "at the end the arrow only scrolls");
  }

  public static void main (String[] args) {
    switch (args[0]) {
      case "cancel": cancelledUnread(); break;
      case "failures": boundedFailures(); break;
      case "blur": blurredAndStale(); break;
      case "stale": staleRetry(); break;
      case "pages": pageErrors(); break;
      case "fallback": unreadFallback(); break;
      case "subtitle": cancelWithoutSnapshot(); break;
      case "close": closeReleasesPage(); break;
      case "reuse": reuseKeepsServerWait(); break;
      case "focus": focusKeepsServerWait(); break;
      case "arrow": arrowLatest(true); arrowLatest(false); break;
      case "arrow-drag": arrowThenDrag(); break;
      case "arrow-normal": arrowNormalPage(); break;
      default: throw new AssertionError(args[0]);
    }
    System.out.println("history snapshot recovery " + args[0] + ": " + checks + " checks passed");
  }
}
'''


def sources(loader_text=None, manager_text=None):
    loader = loader_text or LOADER.read_text(encoding="utf-8")
    manager = manager_text or MANAGER.read_text(encoding="utf-8")
    max_retries = re.search(r"static final int MAX_HISTORY_PREVIEW_RETRIES = \d+;", loader).group(0)
    return (HARNESS.replace("/* LOADER_METHODS */", "\n".join(method(loader, s) for s in LOADER_METHODS))
            .replace("/* MANAGER_METHODS */", "\n".join(method(manager, s) for s in MANAGER_METHODS))
            .replace("/* SCROLL_LISTENER */", method(manager, SCROLL_LISTENER))
            .replace("/* MAX_RETRIES */", max_retries)
            .replace("/* FORUMS */", "static class XgramForums {\n" +
                     method(FORUMS.read_text(encoding="utf-8"), "public static long retryAfterMs (") + "\n}"))


class HistoryPreviewRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="history-preview-recovery-")
        cls.compile(cls.temp.name, sources())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def compile(directory, source):
        java = Path(directory) / "Harness.java"
        java.write_text(source, encoding="utf-8")
        subprocess.run(["javac", "-d", directory, str(java)], check=True)

    def run_case(self, scenario, directory=None):
        return subprocess.run(["java", "-ea", "-cp", directory or self.temp.name, "Harness", scenario],
                              capture_output=True, text=True, timeout=120)

    def assert_passes(self, scenario):
        result = self.run_case(scenario)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_cancelled_unread_navigation_reloads_around_visible_snapshot(self):
        self.assert_passes("cancel")

    def test_failed_snapshot_requests_retry_with_bounded_backoff(self):
        self.assert_passes("failures")

    def test_blurred_page_waits_for_focus_and_navigation_drops_retry(self):
        self.assert_passes("blur")

    def test_stale_retry_generation_is_removed(self):
        self.assert_passes("stale")

    def test_page_errors_keep_header_and_pagination(self):
        self.assert_passes("pages")

    def test_unread_fallback_is_not_reloaded_twice(self):
        self.assert_passes("fallback")

    def test_cancel_without_snapshot_clears_subtitle(self):
        self.assert_passes("subtitle")

    def test_closing_page_removes_long_flood_wait_callback(self):
        self.assert_passes("close")

    def test_reused_page_removes_callback_and_keeps_server_wait(self):
        self.assert_passes("reuse")

    def test_focus_resumes_after_server_wait_only(self):
        self.assert_passes("focus")

    def test_arrow_on_snapshot_requests_history_end_once(self):
        self.assert_passes("arrow")

    def test_drag_replaces_pending_end_request(self):
        self.assert_passes("arrow-drag")

    def test_arrow_on_normal_page_keeps_existing_paths(self):
        self.assert_passes("arrow-normal")

    def negative(self, old, new, scenario, message, target=LOADER):
        text = target.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, old)
        changed = text.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="history-preview-baseline-") as tmp:
            if target == LOADER:
                self.compile(tmp, sources(loader_text=changed))
            else:
                self.compile(tmp, sources(manager_text=changed))
            result = self.run_case(scenario, tmp)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def test_negative_cancel_without_continuation_stays_read_only(self):
        self.negative("        continueHistoryPreview(context, null);\n      } else {", "      } else {", "cancel",
                      "cancelled unread navigation left the snapshot read-only")

    def test_negative_cancel_keeps_updating_subtitle(self):
        self.negative("        manager.controller().setHistoryLoading(false, false); // Nothing is being updated anymore.\n", "",
                      "subtitle", "cancelled navigation must clear the updating subtitle")

    def test_negative_error_without_continuation_stays_read_only(self):
        self.negative("      if (!hasFallback) continueHistoryPreview(currentContextId, error);\n", "", "failures",
                      "retries must be bounded, got 1")

    def test_negative_unbounded_retries(self):
        self.negative("++historyPreviewFailures > MAX_HISTORY_PREVIEW_RETRIES", "++historyPreviewFailures < 0",
                      "failures", "retries must be bounded")

    def test_negative_page_error_marks_header(self):
        self.negative("(initialLoad || historyPreviewShown)", "true", "pages",
                      "a failed page must not mark the header as failed")

    # The first round only ignored a stale callback by contextId; it still held the page.
    REUSE_CANCEL = ("    // Closing or renavigating removes the pending reload itself; historyPreviewAllowedAt stays.\n"
                    "    cancelHistoryPreviewRetry();\n")

    def test_negative_reuse_keeps_callback_stale_generation(self):
        self.negative(self.REUSE_CANCEL, "", "stale", "a reused page must remove the old retry callback")

    def test_negative_reuse_keeps_callback_closed_page(self):
        self.negative(self.REUSE_CANCEL, "", "close", "closing the page must remove the pending snapshot reload")

    def test_negative_blur_keeps_callback(self):
        self.negative("    loader.pauseHistoryPreview();\n", "", "focus",
                      "leaving the page must remove the pending reload", target=MANAGER)

    def test_negative_focus_bypasses_server_wait(self):
        self.negative("    if (wait > 0) {\n      scheduleHistoryPreviewReload(contextId, wait);",
                      "    if (false) {\n      scheduleHistoryPreviewReload(contextId, wait);", "focus",
                      "focus must not bypass the server wait")

    def test_negative_reuse_forgets_server_wait(self):
        self.negative("    historyPreviewToEnd = false;\n    manager.controller().setHistoryLoading(false, false);",
                      "    historyPreviewToEnd = false;\n    historyPreviewAllowedAt = 0;\n    manager.controller().setHistoryLoading(false, false);",
                      "reuse", "a reused page must not reload before the server's wait ends")

    def test_negative_arrow_reloads_old_anchor(self):
        # First-round arrow: scroll the snapshot, then reload around the old visible row.
        old = ("    if (loader.isShowingHistoryPreview()) {\n"
               "      // The snapshot may be older than the chat: keep it on screen and replace it with the history end.\n"
               "      scrollToBottom(true);\n"
               "      loader.showHistoryPreviewEnd();\n"
               "    } else if (loader.canLoadBottom()) {\n"
               "      loadFromStart();\n"
               "    } else {\n"
               "      scrollToBottom(true);\n"
               "    }\n")
        new = ("    if (loader.canLoadBottom()) {\n"
               "      loadFromStart();\n"
               "    } else {\n"
               "      scrollToBottom(true);\n"
               "      loader.resumeHistoryPreview();\n"
               "    }\n")
        self.negative(old, new, "arrow", "one tap on a snapshot must request the history end", target=MANAGER)

    def test_negative_arrow_taps_restart_end_request(self):
        self.negative("    if (historyPreviewToEnd && pending) return; // Repeated taps share the pending end request.\n", "",
                      "arrow", "repeated taps must share the end request")

    def test_negative_drag_keeps_end_request(self):
        self.negative("  public void onHistoryPreviewDragged () {\n    if (historyPreviewToEnd && historyPreviewShown && !historyPublished) {",
                      "  public void onHistoryPreviewDragged () {\n    if (false) {", "arrow-drag",
                      "a drag replaces the end request with one around the visible row")


if __name__ == "__main__":
    unittest.main()
