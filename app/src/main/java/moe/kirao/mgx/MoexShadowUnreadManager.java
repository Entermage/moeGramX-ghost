package moe.kirao.mgx;

import androidx.annotation.NonNull;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;

import tgx.td.Td;

/**
 * Derives per-chat unread counts hidden by Shadow Ban. Exact results and in-flight requests are
 * shared by every folder row; an all-hidden unread range may also be read locally through Ghost
 * Mode, while mixed unread ranges keep TDLib's continuous read position unchanged.
 */
public final class MoexShadowUnreadManager {
  private static final int PAGE_SIZE = 100;
  private static final long LOCAL_READ_DEDUP_DELAY_MS = 1500L;
  private static final Object STATES_LOCK = new Object();
  private static final Map<Tdlib, AccountState> ACCOUNT_STATES = new WeakHashMap<>();

  public interface Callback {
    void onResult (boolean success, int hiddenUnreadCount);
  }

  private MoexShadowUnreadManager () { }

  /**
   * Resolves the Shadow Ban unread count for a regular chat. When every unread inbox message is
   * hidden, the shared result also advances TDLib's local read position while Ghost Read prevents
   * the corresponding server read receipt.
   */
  public static void requestForChat (@NonNull Tdlib tdlib, @NonNull TdApi.Chat chat,
                                     @NonNull Callback callback) {
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

    request(tdlib, chat.id, rawUnreadCount, lastReadInboxMessageId,
      historyTopMessageId, resultCallback);
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
        localReadScope == Tdlib.GhostReadScope.NONE ||
        !tdlib.isGhostReadEnabled(localReadScope)) {
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

    readMessagesLocally(tdlib, accountState, chatId, request, historyTopMessageId);
  }

  private static void readMessagesLocally (Tdlib tdlib, AccountState accountState, long chatId,
                                           LocalReadRequest request, long targetMessageId) {
    tdlib.readMessagesLocally(request.scope, chatId, new long[] {targetMessageId},
      () -> isLocalReadRequestCurrent(tdlib, accountState, chatId, request),
      result -> {
        if (result.getConstructor() == TdApi.Error.CONSTRUCTOR) {
          finishLocalReadRequest(accountState, chatId, request);
        } else {
          tdlib.ui().postDelayed(
            () -> finishLocalReadRequest(accountState, chatId, request),
            LOCAL_READ_DEDUP_DELAY_MS);
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
    if (chatId == 0 || rawUnreadCount <= 0) {
      deliver(tdlib, callback, true, 0);
      return;
    }

    AccountState accountState = accountState(tdlib);
    ChatRequest chatRequest;
    Integer cachedResult = null;
    boolean loadHiddenUsers = false;
    boolean startRequest = false;
    synchronized (accountState) {
      chatRequest = accountState.chatRequests.get(chatId);
      if (chatRequest == null || !chatRequest.matches(rawUnreadCount, lastReadInboxMessageId, topMessageId)) {
        if (chatRequest != null) {
          chatRequest.callbacks.clear();
        }
        chatRequest = new ChatRequest(accountState.generation, chatId, rawUnreadCount,
          lastReadInboxMessageId, topMessageId);
        accountState.chatRequests.put(chatId, chatRequest);
      }
      if (chatRequest.valid) {
        cachedResult = chatRequest.hiddenUnreadCount;
      } else {
        chatRequest.callbacks.add(callback);
        if (!chatRequest.started) {
          if (accountState.hiddenUsersReady) {
            chatRequest.started = true;
            startRequest = true;
          } else if (!accountState.hiddenUsersLoading) {
            accountState.hiddenUsersLoading = true;
            loadHiddenUsers = true;
          }
        }
      }
    }

    if (cachedResult != null) {
      deliver(tdlib, callback, true, cachedResult);
    }
    if (loadHiddenUsers) {
      loadHiddenUsers(tdlib, accountState);
    }
    if (startRequest) {
      startRequest(tdlib, accountState, chatRequest);
    }
  }

  public static void invalidateAccount (int accountId) {
    List<AccountState> states = new ArrayList<>();
    synchronized (STATES_LOCK) {
      for (Map.Entry<Tdlib, AccountState> entry : ACCOUNT_STATES.entrySet()) {
        Tdlib tdlib = entry.getKey();
        if (tdlib != null && tdlib.id() == accountId) {
          states.add(entry.getValue());
        }
      }
    }
    for (AccountState state : states) {
      invalidate(state);
    }
  }

  public static void invalidate (@NonNull Tdlib tdlib) {
    AccountState state;
    synchronized (STATES_LOCK) {
      state = ACCOUNT_STATES.get(tdlib);
    }
    if (state != null) {
      invalidate(state);
    }
  }

  public static void onBlockListChanged (@NonNull Tdlib tdlib, long userId, boolean blocked) {
    if (userId == 0 || tdlib.isSelfUserId(userId)) return;
    AccountState state;
    synchronized (STATES_LOCK) {
      state = ACCOUNT_STATES.get(tdlib);
    }
    if (state == null) return;

    synchronized (state) {
      if (!state.hiddenUsersReady) {
        state.blockOverrides.put(userId, blocked);
        state.localReadRequests.clear();
        return;
      }
      boolean changed;
      if (blocked) {
        changed = state.hiddenUserIds.add(userId);
      } else if (!state.manualUserIds.contains(userId)) {
        changed = state.hiddenUserIds.remove(userId);
      } else {
        changed = false;
      }
      if (changed) {
        state.generation++;
        for (ChatRequest request : state.chatRequests.values()) {
          request.callbacks.clear();
        }
        state.chatRequests.clear();
        state.localReadRequests.clear();
      }
    }
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
      state.hiddenUsersReady = false;
      state.hiddenUsersLoading = false;
      state.hiddenUserIds.clear();
      state.manualUserIds.clear();
      state.blockOverrides.clear();
      for (ChatRequest request : state.chatRequests.values()) {
        request.callbacks.clear();
      }
      state.chatRequests.clear();
      state.localReadRequests.clear();
    }
  }

  private static void loadHiddenUsers (Tdlib tdlib, AccountState accountState) {
    long generation;
    synchronized (accountState) {
      generation = accountState.generation;
    }
    HashSet<Long> manualUserIds = new HashSet<>();
    for (long userId : MoexConfig.instance().getShadowBannedUsers(tdlib.id())) {
      if (userId != 0 && !tdlib.isSelfUserId(userId)) {
        manualUserIds.add(userId);
      }
    }
    loadBlockedUsersPage(tdlib, accountState, generation, 0, manualUserIds,
      new HashSet<>(manualUserIds));
  }

  private static void loadBlockedUsersPage (Tdlib tdlib, AccountState accountState, long generation,
                                            int offset, HashSet<Long> manualUserIds,
                                            HashSet<Long> hiddenUserIds) {
    tdlib.send(new TdApi.GetBlockedMessageSenders(new TdApi.BlockListMain(), offset, PAGE_SIZE),
      (messageSenders, error) -> {
        if (!isCurrent(accountState, generation) || error != null || messageSenders == null) {
          if (error != null || messageSenders == null) {
            completeHiddenUsersLoad(tdlib, accountState, generation, null, null);
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
        if (receivedCount > 0 && nextOffset > offset) {
          loadBlockedUsersPage(tdlib, accountState, generation, nextOffset,
            manualUserIds, hiddenUserIds);
        } else {
          completeHiddenUsersLoad(tdlib, accountState, generation, manualUserIds, hiddenUserIds);
        }
      });
  }

  private static void completeHiddenUsersLoad (Tdlib tdlib, AccountState accountState, long generation,
                                               Set<Long> manualUserIds, Set<Long> hiddenUserIds) {
    List<ChatRequest> pendingRequests = new ArrayList<>();
    List<Callback> failedCallbacks = new ArrayList<>();
    synchronized (accountState) {
      if (accountState.generation != generation || !accountState.hiddenUsersLoading) return;
      accountState.hiddenUsersLoading = false;
      if (hiddenUserIds == null) {
        for (ChatRequest request : accountState.chatRequests.values()) {
          failedCallbacks.addAll(request.callbacks);
          request.callbacks.clear();
        }
        accountState.chatRequests.clear();
      } else {
        for (Map.Entry<Long, Boolean> override : accountState.blockOverrides.entrySet()) {
          if (override.getValue()) {
            hiddenUserIds.add(override.getKey());
          } else if (!manualUserIds.contains(override.getKey())) {
            hiddenUserIds.remove(override.getKey());
          }
        }
        accountState.hiddenUserIds.clear();
        accountState.hiddenUserIds.addAll(hiddenUserIds);
        accountState.manualUserIds.clear();
        accountState.manualUserIds.addAll(manualUserIds);
        accountState.blockOverrides.clear();
        accountState.hiddenUsersReady = true;
        for (ChatRequest request : accountState.chatRequests.values()) {
          if (!request.valid && !request.started) {
            request.started = true;
            pendingRequests.add(request);
          }
        }
      }
    }
    for (Callback callback : failedCallbacks) {
      deliver(tdlib, callback, false, 0);
    }
    for (ChatRequest request : pendingRequests) {
      startRequest(tdlib, accountState, request);
    }
  }

  private static void startRequest (Tdlib tdlib, AccountState accountState, ChatRequest request) {
    HashSet<Long> hiddenUserIds;
    synchronized (accountState) {
      if (!isCurrentLocked(accountState, request) || !accountState.hiddenUsersReady) return;
      hiddenUserIds = new HashSet<>(accountState.hiddenUserIds);
    }
    if (hiddenUserIds.isEmpty()) {
      completeRequest(tdlib, accountState, request, true, 0);
      return;
    }

    long historyPageEstimate = (request.rawUnreadCount + PAGE_SIZE - 1L) / PAGE_SIZE;
    if (historyPageEstimate <= hiddenUserIds.size()) {
      loadHistoryPage(tdlib, accountState, request, hiddenUserIds,
        request.topMessageId, true, 0, 0);
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
    if (!isCurrent(accountState, request)) return;
    if (index >= userIds.length) {
      completeRequest(tdlib, accountState, request, true, hiddenUnreadCount);
      return;
    }
    searchUserPage(tdlib, accountState, request, userIds[index], request.topMessageId,
      0, (success, count) -> {
        if (!success) {
          loadHistoryPage(tdlib, accountState, request, hiddenUserIds,
            request.topMessageId, true, 0, 0);
        } else {
          searchNextUser(tdlib, accountState, request, hiddenUserIds, userIds,
            index + 1, hiddenUnreadCount + count);
        }
      });
  }

  private static void searchUserPage (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                      long userId, long fromMessageId, int hiddenUnreadCount,
                                      Callback callback) {
    if (!isCurrent(accountState, request)) return;
    tdlib.send(new TdApi.SearchChatMessages(request.chatId, null, null,
        new TdApi.MessageSenderUser(userId), fromMessageId, 0, PAGE_SIZE, null),
      (foundMessages, error) -> {
        if (!isCurrent(accountState, request)) return;
        if (error != null || foundMessages == null) {
          callback.onResult(false, 0);
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
          searchUserPage(tdlib, accountState, request, userId, nextFromMessageId,
            newHiddenUnreadCount, callback);
        } else if (!reachedReadPosition && nextFromMessageId != 0) {
          callback.onResult(false, 0);
        } else {
          callback.onResult(true, newHiddenUnreadCount);
        }
      });
  }

  private static void loadHistoryPage (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                       Set<Long> hiddenUserIds, long fromMessageId, boolean firstPage,
                                       int checkedUnreadCount, int hiddenUnreadCount) {
    if (!isCurrent(accountState, request)) return;
    tdlib.send(new TdApi.GetChatHistory(request.chatId, fromMessageId, 0, PAGE_SIZE, false),
      (messages, error) -> {
        if (!isCurrent(accountState, request)) return;
        if (error != null || messages == null) {
          completeRequest(tdlib, accountState, request, false, 0);
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
          completeRequest(tdlib, accountState, request, true, newHiddenUnreadCount);
          return;
        }
        if (reachedReadPosition || nextFromMessageId == 0) {
          completeRequest(tdlib, accountState, request, false, 0);
          return;
        }
        if (fromMessageId != 0 && nextFromMessageId >= fromMessageId) {
          nextFromMessageId = fromMessageId > 1 ? fromMessageId - 1 : 0;
        }
        if (nextFromMessageId == 0) {
          completeRequest(tdlib, accountState, request, false, 0);
        } else {
          loadHistoryPage(tdlib, accountState, request, hiddenUserIds, nextFromMessageId,
            false, newCheckedUnreadCount, newHiddenUnreadCount);
        }
      });
  }

  private static void completeRequest (Tdlib tdlib, AccountState accountState, ChatRequest request,
                                       boolean success, int hiddenUnreadCount) {
    List<Callback> callbacks;
    int clampedHiddenUnreadCount = Math.max(0, Math.min(hiddenUnreadCount, request.rawUnreadCount));
    synchronized (accountState) {
      if (!isCurrentLocked(accountState, request)) return;
      callbacks = new ArrayList<>(request.callbacks);
      request.callbacks.clear();
      if (success) {
        request.hiddenUnreadCount = clampedHiddenUnreadCount;
        request.valid = true;
      } else {
        accountState.chatRequests.remove(request.chatId);
      }
    }
    for (Callback callback : callbacks) {
      deliver(tdlib, callback, success, clampedHiddenUnreadCount);
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
          request.lastReadInboxMessageId, request.topMessageId, request.scope) ||
        !tdlib.isGhostReadEnabled(request.scope)) {
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
    private boolean hiddenUsersReady;
    private boolean hiddenUsersLoading;
    private final HashSet<Long> hiddenUserIds = new HashSet<>();
    private final HashSet<Long> manualUserIds = new HashSet<>();
    private final HashMap<Long, Boolean> blockOverrides = new HashMap<>();
    private final HashMap<Long, ChatRequest> chatRequests = new HashMap<>();
    private final HashMap<Long, LocalReadRequest> localReadRequests = new HashMap<>();
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
    private boolean valid;
    private int hiddenUnreadCount;

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
