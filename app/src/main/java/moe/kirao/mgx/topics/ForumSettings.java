package moe.kirao.mgx.topics;

import org.thunderdog.challegram.unsorted.Settings;
import me.vkryl.leveldb.LevelDB;

/** Local, account-scoped presentation preferences; never changes a group's server settings. */
public final class ForumSettings {
  public static final int FORUM_LAYOUT_GROUP = 0, FORUM_LAYOUT_TABS = 1, FORUM_LAYOUT_LIST = 2;
  private static final ForumSettings INSTANCE = new ForumSettings();
  public static ForumSettings instance () { return INSTANCE; }
  private LevelDB pmc () { return Settings.instance().pmc(); }
  private static final String[] NAMES = {"tab", "side", "layout"};
  private static String prefix (String name, int accountId) { return "moex_forum_" + name + "_" + accountId + "_"; }
  private String key (String name, int accountId, long chatId) { return prefix(name, accountId) + chatId; }
  /** Only for a real logout or data reset: the local slot's next login may be a different user. */
  public void clearAccount (int accountId) {
    String[] prefixes = new String[NAMES.length];
    for (int i = 0; i < NAMES.length; i++) prefixes[i] = prefix(NAMES[i], accountId);
    pmc().removeByAnyPrefix(prefixes);
  }
  public int lastForumTab (int accountId, long chatId, int fallback) { return pmc().getInt(key("tab", accountId, chatId), fallback); }
  public void setLastForumTab (int accountId, long chatId, int tab) { pmc().putInt(key("tab", accountId, chatId), tab); }
  public boolean forumTabsOnSide (int accountId, long chatId) { return pmc().getBoolean(key("side", accountId, chatId), false); }
  public void setForumTabsOnSide (int accountId, long chatId, boolean side) { pmc().putBoolean(key("side", accountId, chatId), side); }
  public int forumLayout (int accountId, long chatId) { return pmc().getInt(key("layout", accountId, chatId), FORUM_LAYOUT_GROUP); }
  public void setForumLayout (int accountId, long chatId, int layout) {
    if (layout == FORUM_LAYOUT_TABS || layout == FORUM_LAYOUT_LIST) pmc().putInt(key("layout", accountId, chatId), layout);
    else pmc().remove(key("layout", accountId, chatId));
  }
}
