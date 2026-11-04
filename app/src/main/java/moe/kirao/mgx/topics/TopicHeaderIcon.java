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
import android.view.View;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.component.emoji.AnimatedEmojiDrawable;
import org.thunderdog.challegram.component.sticker.TGStickerObj;
import org.thunderdog.challegram.navigation.ComplexHeaderView;
import org.thunderdog.challegram.telegram.Tdlib;

import me.vkryl.core.lambda.Destroyable;

/**
 * A forum topic's icon drawn instead of a header cell's avatar, as in Telegram: in the topic's chat and in its
 * profile. Both header cells must show the same thing, because Telegram X swaps one for the other during back
 * gestures (shared header), so a group photo in one of them would flash in the other.
 */
public final class TopicHeaderIcon implements Destroyable, View.OnAttachStateChangeListener {
  private final ComplexHeaderView cell;
  private boolean active;
  private long emojiId;
  @Nullable private AnimatedEmojiDrawable emoji;

  public TopicHeaderIcon (ComplexHeaderView cell) {
    this.cell = cell;
    cell.addOnAttachStateChangeListener(this);
  }

  /** info == null: the default bubble until the topic is known. */
  public void set (Tdlib tdlib, @Nullable TdApi.ForumTopicInfo info) {
    active = true;
    long customEmojiId = info != null && info.icon != null && !info.isGeneral ? info.icon.customEmojiId : 0;
    if (customEmojiId != 0 && customEmojiId == emojiId && emoji != null) {
      cell.xgramSetAvatarDrawable(emoji); // same emoji: no bubble in between
      return;
    }
    destroyEmoji();
    emojiId = customEmojiId;
    cell.xgramSetAvatarDrawable(info != null ? new ForumTopicIconDrawable(info) : new ForumTopicIconDrawable(false, 0x6FB9F0, null));
    if (customEmojiId == 0) {
      return;
    }
    tdlib.emoji().findOrRequest(customEmojiId, (entry, inPlace) -> {
      Runnable act = () -> {
        if (!active || emojiId != customEmojiId || emoji != null || entry.value == null) {
          return;
        }
        emoji = new AnimatedEmojiDrawable(cell);
        if (!cell.isAttachedToWindow()) emoji.detach();
        emoji.setSticker(new TGStickerObj(tdlib, entry.value, null, entry.value.fullType), true);
        cell.xgramSetAvatarDrawable(emoji);
      };
      if (inPlace) {
        act.run();
      } else {
        tdlib.ui().post(act);
      }
    });
  }

  /** The avatar again. */
  public void clear () {
    if (!active) {
      return;
    }
    active = false;
    emojiId = 0;
    destroyEmoji();
    cell.xgramSetAvatarDrawable(null);
  }

  private void destroyEmoji () {
    if (emoji != null) {
      emoji.performDestroy();
      emoji = null;
    }
  }

  @Override
  public void onViewAttachedToWindow (View view) {
    if (emoji != null) emoji.attach();
  }

  @Override
  public void onViewDetachedFromWindow (View view) {
    if (emoji != null) emoji.detach();
  }

  @Override
  public void performDestroy () {
    clear();
    cell.removeOnAttachStateChangeListener(this);
  }
}
