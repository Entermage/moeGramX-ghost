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

import androidx.annotation.Nullable;

import moe.kirao.mgx.topics.ForumSettings;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.component.chat.ChatHeaderView;
import org.thunderdog.challegram.component.chat.MessagesManager;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.navigation.NavigationController;
import org.thunderdog.challegram.navigation.ViewController;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.telegram.TdlibDelegate;
import org.thunderdog.challegram.telegram.TdlibForumTopicManager;
import org.thunderdog.challegram.telegram.TdlibNotification;
import org.thunderdog.challegram.telegram.TdlibUi;
import org.thunderdog.challegram.tool.UI;
import org.thunderdog.challegram.ui.MessagesController;
import org.thunderdog.challegram.util.StringList;

import me.vkryl.core.collection.IntList;
import me.vkryl.core.lambda.FutureInt;
import me.vkryl.core.lambda.RunnableData;
import me.vkryl.core.lambda.RunnableInt;
import me.vkryl.core.lambda.RunnableLong;
import tgx.td.MessageId;

/**
 * Entry points for XGram forum topics, used by hooks in Telegram X code.
 */
public final class XgramForums {
  private XgramForums () { }

  /**
   * Whether tapping this chat should show its topic list instead of the merged history.
   * Forums using the tabs layout get the list too until the tabs view is implemented.
   */
  public static boolean shouldOpenTopicList (Tdlib tdlib, TdApi.Chat chat) {
    if (!tdlib.isForum(chat.id)) {
      return false;
    }
    // Forums with tabs open on a topic instead, see prepareTabsOpen.
    return chat.viewAsTopics && !hasForumTabs(tdlib, chat);
  }

  /**
   * Whether a highlight mode is only the chat list's automatic resume position (first unread or last scroll
   * position) rather than an explicit jump to a message from a link, search result or notification.
   */
  public static boolean isResumePosition (int highlightMode) {
    switch (highlightMode) {
      case MessagesManager.HIGHLIGHT_MODE_NONE:
      case MessagesManager.HIGHLIGHT_MODE_UNREAD:
      case MessagesManager.HIGHLIGHT_MODE_UNREAD_NEXT:
      case MessagesManager.HIGHLIGHT_MODE_POSITION_RESTORE:
        return true;
      default:
        return false;
    }
  }

  public static void openTopicList (TdlibDelegate context, TdApi.Chat chat) {
    openTopicList(context, chat, false);
  }

  /**
   * Opens the topic list. With {@code replaceContext}, the screen it was opened from is dropped
   * from the stack once the topic list has fully slid in.
   *
   * @return false if nothing was opened (navigation busy)
   */
  public static boolean openTopicList (TdlibDelegate context, TdApi.Chat chat, boolean replaceContext) {
    ForumTopicsController c = new ForumTopicsController(context.context(), context.tdlib());
    c.setArguments(new ForumTopicsController.Arguments(chat));
    if (context instanceof ViewController<?> && moe.kirao.mgx.layout.MoexTwoPane.replacesRightPane((ViewController<?>) context)) {
      moe.kirao.mgx.layout.MoexTwoPane.showOnRight((ViewController<?>) context, c); // two panes: replace, don't stack
      return true;
    }
    NavigationController navigation = context.context().navigation();
    if (navigation == null || !navigation.navigateTo(c)) {
      return false;
    }
    if (replaceContext && context instanceof ViewController<?>) {
      destroyWhenCovered((ViewController<?>) context, c);
    }
    return true;
  }

  /**
   * The topic list in place of a forum's merged history (TdlibUi.openChat's routing), placed as a chat would be there.
   * Nothing on screen yet (a notification on a cold start): the topic list with the chat list under it; navigateTo
   * refuses an empty stack, which left the bare navigation (an empty header and nothing under it). From a notification
   * over other screens: the chat list under it, as for a chat. Otherwise as {@link #openTopicList(TdlibDelegate, TdApi.Chat)}.
   */
  public static void openRoutedTopicList (TdlibDelegate context, TdApi.Chat chat, boolean fromNotification) {
    NavigationController navigation = context.context().navigation();
    if (navigation == null || navigation.isDestroyed() || !(navigation.isEmpty() || (fromNotification && navigation.getStackSize() > 1))) {
      openTopicList(context, chat, false);
      return;
    }
    if (!navigation.isEmpty() && context.context().isNavigationBusy()) {
      return; // as TdlibUi.openChat: the tap is dropped, what is on screen stays
    }
    ForumTopicsController c = new ForumTopicsController(context.context(), context.tdlib());
    c.setArguments(new ForumTopicsController.Arguments(chat));
    if (navigation.isEmpty()) {
      navigation.initController(c);
      org.thunderdog.challegram.ui.MainController main = new org.thunderdog.challegram.ui.MainController(context.context(), context.tdlib());
      main.getValue();
      navigation.getStack().insert(main, 0);
    } else {
      navigation.setControllerAnimated(c, true, true);
    }
  }

  /** Intent extra of a message notification: the forum topic of its messages (see {@link #notificationTopicId}). */
  public static final String EXTRA_NOTIFICATION_TOPIC_ID = "xgram_forum_topic_id";

  /**
   * The forum topic all of a notification's messages are in, so tapping it opens that topic: 0 outside forums, when
   * they are in several topics or one isn't known yet (a push): the forum then opens as it does from the chat list.
   * Notification thread.
   */
  public static int notificationTopicId (Tdlib tdlib, long chatId, @Nullable Iterable<TdlibNotification> notifications) {
    if (notifications == null || chatId == 0 || !tdlib.isForum(chatId)) {
      return 0;
    }
    int forumTopicId = 0;
    for (TdlibNotification notification : notifications) {
      TdApi.Message message = notification.getChatId() == chatId ? notification.findMessage() : null;
      if (message == null || !(message.topicId instanceof TdApi.MessageTopicForum)) {
        return 0;
      }
      int id = ((TdApi.MessageTopicForum) message.topicId).forumTopicId;
      if (forumTopicId != 0 && id != forumTopicId) {
        return 0;
      }
      forumTopicId = id;
    }
    return forumTopicId;
  }

  /**
   * A notification of one topic of a forum shown by topics: it opens that topic, at its first unread message when the
   * topic is known here (the notification asked for it), else where it was left or at the bottom. Nothing is waited
   * for, so a cold start never sits on an empty screen. UI thread.
   */
  public static void prepareNotificationTopicOpen (Tdlib tdlib, TdApi.Chat chat, int forumTopicId, TdlibUi.ChatOpenParameters params) {
    params.xgramSkipForumRouting();
    params.messageTopicId = new TdApi.MessageTopicForum(forumTopicId);
    TdApi.ForumTopic topic = knownTopic(tdlib, chat.id, forumTopicId);
    params.forumTopicTitle = topic != null ? topicTitle(topic.info) : null;
    TopicResume resume = topicResume(tdlib, chat.id, forumTopicId, topic);
    params.highlightMessage(resume.highlightMode, resume.anchor);
  }

  /**
   * Removes {@code old} from the stack once {@code opened} gets focus, i.e. after the slide.
   * Removing it any earlier changes which screen the transition slides away from.
   */
  public static void destroyWhenCovered (ViewController<?> old, @Nullable ViewController<?> opened) {
    if (opened == null || opened == old) {
      return;
    }
    opened.addOneShotFocusListener(() -> {
      NavigationController navigation = old.context().navigation();
      if (old.isDestroyed() || navigation == null || navigation.getCurrentStackItem() == old) {
        return;
      }
      if (navigation.getStack().indexOf(old) != -1) {
        navigation.getStack().destroy(old);
      }
    });
  }

  /** Opens the topic at its first unread message, else where it was left, else at the bottom. */
  public static void openTopic (ViewController<?> context, TdApi.Chat chat, TdApi.ForumTopic topic) {
    openTopic(context, chat, topic, null);
  }

  private static void openTopic (TdlibDelegate context, TdApi.Chat chat, TdApi.ForumTopic topic, @Nullable TdlibUi.UrlOpenParameters urlOpenParameters) {
    TdlibUi.ChatOpenParameters params = new TdlibUi.ChatOpenParameters().keepStack().urlOpenParameters(urlOpenParameters);
    params.messageTopicId = new TdApi.MessageTopicForum(topic.info.forumTopicId);
    params.forumTopicTitle = topicTitle(topic.info);
    TopicResume resume = topicResume(context.tdlib(), chat.id, topic.info.forumTopicId, topic);
    params.highlightMessage(resume.highlightMode, resume.anchor);
    context.tdlib().ui().openChat(context, chat, params);
  }

  public static void openTopic (TdlibDelegate context, TdApi.Chat chat, int forumTopicId, long lastReadInboxMessageId) {
    openTopic(context, chat, forumTopicId, lastReadInboxMessageId, null);
  }

  private static void openTopic (TdlibDelegate context, TdApi.Chat chat, int forumTopicId, long lastReadInboxMessageId, @Nullable TdlibUi.UrlOpenParameters urlOpenParameters) {
    TdlibUi.ChatOpenParameters params = new TdlibUi.ChatOpenParameters().keepStack().urlOpenParameters(urlOpenParameters);
    params.messageTopicId = new TdApi.MessageTopicForum(forumTopicId);
    long anchorMessageId = lastReadInboxMessageId != 0 ? lastReadInboxMessageId : MessageId.MIN_VALID_ID;
    params.highlightMessage(MessagesManager.HIGHLIGHT_MODE_UNREAD, new MessageId(chat.id, anchorMessageId));
    context.tdlib().ui().openChat(context, chat, params);
  }

  /**
   * Opens a forum topic from a link. A link to a message inside the topic opens the topic scrolled to that
   * message; a link to the topic itself opens it at the first unread message.
   */
  public static void openTopicLink (TdlibDelegate context, long chatId, TdApi.MessageTopicForum topicId, @Nullable TdApi.Message message, @Nullable TdlibUi.UrlOpenParameters urlOpenParameters) {
    Tdlib tdlib = context.tdlib();
    TdApi.Chat chat = tdlib.chat(chatId);
    if (chat == null) {
      tdlib.ui().openChat(context, chatId, new TdlibUi.ChatOpenParameters().keepStack().urlOpenParameters(urlOpenParameters));
      return;
    }
    boolean isTopicStart = message != null && message.content instanceof TdApi.MessageForumTopicCreated;
    if (message != null && !isTopicStart) {
      TdlibUi.ChatOpenParameters params = new TdlibUi.ChatOpenParameters()
        .keepStack()
        .highlightMessage(new MessageId(message.chatId, message.id))
        .ensureHighlightAvailable()
        .urlOpenParameters(urlOpenParameters);
      params.messageTopicId = topicId;
      tdlib.ui().openChat(context, chat, params);
      return;
    }
    tdlib.send(new TdApi.GetForumTopic(chatId, topicId.forumTopicId), (topic, error) -> tdlib.ui().post(() -> {
      if (topic != null) {
        openTopic(context, chat, normalizeUnread(tdlib, topic), urlOpenParameters);
      } else {
        openTopic(context, chat, topicId.forumTopicId, 0, urlOpenParameters);
      }
    }));
  }

  /**
   * TDLib can report a topic's unread count from before the latest read; a topic whose last message is read
   * (or is your own, which reads everything before it) has nothing unread.
   */
  /** The topic was deleted (or never existed), as opposed to a network, flood or access error. */
  public static boolean isTopicGone (TdApi.Error error) {
    return error.code == 404 || (error.code == 400 && error.message != null && error.message.contains("TOPIC_ID_INVALID"));
  }

  /** How long to wait before asking again: the "retry after N" of a flood wait (bounded to one day), else fallbackMs. */
  public static long retryAfterMs (TdApi.Error error, long fallbackMs) {
    if (error.code == 429 && error.message != null) {
      java.util.regex.Matcher m = java.util.regex.Pattern.compile("retry after (\\d+)").matcher(error.message);
      if (m.find()) {
        try {
          return Math.max(fallbackMs, Math.min(86_400_000L, Long.parseLong(m.group(1)) * 1000L));
        } catch (NumberFormatException ignored) { }
      }
    }
    return fallbackMs;
  }

  /**
   * A normalized copy of a topic someone else owns (TDLib's topic cache): the original stays as TDLib reported it,
   * as normalizing the same object twice would lower its counters twice.
   */
  public static TdApi.ForumTopic normalizedCopy (Tdlib tdlib, TdApi.ForumTopic topic) {
    TdApi.ForumTopic copy = new TdApi.ForumTopic(topic.info, topic.lastMessage, topic.order, topic.isPinned,
      topic.unreadCount, topic.lastReadInboxMessageId, topic.lastReadOutboxMessageId,
      topic.unreadMentionCount, topic.unreadReactionCount, topic.unreadPollVoteCount,
      topic.notificationSettings, topic.draftMessage);
    return normalizeUnread(tdlib, copy);
  }

  /**
   * Where the topic is read up to: the server's read position, or with ghost mode's "don't read" the newest message
   * viewed on this device (the server's stays put, so the first unread would always be the old one).
   */
  public static long topicReadInboxId (Tdlib tdlib, long chatId, TdApi.ForumTopic topic) {
    return topic.lastReadInboxMessageId;
  }

  public static TdApi.ForumTopic normalizeUnread (Tdlib tdlib, TdApi.ForumTopic topic) {
    // Ghost mode: messages viewed without reading them count as read on this device.
    // Local reads, including Ghost Mode, are maintained by moeGramX TDLib.
    TdApi.Message last = topic.lastMessage;
    if (last != null && (last.isOutgoing || topic.lastReadInboxMessageId >= last.id)) {
      topic.unreadCount = 0;
    }
    return topic;
  }

  public static String topicTitle (TdApi.ForumTopicInfo info) {
    return info.isGeneral && info.name.isEmpty() ? Lang.getString(R.string.XgramGeneralTopic) : info.name;
  }

  /**
   * Name of the topic a forum chat's last message belongs to, for the chat list preview ("Topic › Sender: text").
   * Returns null when unknown yet; {@code onLoaded} then runs on the UI thread once the topic has been fetched.
   */
  @Nullable
  public static String chatListTopicName (Tdlib tdlib, TdApi.Chat chat, TdApi.Message message, Runnable onLoaded) {
    if (!(message.topicId instanceof TdApi.MessageTopicForum) || !tdlib.isForum(chat.id)) {
      return null;
    }
    int forumTopicId = ((TdApi.MessageTopicForum) message.topicId).forumTopicId;
    TdlibForumTopicManager.Key key = new TdlibForumTopicManager.Key(chat.id, forumTopicId);
    TdlibForumTopicManager.Entry entry = tdlib.topics().find(key);
    if (entry != null) {
      return entry.value != null ? topicTitle(entry.value.info) : null;
    }
    tdlib.topics().findOrRequest(key, (loadedEntry, inPlace) -> {
      if (!inPlace && loadedEntry.value != null) {
        tdlib.ui().post(onLoaded);
      }
    });
    return null;
  }

  /** The messages of one topic from a page of the whole group (General messages may come without a topic id). */
  public static TdApi.Message[] onlyTopic (TdApi.Message[] messages, TdApi.MessageTopicForum topicId) {
    int count = 0;
    for (TdApi.Message message : messages) {
      if (message != null && isInTopic(message, topicId.forumTopicId)) {
        count++;
      }
    }
    if (count == messages.length) {
      return messages;
    }
    TdApi.Message[] result = new TdApi.Message[count];
    int i = 0;
    for (TdApi.Message message : messages) {
      if (message != null && isInTopic(message, topicId.forumTopicId)) {
        result[i++] = message;
      }
    }
    return result;
  }

  public static boolean isInTopic (TdApi.Message message, int forumTopicId) {
    if (message.topicId instanceof TdApi.MessageTopicForum) {
      return ((TdApi.MessageTopicForum) message.topicId).forumTopicId == forumTopicId;
    }
    return message.topicId == null && forumTopicId == GENERAL_TOPIC_ID;
  }

  /**
   * Notification thread: the topic name of a forum message for its notification. Waits briefly for TDLib when the
   * topic isn't cached yet; null for messages outside forums or when it doesn't arrive in time.
   */
  private static final java.util.Set<String> PENDING_NOTIFICATION_TOPICS = java.util.concurrent.ConcurrentHashMap.newKeySet();

  public static void onClientClosed (Tdlib tdlib) {
    tdlib.ui().post(() -> {
      // Before the queue ends its waiters: the badges withdraw their own first.
      ForumUnreadBadges.forgetAccount(tdlib);
      ForumRequests.onClientClosed(tdlib);
      ForumTopicList.forgetAccount(tdlib);
      XgramTopicReadOutbox.forgetAccount(tdlib.id());
      XgramTopicMute.forgetAccount(tdlib.id());
      PENDING_NOTIFICATION_TOPICS.removeIf(key -> key.startsWith(tdlib.id() + "_"));
    });
  }

  @Nullable
  public static String notificationTopicName (Tdlib tdlib, TdApi.Chat chat, @Nullable TdApi.Message message) {
    if (message == null || !(message.topicId instanceof TdApi.MessageTopicForum) || !tdlib.isForum(chat.id)) {
      return null;
    }
    int forumTopicId = ((TdApi.MessageTopicForum) message.topicId).forumTopicId;
    TdlibForumTopicManager.Key key = new TdlibForumTopicManager.Key(chat.id, forumTopicId);
    TdlibForumTopicManager.Entry entry = tdlib.topics().find(key);
    if (entry != null) {
      return entry.value != null ? topicTitle(entry.value.info) : null;
    }
    // Waiting once per topic is enough: while it is still loading (e.g. offline), don't hold up more notifications.
    String pendingKey = tdlib.id() + "_" + chat.id + "_" + forumTopicId;
    if (!PENDING_NOTIFICATION_TOPICS.add(pendingKey)) {
      return null;
    }
    java.util.concurrent.CountDownLatch latch = new java.util.concurrent.CountDownLatch(1);
    java.util.concurrent.atomic.AtomicReference<String> name = new java.util.concurrent.atomic.AtomicReference<>();
    tdlib.topics().findOrRequest(key, (loadedEntry, inPlace) -> {
      PENDING_NOTIFICATION_TOPICS.remove(pendingKey);
      if (loadedEntry.value != null) {
        name.set(topicTitle(loadedEntry.value.info));
      }
      latch.countDown();
    });
    try {
      latch.await(500, java.util.concurrent.TimeUnit.MILLISECONDS);
    } catch (InterruptedException ignored) { }
    return name.get();
  }

  /**
   * Shows the topic name, with "in <group>" under it, when a chat screen is opened for a forum topic, and
   * passes the topic info to {@code onTopicInfo} (on the UI thread) once known.
   * {@code currentTopic} returns the topic the screen shows now: info that arrives after the screen moved on
   * to another chat or topic is dropped.
   */
  public static void bindTopicHeader (ViewController<?> context, ChatHeaderView headerCell, TdApi.Chat chat, @Nullable TdApi.MessageTopic topicId, FutureInt currentTopic, @Nullable RunnableData<TdApi.ForumTopicInfo> onTopicInfo) {
    if (chat == null) {
      // Telegram X builds an empty chat screen ahead of time, before any chat is opened.
      return;
    }
    if (!(topicId instanceof TdApi.MessageTopicForum)) {
      // e.g. the "All" tab after a topic tab: the whole chat's "typing…" again.
      headerCell.xgramSetStatusTopic(chat.id, null);
      return;
    }
    Tdlib tdlib = context.tdlib();
    int forumTopicId = ((TdApi.MessageTopicForum) topicId).forumTopicId;
    headerCell.setForcedSubtitle(Lang.getString(R.string.XgramTopicInChat, tdlib.chatTitle(chat)));
    // The topic list already knows the topic: its name is there before the screen slides in.
    TdApi.ForumTopic cached = ForumTopicList.peekTopic(tdlib, chat.id, forumTopicId);
    if (cached != null) {
      if (onTopicInfo != null) onTopicInfo.runWithData(cached.info);
      else headerCell.setTitle(topicTitle(cached.info));
    }
    // "typing…" from other topics doesn't belong in this topic's header.
    headerCell.xgramSetStatusTopic(chat.id, topicId);
    tdlib.topics().findOrRequest(new TdlibForumTopicManager.Key(chat.id, forumTopicId), (entry, inPlace) -> {
      Runnable act = () -> {
        if (entry.value != null && !context.isDestroyed() &&
          context.getChatId() == chat.id && currentTopic.getIntValue() == forumTopicId) {
          if (onTopicInfo != null) {
            onTopicInfo.runWithData(entry.value.info);
          } else {
            headerCell.setTitle(topicTitle(entry.value.info));
          }
        }
      };
      if (inPlace) {
        act.run();
      } else {
        // The header isn't in the sliding screen's layer: the title and icon change as soon as the info is here, even
        // mid-slide (the message box of a closed topic, which is in that layer, waits: MessagesController#xgramSetTopicInfo).
        tdlib.ui().post(act);
      }
    });
  }

  // Sharing into topics

  /** Result of {@link #pickTopic}: {@code topicId} is null for General, where messages are sent without a topic. */
  public static final class PickedTopic {
    @Nullable public final TdApi.MessageTopic topicId;
    public final String name;

    PickedTopic (@Nullable TdApi.MessageTopic topicId, String name) {
      this.topicId = topicId;
      this.name = name;
    }
  }

  /** Lets the user choose a topic of a forum, e.g. when sharing into it. Nothing happens if the picker is dismissed. */
  public static void pickTopic (ViewController<?> context, long chatId, RunnableData<PickedTopic> onPicked) {
    Tdlib tdlib = context.tdlib();
    ForumTopicList list = ForumTopicList.obtain(tdlib, chatId);
    if (list.isLoaded()) {
      showTopicPicker(context, chatId, list, onPicked);
      return;
    }
    // ForumTopicList holds listeners weakly: keep this one alive until the topics arrive.
    ForumTopicList.Listener listener = new ForumTopicList.Listener() {
      @Override
      public void onTopicsLoaded (ForumTopicList loadedList) {
        loadedList.removeListener(this);
        PENDING_PICKERS.remove(this);
        if (!context.isDestroyed()) {
          showTopicPicker(context, chatId, loadedList, onPicked);
        }
      }
    };
    PENDING_PICKERS.add(listener);
    list.addListener(listener);
    list.loadMore();
  }

  private static final java.util.Set<ForumTopicList.Listener> PENDING_PICKERS = java.util.Collections.newSetFromMap(new java.util.concurrent.ConcurrentHashMap<>());

  private static void showTopicPicker (ViewController<?> context, long chatId, ForumTopicList list, RunnableData<PickedTopic> onPicked) {
    Tdlib tdlib = context.tdlib();
    if (!list.isEndReached() && list.size() < 100) {
      // Only the first page is loaded: fetch up to 100 topics for the picker, so none of them is missing.
      tdlib.send(new TdApi.GetForumTopics(chatId, "", 0, 0, 0, 100), (result, error) -> tdlib.ui().post(() -> {
        if (context.isDestroyed()) {
          return;
        }
        if (result == null && list.size() == 0) {
          // Nothing to choose from: say why instead of sending into General without asking.
          UI.showError(error);
          return;
        }
        showTopicPicker(context, chatId, result != null ? java.util.Arrays.asList(result.topics) : loadedTopics(list), onPicked);
      }));
      return;
    }
    showTopicPicker(context, chatId, loadedTopics(list), onPicked);
  }

  private static java.util.List<TdApi.ForumTopic> loadedTopics (ForumTopicList list) {
    java.util.List<TdApi.ForumTopic> topics = new java.util.ArrayList<>(list.size());
    for (int i = 0; i < list.size(); i++) {
      topics.add(list.get(i));
    }
    return topics;
  }

  private static void showTopicPicker (ViewController<?> context, long chatId, java.util.List<TdApi.ForumTopic> allTopics, RunnableData<PickedTopic> onPicked) {
    Tdlib tdlib = context.tdlib();
    TdApi.Chat chat = tdlib.chat(chatId);
    boolean canManage = canManageTopics(tdlib, chatId);
    // Only topics the user can write in: closed ones (unless they are theirs or they manage topics) and the hidden
    // General for members who can't manage topics would make the share fail later.
    java.util.List<TdApi.ForumTopic> writable = new java.util.ArrayList<>(allTopics.size());
    for (TdApi.ForumTopic topic : allTopics) {
      if (writable.size() >= 100) {
        break;
      }
      if (chat != null && isTopicClosedForMe(tdlib, chat, topic.info)) {
        continue;
      }
      if (topic.info.isHidden && !canManage) {
        continue;
      }
      writable.add(topic);
    }
    int count = writable.size();
    if (count == 0 && !allTopics.isEmpty()) {
      // Every topic is closed for the user (or is the hidden General): a share would only fail.
      UI.showToast(R.string.XgramTopicClosed, android.widget.Toast.LENGTH_SHORT);
      return;
    }
    if (count == 0) {
      onPicked.runWithData(new PickedTopic(null, Lang.getString(R.string.XgramGeneralTopic)));
      return;
    }
    int[] ids = new int[count];
    String[] titles = new String[count];
    int[] icons = new int[count];
    TdApi.ForumTopic[] topics = new TdApi.ForumTopic[count];
    for (int i = 0; i < count; i++) {
      TdApi.ForumTopic topic = writable.get(i);
      topics[i] = topic;
      ids[i] = i + 1;
      titles[i] = topicTitle(topic.info);
      icons[i] = R.drawable.baseline_forum_24;
    }
    context.showOptions(Lang.getString(R.string.XgramSelectTopic, context.tdlib().chatTitle(chatId)), ids, titles, null, icons, (itemView, id) -> {
      TdApi.ForumTopic topic = topics[id - 1];
      TdApi.MessageTopic topicId = topic.info.isGeneral ? null : new TdApi.MessageTopicForum(topic.info.forumTopicId);
      onPicked.runWithData(new PickedTopic(topicId, topicTitle(topic.info)));
      return true;
    });
  }

  // Permissions (official rules: ChatObject.canManageTopics / canDeleteTopic)

  public static boolean canManageTopics (Tdlib tdlib, long chatId) {
    TdApi.ChatMemberStatus status = tdlib.chatStatus(chatId);
    if (status instanceof TdApi.ChatMemberStatusCreator) {
      return true;
    }
    if (status instanceof TdApi.ChatMemberStatusAdministrator) {
      return ((TdApi.ChatMemberStatusAdministrator) status).rights.canManageTopics;
    }
    return false;
  }

  /** In a closed topic only admins with "Manage topics" and the topic's creator can write. */
  public static boolean isTopicClosedForMe (Tdlib tdlib, TdApi.Chat chat, TdApi.ForumTopicInfo info) {
    return info.isClosed && !info.isOutgoing && !canManageTopics(tdlib, chat.id);
  }

  /** Admins always can; other members need the group's "Create topics" permission. */
  public static boolean canCreateTopics (Tdlib tdlib, TdApi.Chat chat) {
    TdApi.ChatMemberStatus status = tdlib.chatStatus(chat.id);
    if (status instanceof TdApi.ChatMemberStatusCreator) {
      return true;
    }
    if (status instanceof TdApi.ChatMemberStatusAdministrator) {
      return ((TdApi.ChatMemberStatusAdministrator) status).rights.canManageTopics || chat.permissions.canCreateTopics;
    }
    if (status instanceof TdApi.ChatMemberStatusRestricted) {
      TdApi.ChatMemberStatusRestricted restricted = (TdApi.ChatMemberStatusRestricted) status;
      return restricted.isMember && restricted.permissions.canCreateTopics;
    }
    if (status instanceof TdApi.ChatMemberStatusMember) {
      return chat.permissions.canCreateTopics;
    }
    return false;
  }

  public static boolean canDeleteTopic (Tdlib tdlib, long chatId, TdApi.ForumTopic topic) {
    if (topic.info.isGeneral) {
      return false;
    }
    TdApi.ChatMemberStatus status = tdlib.chatStatus(chatId);
    if (status instanceof TdApi.ChatMemberStatusCreator) {
      return true;
    }
    if (status instanceof TdApi.ChatMemberStatusAdministrator) {
      return ((TdApi.ChatMemberStatusAdministrator) status).rights.canDeleteMessages;
    }
    return false;
  }

  // Actions

  // Tabs

  /** TDLib's forum topic id of the General topic. */
  public static final int GENERAL_TOPIC_ID = 1;
  /** Tab id of the merged "All" view. */
  public static final int TAB_ALL = 0;

  /**
   * Forums open on a topic with a tab strip instead of the topic list when their admins chose the tabs layout, unless
   * the user chose Tabs or List for themselves (the group profile's Topics row, kept on this phone only).
   */
  public static boolean hasForumTabs (Tdlib tdlib, @Nullable TdApi.Chat chat) {
    if (chat == null || !tdlib.isForum(chat.id)) {
      return false;
    }
    switch (ForumSettings.instance().forumLayout(tdlib.id(), chat.id)) {
      case ForumSettings.FORUM_LAYOUT_TABS:
        return true;
      case ForumSettings.FORUM_LAYOUT_LIST:
        return false;
    }
    return groupHasForumTabs(tdlib, chat);
  }

  /** The layout the group's admins chose for everyone: tabs, or (false) the topic list. */
  public static boolean groupHasForumTabs (Tdlib tdlib, @Nullable TdApi.Chat chat) {
    if (chat == null || !tdlib.isForum(chat.id)) {
      return false;
    }
    TdApi.Supergroup supergroup = tdlib.chatToSupergroup(chat.id);
    return supergroup != null && supergroup.hasForumTabs;
  }

  // The user's own topics layout (group profile → Topics), for members who can't change the group's

  public static String topicsViewLabel (Tdlib tdlib, TdApi.Chat chat) {
    return Lang.getString(hasForumTabs(tdlib, chat) ? R.string.XgramTopicsTabs : R.string.XgramTopicsList);
  }

  /** Group's choice, Tabs or List, for this user only; the chat opens in it from then on. */
  public static void promptTopicsView (ViewController<?> context, TdApi.Chat chat, Runnable onChanged) {
    Tdlib tdlib = context.tdlib();
    final int current = ForumSettings.instance().forumLayout(tdlib.id(), chat.id);
    final String groupChoice = Lang.getString(R.string.XgramTopicsViewGroup, Lang.getString(groupHasForumTabs(tdlib, chat) ? R.string.XgramTopicsTabs : R.string.XgramTopicsList));
    int[] ids = {R.id.btn_xgramTopicsViewGroup, R.id.btn_xgramTopicsViewTabs, R.id.btn_xgramTopicsViewList};
    String[] titles = {groupChoice, Lang.getString(R.string.XgramTopicsTabs), Lang.getString(R.string.XgramTopicsList)};
    int[] layouts = {ForumSettings.FORUM_LAYOUT_GROUP, ForumSettings.FORUM_LAYOUT_TABS, ForumSettings.FORUM_LAYOUT_LIST};
    RunnableInt apply = layout -> {
      if (layout != current) {
        ForumSettings.instance().setForumLayout(tdlib.id(), chat.id, layout);
        onChanged.run();
      }
    };

    int[] icons = new int[ids.length];
    for (int i = 0; i < ids.length; i++) {
      icons[i] = layouts[i] == current ? R.drawable.baseline_check_24 : 0;
    }
    context.showOptions(Lang.getString(R.string.XgramTopicsViewDesc), ids, titles, null, icons, (itemView, id) -> {
      apply.runWithInt(id == R.id.btn_xgramTopicsViewTabs ? ForumSettings.FORUM_LAYOUT_TABS : id == R.id.btn_xgramTopicsViewList ? ForumSettings.FORUM_LAYOUT_LIST : ForumSettings.FORUM_LAYOUT_GROUP);
      return true;
    });
  }

  public static int lastTab (Tdlib tdlib, long chatId) {
    return ForumSettings.instance().lastForumTab(tdlib.id(), chatId, GENERAL_TOPIC_ID);
  }

  public static void setLastTab (Tdlib tdlib, long chatId, int tab) {
    ForumSettings.instance().setLastForumTab(tdlib.id(), chatId, tab);
  }

  /**
   * The topic's first unread message, or null when it's read (open at the bottom). Unread mentions alone don't
   * count: the mention button reaches them. The topic must be normalized ({@link #normalizeUnread}).
   */
  @Nullable
  public static MessageId topicUnreadAnchor (Tdlib tdlib, long chatId, @Nullable TdApi.ForumTopic topic) {
    if (topic == null || topic.unreadCount <= 0) {
      return null;
    }
    long readId = topicReadInboxId(tdlib, chatId, topic);
    return new MessageId(chatId, readId != 0 ? readId : MessageId.MIN_VALID_ID);
  }

  /** Where a topic opens: at its first unread message, else where it was left, else at the bottom. */
  public static final class TopicResume {
    public final int highlightMode;
    @Nullable public final MessageId anchor;

    TopicResume (int highlightMode, @Nullable MessageId anchor) {
      this.highlightMode = highlightMode;
      this.anchor = anchor;
    }
  }

  public static TopicResume topicResume (Tdlib tdlib, long chatId, int forumTopicId, @Nullable TdApi.ForumTopic topic) {
    MessageId unread = topicUnreadAnchor(tdlib, chatId, topic);
    if (unread != null) {
      return new TopicResume(MessagesManager.HIGHLIGHT_MODE_UNREAD, unread);
    }
    // The position MessagesManager saves under the topic's own key when the topic is left.
    org.thunderdog.challegram.unsorted.Settings.SavedMessageId saved = org.thunderdog.challegram.unsorted.Settings.instance()
      .getScrollMessageId(tdlib.id(), chatId, new TdApi.MessageTopicForum(forumTopicId));
    if (saved != null && saved.id != null && saved.id.getChatId() == chatId && saved.id.getMessageId() != 0) {
      return new TopicResume(MessagesManager.HIGHLIGHT_MODE_POSITION_RESTORE, saved.id);
    }
    return new TopicResume(MessagesManager.HIGHLIGHT_MODE_NONE, null);
  }

  /**
   * The topic as the app already knows it, normalized: the cached topic list (normalized when stored), else a
   * normalized copy from TDLib's topic cache. UI thread only.
   */
  @Nullable
  private static TdApi.ForumTopic knownTopic (Tdlib tdlib, long chatId, int forumTopicId) {
    TdApi.ForumTopic topic = ForumTopicList.peekTopic(tdlib, chatId, forumTopicId);
    if (topic == null) {
      TdlibForumTopicManager.Entry entry = tdlib.topics().find(new TdlibForumTopicManager.Key(chatId, forumTopicId));
      topic = entry != null && !entry.isNotFound() && entry.value != null ? normalizedCopy(tdlib, entry.value) : null;
    }
    return topic;
  }

  /**
   * Whether the open history has unread messages, for the "Unread messages" separator: the thread's state in a
   * thread, the topic's own inside a forum topic (the chat's unread count is the sum over every topic), else the chat's.
   */
  public static boolean topicHasUnread (MessagesController controller, TdApi.Chat chat) {
    org.thunderdog.challegram.data.ThreadInfo messageThread = controller.getMessageThread();
    if (messageThread != null) {
      return messageThread.hasUnreadMessages(chat);
    }
    if (controller.getMessageTopicId() instanceof TdApi.MessageTopicForum) {
      TdApi.ForumTopic topic = controller.xgramTopicReadState();
      return topic != null && topic.unreadCount > 0;
    }
    return chat.unreadCount > 0;
  }

  /** Opening a forum with tabs: the last tab, at its first unread message. */
  public static void prepareTabsOpen (Tdlib tdlib, TdApi.Chat chat, TdlibUi.ChatOpenParameters params) {
    params.xgramSkipForumRouting();
    int tab = lastTab(tdlib, chat.id);
    if (tab == TAB_ALL) {
      // Merged history keeps the chat's own resume position.
      return;
    }
    params.messageTopicId = new TdApi.MessageTopicForum(tab);
    TdApi.ForumTopic topic = knownTopic(tdlib, chat.id, tab);
    params.forumTopicTitle = topic != null ? topicTitle(topic.info) : null;
    TopicResume resume = topicResume(tdlib, chat.id, tab, topic);
    params.highlightMessage(resume.highlightMode, resume.anchor);
  }

  /** Arguments that switch an open forum chat to another tab in place. */
  public static MessagesController.Arguments tabArguments (Tdlib tdlib, @Nullable TdApi.ChatList chatList, TdApi.Chat chat, int tab) {
    if (tab == TAB_ALL) {
      MessagesManager.DefaultAnchor resolved = MessagesManager.resolveDefaultAnchor(tdlib.id(), chat, null);
      int mode = resolved.highlightMode;
      MessageId anchor = resolved.messageId;
      return new MessagesController.Arguments(chatList, chat, null, null, anchor, anchor != null ? mode : MessagesManager.HIGHLIGHT_MODE_NONE, null);
    }
    TdApi.ForumTopic topic = knownTopic(tdlib, chat.id, tab);
    TopicResume resume = topicResume(tdlib, chat.id, tab, topic);
    return new MessagesController.Arguments(chatList, chat, null, new TdApi.MessageTopicForum(tab), resume.anchor, resume.highlightMode, null)
      .setForumTopicTitle(topic != null ? topicTitle(topic.info) : null);
  }

  // Group settings: topics on or off, and their layout

  /** Only the owner can turn topics on or off; discussion groups of channels can't have topics. */
  public static boolean canToggleTopics (Tdlib tdlib, @Nullable TdApi.Chat chat, @Nullable TdApi.SupergroupFullInfo supergroupFull) {
    if (chat == null || tdlib.isChannel(chat.id) || !(tgx.td.ChatId.isSupergroup(chat.id) || tgx.td.ChatId.isBasicGroup(chat.id))) {
      return false;
    }
    if (!org.thunderdog.challegram.data.TD.isCreator(tdlib.chatStatus(chat.id))) {
      return false;
    }
    return supergroupFull == null || supergroupFull.linkedChatId == 0;
  }

  public static String topicsModeLabel (Tdlib tdlib, TdApi.Chat chat) {
    if (!tdlib.isForum(chat.id)) {
      return Lang.getString(R.string.XgramTopicsOff);
    }
    return Lang.getString(groupHasForumTabs(tdlib, chat) ? R.string.XgramTopicsTabs : R.string.XgramTopicsList);
  }

  /** Off, tabs or list. Basic groups are upgraded to supergroups first, as topics need one. */
  public static void promptTopicsMode (ViewController<?> context, TdApi.Chat chat, Runnable onChanged) {
    Tdlib tdlib = context.tdlib();
    int current = !tdlib.isForum(chat.id) ? 0 : groupHasForumTabs(tdlib, chat) ? 1 : 2;
    int[] ids = {R.id.btn_xgramTopicsOff, R.id.btn_xgramTopicsTabs, R.id.btn_xgramTopicsList};
    String[] titles = {Lang.getString(R.string.XgramTopicsOff), Lang.getString(R.string.XgramTopicsTabs), Lang.getString(R.string.XgramTopicsList)};

    int[] colors = {ViewController.OptionColor.NORMAL, ViewController.OptionColor.NORMAL, ViewController.OptionColor.NORMAL};
    int[] icons = new int[3];
    icons[current] = R.drawable.baseline_check_24;
    context.showOptions(Lang.getString(R.string.XgramTopicsDesc), ids, titles, colors, icons, (itemView, id) -> {
      int mode = id == R.id.btn_xgramTopicsTabs ? 1 : id == R.id.btn_xgramTopicsList ? 2 : 0;
      if (mode == current) {
        return true;
      }
      boolean isForum = mode != 0, hasTabs = mode == 1;
      RunnableLong apply = supergroupChatId -> tdlib.send(new TdApi.ToggleSupergroupIsForum(tgx.td.ChatId.toSupergroupId(supergroupChatId), isForum, hasTabs), (ok, error) -> tdlib.ui().post(() -> {
        if (error != null) {
          UI.showError(error);
        } else {
          onChanged.run();
        }
      }));
      if (tgx.td.ChatId.isBasicGroup(chat.id)) {
        if (!isForum) {
          return true;
        }
        tdlib.upgradeToSupergroup(chat.id, (fromChatId, toChatId, error) -> {
          if (error != null) {
            tdlib.ui().post(() -> UI.showError(error));
          } else {
            apply.runWithLong(toChatId);
          }
        });
      } else {
        apply.runWithLong(chat.id);
      }
      return true;
    });
  }

  /** XGram M3E: the topics mode chosen in the radio sheet, applied as the options above do (a basic group upgrades). */
  private static void applyTopicsMode (Tdlib tdlib, TdApi.Chat chat, int mode, Runnable onChanged) {
    boolean isForum = mode != 0, hasTabs = mode == 1;
    RunnableLong apply = supergroupChatId -> tdlib.send(new TdApi.ToggleSupergroupIsForum(tgx.td.ChatId.toSupergroupId(supergroupChatId), isForum, hasTabs), (ok, error) -> tdlib.ui().post(() -> {
      if (error != null) {
        UI.showError(error);
      } else {
        onChanged.run();
      }
    }));
    if (tgx.td.ChatId.isBasicGroup(chat.id)) {
      if (!isForum) {
        return;
      }
      tdlib.upgradeToSupergroup(chat.id, (fromChatId, toChatId, error) -> {
        if (error != null) {
          tdlib.ui().post(() -> UI.showError(error));
        } else {
          apply.runWithLong(toChatId);
        }
      });
    } else {
      apply.runWithLong(chat.id);
    }
  }

  public static boolean isTopicMuted (Tdlib tdlib, long chatId, TdApi.ForumTopic topic) {
    TdApi.ChatNotificationSettings settings = topic.notificationSettings;
    if (settings == null || settings.useDefaultMuteFor) {
      return !tdlib.chatNotificationsEnabled(chatId);
    }
    return settings.muteFor > 0;
  }

  /** Long-press menu of a topic, shared by the topic list and the tabs. */
  public static void showTopicOptions (ViewController<?> context, TdApi.Chat chat, TdApi.ForumTopic topic) {
    final Tdlib tdlib = context.tdlib();
    final int forumTopicId = topic.info.forumTopicId;
    final boolean canManageTopics = canManageTopics(tdlib, chat.id);
    final boolean canManageTopic = canManageTopics || topic.info.isOutgoing;
    final boolean canDelete = canDeleteTopic(tdlib, chat.id, topic);
    final boolean isMuted = isTopicMuted(tdlib, chat.id, topic);

    IntList ids = new IntList(6);
    StringList titles = new StringList(6);
    IntList colors = new IntList(6);
    IntList icons = new IntList(6);

    if (topic.unreadCount > 0 || topic.unreadMentionCount > 0 || topic.unreadReactionCount > 0) {
      ids.append(R.id.btn_xgramTopicRead);
      titles.append(R.string.XgramMarkTopicAsRead);
      colors.append(ViewController.OptionColor.NORMAL);
      icons.append(R.drawable.baseline_done_all_24);
    }
    ids.append(R.id.btn_xgramTopicMute);
    titles.append(isMuted ? R.string.XgramUnmuteTopic : R.string.XgramMuteTopic);
    colors.append(ViewController.OptionColor.NORMAL);
    icons.append(isMuted ? R.drawable.baseline_notifications_24 : R.drawable.baseline_notifications_off_24);
    if (canManageTopics && !topic.info.isHidden) {
      ids.append(R.id.btn_xgramTopicPin);
      titles.append(topic.isPinned ? R.string.XgramUnpinTopic : R.string.XgramPinTopic);
      colors.append(ViewController.OptionColor.NORMAL);
      icons.append(topic.isPinned ? R.drawable.deproko_baseline_pin_undo_24 : R.drawable.deproko_baseline_pin_24);
    }
    if (canManageTopic) {
      ids.append(R.id.btn_xgramTopicEdit);
      titles.append(R.string.XgramEditTopic);
      colors.append(ViewController.OptionColor.NORMAL);
      icons.append(R.drawable.baseline_edit_24);
    }
    if (canManageTopic && !topic.info.isHidden) {
      ids.append(R.id.btn_xgramTopicClose);
      titles.append(topic.info.isClosed ? R.string.XgramReopenTopic : R.string.XgramCloseTopic);
      colors.append(ViewController.OptionColor.NORMAL);
      icons.append(R.drawable.baseline_lock_24);
    }
    if (canManageTopics && topic.info.isGeneral) {
      ids.append(R.id.btn_xgramTopicHideGeneral);
      titles.append(topic.info.isHidden ? R.string.XgramShowGeneralTopic : R.string.XgramHideGeneralTopic);
      colors.append(ViewController.OptionColor.NORMAL);
      icons.append(topic.info.isHidden ? R.drawable.baseline_visibility_24 : R.drawable.baseline_eye_off_24);
    }
    ids.append(R.id.btn_xgramTopicCopyLink);
    titles.append(R.string.CopyLink);
    colors.append(ViewController.OptionColor.NORMAL);
    icons.append(R.drawable.baseline_link_24);
    if (canDelete) {
      ids.append(R.id.btn_xgramTopicDelete);
      titles.append(R.string.XgramDeleteTopic);
      colors.append(ViewController.OptionColor.RED);
      icons.append(R.drawable.baseline_delete_24);
    }

    context.showOptions(topicTitle(topic.info), ids.get(), titles.get(), colors.get(), icons.get(), (itemView, id) -> {
      if (id == R.id.btn_xgramTopicRead) {
        markTopicAsRead(tdlib, chat.id, topic);
      } else if (id == R.id.btn_xgramTopicMute) {
        if (isMuted) {
          setTopicMuted(tdlib, chat.id, topic, false);
        } else {
          promptMuteTopic(context, chat, topic);
        }
      } else if (id == R.id.btn_xgramTopicPin) {
        tdlib.send(new TdApi.ToggleForumTopicIsPinned(chat.id, forumTopicId, !topic.isPinned), tdlib.typedOkHandler());
      } else if (id == R.id.btn_xgramTopicEdit) {
        openTopicEditor(context, chat, topic);
      } else if (id == R.id.btn_xgramTopicClose) {
        tdlib.send(new TdApi.ToggleForumTopicIsClosed(chat.id, forumTopicId, !topic.info.isClosed), tdlib.typedOkHandler());
      } else if (id == R.id.btn_xgramTopicHideGeneral) {
        tdlib.send(new TdApi.ToggleGeneralForumTopicIsHidden(chat.id, !topic.info.isHidden), tdlib.typedOkHandler());
      } else if (id == R.id.btn_xgramTopicCopyLink) {
        tdlib.send(new TdApi.GetForumTopicLink(chat.id, forumTopicId), (link, error) -> tdlib.ui().post(() -> {
          if (link != null) {
            UI.copyText(link.link, link.isPublic ? R.string.CopiedLink : R.string.CopiedLinkPrivate);
          } else {
            UI.showError(error);
          }
        }));
      } else if (id == R.id.btn_xgramTopicDelete) {
        confirmDeleteTopic(context, chat, topic);
      }
      return true;
    });
  }

  private static void confirmDeleteTopic (ViewController<?> context, TdApi.Chat chat, TdApi.ForumTopic topic) {
    Tdlib tdlib = context.tdlib();
    context.showOptions(Lang.getString(R.string.XgramDeleteTopicConfirm, topic.info.name),
      new int[] {R.id.btn_xgramTopicDelete, R.id.btn_cancel},
      new String[] {Lang.getString(R.string.XgramDeleteTopic), Lang.getString(R.string.Cancel)},
      new int[] {ViewController.OptionColor.RED, ViewController.OptionColor.NORMAL},
      new int[] {R.drawable.baseline_delete_24, R.drawable.baseline_cancel_24},
      (itemView, id) -> {
        if (id == R.id.btn_xgramTopicDelete) {
          int forumTopicId = topic.info.forumTopicId;
          // TDLib sends no update for a deleted topic: the list drops it once the server agrees.
          tdlib.send(new TdApi.DeleteForumTopic(chat.id, forumTopicId), tdlib.typedOkHandler(() -> {
            ForumTopicList.onTopicDeleted(tdlib, chat.id, forumTopicId);
            ForumUnreadBadges.onTopicDeleted(tdlib, chat.id, forumTopicId);
          }));
        }
        return true;
      });
  }

  /** Opens the topic editor: name, color and icon. {@code topic} is null to create a new one. */
  public static void openTopicEditor (ViewController<?> context, TdApi.Chat chat, @Nullable TdApi.ForumTopic topic) {
    ForumTopicEditController c = new ForumTopicEditController(context.context(), context.tdlib());
    c.setArguments(new ForumTopicEditController.Args(chat, topic));
    context.navigateTo(c);
  }

  public static void markTopicAsRead (Tdlib tdlib, long chatId, TdApi.ForumTopic topic) {
    if (topic.unreadMentionCount > 0) {
      tdlib.send(new TdApi.ReadAllForumTopicMentions(chatId, topic.info.forumTopicId), tdlib.typedOkHandler());
    }
    if (topic.unreadReactionCount > 0) {
      tdlib.send(new TdApi.ReadAllForumTopicReactions(chatId, topic.info.forumTopicId), tdlib.typedOkHandler());
    }
    if (topic.lastMessage != null && topic.unreadCount > 0) {
      tdlib.send(new TdApi.ViewMessages(chatId, new long[] {topic.lastMessage.id}, new TdApi.MessageSourceForumTopicHistory(), true), tdlib.typedOkHandler());
    }
  }

  /** Marks every topic of a forum as read on the server: mentions and reactions at once, then each unread topic. */
  public static void markAllTopicsAsRead (Tdlib tdlib, long chatId) {
    tdlib.send(new TdApi.ReadAllChatMentions(chatId), tdlib.typedOkHandler());
    tdlib.send(new TdApi.ReadAllChatReactions(chatId), tdlib.typedOkHandler());
    // Topics are sorted by their last message, so unread ones come first.
    tdlib.send(new TdApi.GetForumTopics(chatId, "", 0, 0, 0, 100), (topics, error) -> {
      if (topics == null) {
        return;
      }
      for (TdApi.ForumTopic topic : topics.topics) {
        if (topic.lastMessage != null && topic.unreadCount > 0) {
          tdlib.send(new TdApi.ViewMessages(chatId, new long[] {topic.lastMessage.id}, new TdApi.MessageSourceForumTopicHistory(), true), tdlib.typedOkHandler());
        }
      }
    });
  }

  public static void setTopicMuted (Tdlib tdlib, long chatId, TdApi.ForumTopic topic, boolean mute) {
    setTopicMuteFor(tdlib, chatId, topic, mute ? Integer.MAX_VALUE : 0);
  }

  public static void setTopicMuteFor (Tdlib tdlib, long chatId, TdApi.ForumTopic topic, int muteForSeconds) {
    TdApi.ChatNotificationSettings current = topic.notificationSettings;
    TdApi.ChatNotificationSettings settings = copyOf(current);
    settings.useDefaultMuteFor = false;
    settings.muteFor = muteForSeconds;
    XgramTopicMute.onSettings(tdlib, chatId, topic.info.forumTopicId, settings); // notifications follow right away
    tdlib.send(new TdApi.SetForumTopicNotificationSettings(chatId, topic.info.forumTopicId, settings), tdlib.typedOkHandler());
  }

  /** Mute for 1 hour, 8 hours, 2 days or forever, like the official app. */
  public static void promptMuteTopic (ViewController<?> context, TdApi.Chat chat, TdApi.ForumTopic topic) {
    Tdlib tdlib = context.tdlib();
    int[] durations = {3600, 8 * 3600, 2 * 86400, Integer.MAX_VALUE};
    int[] ids = {R.id.btn_xgramMute1h, R.id.btn_xgramMute8h, R.id.btn_xgramMute2d, R.id.btn_xgramMuteForever};
    String[] titles = {
      Lang.getString(R.string.XgramMuteFor, Lang.plural(R.string.xHours, 1)),
      Lang.getString(R.string.XgramMuteFor, Lang.plural(R.string.xHours, 8)),
      Lang.getString(R.string.XgramMuteFor, Lang.plural(R.string.xDays, 2)),
      Lang.getString(R.string.XgramMuteForever)
    };
    context.showOptions(topicTitle(topic.info), ids, titles, null, null, (itemView, id) -> {
      for (int i = 0; i < ids.length; i++) {
        if (ids[i] == id) {
          setTopicMuteFor(tdlib, chat.id, topic, durations[i]);
        }
      }
      return true;
    });
  }

  private static TdApi.ChatNotificationSettings copyOf (@Nullable TdApi.ChatNotificationSettings s) {
    if (s == null) {
      return new TdApi.ChatNotificationSettings(true, 0, true, 0, true, false, true, false, true, 0, true, false, true, false, true, false);
    }
    return new TdApi.ChatNotificationSettings(
      s.useDefaultMuteFor, s.muteFor,
      s.useDefaultSound, s.soundId,
      s.useDefaultShowPreview, s.showPreview,
      s.useDefaultMuteStories, s.muteStories,
      s.useDefaultStorySound, s.storySoundId,
      s.useDefaultShowStoryPoster, s.showStoryPoster,
      s.useDefaultDisablePinnedMessageNotifications, s.disablePinnedMessageNotifications,
      s.useDefaultDisableMentionNotifications, s.disableMentionNotifications
    );
  }
}
