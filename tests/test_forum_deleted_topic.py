"""Run the topic list's production putTopicImpl against the production ForumUnreadBadges: a topic deleted here isn't
brought back as a row, nor counted, by an answer asked for before the deletion (TDLib sends no update for it)."""
import unittest
import test_history_preview as base
import test_forum_unread_badge as badges

LIST = badges.TOPICS / 'ForumTopicList.java'

HARNESS = r'''
package moe.kirao.mgx.topics;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import java.util.*;

public class DeletedTopicHarness {
  static void check(boolean ok, String what) { if (!ok) throw new AssertionError(what); }
  static class Row implements ForumUnreadBadges.Listener { public void onForumUnreadTopicsChanged(long c) {} }
  static TdApi.ForumTopic t(int id, int unread, long read, long last) {
    TdApi.ForumTopic t = new TdApi.ForumTopic(); t.info.forumTopicId = id; t.unreadCount = unread; t.lastReadInboxMessageId = read;
    TdApi.Message m = new TdApi.Message(); m.id = last; t.lastMessage = m; return t;
  }

  // ---- the topic list around its production putTopicImpl ----
  static class XgramTopicReadOutbox { static void set(Tdlib t, long c, TdApi.ForumTopic x) {} }
  static class XgramTopicMute { static void onSettings(Tdlib t, long c, TdApi.ForumTopic x) {} }
  static class XgramForums { static TdApi.ForumTopic normalizeUnread(Tdlib t, TdApi.ForumTopic x) { return x; } }
  static class IntList { final ArrayList<Integer> l = new ArrayList<>(); boolean contains(int v) { return l.contains(v); } void remove(int v) { l.remove((Integer) v); } }
  interface Listener { void onTopicInserted(TopicList l, int i); void onTopicMoved(TopicList l, int a, int b); void onTopicChanged(TopicList l, int i); }
  static class TopicList {
    final Tdlib tdlib; final long chatId = 100;
    final List<TdApi.ForumTopic> topics = new ArrayList<>(); final IntList pinnedOrder = new IntList();
    final List<Listener> listeners = new ArrayList<>(); final Set<Integer> fetchedWhileLoading = new HashSet<>();
    boolean isLoaded = true, isLoading, endReached = true; int inserted;
    TopicList(Tdlib tdlib) { this.tdlib = tdlib; listeners.add(new Listener() {
      public void onTopicInserted(TopicList l, int i) { inserted++; } public void onTopicMoved(TopicList l, int a, int b) {} public void onTopicChanged(TopicList l, int i) {} }); }
    int indexOf(int id) { for (int i = 0; i < topics.size(); i++) if (topics.get(i).info.forumTopicId == id) return i; return -1; }
    int insertionIndex(TdApi.ForumTopic t) { return 0; }
    void prependPinned(int id) { pinnedOrder.l.add(0, id); }
    static boolean sameVisibleState(TdApi.ForumTopic a, TdApi.ForumTopic b) { return false; }
    PUT_TOPIC
  }

  public static void run() {
    Tdlib d = new Tdlib(); TdApi.Chat c = new TdApi.Chat(); c.id = 100; c.unreadCount = 1; c.viewAsTopics = true;
    d.chats.put(100L, c); d.forums.add(100L);
    ForumUnreadBadges.attach(d, 100, new Row());
    ForumRequests.reply(0, new TdApi.ForumTopics(30, t(1, 0, 900, 900)), null);
    TopicList list = new TopicList(d);
    list.putTopicImpl(t(5, 1, 400, 500));
    check(list.indexOf(5) == 0 && ForumUnreadBadges.badgeCount(d, c) == 1, "setup: topic 5 a row and counted");
    // XgramForums.confirmDeleteTopic: the list drops its row, the badge its count.
    list.topics.remove(0);
    ForumUnreadBadges.onTopicDeleted(d, 100, 5);
    // A fetch asked for before the deletion answers now.
    list.putTopicImpl(t(5, 1, 400, 500));
    check(list.indexOf(5) == -1 && list.inserted == 1, "older answer brought a deleted topic back as a row");
    check(ForumUnreadBadges.badgeCount(d, c) == 0, "older answer brought a deleted topic back into the badge");
    // Other topics still come in.
    list.putTopicImpl(t(6, 1, 600, 700));
    check(list.indexOf(6) == 0 && ForumUnreadBadges.badgeCount(d, c) == 1, "topic after a deletion not put in");
    System.out.println("deleted topic list checks passed");
  }
}
'''


class ForumDeletedTopicTest(unittest.TestCase):
    run_java = base.HistoryPreviewTest.run_java

    def run_harness(self, list_edit=None):
        method = base.method(LIST.read_text(), '  private void putTopicImpl (')
        if list_edit:
            self.assertIn(list_edit[0], method)
            method = method.replace(*list_edit)
        sources = dict(badges.STUBS)
        tdapi = 'org/drinkless/tdlib/TdApi.java'
        sources[tdapi] = sources[tdapi].replace('public class TdApi {', 'public class TdApi { public static class MessageSendingStatePending {}', 1)
        sources['moe/kirao/mgx/topics/ForumUnreadTopics.java'] = (badges.TOPICS / 'ForumUnreadTopics.java').read_text()
        sources['moe/kirao/mgx/topics/ForumUnreadBadges.java'] = (badges.TOPICS / 'ForumUnreadBadges.java').read_text()
        sources['moe/kirao/mgx/topics/DeletedTopicHarness.java'] = HARNESS.replace('PUT_TOPIC', method)
        sources['Harness.java'] = badges.MAIN.replace('CLASS', 'moe.kirao.mgx.topics.DeletedTopicHarness')
        return self.run_java(sources)

    def test_production_deleted_topic_not_restored(self):
        r = self.run_harness()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('deleted topic list checks passed', r.stdout)

    def test_restored_row_rejected(self):
        r = self.run_harness(list_edit=('    if (ForumUnreadBadges.isTopicDeleted(tdlib, chatId, topic.info.forumTopicId)) {\n', '    if (false) {\n'))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('older answer brought a deleted topic back as a row', r.stderr)

    def test_page_loop_skips_deleted(self):
        # loadMore's page loop is too large to run here: a deleted topic is skipped before it is counted or added.
        source = LIST.read_text()
        self.assertIn('        for (TdApi.ForumTopic topic : result.topics) {\n'
                      '          if (ForumUnreadBadges.isTopicDeleted(tdlib, chatId, topic.info.forumTopicId)) {\n'
                      '            continue;', source)
        gone = base.method(source, '  private void fetchTopic (')
        self.assertIn('ForumUnreadBadges.onTopicDeleted(tdlib, chatId, forumTopicId);', gone)


if __name__ == '__main__':
    unittest.main()
