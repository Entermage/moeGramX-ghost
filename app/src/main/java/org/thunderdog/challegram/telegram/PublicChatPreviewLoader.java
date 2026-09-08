package org.thunderdog.challegram.telegram;

import android.os.Looper;
import android.widget.Toast;

import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.navigation.NavigationController;
import org.thunderdog.challegram.navigation.ViewController;
import org.thunderdog.challegram.tool.UI;

import java.util.WeakHashMap;

import me.vkryl.core.StringUtils;
import me.vkryl.core.lambda.RunnableBool;
import moe.kirao.mgx.MoexMessageFilter;
import tgx.td.MessageId;

/** Resolves preview pagination to an existing, visible message without marking history read. */
final class PublicChatPreviewLoader {
  private static final long PAGE_GAP_MS = 200L;
  // Accessed only on the UI thread. A new preview link supersedes the previous lookup.
  private static final WeakHashMap<NavigationController, PublicChatPreviewLoader> active = new WeakHashMap<>();

  private final TdlibDelegate context;
  private final Tdlib tdlib;
  private final String username;
  private final String query;
  private final TdlibUi.UrlOpenParameters openParameters;
  private final RunnableBool after;
  private final NavigationController navigation;
  private final ViewController<?> origin;
  private final PublicChatPreviewPagination pagination;
  private final ViewController.FocusStateListener focusListener;
  private TdApi.Chat chat;
  private boolean finished;

  static void open (TdlibDelegate context, String username, @Nullable String query, int before, int after,
                    @Nullable TdlibUi.UrlOpenParameters openParameters, @Nullable RunnableBool callback) {
    runOnUi(context.tdlib(), () -> new PublicChatPreviewLoader(context, username, query, before, after, openParameters, callback).start());
  }

  static void cancelPending (TdlibDelegate context) {
    runOnUi(context.tdlib(), () -> {
      PublicChatPreviewLoader previous = active.get(context.context().navigation());
      if (previous != null) previous.finish();
    });
  }

  private static void runOnUi (Tdlib tdlib, Runnable action) {
    if (Looper.myLooper() == tdlib.ui().getLooper()) {
      action.run();
    } else {
      tdlib.ui().post(action);
    }
  }

  private PublicChatPreviewLoader (TdlibDelegate context, String username, @Nullable String query, int before, int after,
                                   @Nullable TdlibUi.UrlOpenParameters openParameters, @Nullable RunnableBool callback) {
    this.context = context;
    this.tdlib = context.tdlib();
    this.username = username;
    this.query = query;
    this.openParameters = openParameters;
    this.after = callback;
    this.navigation = context.context().navigation();
    this.origin = navigation.getCurrentStackItem();
    this.pagination = new PublicChatPreviewPagination(
      before != 0 ? MessageId.fromServerMessageId(before) : 0,
      after != 0 ? MessageId.fromServerMessageId(after) : 0,
      !StringUtils.isEmpty(query)
    );
    this.focusListener = (controller, focused) -> {
      if (!focused) finish();
    };
  }

  private void start () {
    PublicChatPreviewLoader previous = active.put(navigation, this);
    if (previous != null) previous.finish();
    if (!isCurrent()) return;
    origin.addFocusListener(focusListener);
    tdlib.send(new TdApi.SearchPublicChat(username), (resolvedChat, error) -> tdlib.ui().post(() -> {
      if (!isCurrent()) return;
      if (error != null) {
        fail(error);
      } else if (resolvedChat == null) {
        noMessage();
      } else {
        chat = resolvedChat;
        requestPage();
      }
    }));
  }

  private boolean isCurrent () {
    if (finished) return false;
    if (navigation.isDestroyed() || origin == null || origin.isDestroyed() ||
        navigation.getCurrentStackItem() != origin || active.get(navigation) != this) {
      finish();
      return false;
    }
    return true;
  }

  private void requestPage () {
    if (!isCurrent()) return;
    if (!pagination.beginRequest()) {
      noMessage();
      return;
    }
    if (pagination.searching) {
      tdlib.send(new TdApi.SearchChatMessages(chat.id, null, query, null, pagination.fromMessageId,
          pagination.offset(), pagination.limit(), null),
        (result, error) -> tdlib.ui().post(() -> onPage(
          result != null ? result.messages : null, result != null ? result.nextFromMessageId : 0, error)));
    } else {
      tdlib.send(new TdApi.GetChatHistory(chat.id, pagination.fromMessageId, pagination.offset(), pagination.limit(), false),
        (result, error) -> tdlib.ui().post(() -> onPage(result != null ? result.messages : null, 0, error)));
    }
  }

  private void onPage (@Nullable TdApi.Message[] messages, long nextSearchFromMessageId, @Nullable TdApi.Error error) {
    if (!isCurrent()) return;
    // In particular, never retry a rate limit response or continue scanning after it.
    if (error != null) {
      fail(error);
      return;
    }
    TdApi.Message[] rawMessages = messages != null ? messages : new TdApi.Message[0];
    long[] rawMessageIds = new long[rawMessages.length];
    boolean[] visible = new boolean[rawMessages.length];
    boolean isChannel = tdlib.isChannelChat(chat);
    for (int i = 0; i < rawMessages.length; i++) {
      TdApi.Message message = rawMessages[i];
      if (message == null || message.chatId != chat.id) continue;
      rawMessageIds[i] = message.id;
      visible[i] = !MoexMessageFilter.shouldHideInChat(tdlib, message, isChannel);
    }
    int candidate = pagination.findVisibleMessage(rawMessageIds, visible);
    if (candidate != -1) {
      TdApi.Message message = rawMessages[candidate];
      TdlibUi.ChatOpenParameters parameters = new TdlibUi.ChatOpenParameters()
        .urlOpenParameters(openParameters).keepStack().ensureHighlightAvailable();
      if (pagination.searching) {
        parameters.foundMessage(query, message);
      } else {
        parameters.highlightMessage(message);
      }
      finish();
      tdlib.ui().openChat(context, chat, parameters);
    } else if (pagination.advance(rawMessageIds, nextSearchFromMessageId)) {
      tdlib.ui().postDelayed(this::requestPage, PAGE_GAP_MS);
    } else {
      noMessage();
    }
  }

  private void fail (TdApi.Error error) {
    finish();
    UI.showError(error);
  }

  private void noMessage () {
    finish();
    UI.showToast(R.string.MessageNotFound, Toast.LENGTH_SHORT);
  }

  private void finish () {
    if (finished) return;
    finished = true;
    if (origin != null) origin.removeFocusListener(focusListener);
    if (active.get(navigation) == this) active.remove(navigation);
    if (after != null) after.runWithBool(true);
  }
}
