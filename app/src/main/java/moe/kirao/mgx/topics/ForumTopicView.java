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
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import android.view.Gravity;
import android.view.ViewGroup;

import androidx.annotation.Nullable;
import androidx.recyclerview.widget.RecyclerView;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.component.dialogs.ChatView;
import org.thunderdog.challegram.component.emoji.AnimatedEmojiDrawable;
import org.thunderdog.challegram.component.sticker.TGStickerObj;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.loader.ComplexReceiver;
import org.thunderdog.challegram.support.RippleSupport;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.theme.ColorId;
import org.thunderdog.challegram.tool.Drawables;
import org.thunderdog.challegram.tool.Icons;
import org.thunderdog.challegram.tool.Paints;
import org.thunderdog.challegram.tool.PorterDuffPaint;
import org.thunderdog.challegram.tool.Screen;
import org.thunderdog.challegram.util.text.Counter;
import org.thunderdog.challegram.util.text.Text;
import org.thunderdog.challegram.widget.SparseDrawableView;

import me.vkryl.core.collection.IntList;

/**
 * One row of the forum topic list: topic icon, name, time, "Sender: last message" preview and badges.
 */
public final class ForumTopicView extends SparseDrawableView {
  public static int getViewHeight () {
    return Screen.dp(64f);
  }

  private static int getIconSize () {
    return Screen.dp(30f);
  }

  private static int getIconLeft () {
    return Screen.dp(14f);
  }

  private static int getIconTop () {
    return Screen.dp(9f);
  }

  public static int getTextLeft () {
    return Screen.dp(58f);
  }

  public static int getRightPaddingPx () {
    return Screen.dp(15f);
  }

  public static Paint getTimePaint () {
    return ChatView.getTimePaint();
  }

  private static int getTitleTop () {
    return Screen.dp(9f);
  }

  private static int getTimeBaseline () {
    return Screen.dp(25f);
  }

  private static int getIconRowTop () {
    return Screen.dp(9f);
  }

  private static int getTextTop () {
    return Screen.dp(35f);
  }

  private static int getCounterCenterY () {
    return Screen.dp(45f);
  }

  private final Tdlib tdlib;
  private final ComplexReceiver textMediaReceiver;
  private TGForumTopic topic;

  private AnimatedEmojiDrawable emojiIcon;
  private long emojiIconId;
  private boolean isAttached;

  public ForumTopicView (Context context, Tdlib tdlib) {
    super(context);
    this.tdlib = tdlib;
    this.textMediaReceiver = new ComplexReceiver(this);
    // Opaque, so rows don't show through each other while the list animates a re-sort.
    RippleSupport.setSimpleWhiteBackground(this);
    setLayoutParams(new RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, getViewHeight()));
  }

  public ComplexReceiver getTextMediaReceiver () {
    return textMediaReceiver;
  }

  @Nullable
  public TGForumTopic getTopic () {
    return topic;
  }

  public void setTopic (@Nullable TGForumTopic topic) {
    if (this.topic != topic) {
      if (this.topic != null) {
        this.topic.detachFromView(this);
      }
      this.topic = topic;
      if (topic != null) {
        topic.checkLayout(getMeasuredWidth());
        topic.attachToView(this);
      }
    }
    requestContent();
    invalidate();
  }

  /** Called when the bound topic's data changed. */
  public void onTopicChanged () {
    requestContent();
    invalidate();
  }

  private void requestContent () {
    Text text = topic != null ? topic.getText() : null;
    if (text != null) {
      text.requestMedia(textMediaReceiver);
    } else {
      textMediaReceiver.clear();
    }
    requestEmojiIcon(topic != null ? topic.getIconCustomEmojiId() : 0);
  }

  private void requestEmojiIcon (long customEmojiId) {
    if (emojiIconId == customEmojiId) {
      return;
    }
    emojiIconId = customEmojiId;
    if (emojiIcon != null) {
      emojiIcon.detach();
      emojiIcon.performDestroy();
      emojiIcon = null;
    }
    if (customEmojiId == 0) {
      return;
    }
    tdlib.emoji().findOrRequest(customEmojiId, (entry, inPlace) -> {
      Runnable act = () -> {
        if (emojiIconId != customEmojiId || emojiIcon != null || entry.value == null) {
          return;
        }
        AnimatedEmojiDrawable drawable = new AnimatedEmojiDrawable(this);
        // A decorative topic icon plays once; an idle list must not redraw at display refresh rate.
        if (!isAttached) drawable.detach();
        drawable.setSticker(new TGStickerObj(tdlib, entry.value, null, entry.value.fullType), true);
        if (isAttached) {
          drawable.attach();
        }
        emojiIcon = drawable;
        invalidate();
      };
      if (inPlace) {
        act.run();
      } else {
        tdlib.ui().post(act);
      }
    });
  }

  public void attach () {
    isAttached = true;
    textMediaReceiver.attach();
    if (emojiIcon != null) {
      emojiIcon.attach();
    }
  }

  public void detach () {
    isAttached = false;
    textMediaReceiver.detach();
    if (emojiIcon != null) {
      emojiIcon.detach();
    }
  }

  public void performDestroy () {
    setTopic(null);
    textMediaReceiver.performDestroy();
    if (emojiIcon != null) {
      emojiIcon.performDestroy();
      emojiIcon = null;
    }
  }

  @Override
  protected void onMeasure (int widthMeasureSpec, int heightMeasureSpec) {
    super.onMeasure(widthMeasureSpec, MeasureSpec.makeMeasureSpec(getViewHeight(), MeasureSpec.EXACTLY));
    if (topic != null && topic.checkLayout(getMeasuredWidth())) {
      requestContent();
    }
  }

  @Override
  protected void onDraw (Canvas c) {
    if (topic == null) {
      return;
    }
    final boolean rtl = Lang.rtl();
    final int viewWidth = getMeasuredWidth();

    // Icon
    int iconSize = getIconSize();
    int iconLeft = rtl ? viewWidth - getIconLeft() - iconSize : getIconLeft();
    Drawable icon = emojiIcon != null ? emojiIcon : topic.getIconDrawable();
    icon.setBounds(iconLeft, getIconTop(), iconLeft + iconSize, getIconTop() + iconSize);
    icon.draw(c);

    // Time
    String time = topic.getTime();
    if (!time.isEmpty()) {
      c.drawText(time, rtl ? viewWidth - topic.getTimeLeft() - topic.getTimeWidth() : topic.getTimeLeft(), getTimeBaseline(), getTimePaint());
    }

    // Title, mute and lock
    Text title = topic.getTitle();
    if (title != null) {
      title.draw(c, getTextLeft(), getTitleTop());
    }
    if (topic.isMuted()) {
      Drawables.drawRtl(c, Icons.getChatMuteDrawable(ColorId.chatListMute), topic.getMuteLeft(), getIconRowTop() + Screen.dp(2f), Paints.getChatsMutePaint(), viewWidth, rtl);
    }
    int checksRight = topic.getChecksRight();
    if (topic.isClosed()) {
      Drawable lock = getSparseDrawable(R.drawable.baseline_lock_16, ColorId.iconLight);
      Drawables.drawRtl(c, lock, topic.getLockLeft(), getTimeBaseline() - Screen.dp(12f), PorterDuffPaint.get(ColorId.iconLight), viewWidth, rtl);
      checksRight -= Screen.dp(20f);
    }

    // Sending state and read ticks
    if (topic.isSending()) {
      int x = checksRight - Screen.dp(10f) - Screen.dp(Icons.CLOCK_SHIFT_X);
      Drawables.drawRtl(c, Icons.getClockIcon(ColorId.iconLight), x, getTimeBaseline() - Screen.dp(11f) - Screen.dp(Icons.CLOCK_SHIFT_Y), Paints.getIconLightPorterDuffPaint(), viewWidth, rtl);
    } else if (topic.isOutgoing()) {
      boolean unread = topic.isUnread();
      int x = checksRight + (unread ? Screen.dp(4f) : 0) - Screen.dp(Icons.TICKS_SHIFT_X) - Screen.dp(14f);
      Drawables.drawRtl(c, unread ? Icons.getSingleTick(ColorId.ticks) : Icons.getDoubleTick(ColorId.ticks), x, getTimeBaseline() - Screen.dp(11f) - Screen.dp(Icons.TICKS_SHIFT_Y), unread ? Paints.getTicksPaint() : Paints.getTicksReadPaint(), viewWidth, rtl);
    }

    // Counters, or a pin for pinned topics without unread messages
    float counterRight = viewWidth - getRightPaddingPx();
    float counterRadius = ChatView.getCounterRadius();
    float counterCenterY = getCounterCenterY();
    Counter counter = topic.getCounter();
    counter.draw(c, counterRight - counterRadius, counterCenterY, Gravity.RIGHT, 1f);
    counterRight -= counter.getScaledWidth(Screen.dp(7f));
    Counter mentionCounter = topic.getMentionCounter();
    mentionCounter.draw(c, counterRight - counterRadius, counterCenterY, Gravity.RIGHT, 1f, this, ColorId.badgeText);
    counterRight -= mentionCounter.getScaledWidth(Screen.dp(7f));
    Counter reactionsCounter = topic.getReactionsCounter();
    reactionsCounter.draw(c, counterRight - counterRadius, counterCenterY, Gravity.RIGHT, 1f, this, topic.isMuted() ? ColorId.badgeMutedText : ColorId.badgeText);
    counterRight -= reactionsCounter.getScaledWidth(Screen.dp(7f));
    if (topic.isPinned() && counterRight == viewWidth - getRightPaddingPx()) {
      Drawable pin = getSparseDrawable(R.drawable.deproko_baseline_pin_16, ColorId.iconLight);
      int pinLeft = viewWidth - getRightPaddingPx() - pin.getMinimumWidth();
      Drawables.drawRtl(c, pin, pinLeft, (int) (counterCenterY - pin.getMinimumHeight() / 2f), PorterDuffPaint.get(ColorId.iconLight), viewWidth, rtl);
    }

    // "Sender: text", sliding away while someone is typing in the topic (as in chats)
    org.thunderdog.challegram.telegram.TdlibStatusManager.Helper status = topic.statusHelper();
    org.thunderdog.challegram.telegram.TdlibStatusManager.ChatState state = status.drawingState();
    float statusVisibility = state != null ? state.visibility() : 0f;
    float textAlpha = 1f - statusVisibility;
    int textTop = getTextTop();
    if (textAlpha > 0f) {
      int dy = (int) (Screen.dp(14f) * statusVisibility);
      int saveCount = dy != 0 ? org.thunderdog.challegram.tool.Views.save(c) : -1;
      if (dy != 0) {
        c.translate(0, dy);
      }
      Text prefix = topic.getPrefix();
      if (prefix != null) {
        prefix.draw(c, getTextLeft(), textTop, null, textAlpha);
      }
      Text text = topic.getText();
      if (text != null) {
        IntList iconIds = topic.getTextIconIds();
        if (iconIds != null) {
          int x = topic.getTextLeft();
          for (int i = 0; i < iconIds.size(); i++) {
            Drawable d = getSparseDrawable(iconIds.get(i), ColorId.NONE);
            int y = textTop + text.getLineHeight(false) / 2 - d.getMinimumHeight() / 2;
            Drawables.drawRtl(c, d, x, y, PorterDuffPaint.get(ColorId.chatListIcon, textAlpha), viewWidth, rtl);
            x += Screen.dp(18f);
          }
        }
        text.draw(c, topic.getTextLeft(), textTop, null, textAlpha, textMediaReceiver);
      }
      if (saveCount != -1) {
        org.thunderdog.challegram.tool.Views.restore(c, saveCount);
      }
    }
    if (statusVisibility > 0f) {
      Text statusText = status.drawingText();
      if (statusText != null) {
        float top = textTop - Screen.dp(14f) * textAlpha;
        int x = getTextLeft();
        org.thunderdog.challegram.tool.DrawAlgorithms.drawStatus(c, state, rtl ? viewWidth - x : x, top + statusText.getLineHeight() / 2f, me.vkryl.core.ColorUtils.alphaColor(statusVisibility, statusText.getTextColor()), this, statusVisibility == 1f ? ColorId.textLight : ColorId.NONE);
        statusText.draw(c, x, (int) top, null, statusVisibility);
      }
    }
  }

  @Nullable
  public TdApi.ForumTopic getForumTopic () {
    return topic != null ? topic.getTopic() : null;
  }
}
