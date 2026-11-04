package moe.kirao.mgx;

import android.os.SystemClock;

import androidx.annotation.NonNull;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.Log;
import org.thunderdog.challegram.telegram.Tdlib;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import tgx.td.Td;

/**
 * Derives per-chat unread counts hidden by Shadow Ban. Exact results and in-flight requests are
 * shared by every folder row; an all-hidden unread range may also be read locally without sending
 * a server read receipt, while mixed unread ranges keep TDLib's continuous read position unchanged.
 */
public final class MoexShadowUnreadManager {
  public static final int UNKNOWN_HIDDEN_UNREAD_COUNT = -1;
  private static final int PAGE_SIZE = 100;
  private static final int MAX_SCAN_REQUESTS = 40;
  private static final int MAX_BLOCKED_USERS_PAGES = 40;
  private static final long CHAT_STATE_DEBOUNCE_MS = 150L;
  private static final long SCAN_REQUEST_GAP_MS = 500L;
  private static final long SCAN_PAGE_GAP_MS = 250L;
  private static final long SCAN_INCOMPLETE_RETRY_DELAY_MS = 1500L;
  private static final long SCAN_FAILURE_COOLDOWN_MS = 15_000L;
  private static final long SCAN_REQUEST_TIMEOUT_MS = 30_000L;
  private static final long HIDDEN_USERS_REFRESH_INTERVAL_MS = 60_000L;
  private static final long LOCAL_READ_DEDUP_DELAY_MS = 1500L;
  private static final Pattern RETRY_AFTER_PATTERN = Pattern.compile(
    "(?i)(?:retry(?:_|\\s+)after\\s*[:=_]?\\s*|flood(?:_[a-z]+)*_wait_)(\\d+)");
  private static final Object STATES_LOCK = new Object();
  private static final Map<Tdlib, AccountState> ACCOUNT_STATES = new WeakHashMap<>();

  public interface Callback {
    void onResult (boolean success, int hiddenUnreadCount);
  }

  public interface HiddenUsersCallback {
    void onResult (boolean ready);
  }

  public interface HiddenUsersListener {
    void onHiddenUsersChanged (long revision);
  }

  /** Main blacklist membership must not depend on whether a private Chat was cached. */
  public static boolean isMainBlocked (@NonNull Tdlib tdlib, long userId) {
    AccountState state = accountState(tdlib);
    synchronized (state) {
      Boolean override = state.blockOverrides.get(userId);
      if (override != null) return override;
      if (state.hiddenUsersReady) return state.mainUserIds.contains(userId);
    }
    return tdlib.chatFullyBlocked(tgx.td.ChatId.fromUserId(userId));
  }

  public static boolean areHiddenUsersReady (@NonNull Tdlib tdlib) {
    AccountState state = accountState(tdlib);
    synchronized (state) { return state.hiddenUsersReady; }
  }

  public static long hiddenUsersRevision (@NonNull Tdlib tdlib) {
    AccountState state = accountState(tdlib);
    synchronized (state) { return state.hiddenUsersRevision; }
  }

  /** Uses the same account queue as unread scans, including its timeout and bounded retry. */
  public static void ensureHiddenUsers (@NonNull Tdlib tdlib, @NonNull HiddenUsersCallback callback) {
    AccountState state = accountState(tdlib);
    final long requestId, generation;
    final boolean ready;
    final boolean failImmediately;
    synchronized (state) {
      requestId = ++state.nextHiddenUsersCallbackId;
      generation = state.hiddenUsersGeneration;
      ready = state.hiddenUsersReady;
      failImmediately = !ready && state.apiAttemptTimedOut;
      if (failImmediately) {
        state.hiddenUsersDemandPending = true;
      } else {
        state.hiddenUsersCallbacks.put(callback, requestId);
      }
      if (!ready) state.hiddenUsersLoadFailed = false;
    }
    if (failImmediately) {
      tdlib.ui().post(() -> callback.onResult(false));
      scheduleHiddenUsersLoad(tdlib, state);
      return;
    }
    if (ready) {
      deliverHiddenUsers(tdlib, state, callback, requestId, generation, true);
    } else {
      scheduleHiddenUsersLoad(tdlib, state);
    }
  }

  /** Reconcile other-client changes without discarding an already usable snapshot. */
  public static void refreshHiddenUsers (@NonNull Tdlib tdlib, boolean force) {
    if (!(tdlib.authorizationState() instanceof TdApi.AuthorizationStateReady)) return;
    AccountState state = accountState(tdlib);
    synchronized (state) {
      if (state.hiddenUsersLoading || state.hiddenUsersLoadScheduled || state.hiddenUsersRefreshPending) return;
      long now = SystemClock.uptimeMillis();
      if (!force && (!state.hiddenUsersReady || now < state.nextHiddenUsersRefreshUptimeMillis)) return;
      state.nextHiddenUsersRefreshUptimeMillis = now + HIDDEN_USERS_REFRESH_INTERVAL_MS;
      state.hiddenUsersLoadFailed = false;
      state.hiddenUsersLoadRetryCount = 0;
      state.hiddenUsersRefreshPending = state.hiddenUsersReady;
      state.hiddenUsersDemandPending = true;
    }
    scheduleHiddenUsersLoad(tdlib, state);
  }

  /** A successful local block may have no chat update when no private chat exists. */
  public static long blockListGeneration (@NonNull Tdlib tdlib) {
    AccountState state = accountState(tdlib);
    synchronized (state) { return state.hiddenUsersGeneration; }
  }

  public static void onBlockListResult (@NonNull Tdlib tdlib, long generation,
                                       TdApi.MessageSender sender, TdApi.BlockList blockList,
                                       TdApi.Object result) {
    if (!(result instanceof TdApi.Ok) || !(sender instanceof TdApi.MessageSenderUser)) return;
    AccountState state = accountState(tdlib);
    synchronized (state) {
      if (state.hiddenUsersGeneration != generation) return;
      onBlockListChanged(tdlib, ((TdApi.MessageSenderUser) sender).userId,
        blockList instanceof TdApi.BlockListMain);
    }
  }

  private static void deliverHiddenUsers (Tdlib tdlib, AccountState state,
                                         HiddenUsersCallback callback, long requestId,
                                         long generation, boolean ready) {
    tdlib.ui().post(() -> {
      final boolean result;
      synchronized (state) {
        Long pendingId = state.hiddenUsersCallbacks.get(callback);
        if (state.hiddenUsersGeneration != generation || pendingId == null || pendingId != requestId) return;
        state.hiddenUsersCallbacks.remove(callback);
        result = ready && state.hiddenUsersReady;
      }
      callback.onResult(result);
    });
  }

  public static void cancelHiddenUsers (@NonNull Tdlib tdlib, HiddenUsersCallback callback) {
    AccountState state = accountState(tdlib);
    synchronized (state) { state.hiddenUsersCallbacks.remove(callback); }
  }

  public static void addHiddenUsersListener (@NonNull Tdlib tdlib, HiddenUsersListener listener) {
    AccountState state = accountState(tdlib);
    synchronized (state) { state.hiddenUsersListeners.add(listener); }
  }

  public static void removeHiddenUsersListener (@NonNull Tdlib tdlib, HiddenUsersListener listener) {
    AccountState state = accountState(tdlib);
    synchronized (state) { state.hiddenUsersListeners.remove(listener); }
  }

  private static void notifyHiddenUsersChanged (Tdlib tdlib, AccountState state) {
    final long revision;
    final List<HiddenUsersListener> listeners;
    synchronized (state) {
      revision = state.hiddenUsersRevision;
      listeners = new ArrayList<>(state.hiddenUsersListeners);
    }
    tdlib.ui().post(() -> {
      for (HiddenUsersListener listener : listeners) {
        synchronized (state) {
          if (state.hiddenUsersRevision != revision || !state.hiddenUsersListeners.contains(listener)) continue;
        }
        listener.onHiddenUsersChanged(revision);
      }
    });
  }

  private interface ScanCallback {
    void onResult (ScanOutcome outcome, int hiddenUnreadCount);
  }

  private enum ScanOutcome {
    SUCCESS,
    TRANSIENT_FAILURE,
    INCOMPLETE,
    SUPERSEDED
  }

  private MoexShadowUnreadManager () { }

  /**
   * Returns a hidden-unread count only when it can be derived from the current in-memory snapshot
   * without an asynchronous history request. The method has no side effects and is safe to use
   * while constructing or rebinding chat rows.
   */
  public static int getKnownHiddenUnreadCount (@NonNull Tdlib tdlib, @NonNull TdApi.Chat chat) {
    int rawUnreadCount = chat.unreadCount;
    if (rawUnreadCount <= 0) return 0;

    int chatType = chat.type.getConstructor();
    if (tdlib.isChannelChat(chat) || chatType == TdApi.ChatTypeSecret.CONSTRUCTOR) return 0;
    if (chatType == TdApi.ChatTypeSupergroup.CONSTRUCTOR) {
      TdApi.Supergroup supergroup = tdlib.chatToSupergroup(chat.id);
      if (supergroup == null || supergroup.isForum) return 0;
    }

    long privateUserId = org.thunderdog.challegram.data.TD.getUserId(chat);
    if (privateUserId != 0) {
      return !tdlib.isSelfUserId(privateUserId) &&
        MoexMessageFilter.isShadowBannedUser(tdlib, privateUserId) ? rawUnreadCount : 0;
    }
    if (chatType != TdApi.ChatTypeBasicGroup.CONSTRUCTOR &&
        chatType != TdApi.ChatTypeSupergroup.CONSTRUCTOR) {
      return 0;
    }

    TdApi.Message topMessage = chat.lastMessage;
    if (rawUnreadCount == 1 && topMessage != null && !topMessage.isOutgoing &&
        topMessage.sendingState == null && topMessage.id > chat.lastReadInboxMessageId) {
      return MoexMessageFilter.isShadowBanned(tdlib, topMessage) ? 1 : 0;
    }

    long historyTopMessageId = topMessage != null && topMessage.sendingState == null ?
      topMessage.id : 0;
    AccountState accountState = accountState(tdlib);
    synchronized (accountState) {
      ChatRequest request = accountState.chatRequests.get(chat.id);
      if (request != null && request.valid && isCurrentLocked(accountState, request) &&
          request.matches(rawUnreadCount, chat.lastReadInboxMessageId, historyTopMessageId)) {
        return Math.max(0, Math.min(request.hiddenUnreadCount, rawUnreadCount));
      }
    }
    return UNKNOWN_HIDDEN_UNREAD_COUNT;
  }

  /** Returns whether this account is already known to have any manual or main-block-list users. */
  public static boolean hasKnownHiddenUsers (@NonNull Tdlib tdlib) {
    if (MoexConfig.instance().getShadowBannedUsers(tdlib.id()).length > 0) {
      return true;
    }
    AccountState accountState;
    synchronized (STATES_LOCK) {
      accountState = ACCOUNT_STATES.get(tdlib);
    }
    if (accountState == null) return false;
    synchronized (accountState) {
      if (accountState.hiddenUsersReady && !accountState.hiddenUserIds.isEmpty()) {
        return true;
      }
      for (Boolean blocked : accountState.blockOverrides.values()) {
        if (Boolean.TRUE.equals(blocked)) {
          return true;
        }
      }
    }
    return false;
  }

  /**
   * Coalesces authoritative TDLib chat updates so Shadow Ban local reads also run for chats that
   * aren't currently represented by an attached row or an open MessagesController.
   */
  public static void scheduleForChat (@NonNull Tdlib tdlib, long chatId) {
    if (chatId == 0) return;
    AccountState accountState = accountState(tdlib);
    TdApi.Chat currentChat = tdlib.chat(chatId);
    if (currentChat != null && currentChat.unreadCount > 0 &&
        getKnownHiddenUnreadCount(tdlib, currentChat) == currentChat.unreadCount) {
      synchronized (accountState) {
        accountState.scheduledChecks.remove(chatId);
      }
      requestForChat(tdlib, currentChat, (success, hiddenUnreadCount) -> { }, true);
      return;
    }
    long checkId;
    synchronized (accountState) {
      checkId = ++accountState.nextScheduledCheckId;
      accountState.scheduledChecks.put(chatId, checkId);
    }
    tdlib.ui().postDelayed(() -> {
      synchronized (accountState) {
        Long scheduledCheckId = accountState.scheduledChecks.get(chatId);
        if (scheduledCheckId == null || scheduledCheckId != checkId) return;
        accountState.scheduledChecks.remove(chatId);
      }
      TdApi.Chat chat = tdlib.chat(chatId);
      if (chat != null && mayHaveAllUnreadHidden(tdlib, chat)) {
        requestForChat(tdlib, chat, (success, hiddenUnreadCount) -> { }, true);
      }
    }, CHAT_STATE_DEBOUNCE_MS);
  }

  private static boolean mayHaveAllUnreadHidden (@NonNull Tdlib tdlib, @NonNull TdApi.Chat chat) {
    if (chat.unreadCount <= 0) return false;
    int chatType = chat.type.getConstructor();
    if (tdlib.isChannelChat(chat) || chatType == TdApi.ChatTypeSecret.CONSTRUCTOR) return false;
    if (chatType == TdApi.ChatTypeSupergroup.CONSTRUCTOR) {
      TdApi.Supergroup supergroup = tdlib.chatToSupergroup(chat.id);
      if (supergroup == null || supergroup.isForum) return false;
    }
    TdApi.Message topMessage = chat.lastMessage;
    if (topMessage == null || topMessage.sendingState != null) return false;
    // An incoming visible top message proves that at least one unread message must stay visible.
    // This cheap test prevents an unnecessary history scan for nearly every ordinary group update.
    return topMessage.isOutgoing || topMessage.id <= chat.lastReadInboxMessageId ||
      MoexMessageFilter.isShadowBanned(tdlib, topMessage);
  }

  /**
   * Resolves the Shadow Ban unread count for a regular chat. When every unread inbox message is
   * hidden, the shared result also advances TDLib's local read position through a chat-scoped
   * native operation that never sends the corresponding server read receipt.
   */
  public static void requestForChat (@NonNull Tdlib tdlib, @NonNull TdApi.Chat chat,
                                     @NonNull Callback callback) {
    requestForChat(tdlib, chat, callback, false);
  }

  private static void requestForChat (@NonNull Tdlib tdlib, @NonNull TdApi.Chat chat,
                                      @NonNull Callback callback, boolean highPriority) {
    AccountState accountState = accountState(tdlib);
    long accountGeneration;
    synchronized (accountState) {
      accountGeneration = accountState.generation;
    }
    int rawUnreadCount = chat.unreadCount;
    long lastReadInboxMessageId = chat.lastReadInboxMessageId;
    long actualTopMessageId = chat.lastMessage != null ? chat.lastMessage.id : 0;
    long historyTopMessageId = chat.lastMessage != null && chat.lastMessage.sendingState == null ?
      chat.lastMessage.id : 0;
    long privateUserId = org.thunderdog.challegram.data.TD.getUserId(chat);
    int chatType = chat.type.getConstructor();
    TdApi.Supergroup supergroup = chatType == TdApi.ChatTypeSupergroup.CONSTRUCTOR ?
      tdlib.chatToSupergroup(chat.id) : null;
    int localReadScope = chat.type.getConstructor() == TdApi.ChatTypeSecret.CONSTRUCTOR ?
      Tdlib.GhostReadScope.NONE : Tdlib.ghostReadScope(chat);

    Callback resultCallback = (success, hiddenUnreadCount) -> {
      boolean current = success && isCurrent(accountState, accountGeneration);
      if (current && privateUserId != 0 && hiddenUnreadCount > 0 &&
          !MoexMessageFilter.isShadowBannedUser(tdlib, privateUserId)) {
        hiddenUnreadCount = 0;
      }
      if (current) {
        markAllUnreadHiddenLocally(tdlib, chat.id, rawUnreadCount, lastReadInboxMessageId,
          actualTopMessageId, historyTopMessageId, privateUserId, localReadScope,
          chat.isMarkedAsUnread, hiddenUnreadCount);
      }
      callback.onResult(current, hiddenUnreadCount);
    };

    if (rawUnreadCount <= 0 || tdlib.isChannelChat(chat) ||
        chatType == TdApi.ChatTypeSupergroup.CONSTRUCTOR &&
          (supergroup == null || supergroup.isForum)) {
      deliver(tdlib, resultCallback, true, 0);
      return;
    }

    if (privateUserId != 0) {
      int hiddenUnreadCount = !tdlib.isSelfUserId(privateUserId) &&
        MoexMessageFilter.isShadowBannedUser(tdlib, privateUserId) ? rawUnreadCount : 0;
      deliver(tdlib, resultCallback, true, hiddenUnreadCount);
      return;
    }

    if (chatType != TdApi.ChatTypeBasicGroup.CONSTRUCTOR &&
        chatType != TdApi.ChatTypeSupergroup.CONSTRUCTOR) {
      deliver(tdlib, resultCallback, true, 0);
      return;
    }

    TdApi.Message topMessage = chat.lastMessage;
    if (rawUnreadCount == 1 && topMessage != null && !topMessage.isOutgoing &&
        topMessage.sendingState == null && topMessage.id > lastReadInboxMessageId &&
        MoexMessageFilter.isShadowBanned(tdlib, topMessage)) {
      // With exactly one inbox unread, a hidden incoming top message is the complete unread range.
      // Avoid queueing a history request that can lag behind unrelated folder-row scans.
      Log.i("Shadow single unread fast path chatId:%d lastRead:%d top:%d marked:%b scope:%d",
        chat.id, lastReadInboxMessageId, topMessage.id, chat.isMarkedAsUnread, localReadScope);
      deliver(tdlib, resultCallback, true, 1);
      return;
    }

    request(tdlib, chat.id, rawUnreadCount, lastReadInboxMessageId,
      historyTopMessageId, resultCallback, highPriority);
  }

  private static void markAllUnreadHiddenLocally (Tdlib tdlib, long chatId, int rawUnreadCount,
                                                  long lastReadInboxMessageId,
                                                  long actualTopMessageId,
                                                  long historyTopMessageId, long privateUserId,
                                                  @Tdlib.GhostReadScope int localReadScope,
                                                  boolean isMarkedAsUnread,
                                                  int hiddenUnreadCount) {
    if (rawUnreadCount <= 0 || hiddenUnreadCount != rawUnreadCount || isMarkedAsUnread ||
        historyTopMessageId <= lastReadInboxMessageId ||
        localReadScope == Tdlib.GhostReadScope.NONE) {
      return;
    }

    AccountState accountState = accountState(tdlib);
    LocalReadRequest request;
    synchronized (accountState) {
      request = new LocalReadRequest(accountState.generation, rawUnreadCount,
        lastReadInboxMessageId, actualTopMessageId, privateUserId, localReadScope);
      LocalReadRequest previous = accountState.localReadRequests.get(chatId);
      if (request.matches(previous)) {
        return;
      }
      accountState.localReadRequests.put(chatId, request);
    }

    Log.i("Shadow local read queued chatId:%d unread:%d lastRead:%d top:%d scope:%d",
      chatId, rawUnreadCount, lastReadInboxMessageId, historyTopMessageId, localReadScope);
    readMessagesLocally(tdlib, accountState, chatId, request, historyTopMessageId);
  }

  private static void readMessagesLocally (Tdlib tdlib, AccountState accountState, long chatId,
                                           LocalReadRequest request, long targetMessageId) {
    tdlib.readMessagesLocally(request.scope, chatId, targetMessageId, request.rawUnreadCount,
      request.lastReadInboxMessageId,
      () -> isLocalReadRequestCurrent(tdlib, accountState, chatId, request),
      result -> {
        Log.i("Shadow local read result chatId:%d target:%d result:%s", chatId,
          targetMessageId, result);
        if (result.getConstructor() == TdApi.Error.CONSTRUCTOR) {
          finishLocalReadRequest(accountState, chatId, request);
        } else {
          tdlib.ui().postDelayed(() -> {
            TdApi.Chat currentChat = tdlib.chat(chatId);
            Log.i("Shadow local read state chatId:%d unread:%d mentions:%d reactions:%d marked:%b lastRead:%d target:%d",
              chatId, currentChat != null ? currentChat.unreadCount : -1,
              currentChat != null ? currentChat.unreadMentionCount : -1,
              currentChat != null ? currentChat.unreadReactionCount : -1,
              currentChat != null && currentChat.isMarkedAsUnread,
              currentChat != null ? currentChat.lastReadInboxMessageId : 0, targetMessageId);
            finishLocalReadRequest(accountState, chatId, request);
          }, LOCAL_READ_DEDUP_DELAY_MS);
        }
      });
  }

  private static void finishLocalReadRequest (AccountState accountState, long chatId,
                                              LocalReadRequest request) {
    synchronized (accountState) {
      if (accountState.localReadRequests.get(chatId) == request) {
        accountState.localReadRequests.remove(chatId);
      }
    }
  }

  public static void request (@NonNull Tdlib tdlib, long chatId, int rawUnreadCount,
                              long lastReadInboxMessageId, long topMessageId,
                              @NonNull Callback callback) {
    request(tdlib, chatId, rawUnreadCount, lastReadInboxMessageId, topMessageId, callback, false);
  }

  private static void request (@NonNull Tdlib tdlib, long chatId, int rawUnreadCount,
                               long lastReadInboxMessageId, long topMessageId,
                               @NonNull Callback callback, boolean highPriority) {
    if (chatId == 0 || rawUnreadCount <= 0) {
      deliver(tdlib, callback, true, 0);
      return;
    }

    AccountState accountState = accountState(tdlib);
    ChatRequest chatRequest;
    Integer cachedResult = null;
    boolean cachedFailure = false;
    List<Callback> staleCallbacks = null;
    boolean scheduleHiddenUsersLoad = false;
    boolean enqueueRequest = false;
    boolean failWaiterImmediately = false;
    synchronized (accountState) {
      long now = SystemClock.uptimeMillis();
      chatRequest = accountState.chatRequests.get(chatId);
      boolean sameSnapshot = chatRequest != null &&
        chatRequest.matches(rawUnreadCount, lastReadInboxMessageId, topMessageId);
      boolean promotedToHighPriority = sameSnapshot && highPriority && !chatRequest.highPriority;
      if (promotedToHighPriority) {
        chatRequest.highPriority = true;
        if (chatRequest.queued) {
          accountState.scanQueue.remove(chatRequest);
          accountState.scanQueue.addFirst(chatRequest);
        }
      }
      if (!accountState.hiddenUsersReady && accountState.hiddenUsersLoadFailed &&
          !accountState.apiAttemptTimedOut) {
        cachedFailure = true;
      } else if (sameSnapshot && chatRequest.valid) {
        cachedResult = chatRequest.hiddenUnreadCount;
      } else if (sameSnapshot && chatRequest.failed &&
          now < chatRequest.failureRetryUptimeMillis && !promotedToHighPriority) {
        cachedFailure = true;
      } else {
        if (accountState.apiAttemptTimedOut && !accountState.hiddenUsersReady) {
          accountState.hiddenUsersLoadFailed = false;
        }
        if (!sameSnapshot) {
          if (chatRequest != null) {
            staleCallbacks = new ArrayList<>(chatRequest.callbacks);
            chatRequest.callbacks.clear();
            chatRequest.started = false;
            if (chatRequest.queued) {
              accountState.scanQueue.remove(chatRequest);
            }
            chatRequest.queued = false;
          }
          chatRequest = new ChatRequest(accountState.generation, chatId, rawUnreadCount,
            lastReadInboxMessageId, topMessageId);
          chatRequest.highPriority = highPriority;
          accountState.chatRequests.put(chatId, chatRequest);
        } else if (chatRequest.failed) {
          chatRequest.failed = false;
          chatRequest.transientRetryCount = promotedToHighPriority ? 1 : 0;
          chatRequest.incompleteRetryUsed = promotedToHighPriority;
          chatRequest.sentRequestCount = 0;
          chatRequest.failureRetryUptimeMillis = 0;
        }
        failWaiterImmediately = accountState.apiAttemptTimedOut;
        if (!failWaiterImmediately) chatRequest.callbacks.add(callback);
        if (!chatRequest.started) {
          if (accountState.hiddenUsersReady) {
            chatRequest.started = true;
            enqueueRequest = true;
          } else {
            scheduleHiddenUsersLoad = true;
          }
        }
      }
    }

    if (staleCallbacks != null) {
      for (Callback staleCallback : staleCallbacks) {
        deliver(tdlib, staleCallback, false, 0);
      }
    }
    if (cachedFailure) {
      deliver(tdlib, callback, false, 0);
      return;
    }
    if (cachedResult != null) {
      deliver(tdlib, callback, true, cachedResult);
      return;
    }
    if (failWaiterImmediately) deliver(tdlib, callback, false, 0);
    if (scheduleHiddenUsersLoad) {
      scheduleHiddenUsersLoad(tdlib, accountState);
    }
    if (enqueueRequest) {
      enqueueScanRequest(tdlib, accountState, chatRequest);
    }
  }

  private static void enqueueScanRequest (@NonNull Tdlib tdlib,
                                          @NonNull AccountState accountState,
                                          @NonNull ChatRequest request) {
    synchronized (accountState) {
      if (!isCurrentLocked(accountState, request) || request.valid || request.queued ||
          accountState.activeScanRequest == request) {
        return;
      }
      request.queued = true;
      if (request.highPriority) {
        accountState.scanQueue.addFirst(request);
      } else {
        accountState.scanQueue.addLast(request);
      }
    }
    scheduleScanPump(tdlib, accountState);
  }

  private static void scheduleScanPump (@NonNull Tdlib tdlib,
                                        @NonNull AccountState accountState) {
    long delayMillis;
    synchronized (accountState) {
      if (accountState.activeApiAttemptId != 0 || accountState.activeScanRequest != null || accountState.scanPumpScheduled ||
          accountState.hiddenUsersLoading || accountState.hiddenUsersRefreshPending ||
          accountState.scanQueue.isEmpty()) {
        return;
      }
      long notBeforeUptimeMillis = Math.max(accountState.nextScanAllowedUptimeMillis,
        accountState.scanRetryAfterUptimeMillis);
      delayMillis = Math.max(0L, notBeforeUptimeMillis - SystemClock.uptimeMillis());
      accountState.scanPumpScheduled = true;
    }
    tdlib.ui().postDelayed(() -> runScanPump(tdlib, accountState), delayMillis);
  }

  private static void runScanPump (@NonNull Tdlib tdlib,
                                   @NonNull AccountState accountState) {
    ChatRequest nextRequest = null;
    boolean waitForCooldown = false;
    synchronized (accountState) {
      accountState.scanPumpScheduled = false;
      if (accountState.activeApiAttemptId != 0 || accountState.activeScanRequest != null ||
          accountState.hiddenUsersLoading || accountState.hiddenUsersRefreshPending) return;
      long notBeforeUptimeMillis = Math.max(accountState.nextScanAllowedUptimeMillis,
        accountState.scanRetryAfterUptimeMillis);
      if (SystemClock.uptimeMillis() < notBeforeUptimeMillis) {
        waitForCooldown = true;
      } else {
        while (!accountState.scanQueue.isEmpty()) {
          ChatRequest candidate = accountState.scanQueue.pollFirst();
          candidate.queued = false;
          if (isCurrentLocked(accountState, candidate) && candidate.started && !candidate.valid) {
            accountState.activeScanRequest = candidate;
            nextRequest = candidate;
            break;
          }
        }
      }
    }
    if (waitForCooldown) {
      scheduleScanPump(tdlib, accountState);
    } else if (nextRequest != null) {
      executeRequest(tdlib, accountState, nextRequest);
    }
  }

  /** Manual Shadow Ban edits preserve the successful server snapshot and any in-flight page. */
  public static void invalidateAccount (int accountId) {
    List<Tdlib> accounts = new ArrayList<>();
    synchronized (STATES_LOCK) {
      for (Tdlib tdlib : ACCOUNT_STATES.keySet()) {
        if (tdlib != null && tdlib.id() == accountId) accounts.add(tdlib);
      }
    }
    for (Tdlib tdlib : accounts) {
      AccountState state = accountState(tdlib);
      if (syncManualUsers(tdlib, state, true)) {
        notifyHiddenUsersChanged(tdlib, state);
      }
    }
  }

  private static boolean syncManualUsers (Tdlib tdlib, AccountState state, boolean invalidateUnread) {
    final long revision;
    synchronized (state) { revision = ++state.manualUsersRevision; }
    HashSet<Long> users = new HashSet<>();
    for (long userId : MoexConfig.instance().getShadowBannedUsers(tdlib.id())) {
      if (userId != 0 && !tdlib.isSelfUserId(userId)) users.add(userId);
    }
    synchronized (state) {
      if (revision != state.manualUsersRevision) return false;
      state.manualUserIds.clear();
      state.manualUserIds.addAll(users);
      rebuildHiddenUsers(state);
      if (invalidateUnread) {
        clearUnreadRequests(state);
        state.hiddenUsersRevision++;
      }
      return true;
    }
  }

  private static void rebuildHiddenUsers (AccountState state) {
    state.hiddenUserIds.clear();
    state.hiddenUserIds.addAll(state.mainUserIds);
    state.hiddenUserIds.addAll(state.manualUserIds);
  }

  private static void clearUnreadRequests (AccountState state) {
    state.generation++;
    state.scanQueue.clear();
    state.scanPumpScheduled = false;
    state.scheduledChecks.clear();
    for (ChatRequest request : state.chatRequests.values()) request.callbacks.clear();
    state.chatRequests.clear();
    state.localReadRequests.clear();
  }

  /** Authorization teardown only; a different login must never inherit the previous snapshot. */
  public static void invalidate (@NonNull Tdlib tdlib) {
    AccountState state;
    synchronized (STATES_LOCK) { state = ACCOUNT_STATES.get(tdlib); }
    if (state == null) return;
    Map<HiddenUsersCallback, Long> callbacks;
    final long generation;
    // Logging out invalidates results, but only Closed guarantees that the old native client
    // can no longer keep a query alive. Ordinary account switches never clear this gate.
    boolean clientClosed = tdlib.authorizationState() instanceof TdApi.AuthorizationStateClosed;
    synchronized (state) {
      callbacks = new HashMap<>(state.hiddenUsersCallbacks);
      invalidate(state);
      if (clientClosed) {
        state.activeApiAttemptId = 0;
        state.apiAttemptTimedOut = false;
        state.activeHiddenUsersPageAttemptId = 0;
        state.activeScanRequest = null;
      }
      generation = state.hiddenUsersGeneration;
    }
    for (Map.Entry<HiddenUsersCallback, Long> callback : callbacks.entrySet()) {
      deliverHiddenUsers(tdlib, state, callback.getKey(), callback.getValue(), generation, false);
    }
  }

  public static void onBlockListChanged (@NonNull Tdlib tdlib, long userId, boolean blocked) {
    if (userId == 0 || tdlib.isSelfUserId(userId)) return;
    AccountState state = accountState(tdlib);
    boolean changed;
    synchronized (state) {
      Boolean previous = null;
      if (!state.hiddenUsersReady || state.hiddenUsersLoading) {
        previous = state.blockOverrides.put(userId, blocked);
      }
      if (!state.hiddenUsersReady) {
        changed = previous == null || previous != blocked;
        state.hiddenUsersLoadFailed = false;
        state.hiddenUsersLoadRetryCount = 0;
      } else {
        changed = blocked ? state.mainUserIds.add(userId) : state.mainUserIds.remove(userId);
        rebuildHiddenUsers(state);
      }
      if (changed) {
        clearUnreadRequests(state);
        state.hiddenUsersRevision++;
      }
    }
    if (changed) notifyHiddenUsersChanged(tdlib, state);
  }

  private static AccountState accountState (Tdlib tdlib) {
    synchronized (STATES_LOCK) {
      AccountState state = ACCOUNT_STATES.get(tdlib);
      if (state == null) {
        state = new AccountState();
        ACCOUNT_STATES.put(tdlib, state);
      }
      return state;
    }
  }

  private static void invalidate (AccountState state) {
    synchronized (state) {
      state.generation++;
      state.hiddenUsersGeneration++;
      state.hiddenUsersReady = false;
      state.hiddenUsersLoading = false;
      state.hiddenUsersLoadFailed = false;
      state.hiddenUsersLoadRetryCount = 0;
      state.hiddenUsersDemandPending = false;
      state.hiddenUsersRefreshPending = false;
      state.nextHiddenUsersRefreshUptimeMillis = 0;
      state.hiddenUsersRevision++;
      state.manualUsersRevision++;
      state.mainUserIds.clear();
      state.hiddenUserIds.clear();
      state.manualUserIds.clear();
      state.blockOverrides.clear();
      state.scheduledChecks.clear();
      state.scanQueue.clear();
      state.scanPumpScheduled = false;
      state.hiddenUsersLoadScheduled = false;
      state.hiddenUsersLoadScheduleId++;
      for (ChatRequest request : state.chatRequests.values()) {
        request.callbacks.clear();
      }
      state.chatRequests.clear();
      state.localReadRequests.clear();
    }
  }

  private static boolean hasHiddenUsersDemand (AccountState state) {
    return !state.chatRequests.isEmpty() || !state.hiddenUsersCallbacks.isEmpty() ||
      state.hiddenUsersDemandPending || state.hiddenUsersRefreshPending || state.hiddenUsersLoadRetryCount > 0 && !state.hiddenUsersLoadFailed;
  }

  private static void scheduleHiddenUsersLoad (Tdlib tdlib, AccountState accountState) {
    long delayMillis;
    long scheduleId;
    synchronized (accountState) {
      if (accountState.activeApiAttemptId != 0 || accountState.activeScanRequest != null || accountState.hiddenUsersLoadFailed ||
          accountState.activeHiddenUsersPageAttemptId != 0 ||
          accountState.hiddenUsersReady && !accountState.hiddenUsersRefreshPending ||
          accountState.hiddenUsersLoading ||
          accountState.hiddenUsersLoadScheduled || !hasHiddenUsersDemand(accountState)) {
        return;
      }
      delayMillis = Math.max(0L,
        accountState.scanRetryAfterUptimeMillis - SystemClock.uptimeMillis());
      accountState.hiddenUsersLoadScheduled = true;
      scheduleId = ++accountState.hiddenUsersLoadScheduleId;
    }
    tdlib.ui().postDelayed(() -> {
      boolean startLoad = false;
      boolean reschedule = false;
      synchronized (accountState) {
        if (!accountState.hiddenUsersLoadScheduled ||
            accountState.hiddenUsersLoadScheduleId != scheduleId) {
          return;
        }
        accountState.hiddenUsersLoadScheduled = false;
        if (accountState.activeApiAttemptId == 0 && accountState.activeScanRequest == null && !accountState.hiddenUsersLoadFailed &&
            accountState.activeHiddenUsersPageAttemptId == 0 &&
            (!accountState.hiddenUsersReady || accountState.hiddenUsersRefreshPending) &&
            !accountState.hiddenUsersLoading &&
            hasHiddenUsersDemand(accountState)) {
          if (SystemClock.uptimeMillis() < accountState.scanRetryAfterUptimeMillis) {
            reschedule = true;
          } else {
            accountState.hiddenUsersLoading = true;
            startLoad = true;
          }
        }
      }
      if (startLoad) {
        loadHiddenUsers(tdlib, accountState);
      } else if (reschedule) {
        scheduleHiddenUsersLoad(tdlib, accountState);
      }
    }, delayMillis);
  }

  private static void resumeAccountWork (Tdlib tdlib, AccountState accountState) {
    scheduleHiddenUsersLoad(tdlib, accountState);
    scheduleScanPump(tdlib, accountState);
  }

  private static boolean isHiddenUsersCurrent (AccountState state, long generation) {
    synchronized (state) { return state.hiddenUsersGeneration == generation; }
  }

  private static void loadHiddenUsers (Tdlib tdlib, AccountState accountState) {
    long generation;
    synchronized (accountState) {
      generation = accountState.hiddenUsersGeneration;
      accountState.hiddenUsersDemandPending = false;
      accountState.hiddenUsersRefreshPending = false;
      accountState.nextHiddenUsersRefreshUptimeMillis = SystemClock.uptimeMillis() + HIDDEN_USERS_REFRESH_INTERVAL_MS;
      // Only events received after this request starts may override its server snapshot.
      accountState.blockOverrides.clear();
    }
    syncManualUsers(tdlib, accountState, false);
    loadBlockedUsersPage(tdlib, accountState, generation, 0, 0, null, new HashSet<>());
  }

  private static void loadBlockedUsersPage (Tdlib tdlib, AccountState accountState, long generation,
                                            int offset, int pageCount,
                                            HashSet<Long> manualUserIds,
                                            HashSet<Long> hiddenUserIds) {
    long cooldownDelayMillis;
    synchronized (accountState) {
      if (accountState.hiddenUsersGeneration != generation || !accountState.hiddenUsersLoading) return;
      cooldownDelayMillis = accountState.scanRetryAfterUptimeMillis -
        SystemClock.uptimeMillis();
    }
    if (cooldownDelayMillis > 0) {
      tdlib.ui().postDelayed(() -> loadBlockedUsersPage(tdlib, accountState, generation,
        offset, pageCount, manualUserIds, hiddenUserIds), cooldownDelayMillis);
      return;
    }
    long reservedPageAttemptId;
    long recheckedCooldownDelayMillis;
    synchronized (accountState) {
      if (accountState.hiddenUsersGeneration != generation || !accountState.hiddenUsersLoading ||
          accountState.activeApiAttemptId != 0 || accountState.activeHiddenUsersPageAttemptId != 0) {
        return;
      }
      recheckedCooldownDelayMillis = accountState.scanRetryAfterUptimeMillis -
        SystemClock.uptimeMillis();
      if (recheckedCooldownDelayMillis > 0) {
        reservedPageAttemptId = 0;
      } else {
        reservedPageAttemptId = ++accountState.nextApiAttemptId;
        accountState.activeApiAttemptId = reservedPageAttemptId;
        accountState.apiAttemptTimedOut = false;
        accountState.activeHiddenUsersPageAttemptId = reservedPageAttemptId;
      }
    }
    if (recheckedCooldownDelayMillis > 0) {
      tdlib.ui().postDelayed(() -> loadBlockedUsersPage(tdlib, accountState, generation,
        offset, pageCount, manualUserIds, hiddenUserIds), recheckedCooldownDelayMillis);
      return;
    }
    long pageAttemptId = reservedPageAttemptId;
    tdlib.ui().postDelayed(() -> onHiddenUsersPageTimeout(tdlib, accountState, generation,
      pageAttemptId), SCAN_REQUEST_TIMEOUT_MS);
    tdlib.send(new TdApi.GetBlockedMessageSenders(new TdApi.BlockListMain(), offset, PAGE_SIZE),
      (messageSenders, error) -> {
        boolean transientFailure = error != null ? isTransientScanError(error) :
          messageSenders == null;
        if (!finishHiddenUsersPageAttempt(tdlib, accountState, pageAttemptId,
            transientFailure, error)) return;
        if (!isHiddenUsersCurrent(accountState, generation)) {
          resumeAccountWork(tdlib, accountState);
          return;
        }
        if (error != null || messageSenders == null) {
          if (transientFailure) {
            completeHiddenUsersLoad(tdlib, accountState, generation, null, null, true);
          } else {
            completeHiddenUsersLoad(tdlib, accountState, generation, null, null, false);
          }
          return;
        }
        int receivedCount = messageSenders.senders != null ? messageSenders.senders.length : 0;
        if (messageSenders.senders != null) {
          for (TdApi.MessageSender sender : messageSenders.senders) {
            if (sender != null && sender.getConstructor() == TdApi.MessageSenderUser.CONSTRUCTOR) {
              long userId = ((TdApi.MessageSenderUser) sender).userId;
              if (userId != 0 && !tdlib.isSelfUserId(userId)) {
                hiddenUserIds.add(userId);
              }
            }
          }
        }
        int nextOffset = offset + receivedCount;
        if (receivedCount > 0 && messageSenders.totalCount > 0 && nextOffset >= messageSenders.totalCount) {
          completeHiddenUsersLoad(tdlib, accountState, generation, manualUserIds, hiddenUserIds,
            false);
        } else if (receivedCount > 0) {
          if (nextOffset <= offset || pageCount + 1 >= MAX_BLOCKED_USERS_PAGES) {
            completeHiddenUsersLoad(tdlib, accountState, generation, null, null, false);
          } else {
            tdlib.ui().postDelayed(() ->
              loadBlockedUsersPage(tdlib, accountState, generation, nextOffset, pageCount + 1,
                manualUserIds, hiddenUserIds), SCAN_PAGE_GAP_MS);
          }
        } else if (messageSenders.totalCount > offset) {
          // A known incomplete page is not an empty authoritative blacklist.
          completeHiddenUsersLoad(tdlib, accountState, generation, null, null, true);
        } else {
          completeHiddenUsersLoad(tdlib, accountState, generation, manualUserIds, hiddenUserIds,
            false);
        }
      });
  }

  private static boolean finishHiddenUsersPageAttempt (Tdlib tdlib, AccountState accountState,
                                                       long pageAttemptId, boolean transientFailure,
                                                       TdApi.Error error) {
    boolean current;
    synchronized (accountState) {
      if (accountState.activeApiAttemptId != pageAttemptId) return false;
      if (transientFailure) applyScanErrorCooldown(accountState, error);
      accountState.activeApiAttemptId = 0;
      accountState.apiAttemptTimedOut = false;
      current = accountState.activeHiddenUsersPageAttemptId == pageAttemptId;
      if (current) accountState.activeHiddenUsersPageAttemptId = 0;
    }
    if (!current) resumeAccountWork(tdlib, accountState);
    return current;
  }

  private static void failAccountWaiters (Tdlib tdlib, AccountState accountState) {
    Map<HiddenUsersCallback, Long> membershipCallbacks;
    List<Callback> callbacks = new ArrayList<>();
    final long generation;
    synchronized (accountState) {
      generation = accountState.hiddenUsersGeneration;
      membershipCallbacks = new HashMap<>(accountState.hiddenUsersCallbacks);
      for (ChatRequest request : accountState.chatRequests.values()) {
        callbacks.addAll(request.callbacks);
        request.callbacks.clear();
      }
    }
    for (Map.Entry<HiddenUsersCallback, Long> callback : membershipCallbacks.entrySet()) {
      deliverHiddenUsers(tdlib, accountState, callback.getKey(), callback.getValue(), generation, false);
    }
    for (Callback callback : callbacks) deliver(tdlib, callback, false, 0);
  }

  private static void onHiddenUsersPageTimeout (Tdlib tdlib, AccountState accountState,
                                               long generation, long pageAttemptId) {
    synchronized (accountState) {
      if (accountState.activeApiAttemptId != pageAttemptId ||
          accountState.activeHiddenUsersPageAttemptId != pageAttemptId) return;
      accountState.activeHiddenUsersPageAttemptId = 0;
      accountState.apiAttemptTimedOut = true;
      boolean current = accountState.hiddenUsersGeneration == generation && accountState.hiddenUsersLoading;
      // Keep timeout bookkeeping atomic with the native callback and Closed invalidation.
      // Waiter delivery and the next pump are posted to the UI queue, never run under this lock.
      applyScanErrorCooldown(accountState, null);
      failAccountWaiters(tdlib, accountState);
      if (current) {
        completeHiddenUsersLoad(tdlib, accountState, generation, null, null, true);
      } else {
        resumeAccountWork(tdlib, accountState);
      }
    }
  }

  private static void completeHiddenUsersLoad (Tdlib tdlib, AccountState accountState, long generation,
                                               Set<Long> manualUserIds, Set<Long> hiddenUserIds,
                                               boolean retryableFailure) {
    List<ChatRequest> pendingRequests = new ArrayList<>();
    List<Callback> failedCallbacks = new ArrayList<>();
    Map<HiddenUsersCallback, Long> membershipCallbacks = new HashMap<>();
    boolean retryLoad = false;
    boolean membershipChanged = false;
    synchronized (accountState) {
      if (accountState.hiddenUsersGeneration != generation || !accountState.hiddenUsersLoading) return;
      accountState.hiddenUsersLoading = false;
      if (hiddenUserIds == null) {
        if (!retryableFailure) {
          accountState.hiddenUsersLoadFailed = true;
        }
        if (retryableFailure) {
          accountState.scanRetryAfterUptimeMillis = Math.max(
            accountState.scanRetryAfterUptimeMillis,
            SystemClock.uptimeMillis() + SCAN_FAILURE_COOLDOWN_MS);
        }
        if (retryableFailure && accountState.hiddenUsersLoadRetryCount == 0) {
          accountState.hiddenUsersLoadRetryCount++;
          accountState.hiddenUsersRefreshPending = accountState.hiddenUsersReady;
          if (!accountState.hiddenUsersReady) {
            for (ChatRequest request : accountState.chatRequests.values()) {
              request.started = false;
              request.queued = false;
            }
            accountState.scanQueue.clear();
          }
          retryLoad = hasHiddenUsersDemand(accountState);
        } else {
          accountState.hiddenUsersLoadRetryCount = 0;
          accountState.scanRetryAfterUptimeMillis = Math.max(accountState.scanRetryAfterUptimeMillis,
            SystemClock.uptimeMillis() + SCAN_FAILURE_COOLDOWN_MS);
          accountState.hiddenUsersLoadFailed = true;
          accountState.hiddenUsersRefreshPending = false;
          if (!accountState.hiddenUsersReady) {
            membershipCallbacks.putAll(accountState.hiddenUsersCallbacks);
            for (ChatRequest request : accountState.chatRequests.values()) {
              failedCallbacks.addAll(request.callbacks);
              request.callbacks.clear();
            }
            accountState.scanQueue.clear();
            accountState.chatRequests.clear();
          }
        }
      } else {
        for (Map.Entry<Long, Boolean> override : accountState.blockOverrides.entrySet()) {
          if (override.getValue()) {
            hiddenUserIds.add(override.getKey());
          } else {
            hiddenUserIds.remove(override.getKey());
          }
        }
        membershipChanged = !accountState.hiddenUsersReady || !accountState.mainUserIds.equals(hiddenUserIds);
        if (accountState.hiddenUsersReady && membershipChanged) clearUnreadRequests(accountState);
        accountState.mainUserIds.clear();
        accountState.mainUserIds.addAll(hiddenUserIds);
        rebuildHiddenUsers(accountState);
        membershipCallbacks.putAll(accountState.hiddenUsersCallbacks);
        accountState.blockOverrides.clear();
        accountState.hiddenUsersReady = true;
        if (membershipChanged) accountState.hiddenUsersRevision++;
        accountState.hiddenUsersLoadFailed = false;
        accountState.hiddenUsersLoadRetryCount = 0;
        for (ChatRequest request : accountState.chatRequests.values()) {
          if (!request.valid && !request.started) {
            request.started = true;
            pendingRequests.add(request);
          }
        }
      }
    }
    if (membershipChanged) notifyHiddenUsersChanged(tdlib, accountState);
    for (Map.Entry<HiddenUsersCallback, Long> callback : membershipCallbacks.entrySet()) {
      deliverHiddenUsers(tdlib, accountState, callback.getKey(), callback.getValue(), generation,
        hiddenUserIds != null);
    }
    for (Callback callback : failedCallbacks) {
      deliver(tdlib, callback, false, 0);
    }
    for (ChatRequest request : pendingRequests) {
      enqueueScanRequest(tdlib, accountState, request);
    }
    if (retryLoad) {
      scheduleHiddenUsersLoad(tdlib, accountState);
    }
    scheduleScanPump(tdlib, accountState);
  }

  private static void executeRequest (Tdlib tdlib, AccountState accountState, ChatRequest request) {
    HashSet<Long> hiddenUserIds = null;
    synchronized (accountState) {
      if (isCurrentLocked(accountState, request) && accountState.hiddenUsersReady) {
        request.sentRequestCount = 0;
        hiddenUserIds = new HashSet<>(accountState.hiddenUserIds);
      }
    }
    if (hiddenUserIds == null) {
      completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
      return;
    }
    if (hiddenUserIds.isEmpty()) {
      completeRequest(tdlib, accountState, request, ScanOutcome.SUCCESS, 0);
      return;
    }

    long historyPageEstimate = (request.rawUnreadCount + PAGE_SIZE - 1L) / PAGE_SIZE;
    if (historyPageEstimate <= hiddenUserIds.size()) {
      loadHistoryPage(tdlib, accountState, request, hiddenUserIds,
        0, true, 0, 0);
    } else {
      long[] userIds = new long[hiddenUserIds.size()];
      int index = 0;
      for (long userId : hiddenUserIds) {
        userIds[index++] = userId;
      }
      searchNextUser(tdlib, accountState, request, hiddenUserIds, userIds, 0, 0);
    }
  }

  private static void searchNextUser (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                      Set<Long> hiddenUserIds, long[] userIds, int index,
                                      int hiddenUnreadCount) {
    if (!isCurrent(accountState, request)) {
      completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
      return;
    }
    if (index >= userIds.length) {
      completeRequest(tdlib, accountState, request, ScanOutcome.SUCCESS, hiddenUnreadCount);
      return;
    }
    searchUserPage(tdlib, accountState, request, userIds[index], request.topMessageId,
      0, (outcome, count) -> {
        if (outcome != ScanOutcome.SUCCESS) {
          completeRequest(tdlib, accountState, request, outcome, 0);
        } else {
          tdlib.ui().postDelayed(() ->
            searchNextUser(tdlib, accountState, request, hiddenUserIds, userIds,
              index + 1, hiddenUnreadCount + count), SCAN_PAGE_GAP_MS);
        }
      });
  }

  private static void searchUserPage (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                      long userId, long fromMessageId, int hiddenUnreadCount,
                                      ScanCallback callback) {
    if (!isCurrent(accountState, request)) {
      completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
      return;
    }
    if (deferScanForCooldown(tdlib, accountState, request, () ->
        searchUserPage(tdlib, accountState, request, userId, fromMessageId,
          hiddenUnreadCount, callback))) {
      return;
    }
    long attemptId = beginScanAttempt(tdlib, accountState, request);
    if (attemptId < 0) {
      boolean deferred = deferScanForCooldown(tdlib, accountState, request, () ->
        searchUserPage(tdlib, accountState, request, userId, fromMessageId,
          hiddenUnreadCount, callback));
      if (!deferred) {
        if (isCurrent(accountState, request)) {
          tdlib.ui().post(() -> searchUserPage(tdlib, accountState, request, userId,
            fromMessageId, hiddenUnreadCount, callback));
        } else {
          completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
        }
      }
      return;
    }
    if (attemptId == 0) {
      if (isCurrent(accountState, request)) {
        callback.onResult(ScanOutcome.INCOMPLETE, 0);
      } else {
        completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
      }
      return;
    }
    tdlib.send(new TdApi.SearchChatMessages(request.chatId, null, null,
        new TdApi.MessageSenderUser(userId), fromMessageId, 0, PAGE_SIZE, null),
      (foundMessages, error) -> {
        boolean transientFailure = error != null ? isTransientScanError(error) :
          foundMessages == null;
        if (!finishScanAttempt(tdlib, accountState, request, attemptId,
            transientFailure, error)) return;
        if (!isCurrent(accountState, request)) {
          completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
          return;
        }
        if (error != null || foundMessages == null) {
          callback.onResult(transientFailure ? ScanOutcome.TRANSIENT_FAILURE :
            ScanOutcome.INCOMPLETE, 0);
          return;
        }
        int newHiddenUnreadCount = hiddenUnreadCount;
        boolean reachedReadPosition = false;
        if (foundMessages.messages != null) {
          for (TdApi.Message message : foundMessages.messages) {
            if (message == null || message.id > request.topMessageId && request.topMessageId != 0) continue;
            if (message.id <= request.lastReadInboxMessageId) {
              reachedReadPosition = true;
              break;
            }
            if (!message.isOutgoing) {
              newHiddenUnreadCount++;
            }
          }
        }
        long nextFromMessageId = foundMessages.nextFromMessageId;
        if (!reachedReadPosition && nextFromMessageId != 0 &&
            (fromMessageId == 0 || nextFromMessageId < fromMessageId)) {
          int continuedHiddenUnreadCount = newHiddenUnreadCount;
          tdlib.ui().postDelayed(() ->
            searchUserPage(tdlib, accountState, request, userId, nextFromMessageId,
              continuedHiddenUnreadCount, callback), SCAN_PAGE_GAP_MS);
        } else if (!reachedReadPosition && nextFromMessageId != 0) {
          callback.onResult(ScanOutcome.INCOMPLETE, 0);
        } else {
          callback.onResult(ScanOutcome.SUCCESS, newHiddenUnreadCount);
        }
      });
  }

  private static void loadHistoryPage (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                       Set<Long> hiddenUserIds, long fromMessageId, boolean firstPage,
                                       int checkedUnreadCount, int hiddenUnreadCount) {
    if (!isCurrent(accountState, request)) {
      completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
      return;
    }
    if (deferScanForCooldown(tdlib, accountState, request, () ->
        loadHistoryPage(tdlib, accountState, request, hiddenUserIds, fromMessageId,
          firstPage, checkedUnreadCount, hiddenUnreadCount))) {
      return;
    }
    long attemptId = beginScanAttempt(tdlib, accountState, request);
    if (attemptId < 0) {
      boolean deferred = deferScanForCooldown(tdlib, accountState, request, () ->
        loadHistoryPage(tdlib, accountState, request, hiddenUserIds, fromMessageId,
          firstPage, checkedUnreadCount, hiddenUnreadCount));
      if (!deferred) {
        if (isCurrent(accountState, request)) {
          tdlib.ui().post(() -> loadHistoryPage(tdlib, accountState, request, hiddenUserIds,
            fromMessageId, firstPage, checkedUnreadCount, hiddenUnreadCount));
        } else {
          completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
        }
      }
      return;
    }
    if (attemptId == 0) {
      completeRequest(tdlib, accountState, request,
        isCurrent(accountState, request) ? ScanOutcome.INCOMPLETE : ScanOutcome.SUPERSEDED, 0);
      return;
    }
    tdlib.send(new TdApi.GetChatHistory(request.chatId, fromMessageId, 0, PAGE_SIZE, false),
      (messages, error) -> {
        boolean transientFailure = error != null ? isTransientScanError(error) :
          messages == null;
        if (!finishScanAttempt(tdlib, accountState, request, attemptId,
            transientFailure, error)) return;
        if (!isCurrent(accountState, request)) {
          completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
          return;
        }
        if (error != null || messages == null) {
          completeRequest(tdlib, accountState, request,
            transientFailure ? ScanOutcome.TRANSIENT_FAILURE : ScanOutcome.INCOMPLETE, 0);
          return;
        }
        int newCheckedUnreadCount = checkedUnreadCount;
        int newHiddenUnreadCount = hiddenUnreadCount;
        long nextFromMessageId = 0;
        boolean reachedReadPosition = false;
        if (messages.messages != null) {
          for (TdApi.Message message : messages.messages) {
            if (message == null || request.topMessageId != 0 && message.id > request.topMessageId ||
                !firstPage && fromMessageId != 0 && message.id >= fromMessageId) {
              continue;
            }
            if (message.id <= request.lastReadInboxMessageId) {
              reachedReadPosition = true;
              break;
            }
            if (nextFromMessageId == 0 || message.id < nextFromMessageId) {
              nextFromMessageId = message.id;
            }
            if (!message.isOutgoing) {
              newCheckedUnreadCount++;
              if (hiddenUserIds.contains(Td.getSenderUserId(message))) {
                newHiddenUnreadCount++;
              }
              if (newCheckedUnreadCount >= request.rawUnreadCount) break;
            }
          }
        }
        if (newCheckedUnreadCount >= request.rawUnreadCount) {
          completeRequest(tdlib, accountState, request, ScanOutcome.SUCCESS,
            newHiddenUnreadCount);
          return;
        }
        if (reachedReadPosition || nextFromMessageId == 0) {
          completeRequest(tdlib, accountState, request, ScanOutcome.INCOMPLETE, 0);
          return;
        }
        if (fromMessageId != 0 && nextFromMessageId >= fromMessageId) {
          nextFromMessageId = fromMessageId > 1 ? fromMessageId - 1 : 0;
        }
        if (nextFromMessageId == 0) {
          completeRequest(tdlib, accountState, request, ScanOutcome.INCOMPLETE, 0);
        } else {
          long continuedFromMessageId = nextFromMessageId;
          int continuedCheckedUnreadCount = newCheckedUnreadCount;
          int continuedHiddenUnreadCount = newHiddenUnreadCount;
          tdlib.ui().postDelayed(() ->
            loadHistoryPage(tdlib, accountState, request, hiddenUserIds, continuedFromMessageId,
              false, continuedCheckedUnreadCount, continuedHiddenUnreadCount),
            SCAN_PAGE_GAP_MS);
        }
      });
  }

  private static long beginScanAttempt (Tdlib tdlib, AccountState accountState,
                                        ChatRequest request) {
    long attemptId;
    synchronized (accountState) {
      if (!isCurrentLocked(accountState, request) ||
          accountState.activeScanRequest != request ||
          accountState.activeApiAttemptId != 0 || request.activeAttemptId != 0 ||
          request.sentRequestCount >= MAX_SCAN_REQUESTS) {
        return 0;
      }
      if (SystemClock.uptimeMillis() < accountState.scanRetryAfterUptimeMillis) {
        return -1;
      }
      request.sentRequestCount++;
      attemptId = ++accountState.nextApiAttemptId;
      accountState.activeApiAttemptId = attemptId;
      accountState.apiAttemptTimedOut = false;
      request.activeAttemptId = attemptId;
    }
    tdlib.ui().postDelayed(() -> onScanAttemptTimeout(tdlib, accountState, request, attemptId),
      SCAN_REQUEST_TIMEOUT_MS);
    return attemptId;
  }

  private static boolean deferScanForCooldown (Tdlib tdlib, AccountState accountState,
                                               ChatRequest request, Runnable continuation) {
    long delayMillis;
    synchronized (accountState) {
      if (!isCurrentLocked(accountState, request) ||
          accountState.activeScanRequest != request) {
        return false;
      }
      delayMillis = accountState.scanRetryAfterUptimeMillis - SystemClock.uptimeMillis();
      if (delayMillis <= 0) return false;
    }
    tdlib.ui().postDelayed(continuation, delayMillis);
    return true;
  }

  private static boolean finishScanAttempt (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                            long attemptId, boolean transientFailure, TdApi.Error error) {
    boolean current;
    synchronized (accountState) {
      if (accountState.activeApiAttemptId != attemptId) return false;
      if (transientFailure) applyScanErrorCooldown(accountState, error);
      accountState.activeApiAttemptId = 0;
      accountState.apiAttemptTimedOut = false;
      current = request.activeAttemptId == attemptId;
      if (current) request.activeAttemptId = 0;
    }
    if (!current) resumeAccountWork(tdlib, accountState);
    return current;
  }

  private static void onScanAttemptTimeout (Tdlib tdlib, AccountState accountState,
                                            ChatRequest request, long attemptId) {
    synchronized (accountState) {
      if (accountState.activeApiAttemptId != attemptId || request.activeAttemptId != attemptId) return;
      request.activeAttemptId = 0;
      accountState.apiAttemptTimedOut = true;
      boolean current = isCurrentLocked(accountState, request) &&
        accountState.activeScanRequest == request;
      applyScanErrorCooldown(accountState, null);
      failAccountWaiters(tdlib, accountState);
      if (current) {
        completeRequest(tdlib, accountState, request, ScanOutcome.TRANSIENT_FAILURE, 0);
      } else {
        completeRequest(tdlib, accountState, request, ScanOutcome.SUPERSEDED, 0);
      }
    }
  }

  private static void applyScanErrorCooldown (AccountState accountState, TdApi.Error error) {
    long cooldownMillis = SCAN_FAILURE_COOLDOWN_MS;
    if (error != null && error.code == 429 && error.message != null) {
      Matcher matcher = RETRY_AFTER_PATTERN.matcher(error.message);
      if (matcher.find()) {
        try {
          long parsedSeconds = Math.min(604_800L, Long.parseLong(matcher.group(1)));
          cooldownMillis = Math.max(cooldownMillis, parsedSeconds * 1000L);
        } catch (NumberFormatException ignored) {
          // Keep the conservative default cooldown when TDLib returns an unexpected value.
        }
      }
    }
    synchronized (accountState) {
      accountState.scanRetryAfterUptimeMillis = Math.max(
        accountState.scanRetryAfterUptimeMillis,
        SystemClock.uptimeMillis() + cooldownMillis);
    }
  }

  private static boolean isTransientScanError (TdApi.Error error) {
    return error == null || error.code <= 0 || error.code == 429 || error.code >= 500;
  }

  private static void completeRequest (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                       ScanOutcome outcome, int hiddenUnreadCount) {
    List<Callback> callbacks = new ArrayList<>();
    boolean retryRequest = false;
    boolean resumeScanPump = false;
    long retryDelayMillis = 0;
    int clampedHiddenUnreadCount = Math.max(0, Math.min(hiddenUnreadCount, request.rawUnreadCount));
    synchronized (accountState) {
      long now = SystemClock.uptimeMillis();
      if (isCurrentLocked(accountState, request)) {
        if (outcome == ScanOutcome.SUCCESS) {
          callbacks.addAll(request.callbacks);
          request.callbacks.clear();
          request.hiddenUnreadCount = clampedHiddenUnreadCount;
          request.valid = true;
          request.failed = false;
          request.failureRetryUptimeMillis = 0;
        } else if (outcome == ScanOutcome.TRANSIENT_FAILURE) {
          accountState.scanRetryAfterUptimeMillis = Math.max(
            accountState.scanRetryAfterUptimeMillis, now + SCAN_FAILURE_COOLDOWN_MS);
          if (request.transientRetryCount == 0) {
            request.transientRetryCount++;
            retryRequest = true;
          } else {
            callbacks.addAll(request.callbacks);
            request.callbacks.clear();
            request.started = false;
            request.failed = true;
            request.failureRetryUptimeMillis = Math.max(
              accountState.scanRetryAfterUptimeMillis, now + SCAN_FAILURE_COOLDOWN_MS);
          }
        } else if (outcome == ScanOutcome.INCOMPLETE) {
          if (request.highPriority && !request.incompleteRetryUsed) {
            request.incompleteRetryUsed = true;
            retryRequest = true;
            retryDelayMillis = SCAN_INCOMPLETE_RETRY_DELAY_MS;
          } else {
            callbacks.addAll(request.callbacks);
            request.callbacks.clear();
            request.started = false;
            request.failed = true;
            request.failureRetryUptimeMillis = now + SCAN_FAILURE_COOLDOWN_MS;
          }
        }
      }
      if (accountState.activeScanRequest == request) {
        accountState.activeScanRequest = null;
        request.activeAttemptId = 0;
        accountState.nextScanAllowedUptimeMillis = Math.max(
          accountState.nextScanAllowedUptimeMillis,
          outcome == ScanOutcome.TRANSIENT_FAILURE ?
            accountState.scanRetryAfterUptimeMillis : now + SCAN_REQUEST_GAP_MS);
        resumeScanPump = true;
      }
    }
    for (Callback callback : callbacks) {
      deliver(tdlib, callback, outcome == ScanOutcome.SUCCESS, clampedHiddenUnreadCount);
    }
    if (retryRequest) {
      long scheduledRetryDelayMillis = retryDelayMillis;
      if (scheduledRetryDelayMillis > 0) {
        tdlib.ui().postDelayed(() -> enqueueScanRequest(tdlib, accountState, request),
          scheduledRetryDelayMillis);
      } else {
        enqueueScanRequest(tdlib, accountState, request);
      }
    }
    if (resumeScanPump) {
      resumeAccountWork(tdlib, accountState);
    }
  }

  private static boolean isCurrent (AccountState accountState, long generation) {
    synchronized (accountState) {
      return accountState.generation == generation;
    }
  }

  private static boolean isLocalReadRequestCurrent (Tdlib tdlib, AccountState accountState,
                                                    long chatId, LocalReadRequest request) {
    synchronized (accountState) {
      if (accountState.generation != request.generation ||
          accountState.localReadRequests.get(chatId) != request) {
        return false;
      }
    }
    if (!tdlib.isChatReadSnapshotCurrent(chatId, request.rawUnreadCount,
          request.lastReadInboxMessageId, request.topMessageId, request.scope)) {
      return false;
    }
    return request.privateUserId == 0 ||
      MoexMessageFilter.isShadowBannedUser(tdlib, request.privateUserId);
  }

  private static boolean isCurrent (AccountState accountState, ChatRequest request) {
    synchronized (accountState) {
      return isCurrentLocked(accountState, request);
    }
  }

  private static boolean isCurrentLocked (AccountState accountState, ChatRequest request) {
    return accountState.generation == request.generation &&
      accountState.chatRequests.get(request.chatId) == request;
  }

  private static void deliver (Tdlib tdlib, Callback callback, boolean success, int hiddenUnreadCount) {
    tdlib.ui().post(() -> callback.onResult(success, hiddenUnreadCount));
  }

  private static final class AccountState {
    private long generation;
    private long hiddenUsersGeneration;
    private long hiddenUsersRevision;
    private long manualUsersRevision;
    private final HashSet<Long> mainUserIds = new HashSet<>();
    private long nextHiddenUsersCallbackId;
    private final HashMap<HiddenUsersCallback, Long> hiddenUsersCallbacks = new HashMap<>();
    private final HashSet<HiddenUsersListener> hiddenUsersListeners = new HashSet<>();
    private boolean hiddenUsersReady;
    private boolean hiddenUsersLoading;
    private boolean hiddenUsersLoadFailed;
    private boolean hiddenUsersDemandPending;
    private boolean hiddenUsersRefreshPending;
    private long nextHiddenUsersRefreshUptimeMillis;
    private final HashSet<Long> hiddenUserIds = new HashSet<>();
    private final HashSet<Long> manualUserIds = new HashSet<>();
    private final HashMap<Long, Boolean> blockOverrides = new HashMap<>();
    private final HashMap<Long, Long> scheduledChecks = new HashMap<>();
    private final ArrayDeque<ChatRequest> scanQueue = new ArrayDeque<>();
    private final HashMap<Long, ChatRequest> chatRequests = new HashMap<>();
    private final HashMap<Long, LocalReadRequest> localReadRequests = new HashMap<>();
    private ChatRequest activeScanRequest;
    private long nextScheduledCheckId;
    // API completion owns this gate. The 30-second UI deadline must never release it.
    // IDs remain monotonic across Closed so an old client callback cannot unlock a new request.
    private long nextApiAttemptId;
    private long activeApiAttemptId;
    private boolean apiAttemptTimedOut;
    private long hiddenUsersLoadScheduleId;
    private long activeHiddenUsersPageAttemptId;
    private int hiddenUsersLoadRetryCount;
    private boolean scanPumpScheduled;
    private boolean hiddenUsersLoadScheduled;
    private long nextScanAllowedUptimeMillis;
    private long scanRetryAfterUptimeMillis;
  }

  private static final class LocalReadRequest {
    private final long generation;
    private final int rawUnreadCount;
    private final long lastReadInboxMessageId;
    private final long topMessageId;
    private final long privateUserId;
    private final @Tdlib.GhostReadScope int scope;

    private LocalReadRequest (long generation, int rawUnreadCount, long lastReadInboxMessageId,
                              long topMessageId, long privateUserId,
                              @Tdlib.GhostReadScope int scope) {
      this.generation = generation;
      this.rawUnreadCount = rawUnreadCount;
      this.lastReadInboxMessageId = lastReadInboxMessageId;
      this.topMessageId = topMessageId;
      this.privateUserId = privateUserId;
      this.scope = scope;
    }

    private boolean matches (LocalReadRequest other) {
      return other != null && generation == other.generation &&
        rawUnreadCount == other.rawUnreadCount &&
        lastReadInboxMessageId == other.lastReadInboxMessageId &&
        topMessageId == other.topMessageId && privateUserId == other.privateUserId &&
        scope == other.scope;
    }
  }

  private static final class ChatRequest {
    private final long generation;
    private final long chatId;
    private final int rawUnreadCount;
    private final long lastReadInboxMessageId;
    private final long topMessageId;
    private final List<Callback> callbacks = new ArrayList<>();
    private boolean started;
    private boolean queued;
    private boolean valid;
    private boolean failed;
    private boolean highPriority;
    private int hiddenUnreadCount;
    private int sentRequestCount;
    private int transientRetryCount;
    private boolean incompleteRetryUsed;
    private long activeAttemptId;
    private long failureRetryUptimeMillis;

    private ChatRequest (long generation, long chatId, int rawUnreadCount,
                         long lastReadInboxMessageId, long topMessageId) {
      this.generation = generation;
      this.chatId = chatId;
      this.rawUnreadCount = rawUnreadCount;
      this.lastReadInboxMessageId = lastReadInboxMessageId;
      this.topMessageId = topMessageId;
    }

    private boolean matches (int rawUnreadCount, long lastReadInboxMessageId, long topMessageId) {
      return this.rawUnreadCount == rawUnreadCount &&
        this.lastReadInboxMessageId == lastReadInboxMessageId &&
        this.topMessageId == topMessageId;
    }
  }
}
