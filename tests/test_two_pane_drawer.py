"""Run the production drawer Archive entry against navigation/animation doubles.

These checks guard the routing regression seen on the emulator; actual drawer
rendering, archive contents and Back still need Android validation.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
DRAWER = ROOT / 'app/src/main/java/org/thunderdog/challegram/navigation/DrawerController.java'


class TwoPaneDrawerTest(unittest.TestCase):
    def test_production_archive_entry(self):
        methods = '\n'.join(block(DRAWER, signature) for signature in (
            'private void openArchive ()',
            'private void openController (ViewController<?> c)',
            'private void openController (ViewController<?> c, boolean inListPane)',
        ))
        harness = r"""
package moe.kirao.mgx.layout;

public class DrawerArchiveTest {
  static class Tdlib { }
  static class TdApi {
    static class ChatList { }
    static class ChatListArchive extends ChatList { }
  }
  static class ChatPosition {
    static final TdApi.ChatList CHAT_LIST_ARCHIVE = new TdApi.ChatListArchive();
  }
  static class Context {
    final Tdlib account = new Tdlib();
    boolean active, busy;
    int leftNavigations;
    ViewController<?> leftTop, leftOpened;
    Tdlib currentTdlib () { return account; }
  }
  static class ViewController<T> {
    final Context context;
    final Tdlib account;
    boolean async = true, destroyed;
    Runnable animationReady;
    ViewController (Context c, Tdlib t) { context = c; account = t; }
    Tdlib tdlib () { return account; }
    Context context () { return context; }
    boolean needAsynchronousAnimation () { return async; }
    void postOnAnimationReady (Runnable callback) { animationReady = callback; }
    void destroy () { destroyed = true; animationReady = null; }
  }
  static class ChatsController extends ViewController<Void> {
    static int created;
    boolean picker, filtered;
    Arguments args;
    ChatsController (Context c, Tdlib t) { super(c, t); created++; }
    void setArguments (Arguments args) { this.args = args; }
    TdApi.ChatList chatList () { return args.list; }
    boolean isPicker () { return picker; }
    boolean isFiltered () { return filtered; }
    static class Arguments {
      final TdApi.ChatList list;
      boolean search;
      Arguments (TdApi.ChatList list) { this.list = list; }
      Arguments setNeedMessagesSearch (boolean value) { search = value; return this; }
    }
  }
  static class UI {
    static int rightNavigations;
    static ViewController<?> rightOpened;
    static void navigateTo (ViewController<?> c) { rightNavigations++; rightOpened = c; }
  }
  static class Drawer extends ViewController<Void> {
    boolean ignoreClose;
    int closeCount;
    Drawer (Context context) { super(context, context.currentTdlib()); }
    MoexTwoPane moexTwoPane () { return context.active ? new MoexTwoPane() : null; }
    void close (float velocity, Runnable after) { if (!ignoreClose) closeCount++; }
    __METHODS__
  }
  static int checks;
  static void check (boolean value, String message) {
    checks++;
    if (!value) throw new AssertionError(message);
  }
  static Drawer fixture (boolean active) {
    UI.rightNavigations = 0; UI.rightOpened = null;
    Context context = new Context(); context.active = active;
    return new Drawer(context);
  }
  static ChatsController archived (Context context, Tdlib account) {
    ChatsController chats = new ChatsController(context, account);
    chats.setArguments(new ChatsController.Arguments(ChatPosition.CHAT_LIST_ARCHIVE).setNeedMessagesSearch(true));
    return chats;
  }
  public static void main (String[] args) {
    Drawer narrow = fixture(false);
    narrow.openArchive();
    check(UI.rightNavigations == 1 && narrow.context.leftNavigations == 0,
      "Single-pane Archive retains the original navigation destination");
    ChatsController narrowArchive = (ChatsController) UI.rightOpened;
    check(narrowArchive.chatList() instanceof TdApi.ChatListArchive && narrowArchive.args.search,
      "Archive keeps its archive filter and message-search support");
    check(narrow.ignoreClose, "The drawer stays open until asynchronous archive content is ready");
    narrowArchive.animationReady.run();
    check(!narrow.ignoreClose && narrow.closeCount == 1,
      "Content readiness unblocks and closes the drawer");

    Drawer wide = fixture(true);
    wide.openArchive();
    check(wide.context.leftNavigations == 1 && UI.rightNavigations == 0,
      "Wide-window Archive opens in the list pane and leaves the chat pane untouched");
    ChatsController opened = (ChatsController) wide.context.leftOpened;
    check(opened.tdlib() == wide.context.currentTdlib(), "Archive belongs to the current account");
    opened.animationReady.run();
    check(!wide.ignoreClose && wide.closeCount == 1,
      "Left-pane archive readiness also closes the drawer");
    wide.context.leftTop = opened;
    int createdBefore = ChatsController.created;
    wide.openArchive();
    check(ChatsController.created == createdBefore && wide.context.leftNavigations == 1 && UI.rightNavigations == 0,
      "Reopening an existing left archive does not allocate or stack another controller");
    check(wide.context.leftTop == opened && !opened.destroyed && wide.closeCount == 2,
      "Duplicate Archive preserves the existing controller and closes the drawer");

    Drawer differentAccount = fixture(true);
    differentAccount.context.leftTop = archived(differentAccount.context, new Tdlib());
    differentAccount.openArchive();
    check(differentAccount.context.leftNavigations == 1,
      "An archive from another account must not be mistaken for the current account's archive");

    Drawer filtered = fixture(true);
    ChatsController filteredArchive = archived(filtered.context, filtered.context.currentTdlib());
    filteredArchive.filtered = true; filtered.context.leftTop = filteredArchive;
    filtered.openArchive();
    check(filtered.context.leftNavigations == 1, "A filtered archive is replaced by the full archive");
    Drawer picker = fixture(true);
    ChatsController pickerArchive = archived(picker.context, picker.context.currentTdlib());
    pickerArchive.picker = true; picker.context.leftTop = pickerArchive;
    picker.openArchive();
    check(picker.context.leftNavigations == 1, "A chat picker is not reused as the full archive");

    Drawer busy = fixture(true); busy.context.busy = true;
    busy.openArchive();
    check(UI.rightNavigations == 0 && busy.context.leftNavigations == 0,
      "A busy list pane must never redirect Archive into the chat pane");
    check(busy.context.leftOpened.destroyed && !busy.ignoreClose && busy.closeCount == 1,
      "Failed list navigation releases the unused controller and drawer close lock");

    Drawer other = fixture(true);
    ViewController<?> settings = new ViewController<Void>(other.context, other.context.currentTdlib());
    other.openController(settings);
    check(UI.rightOpened == settings && UI.rightNavigations == 1 && other.context.leftNavigations == 0,
      "Other drawer destinations retain their existing right-pane navigation");
    System.out.println("Drawer Archive: " + checks + " production-method checks passed (JVM state doubles)");
  }
}

class MoexTwoPane {
  static DrawerArchiveTest.ViewController<?> leftTop (DrawerArchiveTest.Context context) {
    return context.leftTop;
  }
  static boolean showOnLeft (DrawerArchiveTest.ViewController<?> owner, DrawerArchiveTest.ViewController<?> c) {
    DrawerArchiveTest.Context context = owner.context();
    context.leftOpened = c;
    if (!context.active || context.busy) return false;
    context.leftNavigations++;
    return true;
  }
}
""".replace('__METHODS__', methods)
        with tempfile.TemporaryDirectory(prefix='two-pane-drawer-') as directory:
            java = Path(directory) / 'DrawerArchiveTest.java'
            java.write_text(harness, encoding='utf-8')
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', directory, str(java)], check=True)
            subprocess.run(['java', '-cp', directory, 'moe.kirao.mgx.layout.DrawerArchiveTest'], check=True)


if __name__ == '__main__':
    unittest.main()
