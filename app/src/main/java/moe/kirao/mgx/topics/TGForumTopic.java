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

import android.view.Gravity;
import android.view.View;

import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.U;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.data.ContentPreview;
import org.thunderdog.challegram.loader.ComplexReceiver;
import org.thunderdog.challegram.navigation.ViewController;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.telegram.TdlibStatusManager;
import org.thunderdog.challegram.tool.Icons;
import org.thunderdog.challegram.tool.Paints;
import org.thunderdog.challegram.tool.Screen;
import org.thunderdog.challegram.util.text.Counter;
import org.thunderdog.challegram.util.text.Text;
import org.thunderdog.challegram.util.text.TextColorSets;
import org.thunderdog.challegram.util.text.TextEntity;
import org.thunderdog.challegram.util.text.TextStyleProvider;

import java.util.concurrent.TimeUnit;

import me.vkryl.android.util.MultipleViewProvider;
import me.vkryl.core.StringUtils;
import me.vkryl.core.collection.IntList;
import tgx.td.Td;

/**
 * Layout of one row in the forum topic list, modeled on {@link org.thunderdog.challegram.data.TGChat}.
 */
public final class TGForumTopic implements Counter.Callback, ContentPreview.RefreshCallback, TdlibStatusManager.HelperTarget {
  private final ViewController<?> context;
  private final Tdlib tdlib;
  private final long chatId;
  private TdApi.ForumTopic topic;

  private final MultipleViewProvider currentViews = new MultipleViewProvider();
  private final Counter counter, mentionCounter, reactionsCounter;
  private ForumTopicIconDrawable iconDrawable;
  // What iconDrawable was built from. A rename arrives on the same ForumTopic object the row already holds,
  // so comparing the new info with this.topic.info would never notice it.
  private String iconName;
  private int iconColor;
  private long iconCustomEmojiId;
  private boolean iconIsGeneral;

  private int currentWidth;
  private Text title;
  private String time = "";
  private int timeWidth, timeLeft, checksRight, muteLeft, lockLeft;

  private boolean hasPrefix, isDraft;
  private Text prefix, text;
  private String textValue;
  private TextEntity[] textEntities;
  private IntList textIconIds;
  private int textLeft, textIconsPadding;
  private ContentPreview currentPreview;

  public TGForumTopic (ViewController<?> context, long chatId, TdApi.ForumTopic topic) {
    this.context = context;
    this.tdlib = context.tdlib();
    this.chatId = chatId;
    this.topic = topic;
    this.counter = new Counter.Builder().callback(this).build();
    this.mentionCounter = new Counter.Builder()
      .drawable(R.drawable.baseline_at_16, 16f, 0f, Gravity.CENTER)
      .callback(this)
      .build();
    this.reactionsCounter = new Counter.Builder()
      .drawable(R.drawable.baseline_favorite_14, 16f, 0f, Gravity.CENTER)
      .callback(this)
      .build();
    buildIcon(topic.info);
    this.statusHelper = new TdlibStatusManager.Helper(context.context(), tdlib, this, context);
    setCounter(false);
  }

  private void buildIcon (TdApi.ForumTopicInfo info) {
    iconDrawable = new ForumTopicIconDrawable(info);
    iconName = info.name;
    iconColor = info.icon != null ? info.icon.color : 0;
    iconCustomEmojiId = info.icon != null ? info.icon.customEmojiId : 0;
    iconIsGeneral = info.isGeneral;
  }

  private boolean iconMatches (TdApi.ForumTopicInfo info) {
    return StringUtils.equalsOrBothEmpty(iconName, info.name) &&
      iconColor == (info.icon != null ? info.icon.color : 0) &&
      iconCustomEmojiId == (info.icon != null ? info.icon.customEmojiId : 0) &&
      iconIsGeneral == info.isGeneral;
  }

  public long getChatId () {
    return chatId;
  }

  public int getForumTopicId () {
    return topic.info.forumTopicId;
  }

  public TdApi.ForumTopic getTopic () {
    return topic;
  }

  /** Replaces the topic data; the list keeps rows for the same topic id. */
  public void setTopic (TdApi.ForumTopic topic) {
    this.topic = topic;
    if (!iconMatches(topic.info)) {
      buildIcon(topic.info);
    }
    setCounter(needAnimateChanges());
    if (currentWidth > 0) {
      int width = currentWidth;
      currentWidth = 0;
      checkLayout(width);
    }
    currentViews.invalidate();
  }

  public ForumTopicIconDrawable getIconDrawable () {
    return iconDrawable;
  }

  public long getIconCustomEmojiId () {
    return topic.info.icon != null && !topic.info.isGeneral ? topic.info.icon.customEmojiId : 0;
  }

  // Views

  public void attachToView (View view) {
    if (currentViews.attachToView(view)) {
      setViewAttached(currentViews.hasAnyTargetToInvalidate());
    }
  }

  public void detachFromView (View view) {
    if (currentViews.detachFromView(view)) {
      setViewAttached(currentViews.hasAnyTargetToInvalidate());
    }
  }

  // "Alice is typing…" in the topic row, like chats (only while a row shows the topic).

  private final TdlibStatusManager.Helper statusHelper;
  private boolean isViewAttached;

  private void setViewAttached (boolean isAttached) {
    if (this.isViewAttached != isAttached) {
      this.isViewAttached = isAttached;
      if (isAttached) {
        statusHelper.attachToChat(chatId, new TdApi.MessageTopicForum(topic.info.forumTopicId));
      } else {
        statusHelper.detachFromAnyChat();
      }
    }
  }

  public TdlibStatusManager.Helper statusHelper () {
    return statusHelper;
  }

  @Override
  public void layoutChatAction () {
    String chatActionText = statusHelper.fullText();
    Text trimmed = null;
    if (!StringUtils.isEmpty(chatActionText)) {
      int avail = currentWidth - ForumTopicView.getTextLeft() - ForumTopicView.getRightPaddingPx() - getCounterAddWidth();
      int iconWidth = statusHelper.actionIconWidth();
      if (avail > 0) {
        Text.Builder b = new Text.Builder(chatActionText, avail, textStyleProvider(), TextColorSets.Regular.LIGHT).singleLine();
        if (iconWidth > 0) {
          b.lineMarginProvider((lineIndex, y, defaultMaxWidth, lineHeight) -> lineIndex == 0 ? iconWidth : 0);
        }
        trimmed = b.build();
      }
    }
    statusHelper.setDrawingText(trimmed);
  }

  @Override
  public void invalidateTypingPart (boolean onlyIcon) {
    currentViews.invalidate();
  }

  @Override
  public boolean canLoop () {
    return isViewAttached;
  }

  @Override
  public boolean canAnimate () {
    return isViewAttached && currentViews.hasAnyTargetToInvalidate() && context.getAttachState();
  }

  @Override
  public void onCounterAppearanceChanged (Counter counter, boolean sizeChanged) {
    if (sizeChanged && currentWidth > 0) {
      layoutText();
    }
    currentViews.invalidate();
  }

  @Override
  public boolean needAnimateChanges (Counter counter) {
    return needAnimateChanges();
  }

  private boolean needAnimateChanges () {
    View view = currentViews.findAnyTarget();
    return view != null && context.isAttachedToNavigationController();
  }

  // State

  public boolean isMuted () {
    TdApi.ChatNotificationSettings settings = topic.notificationSettings;
    if (settings == null || settings.useDefaultMuteFor) {
      return !tdlib.chatNotificationsEnabled(chatId);
    }
    return settings.muteFor > 0;
  }

  public boolean isClosed () {
    return topic.info.isClosed;
  }

  public boolean isPinned () {
    return topic.isPinned;
  }

  private boolean showDraft () {
    return topic.draftMessage != null && topic.draftMessage.content instanceof TdApi.DraftMessageContentText &&
      !Td.isEmpty(((TdApi.DraftMessageContentText) topic.draftMessage.content).text);
  }

  public boolean isOutgoing () {
    return !showDraft() && topic.lastMessage != null && topic.lastMessage.isOutgoing;
  }

  /** Outgoing last message that the other side hasn't read yet. */
  public boolean isUnread () {
    return topic.lastMessage != null && topic.lastMessage.id > topic.lastReadOutboxMessageId;
  }

  public boolean isSending () {
    return topic.lastMessage != null && tdlib.messageSending(topic.lastMessage);
  }

  private void setCounter (boolean animated) {
    boolean muted = isMuted();
    boolean hasMentions = topic.unreadMentionCount > 0;
    reactionsCounter.setCount(topic.unreadReactionCount > 0 ? Tdlib.CHAT_MARKED_AS_UNREAD : 0, muted, animated);
    mentionCounter.setCount(hasMentions ? Tdlib.CHAT_MARKED_AS_UNREAD : 0, false, animated);
    counter.setCount(hasMentions && topic.unreadCount == 1 ? 0 : topic.unreadCount, muted, animated);
  }

  public Counter getCounter () {
    return counter;
  }

  public Counter getMentionCounter () {
    return mentionCounter;
  }

  public Counter getReactionsCounter () {
    return reactionsCounter;
  }

  // Layout

  public boolean checkLayout (int width) {
    if (width > 0 && currentWidth != width) {
      currentWidth = width;
      setTime();
      layoutTitle();
      setText();
      layoutChatAction();
      return true;
    }
    return false;
  }

  private static TextStyleProvider titleStyleProvider () {
    return Paints.robotoStyleProvider(16);
  }

  private static TextStyleProvider textStyleProvider () {
    return Paints.robotoStyleProvider(15);
  }

  private void setTime () {
    int date = showDraft() ? topic.draftMessage.date : topic.lastMessage != null ? topic.lastMessage.date : topic.info.creationDate;
    time = date != 0 ? Lang.timeOrDateShort(date, TimeUnit.SECONDS) : "";
    timeWidth = (int) U.measureText(time, ForumTopicView.getTimePaint());
    timeLeft = currentWidth - ForumTopicView.getRightPaddingPx() - timeWidth;
    checksRight = timeLeft - Screen.dp(7f);
    lockLeft = timeLeft - Screen.dp(4f) - Screen.dp(16f);
  }

  private void layoutTitle () {
    int avail = currentWidth - ForumTopicView.getTextLeft() - timeWidth - ForumTopicView.getRightPaddingPx() - Screen.dp(7f);
    if (isClosed()) {
      avail -= Screen.dp(20f);
    }
    if (isOutgoing() || isSending()) {
      avail -= Screen.dp(20f);
    }
    if (isMuted()) {
      avail -= Screen.dp(1f) + Icons.getChatMuteDrawableWidth();
    }
    String name = StringUtils.isEmpty(topic.info.name) && topic.info.isGeneral ? Lang.getString(R.string.XgramGeneralTopic) : topic.info.name;
    if (avail > 0 && !StringUtils.isEmpty(name)) {
      title = new Text.Builder(name, avail, titleStyleProvider(), TextColorSets.Regular.NORMAL)
        .singleLine()
        .allBold()
        .clipTextArea()
        .build();
    } else {
      title = null;
    }
    muteLeft = ForumTopicView.getTextLeft() + (title != null ? title.getWidth() : 0) + Screen.dp(1f);
  }

  private void setText () {
    hasPrefix = false;
    isDraft = false;
    currentPreview = null;
    if (textIconIds != null) {
      textIconIds.clear();
    }
    if (showDraft()) {
      isDraft = true;
      hasPrefix = true;
      TdApi.FormattedText draft = ((TdApi.DraftMessageContentText) topic.draftMessage.content).text;
      setTextValue(draft.text, TextEntity.valueOf(tdlib, draft.text, draft.entities, null));
      setPrefix();
      return;
    }
    TdApi.Message msg = topic.lastMessage;
    if (msg != null && (!moe.kirao.mgx.MoexShadowUnreadManager.areHiddenUsersReady(tdlib) ||
      moe.kirao.mgx.MoexMessageFilter.matches(tdlib, msg))) {
      setTextValue(Lang.getString(R.string.FilteredMessage), null);
      setPrefix();
      return;
    }
    if (msg == null) {
      setTextValue(Lang.getString(R.string.XgramTopicNoMessages), null);
      setPrefix();
      return;
    }
    setContentPreview(ContentPreview.getChatListPreview(tdlib, chatId, msg, false));
  }

  private void setContentPreview (ContentPreview preview) {
    currentPreview = preview;
    if (textIconIds != null) {
      textIconIds.clear();
    }
    String value = preview.buildText(true);
    setTextValue(value, preview.formattedText != null ? TextEntity.valueOf(tdlib, value, preview.formattedText.entities, null) : null);
    if (preview.parentEmoji != null) {
      addIcon(preview.parentEmoji.iconRepresentation);
    }
    if (preview.emoji != null) {
      addIcon(preview.emoji.iconRepresentation);
    }
    hasPrefix = !preview.hideAuthor && topic.lastMessage != null && !Td.isProximityAlertTriggered(topic.lastMessage.content);
    setPrefix();
    if (preview.hasRefresher()) {
      preview.refreshContent(this);
    }
  }

  @Override
  public void onContentPreviewChanged (long chatId, long messageId, ContentPreview newPreview, ContentPreview oldPreview) {
    tdlib.ui().post(() -> {
      if (currentPreview == oldPreview && topic.lastMessage != null &&
        moe.kirao.mgx.MoexShadowUnreadManager.areHiddenUsersReady(tdlib) &&
        !moe.kirao.mgx.MoexMessageFilter.matches(tdlib, topic.lastMessage)) {
        setContentPreview(newPreview);
        currentViews.invalidate();
      }
    });
  }

  private void addIcon (int icon) {
    if (icon != 0) {
      if (textIconIds == null) {
        textIconIds = new IntList(2);
      }
      textIconIds.append(icon);
    }
  }

  private void setTextValue (String value, @Nullable TextEntity[] entities) {
    this.textValue = value;
    this.textEntities = entities != null && entities.length > 0 ? entities : null;
  }

  private void setPrefix () {
    String prefixValue = null;
    if (hasPrefix) {
      if (isDraft) {
        prefixValue = Lang.getString(R.string.Draft);
      } else if (topic.lastMessage != null) {
        prefixValue = topic.lastMessage.isOutgoing ? Lang.getString(R.string.FromYou) : tdlib.senderName(topic.lastMessage, false, true);
      }
    }
    if (!StringUtils.isEmpty(prefixValue)) {
      prefix = new Text.Builder(prefixValue, Screen.dp(120f), textStyleProvider(), isDraft ? TextColorSets.Regular.NEGATIVE : TextColorSets.Regular.NORMAL)
        .singleLine()
        .textFlags(Text.FLAG_ELLIPSIZE_NO_FILL)
        .suffix(": ")
        .build();
    } else {
      prefix = null;
    }
    layoutText();
  }

  private int getCounterAddWidth () {
    int padding = Screen.dp(7f);
    return Math.round(
      counter.getScaledWidth(padding) +
      mentionCounter.getScaledWidth(padding) +
      reactionsCounter.getScaledWidth(padding)
    );
  }

  private void layoutText () {
    int avail = currentWidth - ForumTopicView.getTextLeft() - ForumTopicView.getRightPaddingPx() - getCounterAddWidth();
    textLeft = ForumTopicView.getTextLeft();
    if (prefix != null) {
      avail -= prefix.getWidth();
      textLeft += prefix.getWidth();
    }
    textIconsPadding = textIconIds != null && textIconIds.size() > 0 ? Screen.dp(2f) + Screen.dp(18f) * textIconIds.size() : 0;
    if (avail > 0 && !StringUtils.isEmpty(textValue)) {
      text = new Text.Builder(textValue, avail, textStyleProvider(), TextColorSets.Regular.LIGHT)
        .singleLine()
        .ignoreNewLines()
        .lineMarginProvider((lineIndex, y, defaultMaxWidth, lineHeight) -> lineIndex == 0 ? textIconsPadding : 0)
        .viewProvider(currentViews)
        .entities(textEntities, (text, specificMedia) -> {
          if (this.text == text) {
            for (View view : currentViews) {
              ComplexReceiver receiver = ((ForumTopicView) view).getTextMediaReceiver();
              if (!text.invalidateMediaContent(receiver, specificMedia)) {
                text.requestMedia(receiver);
              }
            }
          }
        })
        .noClickable()
        .build();
      currentViews.invalidateContent(this);
    } else {
      text = null;
    }
    layoutChatAction();
  }

  // Getters for drawing

  @Nullable
  public Text getTitle () {
    return title;
  }

  public String getTime () {
    return time;
  }

  public int getTimeLeft () {
    return timeLeft;
  }

  public int getTimeWidth () {
    return timeWidth;
  }

  public int getChecksRight () {
    return checksRight;
  }

  public int getMuteLeft () {
    return muteLeft;
  }

  public int getLockLeft () {
    return lockLeft;
  }

  @Nullable
  public Text getPrefix () {
    return prefix;
  }

  @Nullable
  public Text getText () {
    return text;
  }

  public int getTextLeft () {
    return textLeft;
  }

  @Nullable
  public IntList getTextIconIds () {
    return textIconIds;
  }
}
