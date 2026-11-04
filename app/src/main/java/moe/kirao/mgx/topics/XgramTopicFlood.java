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

import android.os.SystemClock;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * FLOOD_WAIT of the topic requests ({@code GetForumTopics}, {@code GetForumTopic}) of an account. Once the server
 * asks to wait, every topic request of the account waits too: the topic list, its refreshes, search and the forum
 * badges. Asking again meanwhile only fails and makes the wait longer.
 */
public final class XgramTopicFlood {
  private XgramTopicFlood () { }

  /** Uptime (ms) before which topic requests of an account aren't sent, by account id. */
  private static final Map<Integer, Long> until = new ConcurrentHashMap<>();

  /**
   * Any thread: notes the error of a topic request. Returns how long to wait before asking again: the "retry after"
   * of a flood wait, else {@code fallbackMs} (see {@link XgramForums#retryAfterMs}).
   */
  public static long onError (Tdlib tdlib, TdApi.Error error, long fallbackMs) {
    long delay = XgramForums.retryAfterMs(error, fallbackMs);
    if (error.code == 429) {
      until.merge(tdlib.id(), SystemClock.uptimeMillis() + Math.max(delay, 1000), Math::max);
    }
    return delay;
  }

  /** Any thread: milliseconds left before topic requests of the account may be sent again, 0 when they may now. */
  public static long waitMs (Tdlib tdlib) {
    Long at = until.get(tdlib.id());
    if (at == null) {
      return 0;
    }
    long left = at - SystemClock.uptimeMillis();
    if (left <= 0) {
      until.remove(tdlib.id(), at);
      return 0;
    }
    return left;
  }
}
