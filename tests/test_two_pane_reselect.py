"""Production two-pane reselect/arrow methods with UI doubles, not device E2E."""
from pathlib import Path
import unittest

from test_chat_navigation import block
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java"
CORE = JAVA / "moe/kirao/mgx/layout/MoexTwoPane.java"
UI = JAVA / "org/thunderdog/challegram/telegram/TdlibUi.java"
CONTROLLER = JAVA / "org/thunderdog/challegram/ui/MessagesController.java"


class TwoPaneReselectTest(unittest.TestCase):
    def test_plain_selection_excludes_explicit_targets(self):
        predicate = block(UI, "public boolean isPlainChatSelection ()")
        harness = r'''
import java.lang.reflect.Field;
public class PlainSelectionHarness {
  static final int CHAT_OPTION_KEEP_STACK=1;
  static class Params {
    public int options,highlightMode;
    public boolean highlightSet;
    public Object highlightMessageId,searchQuery,foundMessage,urlOpenParameters,shareItem,
      inviteLink,inviteLinkInfo,threadInfo,messageTopicId,messageLinkTarget,filter,
      videoChatOrLiveStreamInvitation,fillDraft,chatList,after,onDone;
    __PREDICATE__
  }
  static int checks;
  static void check(boolean yes,String why){checks++;if(!yes)throw new AssertionError(why);}
  public static void main(String[] args) throws Exception {
    Params p=new Params();check(p.isPlainChatSelection(),"ordinary main-list click");
    p.options=CHAT_OPTION_KEEP_STACK;check(p.isPlainChatSelection(),"archive/folder list click");
    p.chatList=new Object();p.after=new Object();p.onDone=new Object();
    check(p.isPlainChatSelection(),"list metadata and completion callbacks do not change navigation target");
    for(int bit=1;bit<31;bit++){
      p.options=CHAT_OPTION_KEEP_STACK|(1<<bit);check(!p.isPlainChatSelection(),"explicit or future option "+bit);
    }
    for(String field:new String[]{"highlightMessageId","searchQuery","foundMessage","urlOpenParameters","shareItem",
        "inviteLink","inviteLinkInfo","threadInfo","messageTopicId","messageLinkTarget","filter",
        "videoChatOrLiveStreamInvitation","fillDraft"}) {
      p=new Params();Field f=Params.class.getField(field);f.set(p,new Object());
      check(!p.isPlainChatSelection(),"explicit target excluded: "+field);
    }
    p=new Params();p.highlightSet=true;check(!p.isPlainChatSelection(),"explicit null highlight still excluded");
    p=new Params();p.highlightMode=3;check(!p.isPlainChatSelection(),"explicit restore mode excluded");
    System.out.println("Plain chat reselect: "+checks+" production checks passed");
  }
}
'''.replace("__PREDICATE__", predicate)
        run_java({"PlainSelectionHarness.java": harness}, "PlainSelectionHarness")

    def test_reselection_uses_exact_arrow_action_without_replacing_controller(self):
        route = block(CORE, "public static boolean reselectChatFromList (")
        arrow = block(CONTROLLER, "public void scrollToUnreadOrStartMessage ()")
        eligible = block(CONTROLLER, "public boolean canReselectFromChatList ()")
        harness = r'''
public class ReselectHarness {
  @interface Nullable {}
  static class Tdlib {int id(){return 7;}}
  static class Activity {MoexTwoPane panes;MoexTwoPane moexTwoPane(){return panes;}}
  static class ViewController<T> {
    Activity activity;Tdlib account;ViewController<?> parent;NavigationController nav;boolean destroyed;
    ViewController(Activity a,Tdlib t){activity=a;account=t;}
    Activity context(){return activity;} Tdlib tdlib(){return account;} boolean isDestroyed(){return destroyed;}
    ViewController<?> getParentOrSelf(){return parent!=null?parent:this;}
    NavigationController navigationController(){return nav;}
  }
  static class ChatsController extends ViewController<Object> {ChatsController(Activity a,Tdlib t){super(a,t);}}
  static class NavigationController {
    ViewController<?> current;boolean destroyed,animating;
    boolean isDestroyed(){return destroyed;}boolean isAnimating(){return animating;}
    ViewController<?> getCurrentStackItem(){return current;}
  }
  static class MoexTwoPane {
    boolean isActive=true,destroyed;NavigationController leftNavigation=new NavigationController(),navigation=new NavigationController();
    __ROUTE__
  }
  static class MessageId {
    long chat,id;MessageId(long c,long i){chat=c;id=i;}
    long getChatId(){return chat;}long getMessageId(){return id;}
  }
  static class Chat {long id=-100;}
  static class TGMessage {MessageId id;TGMessage(long c,long i){id=new MessageId(c,i);}MessageId toMessageId(){return id;}}
  static class Adapter {int index=-1;int indexOfMessageContainer(MessageId id){return index;}}
  static class MessagesManager {
    static final int HIGHLIGHT_MODE_UNREAD=2,HIGHLIGHT_MODE_UNREAD_NEXT=4;
    static class DefaultAnchor {int highlightMode;MessageId messageId=new MessageId(-100,20);}
    static DefaultAnchor anchor=new DefaultAnchor();static boolean canUnread;
    static DefaultAnchor resolveDefaultAnchor(int account,Chat chat,Object thread){return anchor;}
    static boolean canGoUnread(Chat chat,Object thread){return canUnread;}
    static MessageId resolveUnreadAnchor(Chat chat,Object thread){return anchor.messageId;}
    boolean returnMessage;int firstUnread=-1;TGMessage bottom;Adapter adapter=new Adapter();
    String action="";int actions;
    boolean hasReturnMessage(){return returnMessage;}int indexOfFirstUnreadMessage(){return firstUnread;}
    TGMessage findBottomMessage(){return bottom;}Adapter getAdapter(){return adapter;}
    void highlightMessage(MessageId id,int mode,Object unused,boolean animated){action="highlight:"+id.id+":"+mode;actions++;}
    void resetByMessage(MessageId id,int mode){action="reset:"+id.id+":"+mode;actions++;}
    void scrollToStart(boolean force){action="start:"+force;actions++;}
  }
  static class MessagesController extends ViewController<Object> {
    Tdlib tdlib;Chat chat=new Chat();Object messageThread,messageTopicId,previewSearchFilter,previewSearchSender,previewSearchQuery;boolean scheduled,inPreviewMode,forceTouch,onlyFound,searchMode;
    MessagesManager manager=new MessagesManager();
    MessagesController(Activity a,Tdlib t){super(a,t);tdlib=t;}
    boolean inPreviewMode(){return inPreviewMode;}boolean isInForceTouchMode(){return forceTouch;}
    boolean compareChat(long id,Object thread,boolean scheduled){return chat.id==id&&messageThread==thread&&this.scheduled==scheduled;}
    boolean areScheduledOnly(){return scheduled;}boolean inOnlyFoundMode(){return onlyFound;}boolean inSearchMode(){return searchMode;}
    private boolean scrollToForumUnreadOrStartMessage(){return false;} // Ordinary-chat fixture; Topic routing has its own regression.
    __ELIGIBLE__
    __ARROW__
  }
  static class Fixture {
    Activity a=new Activity();Tdlib tdlib=new Tdlib();MoexTwoPane panes=new MoexTwoPane();
    ChatsController source=new ChatsController(a,tdlib);ViewController<Object> owner=new ViewController<>(a,tdlib);
    MessagesController right=new MessagesController(a,tdlib);
    Fixture(){a.panes=panes;source.parent=owner;owner.nav=panes.leftNavigation;panes.leftNavigation.current=owner;panes.navigation.current=right;
      MessagesManager.anchor=new MessagesManager.DefaultAnchor();MessagesManager.canUnread=false;}
  }
  static int checks;
  static void check(boolean value,String why){checks++;if(!value)throw new AssertionError(why);}
  static void reject(Fixture f,String why){check(!MoexTwoPane.reselectChatFromList(f.source,-100)&&f.right.manager.actions==0,why);}
  static void sameAsArrow(Fixture f,String expected){
    f.right.scrollToUnreadOrStartMessage();String direct=f.right.manager.action;int before=f.right.manager.actions;
    ViewController<?> same=f.panes.navigation.current;
    check(MoexTwoPane.reselectChatFromList(f.source,-100),"accepted visible left-list repeat");
    check(f.right.manager.actions==before+1&&direct.equals(f.right.manager.action)&&expected.equals(direct),"same arrow action: "+expected);
    check(f.panes.navigation.current==same,"current controller remains unchanged");
  }
  public static void main(String[] args){
    Fixture f=new Fixture();sameAsArrow(f,"start:false");
    f=new Fixture();MessagesManager.anchor.highlightMode=2;sameAsArrow(f,"highlight:20:4");
    f=new Fixture();MessagesManager.anchor.highlightMode=2;f.right.manager.returnMessage=true;sameAsArrow(f,"start:false");
    f=new Fixture();MessagesManager.canUnread=true;sameAsArrow(f,"reset:20:2");
    f=new Fixture();MessagesManager.canUnread=true;f.right.manager.adapter.index=3;sameAsArrow(f,"highlight:20:4");
    f=new Fixture();MessagesManager.canUnread=true;f.right.manager.bottom=new TGMessage(-100,40);sameAsArrow(f,"start:false");
    f=new Fixture();f.source.parent=null;f.source.nav=f.panes.leftNavigation;f.panes.leftNavigation.current=f.source;sameAsArrow(f,"start:false");
    f=new Fixture();check(!MoexTwoPane.reselectChatFromList(f.source,-200)&&f.right.manager.actions==0,"different chat uses original replacement path");
    check(!MoexTwoPane.reselectChatFromList(null,-100),"null source");
    check(!MoexTwoPane.reselectChatFromList(f.owner,-100),"non-list source");
    check(!MoexTwoPane.reselectChatFromList(f.source,0),"zero chat");
    f=new Fixture();f.a.panes=null;reject(f,"no panes");
    f=new Fixture();f.panes.isActive=false;reject(f,"single pane");
    f=new Fixture();f.panes.destroyed=true;reject(f,"destroyed panes");
    f=new Fixture();f.source.destroyed=true;reject(f,"destroyed list");
    f=new Fixture();f.owner.nav=f.panes.navigation;reject(f,"hidden right-root list is not visible left source");
    f=new Fixture();f.panes.leftNavigation.current=f.source;reject(f,"background left controller");
    f=new Fixture();f.panes.leftNavigation.animating=true;reject(f,"left transition");
    f=new Fixture();f.panes.navigation.animating=true;reject(f,"right transition");
    f=new Fixture();f.panes.leftNavigation.destroyed=true;reject(f,"destroyed left nav");
    f=new Fixture();f.panes.navigation.destroyed=true;reject(f,"destroyed right nav");
    f=new Fixture();f.panes.navigation.current=f.owner;reject(f,"right profile or details screen");
    f=new Fixture();f.right.destroyed=true;reject(f,"destroyed right controller");
    f=new Fixture();f.right.account=new Tdlib();reject(f,"different account");
    f=new Fixture();f.right.inPreviewMode=true;reject(f,"search/event preview");
    f=new Fixture();f.right.forceTouch=true;reject(f,"force-touch preview");
    f=new Fixture();f.right.messageThread=new Object();reject(f,"right thread differs from ordinary chat");
    f=new Fixture();f.right.messageTopicId=new Object();reject(f,"right topic differs from ordinary chat");
    f=new Fixture();f.right.scheduled=true;reject(f,"scheduled screen differs from ordinary chat");
    f=new Fixture();f.right.previewSearchFilter=new Object();reject(f,"pinned/filter view must reopen ordinary chat");
    f=new Fixture();f.right.previewSearchSender=new Object();reject(f,"sender-filtered view");
    f=new Fixture();f.right.previewSearchQuery="";reject(f,"explicit empty search remains a search view");
    f=new Fixture();f.right.onlyFound=true;reject(f,"only-found search results in ordinary controller");
    f=new Fixture();f.right.searchMode=true;reject(f,"active search toolbar in ordinary controller");
    System.out.println("Pane arrow reselect: "+checks+" production checks passed");
  }
}
'''.replace("__ROUTE__", route).replace("__ARROW__", arrow).replace("__ELIGIBLE__", eligible)
        run_java({"ReselectHarness.java": harness}, "ReselectHarness")
        open_chat = block(UI, "public void openChat (final TdlibDelegate context, final @NonNull TdApi.Chat chatFinal")
        self.assertIn("(params == null || params.isPlainChatSelection()) &&", open_chat)
        self.assertIn("MoexTwoPane.reselectChatFromList((ViewController<?>) context, chat.id)", open_chat)
        self.assertLess(open_chat.index("MoexTwoPane.reselectChatFromList"), open_chat.index("final MessagesController controller;"))
        self.assertIn("if (doneOpen) {\n      if (after != null)", open_chat)
        self.assertIn("if (params != null) {\n        params.onDone();\n      }\n      return;", open_chat)
        click = block(CONTROLLER, "public void onClick (View v)")
        self.assertIn("viewId == R.id.btn_scroll) {\n      scrollToUnreadOrStartMessage();", click)


if __name__ == "__main__":
    unittest.main()
