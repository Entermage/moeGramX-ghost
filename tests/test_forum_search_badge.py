"""Run the production search row badge of forums: BetterChatView's lifecycle and TGFoundChat's count and mute
against the production ForumUnreadBadges, as the chat list row has them."""
import unittest
import test_history_preview as base
import test_forum_unread_badge as badges

WIDGET = base.SRC / 'widget/BetterChatView.java'
FOUND = base.SRC / 'data/TGFoundChat.java'


def block(text, start, end_signature):
    """From start up to the end of the method beginning with end_signature."""
    begin = text.index(start)
    method = base.method(text, end_signature)
    return text[begin:text.index(method) + len(method)]


HARNESS = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import androidx.annotation.Nullable;
import java.util.*;

public class SearchRowHarness {
  static void check(boolean ok, String what) { if (!ok) throw new AssertionError(what); }

  // ---- TGFoundChat around its production badge methods ----
  static class TGFoundChat {
    static final int FLAG_NO_UNREAD = 1 << 1;
    final Tdlib tdlib; final TdApi.Chat chat; final long chatId; int flags; boolean notificationsEnabled = true;
    TGFoundChat(Tdlib tdlib, TdApi.Chat chat) { this.tdlib = tdlib; this.chat = chat; this.chatId = chat.id; }
    long getId() { return chatId; } long getChatId() { return chatId; } TdApi.Chat getChat() { return chat; }
    long getUserId() { return 0; } boolean isSecret() { return false; } boolean isSelfChat() { return false; }
    boolean isGlobal() { return false; } Object getList() { return null; } Object getTitle() { return null; }
    Object getTitleHighlight() { return null; } void requestAvatar(Object receiver, int options) {} void updateChat() {}
    FOUND_METHODS
  }

  // ---- BetterChatView around its production lifecycle and badge methods ----
  static class AvatarReceiver { static class Options { static final int SHOW_ONLINE = 1; } }
  static class Receiver { void attach() {} void detach() {} }
  static class BitwiseUtils { static int setFlag(int flags, int flag, boolean on) { return on ? flags | flag : flags & ~flag; } }
  static class ChatId { static long fromUserId(long id) { return id; } }
  static class Row implements ForumUnreadBadges.Listener {
    static final int FLAG_SELF_CHAT = 1 << 3;
    final Receiver avatarReceiver = new Receiver(), subtitleMediaReceiver = new Receiver(), emojiStatusHelper = new Receiver();
    static class ViewTdlib { Object chatUser(TdApi.Chat chat) { return null; } ViewTdlib cache() { return this; } Object user(long id) { return null; } }
    final ViewTdlib tdlib = new ViewTdlib(); // the view's own; badges use the found chat's account
    TGFoundChat lastChat; int flags, count = 99, counterUpdates; boolean muted, needStatusUiUpdates;
    void setUnreadCount(int c, boolean m, boolean animated) { count = c; muted = m; counterUpdates++; }
    void addListeners(TdApi.Chat chat, boolean add, boolean status) {} void addListeners(long userId, boolean add, boolean status) {}
    void setIsSecret(boolean secret) {} void setPreviewChatId(Object list, long chatId, Object x) {}
    void setTitle(Object title, Object highlight) {} void setEmojiStatus(Object user) {} void updateSubtitle() {} void setTime(String t) {}
    VIEW_METHODS
  }

  static TdApi.Chat chat(Tdlib t, long id, int unread) {
    TdApi.Chat c = new TdApi.Chat(); c.id = id; c.unreadCount = unread; c.viewAsTopics = true; c.lastReadInboxMessageId = 10;
    t.chats.put(id, c); t.forums.add(id); return c;
  }
  static TdApi.ForumTopic t(int id, int unread, long read, long last) {
    TdApi.ForumTopic t = new TdApi.ForumTopic(); t.info.forumTopicId = id; t.unreadCount = unread; t.lastReadInboxMessageId = read;
    TdApi.Message m = new TdApi.Message(); m.id = last; t.lastMessage = m; return t;
  }
  static TdApi.UpdateForumTopic unmuted(long chat, int id, long read) {
    TdApi.UpdateForumTopic u = new TdApi.UpdateForumTopic(); u.chatId = chat; u.forumTopicId = id; u.lastReadInboxMessageId = read;
    u.notificationSettings = new TdApi.ChatNotificationSettings(); u.notificationSettings.useDefaultMuteFor = false; u.notificationSettings.muteFor = 0;
    return u;
  }
  static int sent() { return ForumRequests.sent.size(); }

  public static void run() {
    // ---- cold start: the first forum row is a search row ----
    Tdlib d = new Tdlib(); TdApi.Chat a = chat(d, 100, 5), b = chat(d, 200, 3);
    TGFoundChat foundA = new TGFoundChat(d, a); foundA.notificationsEnabled = false;
    Row row = new Row();
    row.setChatImpl(foundA); row.updateChat(false);
    check(sent() == 0, "search row asked for topics before it was shown");
    check(row.count == Tdlib.CHAT_MARKED_AS_UNREAD, "dot expected before the topics are known");
    row.attach();
    check(sent() == 1 && ForumRequests.sent.get(0).chatId == 100, "shown search row never asks for topics");
    ForumRequests.reply(0, new TdApi.ForumTopics(t(5, 2, 400, 500), t(6, 1, 500, 600), t(7, 0, 700, 700)), null);
    check(row.count == 2, "search row stays a dot after its topics loaded: " + row.count);
    check(row.muted, "muted forum without unmuted unread topics drawn unmuted");
    d.chatListeners.get(100L).onForumTopicUpdated(unmuted(100, 5, 400));
    check(row.count == 2 && !row.muted, "unmuted unread topic drawn muted in search");
    // The topic list opened on the right counts its topics in the search row too.
    ForumUnreadBadges.onTopicLoaded(d, 100, t(30, 4, 0, 50));
    check(row.count == 3, "topic loaded by the topic list not shown in search");

    // ---- the row is reused for another forum while shown ----
    TGFoundChat foundB = new TGFoundChat(d, b);
    row.setChatImpl(foundB); row.updateChat(false);
    check(sent() == 2 && ForumRequests.sent.get(1).chatId == 200, "reused row didn't follow its new forum");
    int updates = row.counterUpdates;
    ForumUnreadBadges.onTopicLoaded(d, 100, t(31, 1, 0, 60));
    check(row.counterUpdates == updates, "reused row redrawn for its previous chat");
    ForumRequests.reply(1, new TdApi.ForumTopics(t(8, 1, 0, 800)), null);
    check(row.count == 1, "reused row not updated for its new forum");
    // No row shows the previous forum: a reload of it waits for one.
    d.chatListeners.get(100L).onChatReadInbox(100, 11, 5, false);
    d.ui.advance(2001);
    check(sent() == 2, "reused row followed its previous chat");

    // ---- hidden: closed search or a row scrolled away ----
    row.detach();
    updates = row.counterUpdates;
    ForumUnreadBadges.onTopicLoaded(d, 200, t(9, 1, 0, 900));
    check(row.counterUpdates == updates, "detached search row still updated");
    d.chatListeners.get(200L).onChatReadInbox(200, 11, 1, false);
    d.ui.advance(2001);
    check(sent() == 2, "page loaded for a hidden search row");
    row.attach();
    check(sent() == 3, "stale forum not asked for again once its search row is shown");
    ForumRequests.reply(2, new TdApi.ForumTopics(t(8, 0, 800, 800)), null);
    check(row.count == 0, "search row not updated by the reload");
    row.setChatImpl(null);
    updates = row.counterUpdates;
    ForumUnreadBadges.onTopicLoaded(d, 200, t(10, 1, 0, 950));
    check(row.counterUpdates == updates, "destroyed search row still updated");

    // ---- rows that show no unread badge ask for nothing ----
    TdApi.Chat c = chat(d, 300, 4);
    TGFoundChat filtered = new TGFoundChat(d, c); filtered.flags |= TGFoundChat.FLAG_NO_UNREAD;
    Row other = new Row(); other.attach(); other.setChatImpl(filtered); other.updateChat(false);
    check(sent() == 3 && other.count == 0, "filtered row asked for topics");
    // A zero chat counter isn't read topics: reading the whole forum reads none of them (TDLib's mark_dialog_as_read).
    TdApi.Chat read = chat(d, 400, 0);
    Row readRow = new Row(); readRow.attach(); readRow.setChatImpl(new TGFoundChat(d, read)); readRow.updateChat(false);
    check(sent() == 4 && ForumRequests.sent.get(3).chatId == 400, "forum row with a zero chat counter not followed");
    check(readRow.count == 0, "forum row with a zero chat counter shows a badge before its topics");
    ForumRequests.reply(3, new TdApi.ForumTopics(t(1, 2, 0, 20)), null);
    check(readRow.count == 1, "unread topic of a forum with a zero chat counter not shown");
    // A group shown as merged messages, then as topics: followed from then on.
    TdApi.Chat merged = chat(d, 500, 0); merged.viewAsTopics = false;
    Row mergedRow = new Row(); mergedRow.attach(); mergedRow.setChatImpl(new TGFoundChat(d, merged)); mergedRow.updateChat(false);
    check(sent() == 4, "forum shown as merged messages asked for topics");
    merged.viewAsTopics = true; // updateChatViewAsTopics: the row's chat listener updates it
    mergedRow.updateChat(true);
    check(sent() == 5 && ForumRequests.sent.get(4).chatId == 500, "row not followed once its forum is shown as topics");
    ForumRequests.reply(4, new TdApi.ForumTopics(t(1, 1, 0, 20)), null);
    check(mergedRow.count == 1, "row got no count once followed");

    // ---- another account's row ----
    ForumUnreadBadges.forgetAccount(d);
    readRow.detach();
    Tdlib e = new Tdlib(); TdApi.Chat ea = chat(e, 100, 1);
    readRow.setChatImpl(new TGFoundChat(e, ea)); readRow.attach();
    check(sent() == 6 && ForumRequests.sent.get(5).chatId == 100, "row of a new account's forum not followed");
    ForumRequests.reply(5, new TdApi.ForumTopics(t(2, 1, 0, 30)), null);
    check(readRow.count == 1, "row of a new account not updated");
    System.out.println("forum search row badge checks passed");
  }
}
'''


class ForumSearchBadgeTest(unittest.TestCase):
    run_java = base.HistoryPreviewTest.run_java

    def run_harness(self, view_edit=None, found_edit=None):
        view = WIDGET.read_text()
        methods = '\n'.join([
            block(view, '  private boolean isAttached;', '  public void detach () {'),
            base.method(view, '  private void setChatImpl ('),
            block(view, '  private @Nullable Tdlib forumBadgeTdlib;', '  public void onForumUnreadTopicsChanged ('),
            base.method(view, '  private void updateChat (boolean update) {'),
        ])
        found = FOUND.read_text()
        found_methods = '\n'.join(base.method(found, s) for s in [
            '  public Tdlib tdlib () {', '  public boolean usesForumTopicBadge () {',
            '  public boolean isUnreadMuted () {', '  public int getUnreadCount () {'])
        if view_edit:
            self.assertIn(view_edit[0], methods)
            methods = methods.replace(*view_edit)
        if found_edit:
            self.assertIn(found_edit[0], found_methods)
            found_methods = found_methods.replace(*found_edit)
        sources = dict(badges.STUBS)
        sources['moe/kirao/mgx/topics/ForumUnreadTopics.java'] = (badges.TOPICS / 'ForumUnreadTopics.java').read_text()
        sources['moe/kirao/mgx/topics/ForumUnreadBadges.java'] = (badges.TOPICS / 'ForumUnreadBadges.java').read_text()
        sources['moe/kirao/mgx/topics/SearchRowHarness.java'] = \
            HARNESS.replace('VIEW_METHODS', methods).replace('FOUND_METHODS', found_methods)
        sources['Harness.java'] = badges.MAIN.replace('CLASS', 'moe.kirao.mgx.topics.SearchRowHarness')
        return self.run_java(sources)

    def rejected(self, message, **edits):
        r = self.run_harness(**edits)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertRegex(r.stderr, message)

    def test_production_search_row(self):
        r = self.run_harness()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('forum search row badge checks passed', r.stdout)

    def test_unattached_row_rejected(self):
        # As before: the row read the cache, nothing asked for it.
        self.rejected('shown search row never asks for topics',
                      view_edit=('    isAttached = true;\n    updateForumBadge();', '    isAttached = true;'))

    def test_chat_mute_color_rejected(self):
        self.rejected('unmuted unread topic drawn muted in search', found_edit=(
            'return usesForumTopicBadge() ? ForumUnreadBadges.isBadgeMuted(tdlib, chat.id, muted) : muted;', 'return muted;'))

    def test_previous_chat_kept_rejected(self):
        self.rejected('reused row followed its previous chat', view_edit=(
            '      ForumUnreadBadges.detach(forumBadgeTdlib, forumBadgeChatId, this);', ''))

    def test_detach_kept_rejected(self):
        self.rejected('detached search row still updated',
                      view_edit=('    isAttached = false;\n    updateForumBadge();', '    isAttached = false;'))

    def test_zero_counter_gate_rejected(self):
        # Round 1: a forum row with nothing in the chat's counter wasn't followed.
        self.rejected('forum row with a zero chat counter not followed', view_edit=(
            'boolean follow = isAttached && chat != null && lastChat.usesForumTopicBadge();',
            'boolean follow = isAttached && chat != null && lastChat.usesForumTopicBadge() && (chat.unreadCount > 0 || chat.isMarkedAsUnread);'))

    def test_topics_view_change_ignored_rejected(self):
        self.rejected('row not followed once its forum is shown as topics', view_edit=(
            '    updateForumBadge();\n    setUnreadCount(lastChat.getUnreadCount()', '    setUnreadCount(lastChat.getUnreadCount()'))

    def test_filtered_row_rejected(self):
        self.rejected('filtered row asked for topics', found_edit=(
            'return (flags & FLAG_NO_UNREAD) == 0 && chat != null', 'return chat != null'))


if __name__ == '__main__':
    unittest.main()
