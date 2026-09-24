"""Production JVM/method tests with Android/TDLib doubles, not device E2E.

Compile the real filter and ListManager; extract unchanged preview/config method
bodies as in test_chat_navigation. Network responses, layout and media are doubles.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java"
BASE = JAVA / "org/thunderdog/challegram"
PREVIEW = BASE / "component/chat/MessagePreviewView.java"
CONFIG = JAVA / "moe/kirao/mgx/MoexConfig.java"


def fixtures():
    sources = {}
    for name in ("Nullable", "NonNull", "UiThread"):
        sources[f"androidx/annotation/{name}.java"] = f"package androidx.annotation; public @interface {name} {{}}"
    sources["org/drinkless/tdlib/TdApi.java"] = r'''
package org.drinkless.tdlib;
public class TdApi {
  public static class Object { public int getConstructor() { return 0; } }
  public static class Function<T> extends Object {}
  public static class Error extends Object {
    public static final int CONSTRUCTOR=1;
    public int getConstructor() { return CONSTRUCTOR; }
  }
  public static class MessageContent { public String text="Amazon secret"; }
  public static class FormattedText { public String text; public FormattedText(String t) { text=t; } }
  public static class Message {
    public long chatId=-100, id=10, userId=42;
    public MessageContent content=new MessageContent();
  }
  public static class Chat { public java.lang.Object photo=new java.lang.Object(); }
  public static class BlockList {}
  public static class InputTextQuote { public String text="secret quote"; }
}
'''
    sources["org/drinkless/tdlib/Client.java"] = r'''
package org.drinkless.tdlib;
public class Client {
  public interface ResultHandler { void onResult(TdApi.Object object); }
  public int sends; public ResultHandler pending;
  public void send(TdApi.Function<?> f,ResultHandler h) { sends++; pending=h; }
}
'''
    sources["org/thunderdog/challegram/telegram/Tdlib.java"] = r'''
package org.thunderdog.challegram.telegram;
import org.drinkless.tdlib.*;
import java.util.*;
public class Tdlib {
  public int account=7; public boolean channel;
  public Set<Long> blocked=new HashSet<>();
  public Client client=new Client(); public Dispatcher ui=new Dispatcher();
  public int id() { return account; }
  public boolean isChannel(long c) { return channel; }
  public boolean chatFullyBlocked(long c) { return blocked.contains(c); }
  public Client client() { return client; }
  public Dispatcher ui() { return ui; }
  public void runOnUiThread(Runnable r) { ui.post(r); }
  public String senderName(TdApi.Message m,boolean a,boolean b) { return "author"; }
  public TdApi.Chat chat(long id) { return new TdApi.Chat(); }
  public static class Album { public List<TdApi.Message> messages=new ArrayList<>(); }
  public static class Dispatcher {
    public Queue<Runnable> tasks=new ArrayDeque<>();
    public void post(Runnable r) { tasks.add(r); }
    public void flush() { while(!tasks.isEmpty()) tasks.remove().run(); }
  }
}
'''
    sources["org/thunderdog/challegram/tool/UI.java"] = r'''
package org.thunderdog.challegram.tool;
public class UI { public static int errors; public static void showError(java.lang.Object error) { errors++; } }
'''
    sources["tgx/td/ChatId.java"] = r'''
package tgx.td;
public class ChatId {
  public static long fromUserId(long id) { return id; }
  public static long toUserId(long id) { return id; }
  public static boolean isUserChat(long id) { return id>0; }
}
'''
    sources["tgx/td/Td.java"] = r'''
package tgx.td;
import org.drinkless.tdlib.TdApi;
public class Td {
  public static long getSenderUserId(TdApi.Message m) { return m.userId; }
  public static TdApi.FormattedText textOrCaption(TdApi.MessageContent c) { return c==null ? null : new TdApi.FormattedText(c.text); }
  public static boolean isEmpty(TdApi.InputTextQuote q) { return q==null; }
}
'''
    sources["me/vkryl/core/lambda/Destroyable.java"] = "package me.vkryl.core.lambda; public interface Destroyable { void performDestroy(); }"
    for path in ("org/thunderdog/challegram/telegram/ListManager.java",
                 "org/thunderdog/challegram/telegram/TdlibProvider.java", "moe/kirao/mgx/MoexMessageFilter.java"):
        sources[path] = (JAVA / path).read_text()
    methods = "\n".join(block(CONFIG, s) for s in (
        "public void setFilterEnabled (", "public void setFilterInChats (",
        "public void setFilterCaseInsensitive (", "public void setFilterPatterns (",
        "private static String shadowBannedUsersKey (", "public static boolean isMessageFilterSetting (",
        "public synchronized boolean isShadowBanned (", "public synchronized void setShadowBanned (",
        "public synchronized long[] getShadowBannedUsers (", "public synchronized void setShadowBannedUsers (",
    ))
    sources["moe/kirao/mgx/MoexConfig.java"] = r'''
package moe.kirao.mgx;
import java.util.*;
import androidx.annotation.NonNull;
public class MoexConfig {
  static final MoexConfig INSTANCE=new MoexConfig();
  public static MoexConfig instance() { return INSTANCE; }
  public static boolean filterEnabled,filterInChats=true,filterCaseInsensitive=true;
  public static final String KEY_FILTER_ENABLED="filter_enabled", KEY_FILTER_IN_CHATS="filter_in_chats",
    KEY_FILTER_CASE_INSENSITIVE="filter_case_insensitive", KEY_FILTER_PATTERNS="filter_patterns",
    KEY_SHADOW_BANNED_USERS_PREFIX="shadow_banned_users_";
  Map<String,Object> db=new HashMap<>();
  public interface Listener { void changed(String k,Object n,Object o); }
  public List<Listener> listeners=new ArrayList<>();
  void notifyClientListeners(String k,Object n,Object o) { for(Listener l:listeners) l.changed(k,n,o); }
  void putBoolean(String k,boolean v) { db.put(k,v); }
  void putString(String k,String v) { db.put(k,v); }
  void putLongArray(String k,long[] v) { db.put(k,v.clone()); }
  long[] getLongArray(String k) { long[] v=(long[])db.get(k); return v==null ? null : v.clone(); }
  public String getString(String k,String d) { return (String)db.getOrDefault(k,d); }
  __METHODS__
}
class MoexShadowUnreadManager { static void invalidateAccount(int id) {} }
'''.replace("__METHODS__", methods)
    return sources


def run_java(sources, main):
    with tempfile.TemporaryDirectory(prefix="preview-test-") as directory:
        paths = []
        for name, content in sources.items():
            path = Path(directory) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            paths.append(str(path))
        subprocess.run(["javac", "-d", directory, *paths], check=True)
        subprocess.run(["java", "-cp", directory, main], check=True)


class PreviewFilterTest(unittest.TestCase):
    def test_production_list_error_recovery(self):
        sources = fixtures()
        sources["ListHarness.java"] = r'''
import java.util.*;
import org.drinkless.tdlib.*;
import org.thunderdog.challegram.telegram.*;
import org.thunderdog.challegram.tool.UI;
public class ListHarness extends ListManager<Integer> {
  ListHarness(Tdlib t) { super(t,1,1,true,null); }
  protected void subscribeToUpdates() {}
  protected void unsubscribeFromUpdates() {}
  protected TdApi.Function<?> nextLoadFunction(boolean r,int i,int c) { return new TdApi.Function<>(); }
  static class Page extends TdApi.Object { List<Integer> values; Page(Integer... n) { values=Arrays.asList(n); } }
  protected Response<Integer> processResponse(TdApi.Object o,Client.ResultHandler h,int c,boolean r) {
    return new Response<>(((Page)o).values,5);
  }
  static int checks;
  static void check(boolean v,String m) { checks++; if(!v) throw new AssertionError(m); }
  public static void main(String[] args) {
    Tdlib t=new Tdlib(); ListHarness h=new ListHarness(t); int[] after={0};
    h.loadInitialChunk(()->after[0]++); h.loadItems(false,null);
    check(t.client.sends==1,"single in-flight request");
    t.client.pending.onResult(new TdApi.Error());
    check(UI.errors==0,"error must be dispatched on UI thread");
    t.ui.flush();
    check(UI.errors==1 && after[0]==0,"show error once, do not run successful completion");
    h.loadInitialChunk(null);
    check(t.client.sends==2,"first-page error permits manual retry");
    t.client.pending.onResult(new Page(1)); t.ui.flush();
    check(h.getCount()==1 && h.getItem(0)==1,"successful retry renders data");
    h.loadAll(); t.client.pending.onResult(new TdApi.Error()); t.ui.flush();
    check(t.client.sends==3 && h.getCount()==1,"loadAll error does not retry automatically or clear content");
    h.loadItems(true,null);
    check(t.client.sends==4,"reverse load still allowed after error");
    t.client.pending.onResult(new TdApi.Error()); t.ui.flush();
    h.loadItems(true,null); t.client.pending.onResult(new Page(0)); t.ui.flush();
    check(h.getCount()==2 && h.getItem(0)==0,"reverse retry preserves ordering");
    h.loadItems(false,null); Client.ResultHandler late=t.client.pending;
    int errors=UI.errors, sends=t.client.sends;
    h.performDestroy(); late.onResult(new TdApi.Error()); t.ui.flush(); h.loadItems(false,null);
    check(UI.errors==errors && t.client.sends==sends,"destroyed manager ignores late errors and loads");
    System.out.println("ListManager: "+checks+" production checks passed");
  }
}
'''
        run_java(sources, "ListHarness")

    def test_production_preview_filter_transitions(self):
        sources = fixtures()
        methods = "\n".join(block(PREVIEW, s) for s in (
            "public boolean isMessageFiltered ()", "private void refreshMessageFilter ()",
            "public void onSettingsChanged (", "public void setPreviewMessageOverride (",
            "public void setMessagePreviewDisabled (",
            "private void updatePreviewChat ()", "private void buildPreview ()",
            "private void buildMediaPreview (", "private String getTitle ()",
            "public void onChatBlockListChanged (", "public void detach ()",
            "public boolean isMediaGroup ()", "public List<TdApi.Message> getVisibleMediaGroup ()",
            "public TdApi.Message getVisibleMessage ()",
        ))
        sources["PreviewHarness.java"] = r'''
import java.util.*;
import java.util.function.Consumer;
import androidx.annotation.Nullable;
import org.drinkless.tdlib.TdApi;
import org.thunderdog.challegram.telegram.Tdlib;
import moe.kirao.mgx.*;
import tgx.td.*;
public class PreviewHarness {
  static class MessageId {
    long chatId,id; MessageId(TdApi.Message m) { chatId=m.chatId; id=m.id; }
    MessageId(long c,long i) { chatId=c; id=i; } long getChatId() { return chatId; }
  }
  static class Options { static final int IGNORE_ALBUM_REFRESHERS=1,DISABLE_MESSAGE_PREVIEW=2; }
  static class BitwiseUtils { static boolean hasFlag(int a,int b) { return (a&b)!=0; } }
  static class StringUtils { static boolean isEmpty(String s) { return s==null||s.isEmpty(); } }
  static class R { static class string { static final int FilteredMessage=1; } }
  static class Lang { static String getString(int r) { return "Filtered message"; } }
  static class Screen { static int dp(float n) { return (int)n; } }
  static class ComplexReceiver { int attaches,detaches; void attach() { attaches++; } void detach() { detaches++; } }
  static class ListAnimator { static class Entry<T> { T item; Entry(T i) { item=i; } } }
  static class Animator<T> extends ArrayList<ListAnimator.Entry<T>> {
    boolean animated; void replace(T t,boolean a) { clear(); animated=a; if(t!=null) add(new ListAnimator.Entry<>(t)); }
  }
  static class MediaEntry { ComplexReceiver receiver; MediaEntry(MediaPreview p,ComplexReceiver r) { receiver=r; } }
  static class TextEntry { ComplexReceiver receiver=new ComplexReceiver(); }
  static class MediaPreview {
    static int builds;
    static MediaPreview valueOf(Object... a) { builds++; return new MediaPreview(); }
    void requestFiles(ComplexReceiver r,boolean f) {}
  }
  static class BoolAnimator { void setValue(boolean v,boolean a) {} }
  static class LocalFile {
    ContentPreview buildContentPreview() { return new ContentPreview("local secret",false); }
    MediaPreview buildMediaPreview(Object... a) { return new MediaPreview(); }
  }
  static class DisplayData {
    TdApi.Message message=new TdApi.Message(); TdApi.InputTextQuote quote; int options;
    Object linkPreview,filter; String forcedTitle; LocalFile forcedLocalPickedFile; boolean messageDeleted;
    boolean relatedToUser(long id) { return message.userId==id; }
    boolean isLinkPreviewShowSmallMedia() { return false; }
  }
  static class ContentPreview {
    interface Refresher { void done(long c,long id,ContentPreview newer,ContentPreview older); }
    String text; boolean refresh; Refresher callback; Tdlib.Album album=new Tdlib.Album();
    ContentPreview(String t,boolean b) { text=t; }
    static ContentPreview getChatListPreview(Tdlib t,long c,TdApi.Message m,boolean a) {
      ContentPreview p=new ContentPreview(m.content.text,false); p.refresh=true; return p;
    }
    boolean hasRefresher() { return refresh; }
    boolean isMediaGroup() { return true; }
    Tdlib.Album getAlbum() { return album; }
    void refreshContent(Refresher f) { callback=f; }
  }
  final Tdlib tdlib=new Tdlib(); DisplayData data=new DisplayData(); ContentPreview contentPreview;
  boolean messageFiltered,messagePreviewDisabled,useAvatarFallback=true,isAttached=true; MessageId previewMessageOverride,target;
  Animator<MediaEntry> mediaPreview=new Animator<>(); Animator<TextEntry> contentText=new Animator<>();
  BoolAnimator showSmallMedia=new BoolAnimator(); static final int IMAGE_HEIGHT=40;
  void buildText(boolean b) {} void updateContentText() {} void invalidate() {}
  ComplexReceiver newComplexReceiver(boolean b) { return new ComplexReceiver(); }
  void setPreviewChatId(Object a,long c,Object b,MessageId m,Object f) { target=m; }
  void clearPreviewChat() { target=null; }
  void runOnUiThreadOptional(Consumer<DisplayData> r) { tdlib.runOnUiThread(()->{ if(data!=null) r.accept(data); }); }
  __METHODS__
  static int checks;
  static void check(boolean v,String m) { checks++; if(!v) throw new AssertionError(m); }
  public static void main(String[] args) {
    PreviewHarness h=new PreviewHarness(); MoexConfig c=MoexConfig.instance();
    c.listeners.add(h::onSettingsChanged);
    h.buildPreview(); ContentPreview stale=h.contentPreview;
    check(h.getTitle().equals("author") && h.contentPreview.text.equals("Amazon secret"),"ordinary preview retained");
    check(h.target.id==10 && !h.mediaPreview.isEmpty(),"ordinary target and thumbnail retained");
    c.setFilterPatterns("unrelated"); h.tdlib.ui.flush();
    check(h.contentPreview==stale,"unchanged visibility does not restart album requests");
    h.setPreviewMessageOverride(new MessageId(-200,99));
    c.setShadowBanned(7,42,true); h.tdlib.ui.flush();
    check(h.messageFiltered && h.getTitle().equals("Filtered message"),"ban refreshes without rebind");
    check(h.contentPreview.text.isEmpty() && !h.contentPreview.hasRefresher(),"hidden content and album callbacks dropped");
    check(h.mediaPreview.isEmpty() && !h.mediaPreview.animated,"thumbnail removed without animation");
    check(h.target==null && h.getVisibleMessage()==null && h.getVisibleMediaGroup()==null && !h.isMediaGroup(),"no peek or visible-message read registration");
    stale.callback.done(-100,10,new ContentPreview("late leak",false),stale); h.tdlib.ui.flush();
    check(h.contentPreview.text.isEmpty(),"late album response cannot leak content");
    h.data.quote=new TdApi.InputTextQuote(); h.data.forcedTitle="forced author";
    h.data.forcedLocalPickedFile=new LocalFile(); h.buildPreview();
    check(h.contentPreview.text.isEmpty() && h.getTitle().equals("Filtered message") && h.mediaPreview.isEmpty(),"quote, forced title and local media cannot bypass ban");
    c.setShadowBannedUsers(7,null); h.tdlib.ui.flush();
    check(!h.messageFiltered && h.target.chatId==-200 && h.target.id==99,"bulk unban restores custom thread target");
    h.data.quote=null; h.data.forcedLocalPickedFile=null; h.data.forcedTitle=null;
    c.setFilterPatterns("amazon"); c.setFilterEnabled(true); h.tdlib.ui.flush();
    check(h.messageFiltered,"case-insensitive regex hides preview");
    c.setFilterCaseInsensitive(false); h.tdlib.ui.flush();
    check(!h.messageFiltered,"case change invalidates regex cache and refreshes");
    c.setFilterPatterns("Amazon"); h.tdlib.ui.flush();
    check(h.messageFiltered,"pattern edit refreshes");
    c.setFilterInChats(false); h.tdlib.ui.flush();
    check(!h.messageFiltered,"in-chat toggle respected for group");
    h.tdlib.channel=true; h.buildPreview(); check(h.messageFiltered,"channel regex still applies");
    c.setFilterEnabled(false); h.tdlib.ui.flush(); check(!h.messageFiltered,"turning filter off restores preview");
    c.setShadowBanned(8,42,true); h.tdlib.ui.flush(); check(!h.messageFiltered,"other account ban isolated");
    h.tdlib.blocked.add(42L); h.onChatBlockListChanged(42,null); h.tdlib.ui.flush();
    check(h.messageFiltered,"main blacklist update redacts preview");
    h.tdlib.blocked.clear(); h.onChatBlockListChanged(42,null); h.tdlib.ui.flush();
    check(!h.messageFiltered && h.target.id==99,"main blacklist removal restores custom preview");
    c.setShadowBanned(7,42,true); h.tdlib.ui.flush();
    h.data.linkPreview=new Object(); h.buildPreview(); check(!h.messageFiltered,"synthetic composing URL preview exempt");
    h.data.linkPreview=null; c.setShadowBanned(7,42,false); h.tdlib.ui.flush();
    h.data.options=Options.DISABLE_MESSAGE_PREVIEW; h.buildPreview(); check(h.target==null,"explicit peek opt-out preserved");
    h.data.options=0; h.setPreviewMessageOverride(null); h.buildPreview();
    check(h.target.id==10,"recycled normal pinned entry uses normal target");
    h.setMessagePreviewDisabled(true); h.buildPreview();
    check(h.target==null,"reply input bar keeps host peek opt-out across refreshes");
    h.setMessagePreviewDisabled(false); check(h.target.id==10,"host may restore ordinary preview");
    ComplexReceiver media=h.mediaPreview.get(0).item.receiver; TextEntry text=new TextEntry();
    h.contentText.replace(text,false); h.detach();
    check(!h.isAttached && media.detaches==1 && media.attaches==0 && text.receiver.detaches==1,"detach releases both receivers");
    c.setFilterPatterns("[\n^Amazon"); c.setFilterEnabled(true); c.setFilterInChats(true); h.tdlib.ui.flush();
    check(h.messageFiltered,"invalid regex line does not break other valid lines");
    h.data=null; h.refreshMessageFilter(); h.updatePreviewChat();
    check(!h.isMessageFiltered() && h.getVisibleMessage()==null && h.target==null,"cleared view rejects delayed updates");
    check(MoexConfig.isMessageFilterSetting("shadow_banned_users_7",7) && !MoexConfig.isMessageFilterSetting("shadow_banned_users_8",7),"account-specific notification routing");
    System.out.println("Preview/filter: "+checks+" production-method checks passed (UI doubles)");
  }
}
'''.replace("__METHODS__", methods)
        run_java(sources, "PreviewHarness")

    def test_listener_and_pinned_action_wiring(self):
        source = PREVIEW.read_text()
        self.assertIn("MoexConfig.instance().addSettingsListener(this)", source)
        self.assertIn("MoexConfig.instance().removeSettingsListener(this)", source[source.rindex("public void performDestroy ()"):])
        self.assertIn("this.previewMessageOverride = null", block(PREVIEW, "private void setDisplayData ("))
        for signature, operation in (("public void subscribeToUpdates (", "subscribeToChatUpdates"),
                                     ("public void unsubscribeFromUpdates (", "unsubscribeFromChatUpdates")):
            body = block(PREVIEW, signature)
            self.assertIn(operation + "(ChatId.fromUserId", body)
        bar = BASE / "component/chat/PinnedMessagesBar.java"
        self.assertIn("!MoexMessageFilter.shouldHideInChat", block(bar, "public void onClick ("))
        bind = block(bar, "protected void setMessagePreview (")
        self.assertIn("messageListener != null && !previewView.isMessageFiltered()", bind)
        self.assertIn("setPreviewMessageOverride(highlightMessageId)", bind)
        self.assertIn("setPreviewMessageOverride(null)", bind)
        reply = BASE / "component/chat/ReplyBarView.java"
        self.assertIn("setMessagePreviewDisabled(true)", block(reply, "public void onCreateMessagePreview ("))


if __name__ == "__main__":
    unittest.main()
