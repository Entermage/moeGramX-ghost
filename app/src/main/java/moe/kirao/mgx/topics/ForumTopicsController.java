/*
 * This file is a part of XGram, a fork of Telegram X
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
package moe.kirao.mgx.topics;

import android.content.Context;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.ItemTouchHelper;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.component.chat.ChatHeaderView;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.navigation.MoreDelegate;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.telegram.TdlibUi;
import org.thunderdog.challegram.theme.Theme;
import org.thunderdog.challegram.theme.ColorId;
import org.thunderdog.challegram.tool.Screen;
import org.thunderdog.challegram.ui.RecyclerViewController;
import org.thunderdog.challegram.util.StringList;
import org.thunderdog.challegram.v.CustomRecyclerView;
import org.thunderdog.challegram.widget.ProgressComponentView;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import me.vkryl.core.collection.IntList;

/**
 * Topic list of a forum supergroup, shown when the forum is opened in "view as topics" mode.
 */
public final class ForumTopicsController extends RecyclerViewController<ForumTopicsController.Arguments> implements
  ForumTopicList.Listener, ChatHeaderView.Callback, MoreDelegate, View.OnClickListener, View.OnLongClickListener {

  public static class Arguments {
    public final TdApi.Chat chat;

    public Arguments (TdApi.Chat chat) {
      this.chat = chat;
    }
  }

  private TdApi.Chat chat;
  private ForumTopicList list;
  private boolean listAttached;
  private ChatHeaderView headerCell;
  private TopicsAdapter adapter;
  private final Map<Integer, TGForumTopic> rows = new HashMap<>();

  public ForumTopicsController (Context context, Tdlib tdlib) {
    super(context, tdlib);
  }

  @Override
  public int getId () {
    return R.id.controller_xgramForumTopics;
  }

  @Override
  public long getChatId () {
    return getArgumentsStrict().chat.id;
  }

  @Override
  public CharSequence getName () {
    return chat != null ? tdlib.chatTitle(chat) : Lang.getString(R.string.XgramTopics);
  }

  @Override
  public View getCustomHeaderCell () {
    return headerCell;
  }

  @Override
  protected int getMenuId () {
    return R.id.menu_xgramTopics;
  }

  @Override
  protected int getSearchMenuId () {
    return R.id.menu_clear;
  }

  @Override
  public void fillMenuItems (int id, org.thunderdog.challegram.navigation.HeaderView header, android.widget.LinearLayout menu) {
    if (id == R.id.menu_xgramTopics) {
      header.addSearchButton(menu, this);
      header.addMoreButton(menu, this);
    } else {
      super.fillMenuItems(id, header, menu);
    }
  }

  // Search keeps server result ordering, while matching rows still receive live metadata updates.

  private @androidx.annotation.Nullable List<TdApi.ForumTopic> searchResults;
  private String searchQuery = "";
  private long searchGeneration;

  @Override
  protected void onSearchInputChanged (String query) {
    super.onSearchInputChanged(query);
    String trimmed = query.trim();
    if (trimmed.equals(searchQuery)) {
      return;
    }
    searchQuery = trimmed;
    cancelSearchRequests();
    if (trimmed.isEmpty()) {
      setSearchResults(null);
      return;
    }
    // Only once typing pauses: a request per key ended in FLOOD_WAIT, and only the last query's results are shown.
    scheduleSearch(trimmed, SEARCH_DELAY_MS);
  }

  private static final long SEARCH_DELAY_MS = 350;
  private @androidx.annotation.Nullable Runnable pendingSearch;

  private void scheduleSearch (String query, long delay) {
    cancelPendingSearch();
    Runnable search = () -> {
      pendingSearch = null;
      searchTopics(query);
    };
    pendingSearch = search;
    tdlib.ui().postDelayed(search, delay);
  }

  private void cancelPendingSearch () {
    if (pendingSearch != null) {
      tdlib.ui().removeCallbacks(pendingSearch);
      pendingSearch = null;
    }
  }

  private void cancelSearchRequests () {
    searchGeneration++;
    cancelPendingSearch();
    ForumRequests.cancel(tdlib, this);
  }

  private void resumeSearch () {
    if (!isDestroyed() && isFocused() && inSearchMode() && !searchQuery.isEmpty()) {
      scheduleSearch(searchQuery, 0);
    }
  }

  private void searchTopics (String query) {
    if (isDestroyed() || !isFocused() || !query.equals(searchQuery) || !inSearchMode()) {
      return;
    }
    long floodWait = XgramTopicFlood.waitMs(tdlib);
    if (floodWait > 0) {
      scheduleSearch(query, floodWait);
      return;
    }
    final long generation = searchGeneration;
    ForumRequests.send(tdlib, this, new TdApi.GetForumTopics(chat.id, query, 0, 0, 0, 100), (topics, error) -> runOnUiThreadOptional(() -> {
      if (isDestroyed() || !isFocused() || generation != searchGeneration || !query.equals(searchQuery) || !inSearchMode()) {
        return;
      }
      if (topics == null) {
        long delay = XgramTopicFlood.onError(tdlib, error, 0);
        if (XgramTopicFlood.waitMs(tdlib) > 0) {
          // Asked to wait: the same query goes again then, the results shown so far stay meanwhile.
          scheduleSearch(query, delay);
        }
        return;
      }
      List<TdApi.ForumTopic> results = new ArrayList<>();
      if (topics != null) {
        for (TdApi.ForumTopic topic : topics.topics) {
          results.add(XgramForums.normalizeUnread(tdlib, topic));
        }
      }
      setSearchResults(results);
    }));
  }

  @Override
  protected void onLeaveSearchMode () {
    super.onLeaveSearchMode();
    searchQuery = "";
    cancelSearchRequests();
    setSearchResults(null);
  }

  private void updateSearchTopic (long chatId, int topicId, @androidx.annotation.Nullable TdApi.ForumTopicInfo info, @androidx.annotation.Nullable TdApi.UpdateForumTopic update) {
    if (isDestroyed() || !isFocused() || !inSearchMode() || chat == null || chat.id != chatId || searchResults == null) return;
    for (int i = 0; i < searchResults.size(); i++) {
      TdApi.ForumTopic previous = searchResults.get(i);
      if (previous.info.forumTopicId != topicId) continue;
      ForumTopicSnapshotUpdates changes = new ForumTopicSnapshotUpdates();
      if (info != null) changes.record(info);
      if (update != null) changes.record(update);
      TdApi.ForumTopic current = (TdApi.ForumTopic) changes.apply((TdApi.Object) previous);
      searchResults.set(i, current);
      TGForumTopic row = rows.get(topicId);
      if (row != null) row.setTopic(current);
      if (adapter != null) adapter.notifyItemChanged(i);
      return;
    }
  }

  private void setSearchResults (@androidx.annotation.Nullable List<TdApi.ForumTopic> results) {
    if (searchResults == null && results == null) {
      return;
    }
    searchResults = results;
    if (adapter != null) {
      adapter.notifyDataSetChanged();
    }
  }

  private int visibleCount () {
    return searchResults != null ? searchResults.size() : list != null ? list.size() : 0;
  }

  private TdApi.ForumTopic visibleTopic (int position) {
    return searchResults != null ? searchResults.get(position) : list.get(position);
  }

  // Mentions: like the official app, an @ button jumps to the topic with the next unread mention.

  private org.thunderdog.challegram.widget.CircleButton mentionButton;
  private org.thunderdog.challegram.component.chat.CounterBadgeView mentionCountView;
  private FrameLayout mentionWrap;

  private final org.thunderdog.challegram.telegram.ChatListener mentionListener = new org.thunderdog.challegram.telegram.ChatListener() {
    @Override
    public void onChatUnreadMentionCount (long chatId, int unreadMentionCount, boolean availabilityChanged) {
      runOnUiThreadOptional(() -> updateMentionButton(true));
    }

    @Override
    public void onForumTopicInfoChanged (TdApi.ForumTopicInfo info) {
      runOnUiThreadOptional(() -> updateSearchTopic(info.chatId, info.forumTopicId, info, null));
    }

    @Override
    public void onForumTopicUpdated (TdApi.UpdateForumTopic update) {
      runOnUiThreadOptional(() -> updateSearchTopic(update.chatId, update.forumTopicId, null, update));
    }
  };

  @Override
  protected View onCreateView (Context context) {
    View view = super.onCreateView(context);
    if (view instanceof ViewGroup) {
      int padding = Screen.dp(4f);
      mentionWrap = new FrameLayout(context);
      FrameLayout.LayoutParams wrapParams = new FrameLayout.LayoutParams(Screen.dp(48f) + padding * 2 + Screen.dp(24f), Screen.dp(48f) + padding * 2 + Screen.dp(14f), Gravity.RIGHT | Gravity.BOTTOM);
      wrapParams.rightMargin = wrapParams.bottomMargin = Screen.dp(16f) - padding;
      mentionWrap.setLayoutParams(wrapParams);

      mentionButton = new org.thunderdog.challegram.widget.CircleButton(context);
      mentionButton.init(R.drawable.baseline_alternate_email_24, 48f, 4f, ColorId.circleButtonChat, ColorId.circleButtonChatIcon);
      mentionButton.setLayoutParams(new FrameLayout.LayoutParams(Screen.dp(48f) + padding * 2, Screen.dp(48f) + padding * 2, Gravity.RIGHT | Gravity.BOTTOM));
      mentionButton.setOnClickListener(v -> openNextMention());
      addThemeInvalidateListener(mentionButton);
      mentionWrap.addView(mentionButton);

      mentionCountView = new org.thunderdog.challegram.component.chat.CounterBadgeView(context);
      mentionCountView.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.LEFT | Gravity.TOP));
      addThemeInvalidateListener(mentionCountView);
      mentionWrap.addView(mentionCountView);

      ((ViewGroup) view).addView(mentionWrap);
      tdlib.listeners().subscribeToChatUpdates(getArgumentsStrict().chat.id, mentionListener);
      updateMentionButton(false);

      createRequestsBar(context, (ViewGroup) view);
    }
    return view;
  }

  // Join requests: the bar Telegram X shows over a group's messages, here over the topics, so admins of forums see them.

  private android.widget.LinearLayout requestsWrap;
  private org.thunderdog.challegram.component.chat.JoinRequestsView requestsView;

  private final org.thunderdog.challegram.telegram.ChatListener requestsListener = new org.thunderdog.challegram.telegram.ChatListener() {
    @Override
    public void onChatPendingJoinRequestsChanged (long chatId, TdApi.ChatJoinRequestsInfo pendingJoinRequests) {
      runOnUiThreadOptional(() -> checkJoinRequests(pendingJoinRequests, true));
    }
  };

  private final org.thunderdog.challegram.telegram.TdlibSettingsManager.DismissRequestsListener requestsDismissListener = new org.thunderdog.challegram.telegram.TdlibSettingsManager.DismissRequestsListener() {
    @Override
    public void onJoinRequestsDismissed (long chatId) {
      onRequestsDismissChanged(chatId);
    }

    @Override
    public void onJoinRequestsRestore (long chatId) {
      onRequestsDismissChanged(chatId);
    }
  };

  private void onRequestsDismissChanged (long chatId) {
    runOnUiThreadOptional(() -> {
      if (chat != null && chat.id == chatId) {
        checkJoinRequests(pendingJoinRequests(), true);
      }
    });
  }

  private void createRequestsBar (Context context, ViewGroup parent) {
    requestsView = new org.thunderdog.challegram.component.chat.JoinRequestsView(context, tdlib);
    requestsView.setLayoutParams(new android.widget.LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Screen.dp(48f)));
    requestsView.setOnClickListener(v -> org.thunderdog.challegram.component.popups.ModernActionedLayout.showJoinRequests(this, chat.id, requestsView.getInfo()));
    requestsView.setOnDismissRunnable(() -> tdlib.settings().dismissRequests(chat.id, requestsView.getInfo()));
    org.thunderdog.challegram.support.RippleSupport.setSimpleWhiteBackground(requestsView, this);
    org.thunderdog.challegram.tool.Views.setClickable(requestsView);

    org.thunderdog.challegram.widget.ShadowView shadowView = new org.thunderdog.challegram.widget.ShadowView(context);
    shadowView.setSimpleBottomTransparentShadow(true);

    requestsWrap = new android.widget.LinearLayout(context);
    requestsWrap.setOrientation(android.widget.LinearLayout.VERTICAL);
    requestsWrap.setLayoutParams(new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP));
    requestsWrap.addView(requestsView);
    requestsWrap.addView(shadowView);
    requestsWrap.setVisibility(View.GONE);
    parent.addView(requestsWrap);

    tdlib.listeners().subscribeToChatUpdates(chat.id, requestsListener);
    tdlib.settings().addJoinRequestsDismissListener(requestsDismissListener);
    checkJoinRequests(pendingJoinRequests(), false);
  }

  private TdApi.ChatJoinRequestsInfo pendingJoinRequests () {
    TdApi.Chat current = tdlib.chat(chat.id);
    return current != null ? current.pendingJoinRequests : chat.pendingJoinRequests;
  }

  /** As MessagesController.checkJoinRequests: shown while there are requests the admin hasn't dismissed. */
  private void checkJoinRequests (TdApi.ChatJoinRequestsInfo info, boolean animated) {
    if (requestsWrap == null || chat == null || isDestroyed()) {
      return;
    }
    boolean show = info != null && info.totalCount > 0 && tdlib.canInviteUsers(chat, false) && !tdlib.settings().isRequestsDismissed(chat.id, info);
    if (show) {
      tdlib.settings().restoreRequests(chat.id, true);
      requestsView.setInfo(info, animated);
    }
    if ((requestsWrap.getVisibility() == View.VISIBLE) != show) {
      requestsWrap.setVisibility(show ? View.VISIBLE : View.GONE);
      org.thunderdog.challegram.tool.Views.setTopMargin(getRecyclerView(), show ? Screen.dp(48f) : 0);
    }
  }

  private void updateMentionButton (boolean animated) {
    if (mentionWrap == null || chat == null) {
      return;
    }
    TdApi.Chat current = tdlib.chat(chat.id);
    int count = current != null ? current.unreadMentionCount : 0;
    mentionCountView.setCounter(count, false, animated);
    mentionWrap.setVisibility(count > 0 ? View.VISIBLE : View.GONE);
  }

  private void openNextMention () {
    long chatId = chat.id;
    tdlib.send(new TdApi.SearchChatMessages(chatId, null, "", null, 0, 0, 1, new TdApi.SearchMessagesFilterUnreadMention()), (found, error) -> runOnUiThreadOptional(() -> {
      if (found != null && found.messages.length > 0) {
        TdApi.Message message = found.messages[0];
        if (message.topicId instanceof TdApi.MessageTopicForum) {
          XgramForums.openTopicLink(this, chatId, (TdApi.MessageTopicForum) message.topicId, message, null);
        } else {
          XgramForums.openTopicLink(this, chatId, new TdApi.MessageTopicForum(XgramForums.GENERAL_TOPIC_ID), message, null);
        }
      } else if (!tdlib.isGhostReadEnabled(chatId)) {
        // The counter is stale (the mention was deleted): clear it, as the official app does.
        tdlib.send(new TdApi.ReadAllChatMentions(chatId), tdlib.typedOkHandler());
      }
    }));
  }

  @Override
  protected void onCreateView (Context context, CustomRecyclerView recyclerView) {
    chat = getArgumentsStrict().chat;

    headerCell = new ChatHeaderView(context, tdlib, this);
    headerCell.setCallback(this);
    headerCell.initWithController(this, true);
    // Room for both header buttons (search and more): the chat header leaves room for one, so long titles ran under search.
    headerCell.setInnerMargins(Screen.dp(56f), Screen.dp(49f) * 2);
    headerCell.xgramHideChatActions(); // as in Telegram: who is typing shows in the topic rows, not over the whole list
    headerCell.setChat(tdlib, chat, null);

    adapter = new TopicsAdapter();
    adapter.setHasStableIds(true);
    recyclerView.setLayoutManager(new LinearLayoutManager(context, RecyclerView.VERTICAL, false));
    // As Telegram X's chat list: rows change in place with no item animator, so counter and order updates never
    // animate on top of a slide in or out; the animator only runs while a pinned topic is dragged.
    recyclerView.setItemAnimator(null);
    recyclerView.setAdapter(adapter);
    new ItemTouchHelper(new ReorderCallback()).attachToRecyclerView(recyclerView);
    recyclerView.addOnScrollListener(new RecyclerView.OnScrollListener() {
      @Override
      public void onScrolled (@NonNull RecyclerView recyclerView, int dx, int dy) {
        checkLoadMore();
      }
    });

    moe.kirao.mgx.MoexShadowUnreadManager.addHiddenUsersListener(tdlib, hiddenUsersListener);
    moe.kirao.mgx.MoexShadowUnreadManager.refreshHiddenUsers(tdlib, false);
    ensureList();
  }

  private ForumTopicList ensureList () {
    if (!listAttached) {
      ForumTopicList previous = list;
      list = ForumTopicList.obtain(tdlib, getArgumentsStrict().chat.id);
      list.restoreFrom(previous);
      list.addListener(this);
      listAttached = true;
      if (!list.isLoaded()) list.loadMore();
    }
    return list;
  }

  private final moe.kirao.mgx.MoexShadowUnreadManager.HiddenUsersListener hiddenUsersListener = revision -> {
    if (isDestroyed()) return;
    for (TGForumTopic row : rows.values()) row.setTopic(row.getTopic());
    if (adapter != null) adapter.notifyDataSetChanged();
  };

  private boolean xgramFocusedOnce;

  @Override
  public void onFocus () {
    super.onFocus();
    ensureList();
    // Counters may have changed while a topic was open (TDLib doesn't report every topic's unread count). The list
    // was just loaded on the first focus, so that refresh would only add work right after the slide in.
    if (xgramFocusedOnce && list != null && list.isLoaded()) {
      list.refreshOnReturn();
    }
    xgramFocusedOnce = true;
    resumeSearch();
  }

  @Override
  public void onActivityResume () {
    super.onActivityResume();
    // Back from the background with the topics on screen: they missed the same as while a topic was open. (With a
    // topic open, the list refreshes once it is back in front.)
    if (isFocused()) {
      ensureList();
      if (list.isLoaded()) list.refreshOnReturn();
      resumeSearch();
    }
  }

  private void releaseList () {
    cancelSearchRequests();
    if (listAttached) {
      listAttached = false;
      list.removeListener(this);
      // Keep the released rows and cursor for Back, without subscriptions, requests or retries.
    }
  }

  @Override
  public void onBlur () { super.onBlur(); releaseList(); }

  @Override
  public void onActivityPause () { super.onActivityPause(); releaseList(); }

  private org.thunderdog.challegram.component.attach.CustomItemAnimator dragAnimator;
  /** A pinned topic is being dragged: the drag moves rows and scrolls, the list is left alone meanwhile. */
  private boolean dragging;

  /** Telegram X's chat list animator, only while a pinned topic is dragged. */
  private void setDragging (boolean dragging) {
    this.dragging = dragging;
    CustomRecyclerView recyclerView = getRecyclerView();
    if (recyclerView == null) {
      return;
    }
    if (dragging) {
      if (dragAnimator == null) {
        dragAnimator = new org.thunderdog.challegram.component.attach.CustomItemAnimator(me.vkryl.android.AnimatorUtils.DECELERATE_INTERPOLATOR, 180L);
      }
      recyclerView.setItemAnimator(dragAnimator);
    } else {
      recyclerView.setItemAnimator(null);
    }
  }

  // The group should open immediately even while its first topic page is pending.
  // onCreateView starts the bounded load; the list's loading row covers that wait.
  @Override
  public boolean needAsynchronousAnimation () {
    return false;
  }

  private void checkLoadMore () {
    if (listAttached && list.canLoadMore() && list.isLoaded()) {
      int lastVisible = findLastVisiblePosition();
      if (lastVisible >= adapter.getItemCount() - 5) {
        list.loadMore();
      }
    }
  }

  private TGForumTopic rowFor (TdApi.ForumTopic topic) {
    TGForumTopic row = rows.get(topic.info.forumTopicId);
    if (row == null) {
      row = new TGForumTopic(this, chat.id, topic);
      rows.put(topic.info.forumTopicId, row);
    } else if (row.getTopic() != topic) {
      row.setTopic(topic);
    }
    return row;
  }

  // ForumTopicList.Listener

  @Override
  public void onTopicsLoaded (ForumTopicList list) {
    if (adapter != null && searchResults == null) {
      adapter.notifyDataSetChanged();
      getRecyclerView().post(this::checkLoadMore);
    }
    executeScheduledAnimation();
  }

  @Override
  public void onLoadMoreAvailable (ForumTopicList list) {
    if (adapter != null && searchResults == null) {
      checkLoadMore();
    }
  }

  @Override
  public void onTopicInserted (ForumTopicList list, int index) {
    if (adapter == null || searchResults != null) {
      return;
    }
    if (list.size() == 1) {
      adapter.notifyDataSetChanged();
    } else {
      int[] scroll = captureScroll();
      adapter.notifyItemInserted(index);
      restoreScroll(scroll, -1);
    }
  }

  @Override
  public void onTopicRemoved (ForumTopicList list, int index) {
    if (adapter == null || searchResults != null) {
      return;
    }
    if (list.size() == 0) {
      adapter.notifyDataSetChanged();
    } else {
      adapter.notifyItemRemoved(index);
    }
  }

  @Override
  public void onTopicMoved (ForumTopicList list, int fromIndex, int toIndex) {
    if (adapter == null || searchResults != null) {
      return;
    }
    int[] scroll = captureScroll();
    adapter.notifyItemMoved(fromIndex, toIndex);
    restoreScroll(scroll, fromIndex);
  }

  /**
   * Where the list is scrolled to before a row moves or comes in: {first visible position, its offset}, or null to
   * leave it to RecyclerView. RecyclerView keeps the first row on screen in place, so a row moving or coming in at the
   * top stayed above the screen, hidden, and moving that first row away scrolled the list along with it.
   */
  @androidx.annotation.Nullable
  private int[] captureScroll () {
    CustomRecyclerView recyclerView = getRecyclerView();
    if (dragging || recyclerView == null || recyclerView.getScrollState() != RecyclerView.SCROLL_STATE_IDLE ||
      !(recyclerView.getLayoutManager() instanceof LinearLayoutManager)) {
      return null;
    }
    if (!recyclerView.canScrollVertically(-1)) {
      return new int[] {0, 0}; // at the top: stays at the top
    }
    if (recyclerView.hasPendingAdapterUpdates()) {
      return null; // the positions on screen are from before the changes still pending
    }
    LinearLayoutManager manager = (LinearLayoutManager) recyclerView.getLayoutManager();
    int first = manager.findFirstVisibleItemPosition();
    View view = first != RecyclerView.NO_POSITION ? manager.findViewByPosition(first) : null;
    return view != null ? new int[] {first, manager.getDecoratedTop(view) - manager.getPaddingTop()} : null;
  }

  /** After the change: at the top, stays there; moving the first row on screen away, keeps the place. */
  private void restoreScroll (@androidx.annotation.Nullable int[] scroll, int movedFrom) {
    if (scroll == null) {
      return;
    }
    boolean atTop = scroll[0] == 0 && scroll[1] == 0;
    if (atTop || movedFrom == scroll[0]) {
      ((LinearLayoutManager) getRecyclerView().getLayoutManager()).scrollToPositionWithOffset(scroll[0], scroll[1]);
    }
  }

  @Override
  public void onTopicChanged (ForumTopicList list, int index) {
    if (adapter == null || searchResults != null) {
      return;
    }
    TdApi.ForumTopic topic = list.get(index);
    TGForumTopic row = rows.get(topic.info.forumTopicId);
    if (row != null) {
      row.setTopic(topic);
    }
    // By topic, not by position: right after a move the view at a position is still the row that was there.
    ForumTopicView view = findTopicView(topic.info.forumTopicId);
    if (view != null) {
      view.onTopicChanged();
    } else {
      adapter.notifyItemChanged(index);
    }
  }

  @androidx.annotation.Nullable
  private ForumTopicView findTopicView (int forumTopicId) {
    CustomRecyclerView recyclerView = getRecyclerView();
    if (recyclerView == null) {
      return null;
    }
    for (int i = 0; i < recyclerView.getChildCount(); i++) {
      View child = recyclerView.getChildAt(i);
      if (child instanceof ForumTopicView) {
        TdApi.ForumTopic shown = ((ForumTopicView) child).getForumTopic();
        if (shown != null && shown.info.forumTopicId == forumTopicId) {
          return (ForumTopicView) child;
        }
      }
    }
    return null;
  }

  // Header

  @Override
  public void onChatHeaderClick () {
    tdlib.ui().openChatProfile(this, chat, null, null);
  }

  @Override
  protected void openMoreMenu () {
    IntList ids = new IntList(2);
    StringList titles = new StringList(2);
    if (XgramForums.canCreateTopics(tdlib, chat)) {
      ids.append(R.id.btn_xgramCreateTopic);
      titles.append(R.string.XgramCreateTopic);
    }
    if (reorderMode || (XgramForums.canManageTopics(tdlib, chat.id) && list != null && list.pinnedTopicIds().length > 1)) {
      ids.append(R.id.btn_xgramReorderTopics);
      titles.append(reorderMode ? R.string.XgramReorderTopicsDone : R.string.XgramReorderTopics);
    }
    TdApi.Chat current = tdlib.chat(chat.id);
    if (current != null && (current.unreadCount > 0 || current.unreadMentionCount > 0 || current.unreadReactionCount > 0)) {
      ids.append(R.id.btn_xgramMarkAllTopicsRead);
      titles.append(R.string.XgramMarkAllTopicsRead);
    }

    ids.append(R.id.btn_xgramViewAsMessages);
    titles.append(R.string.XgramViewAsMessages);
    showMore(ids.get(), titles.get(), 0);
  }

  @Override
  public void onMoreItemPressed (int id) {
    if (id == R.id.btn_xgramCreateTopic) {
      XgramForums.openTopicEditor(this, chat, null);

    } else if (id == R.id.btn_xgramMarkAllTopicsRead) {
      XgramForums.markAllTopicsAsRead(tdlib, chat.id);
    } else if (id == R.id.btn_xgramReorderTopics) {
      reorderMode = !reorderMode;
      if (reorderMode) {
        org.thunderdog.challegram.tool.UI.showToast(R.string.XgramReorderTopicsHint, android.widget.Toast.LENGTH_LONG);
      }
    } else if (id == R.id.btn_xgramViewAsMessages) {
      if (context().isNavigationBusy()) {
        return;
      }
      tdlib.ui().openChat(this, chat, new TdlibUi.ChatOpenParameters().keepStack().xgramSkipForumRouting().after(chatId -> {
        // Runs once the chat is pushed, before the slide: drop this list only after the chat has focus.
        tdlib.send(new TdApi.ToggleChatViewAsTopics(chat.id, false), tdlib.typedOkHandler());
        if (!isDestroyed()) {
          org.thunderdog.challegram.navigation.NavigationController nav = context().navigation();
          XgramForums.destroyWhenCovered(this, nav != null ? nav.getCurrentStackItem() : null);
        }
      }));
    }
  }

  // Rows

  @Override
  public void onClick (View v) {
    if (!(v instanceof ForumTopicView)) {
      return;
    }
    TdApi.ForumTopic topic = ((ForumTopicView) v).getForumTopic();
    if (topic != null) {
      XgramForums.openTopic(this, chat, topic);
    }
  }

  @Override
  public boolean onLongClick (View v) {
    if (!(v instanceof ForumTopicView)) {
      return false;
    }
    TdApi.ForumTopic topic = ((ForumTopicView) v).getForumTopic();
    if (topic == null || (reorderMode && topic.isPinned)) {
      // In reorder mode a long press on a pinned topic starts dragging it.
      return false;
    }
    showTopicOptions(topic);
    return true;
  }

  // Pinned topics reordering

  private boolean reorderMode, reorderChanged;

  private class ReorderCallback extends ItemTouchHelper.Callback {
    private boolean isPinnedRow (RecyclerView.ViewHolder holder) {
      int position = holder.getBindingAdapterPosition();
      if (list == null || position < 0 || position >= list.size()) {
        return false;
      }
      TdApi.ForumTopic topic = list.get(position);
      // The hidden General stays first whether it is pinned or not, so it can't be dragged or dragged onto.
      return topic.isPinned && !topic.info.isHidden;
    }

    @Override
    public boolean isLongPressDragEnabled () {
      return reorderMode;
    }

    @Override
    public boolean isItemViewSwipeEnabled () {
      return false;
    }

    @Override
    public int getMovementFlags (@NonNull RecyclerView recyclerView, @NonNull RecyclerView.ViewHolder viewHolder) {
      return reorderMode && searchResults == null && isPinnedRow(viewHolder) ? makeMovementFlags(ItemTouchHelper.UP | ItemTouchHelper.DOWN, 0) : 0;
    }

    @Override
    public boolean onMove (@NonNull RecyclerView recyclerView, @NonNull RecyclerView.ViewHolder viewHolder, @NonNull RecyclerView.ViewHolder target) {
      if (!isPinnedRow(target)) {
        return false;
      }
      boolean moved = list.movePinnedLocally(viewHolder.getBindingAdapterPosition(), target.getBindingAdapterPosition());
      reorderChanged |= moved;
      return moved;
    }

    @Override
    public void onSwiped (@NonNull RecyclerView.ViewHolder viewHolder, int direction) { }

    @Override
    public void onSelectedChanged (@androidx.annotation.Nullable RecyclerView.ViewHolder viewHolder, int actionState) {
      super.onSelectedChanged(viewHolder, actionState);
      if (actionState == ItemTouchHelper.ACTION_STATE_DRAG) {
        setDragging(true);
      }
    }

    @Override
    public void clearView (@NonNull RecyclerView recyclerView, @NonNull RecyclerView.ViewHolder viewHolder) {
      super.clearView(recyclerView, viewHolder);
      recyclerView.post(() -> setDragging(false)); // after the dropped row settles
      if (reorderChanged && list != null) {
        reorderChanged = false;
        final ForumTopicList targetList = list;
        final int[] pinnedIds = targetList.pinnedTopicIds();
        final int reorderVersion = targetList.localReorderVersion();
        // The exact list owns this reply; a destroyed list ignores its follow-up refresh.
        tdlib.send(new TdApi.SetPinnedForumTopics(chat.id, pinnedIds), (ok, error) -> tdlib.ui().post(() -> {
          if (error != null) {
            org.thunderdog.challegram.tool.UI.showError(error);
            // The server kept its order: fetch it to undo the move.
            targetList.resyncFirstPage(true);
          } else {
            // The order the server accepted is the one shown; it sticks until the server says otherwise. A newer
            // drag (still on its way to the server) is left alone.
            targetList.setPinnedOrder(pinnedIds, reorderVersion);
          }
        }));
      }
    }
  }

  private void showTopicOptions (TdApi.ForumTopic topic) {
    XgramForums.showTopicOptions(this, chat, topic);
  }

  @Override
  public void destroy () {
    moe.kirao.mgx.MoexShadowUnreadManager.removeHiddenUsersListener(tdlib, hiddenUsersListener);
    releaseList();
    list = null;
    super.destroy();
    cancelPendingSearch();
    for (TGForumTopic row : rows.values()) {
      row.statusHelper().detachFromAnyChat();
    }
    tdlib.listeners().unsubscribeFromChatUpdates(getArgumentsStrict().chat.id, mentionListener);
    if (requestsView != null) {
      tdlib.listeners().unsubscribeFromChatUpdates(getArgumentsStrict().chat.id, requestsListener);
      tdlib.settings().removeJoinRequestsDismissListener(requestsDismissListener);
      requestsView.performDestroy();
    }
    if (headerCell != null) {
      headerCell.performDestroy();
    }
  }

  // Adapter

  private static final int VIEW_TYPE_TOPIC = 0;
  private static final int VIEW_TYPE_LOADING = 1;
  private static final int VIEW_TYPE_EMPTY = 2;

  private static class Holder extends RecyclerView.ViewHolder {
    Holder (View itemView) {
      super(itemView);
    }
  }

  private class TopicsAdapter extends RecyclerView.Adapter<Holder> {
    private boolean showLoading () {
      if (searchResults != null) {
        return false;
      }
      return list == null || !list.isLoaded() || !list.isEndReached();
    }

    @Override
    public int getItemCount () {
      if (list == null) {
        return 0;
      }
      int count = visibleCount();
      if (showLoading()) {
        count++;
      } else if (count == 0) {
        count = 1;
      }
      return count;
    }

    @Override
    public long getItemId (int position) {
      if (list != null && position < visibleCount()) {
        return visibleTopic(position).info.forumTopicId;
      }
      // Footer rows (loading or empty state) never collide with topic ids, which are positive.
      return -1 - getItemViewType(position);
    }

    @Override
    public int getItemViewType (int position) {
      if (list != null && position < visibleCount()) {
        return VIEW_TYPE_TOPIC;
      }
      return showLoading() ? VIEW_TYPE_LOADING : VIEW_TYPE_EMPTY;
    }

    @NonNull
    @Override
    public Holder onCreateViewHolder (@NonNull ViewGroup parent, int viewType) {
      Context context = parent.getContext();
      switch (viewType) {
        case VIEW_TYPE_TOPIC: {
          ForumTopicView view = new ForumTopicView(context, tdlib);
          view.setOnClickListener(ForumTopicsController.this);
          view.setOnLongClickListener(ForumTopicsController.this);
          addThemeInvalidateListener(view);
          return new Holder(view);
        }
        case VIEW_TYPE_LOADING: {
          FrameLayout frame = new FrameLayout(context);
          frame.setLayoutParams(new RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Screen.dp(56f)));
          ProgressComponentView progress = new ProgressComponentView(context);
          progress.initMedium(1f);
          frame.addView(progress, new FrameLayout.LayoutParams(Screen.dp(40f), Screen.dp(40f), Gravity.CENTER));
          return new Holder(frame);
        }
        case VIEW_TYPE_EMPTY:
        default: {
          TextView text = new TextView(context);
          text.setLayoutParams(new RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Screen.dp(120f)));
          text.setGravity(Gravity.CENTER);
          text.setTextSize(TypedValue.COMPLEX_UNIT_DIP, 15f);
          text.setTextColor(Theme.textDecentColor());
          addThemeTextDecentColorListener(text);
          text.setText(Lang.getString(R.string.XgramNoTopics));
          return new Holder(text);
        }
      }
    }

    @Override
    public void onBindViewHolder (@NonNull Holder holder, int position) {
      if (holder.itemView instanceof ForumTopicView) {
        ((ForumTopicView) holder.itemView).setTopic(rowFor(visibleTopic(position)));
      }
    }

    @Override
    public void onViewAttachedToWindow (@NonNull Holder holder) {
      if (holder.itemView instanceof ForumTopicView) {
        ((ForumTopicView) holder.itemView).attach();
      }
    }

    @Override
    public void onViewDetachedFromWindow (@NonNull Holder holder) {
      if (holder.itemView instanceof ForumTopicView) {
        ((ForumTopicView) holder.itemView).detach();
      }
    }

    @Override
    public void onViewRecycled (@NonNull Holder holder) {
      if (holder.itemView instanceof ForumTopicView) {
        ((ForumTopicView) holder.itemView).setTopic(null);
      }
    }
  }
}
