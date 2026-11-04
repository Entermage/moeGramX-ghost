"""Production tail request state and visible-window retention; not device E2E."""
from pathlib import Path
import subprocess
import unittest
from test_chat_open_latency import method
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'app/src/main/java/org/thunderdog/challegram/component/chat'


class HistoryTailTransitionTest(unittest.TestCase):
    def run_state(self, old_clear=False, old_mode=False):
        manager = (JAVA / 'MessagesManager.java').read_text()
        loader = (JAVA / 'MessagesLoader.java').read_text()
        start = method(manager, 'private void loadFromStart (MessageId fromId, TGMessage startMessage)')
        if old_clear:
            start = start.replace('boolean retain = startMessage == null', 'boolean retain = false && startMessage == null')
        load = method(loader, 'public void loadFromStart (MessageId startMessageId, boolean retain)')
        if old_mode:
            load = load.replace('retain ? MODE_REPEAT_INITIAL : MODE_INITIAL', 'MODE_INITIAL')
        methods = '\n'.join(method(loader, signature) for signature in [
            'public boolean isRetainingHistory ()', 'private void restoreRetainedHistory ()',
            'private boolean cancelRetainedHistoryOnScroll ()', 'public boolean canLoadTop ()',
            'public boolean canLoadBottom ()', 'public void loadFromStart (MessageId startMessageId)'])
        harness = r'''
public class HistoryTailHarness {
  static class MessageId {}
  static class TGMessage {}
  static class Settings {static Settings instance(){return new Settings();}boolean dontReadMessages(){return false;}}
  static class Controller {int loadingClears;void setHistoryLoading(boolean l,boolean u){loadingClears++;}boolean isInForceTouchMode(){return false;}}
  static class Adapter {int rows=30,resets;int getMessageCount(){return rows;}void reset(TGMessage m){rows=m==null?0:1;resets++;}}
  static class MessagesManager {
    Adapter adapter=new Adapter();Controller controller=new Controller();Loader loader=new Loader(this);
    int scrollActions,positionChanges,readCalls;
    int getUserScrollActionsCount(){return scrollActions;}Controller controller(){return controller;}
    void scrollToPositionWithOffsetImpl(int p,int o){positionChanges++;}void viewMessages(boolean b){readCalls++;}
    void onBottomEndLoaded(){}
    START
    READ
  }
  static class Loader {
    static final int CHUNK_SIZE_SMALL=20,MODE_INITIAL=0,MODE_REPEAT_INITIAL=3;
    MessagesManager manager;Loader(MessagesManager m){manager=m;}
    final Object lock=new Object();boolean retainingHistory,retainedCanLoadTop,retainedCanLoadBottom;
    int retainedScrollActions;boolean canLoadTop=true,canLoadBottom=true,isLoading,preview,supported=true,end;
    Object hiddenUsersCallback,lastHandler;long contextId=1;MessageId scrollMessageId;int scrollHighlightMode;
    int requests,lastMode;boolean lastOnlyLocal;
    boolean supportsHistoryPreview(){return supported;}boolean isShowingHistoryPreview(){return preview;}
    boolean isEndReached(){return end;}
    void reuse(){restoreRetainedHistory();isLoading=false;contextId++;canLoadTop=canLoadBottom=false;}
    void load(MessageId id,int offset,int count,int mode,boolean local,boolean top,boolean bottom){requests++;lastMode=mode;lastOnlyLocal=local;isLoading=true;}
    METHODS
    LOAD
  }
  static int checks;
  static void check(boolean x,String why){checks++;if(!x)throw new AssertionError(why);}
  public static void main(String[] args){
    MessagesManager m=new MessagesManager();Loader l=m.loader;
    m.loadFromStart(new MessageId(),null);
    check(m.adapter.rows==30&&m.adapter.resets==0,"arrow must keep existing rows until new page arrives");
    check(m.positionChanges==0&&m.readCalls==0,"pending tail must not move/read old rows");
    check(l.requests==1&&l.lastMode==Loader.MODE_REPEAT_INITIAL&&l.lastOnlyLocal,"tail must replace, not append a disjoint page");
    check(l.isRetainingHistory()&&m.readMessagesDisabled(),"retained window is display-only");
    check(l.canLoadTop()&&l.canLoadBottom(),"retain old window pagination while replacement is pending");
    for(int i=0;i<20;i++)m.loadFromStart(new MessageId(),null);
    check(l.requests==1,"repeated arrow taps must share native request");
    long generation=l.contextId;l.restoreRetainedHistory();l.isLoading=false;
    check(!l.retainingHistory&&l.canLoadTop&&l.canLoadBottom&&m.adapter.rows==30,"failure restores readable old window");
    m.loadFromStart(new MessageId(),null);check(l.requests==2,"manual retry after failure");
    check(!l.cancelRetainedHistoryOnScroll(),"unchanged viewport accepts result");
    m.scrollActions++;check(l.cancelRetainedHistoryOnScroll(),"manual scroll cancels late jump");
    check(l.contextId>generation&&!l.isLoading&&!l.retainingHistory&&l.lastHandler==null,"cancel invalidates callbacks and releases UI state");
    check(m.adapter.rows==30&&l.canLoadTop&&l.canLoadBottom,"cancel keeps old history and pagination");
    check(m.controller.loadingClears==1,"cancel clears top loading label");
    m=new MessagesManager();m.adapter.rows=0;m.loadFromStart(new MessageId(),null);
    check(m.loader.lastMode==Loader.MODE_INITIAL&&!m.loader.retainingHistory,"initial empty-chat load unchanged");
    m=new MessagesManager();m.loader.supported=false;m.loadFromStart(new MessageId(),null);
    check(m.adapter.rows==0&&!m.loader.retainingHistory,"preview/special mode does not reuse ordinary history");
    m=new MessagesManager();m.loadFromStart(new MessageId(),new TGMessage());
    check(m.adapter.rows==1&&!m.loader.retainingHistory,"explicit initial-message path unchanged");
    System.out.println(checks+" production tail-state checks passed");
  }
}
'''.replace('START', start).replace('READ', method(manager, 'public boolean readMessagesDisabled ()')).replace('METHODS', methods).replace('LOAD', load)
        harness = harness.replace('MessagesManager.HIGHLIGHT_MODE_NONE', '0')
        run_java({'HistoryTailHarness.java': harness}, 'HistoryTailHarness')

    def test_production_window_and_request_lifecycle(self):
        self.run_state()

    def test_old_clear_before_response_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_state(old_clear=True)
        self.assertEqual(caught.exception.cmd[0], 'java')

    def test_append_disjoint_history_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_state(old_mode=True)
        self.assertEqual(caught.exception.cmd[0], 'java')


if __name__ == '__main__':
    unittest.main()
