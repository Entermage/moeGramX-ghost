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
package moe.kirao.mgx;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.R;
import org.thunderdog.challegram.component.chat.MessageView;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.data.TD;
import org.thunderdog.challegram.data.TGMessage;
import org.thunderdog.challegram.data.ThreadInfo;
import org.thunderdog.challegram.telegram.Tdlib;
import org.thunderdog.challegram.telegram.TdlibUi;
import org.thunderdog.challegram.ui.MessagesController;

import me.vkryl.core.collection.IntList;
import tgx.td.ChatId;
import tgx.td.Td;

/**
 * Long press on a sender's avatar in a chat: View Profile, Send Message, Mention and Messages from X.
 * <p>
 * Ported from XGram 061781b2 ({@code com.fahadali.xgram.chats.XgramAvatarMenu}) and adapted to moeGramX: only the
 * avatar shown on top of a message group, existing strings/ids only, the mention and search go through narrow
 * {@link MessagesController} methods, and every delayed menu click checks again that the same page is still open.
 * <p>
 * Users only: channels, anonymous admins, ads and forward/import origins shown as the author keep the message's own
 * long press, as do selection, editing and previews.
 */
public final class XgramAvatarMenu {
  private XgramAvatarMenu () { }

  /** Opens the menu when (x, y) is on a user's avatar beside {@code msg}; false leaves the long press to the message. */
  public static boolean show (@NonNull MessageView view, @Nullable TGMessage msg, float x, float y) {
    if (msg == null || msg.isDestroyed()) {
      return false;
    }
    final MessagesController m = msg.messagesController();
    if (m == null || m.isDestroyed() || m.inSelectMode() || m.inPreviewMode() || m.isInForceTouchMode() || m.isEditingMessage()) {
      return false;
    }
    final long chatId = m.getChatId();
    if (chatId == 0 || chatId != msg.getChatId()) {
      return false;
    }
    final long userId = msg.xgramAvatarUserAt(view, x, y);
    if (userId == 0) {
      return false;
    }
    final Tdlib tdlib = msg.tdlib();
    final TdApi.User user = tdlib.cache().user(userId);
    if (user == null) {
      return false;
    }
    final boolean isDeleted = TD.isUserDeleted(user);
    final boolean isSelf = tdlib.isSelfUserId(userId);
    final String firstName = tdlib.cache().userFirstName(userId);

    // Send Message: not for deleted accounts, yourself (that would be Saved Messages), or the private chat already open
    final boolean canMessage = !isDeleted && !isSelf && chatId != ChatId.fromUserId(userId);
    final boolean canMention = !isDeleted && m.xgramCanInsertMention();
    final boolean canSearch = m.xgramCanSearchMessagesFromSender();

    final IntList ids = new IntList(4);
    final IntList icons = new IntList(4);
    final String[] titles = new String[4];
    int count = 0;

    ids.append(R.id.btn_openProfile);
    icons.append(R.drawable.baseline_person_24);
    titles[count++] = Lang.getString(R.string.OpenProfile);

    if (canMessage) {
      ids.append(R.id.btn_openChat);
      icons.append(R.drawable.baseline_chat_bubble_24);
      titles[count++] = Lang.getString(R.string.SendMessageToX, firstName);
    }
    if (canMention) {
      ids.append(R.id.btn_mention);
      icons.append(R.drawable.baseline_alternate_email_24);
      titles[count++] = Lang.getString(R.string.Mention);
    }
    if (canSearch) {
      ids.append(R.id.btn_messageViewList);
      icons.append(R.drawable.baseline_search_24);
      titles[count++] = isSelf ? Lang.getString(R.string.ViewMessagesFromYou) : Lang.getString(R.string.ViewMessagesFromUser, firstName);
    }
    final String[] strings = new String[count];
    System.arraycopy(titles, 0, strings, 0, count);

    // What the menu was opened for: a click arriving later must find the same page
    final ThreadInfo thread = m.getMessageThread();
    final TdApi.MessageTopic topicId = m.getMessageTopicId();

    return m.showOptions(tdlib.cache().userName(userId), ids.get(), strings, null, icons.get(), (itemView, id) -> {
      if (!isSamePage(m, msg, chatId, thread, topicId)) {
        return true;
      }
      if (id == R.id.btn_openProfile) {
        tdlib.ui().openPrivateProfile(m, userId, msg.openParameters());
      } else if (id == R.id.btn_openChat) {
        if (!tdlib.cache().userDeleted(userId)) {
          tdlib.ui().openPrivateChat(m, userId, new TdlibUi.ChatOpenParameters().keepStack());
        }
      } else if (id == R.id.btn_mention) {
        m.xgramInsertMention(userId);
      } else if (id == R.id.btn_messageViewList) {
        m.xgramSearchMessagesFromSender(msg, userId);
      }
      return true;
    }) != null;
  }

  /** The controller is still open on the same chat, thread and topic, and still shows the message. */
  private static boolean isSamePage (@NonNull MessagesController m, @NonNull TGMessage msg, long chatId, @Nullable ThreadInfo thread, @Nullable TdApi.MessageTopic topicId) {
    return m.xgramIsCurrentStackItem() &&
      !msg.isDestroyed() && msg.messagesController() == m && msg.getChatId() == chatId &&
      m.compareChat(chatId, thread) && (topicId == null ? m.getMessageTopicId() == null : Td.equalsTo(topicId, m.getMessageTopicId()));
  }
}
