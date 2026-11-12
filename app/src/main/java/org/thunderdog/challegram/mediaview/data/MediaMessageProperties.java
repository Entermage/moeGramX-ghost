/*
 * This file is a part of Telegram X
 * Copyright © 2014 (tgx-android@pm.me)
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
package org.thunderdog.challegram.mediaview.data;

import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;

/**
 * Last {@link TdApi.MessageProperties} of the message shown by a {@link MediaItem}.
 *
 * An answer is reused only for the message id it was asked for. When sending succeeds,
 * TGMessage changes the id and sending state of the same {@link TdApi.Message} object
 * the viewer holds, so an answer for the pending message must not outlive it.
 * A failed request is not kept either: it is not a "can't" answer.
 */
final class MediaMessageProperties {
  interface Source {
    @Nullable TdApi.MessageProperties get (long chatId, long messageId);
  }

  private TdApi.MessageProperties properties;
  private long chatId, messageId;

  /**
   * @return {@code null} while the message is pending or failed to send
   * (TDLib can't forward it yet, and its id will change), or when the request failed.
   */
  @Nullable
  TdApi.MessageProperties get (TdApi.Message message, Source source) {
    if (message.sendingState != null) {
      return null;
    }
    if (properties != null && chatId == message.chatId && messageId == message.id) {
      return properties;
    }
    TdApi.MessageProperties properties = source.get(message.chatId, message.id);
    if (properties != null) {
      this.properties = properties;
      this.chatId = message.chatId;
      this.messageId = message.id;
    }
    return properties;
  }
}
