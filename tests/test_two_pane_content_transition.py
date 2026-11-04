"""Execute production pane policy and navigation lifecycle with deterministic UI doubles."""
from pathlib import Path
import re
import unittest
import subprocess
from test_chat_open_latency import method
from test_preview_filter import run_java

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'app/src/main/java'


class PaneContentTransitionTest(unittest.TestCase):
    def run_navigation(self, old_gate=False, old_animator=False, old_topic_wait=False):
        pane = (JAVA / 'moe/kirao/mgx/layout/MoexTwoPane.java').read_text()
        nav = (JAVA / 'org/thunderdog/challegram/navigation/NavigationController.java').read_text()
        if old_topic_wait:
            # The previous policy: forward Topic entry kept native readiness and reveal.
            old = 'isPaneContent(from) && isPaneContent(to);'
            self.assertIn(old, pane)
            pane = pane.replace(old, 'isPaneContent(from) && isPaneContent(to) &&\n      !(forward && to instanceof MessagesController &&\n'
                                '        ((MessagesController) to).getMessageTopicId() instanceof TdApi.MessageTopicForum);')
        methods = method(nav, 'void navigate (') + method(nav, 'void animateNavigate (')
        methods = methods.replace('moe.kirao.mgx.layout.', '')
        if old_gate:
            methods = methods.replace('direction == TRANSLATION_NONE || USE_ASYNC_IN_STEP_2', 'USE_ASYNC_IN_STEP_2')
        if old_animator:
            methods = methods.replace('!isAttachedToWindow || direction == TRANSLATION_NONE', '!isAttachedToWindow')
        header = (JAVA / 'org/thunderdog/challegram/navigation/HeaderView.java').read_text()
        header_constants = '\n'.join(re.findall(r'^  static final int MODE_\w+ = \d+;', header, re.M))
        nav_constants = '\n'.join(re.findall(r'^  private static final int TRANSLATION_\w+ = [^;]+;', nav, re.M))
        harness = r'''
public class PaneTransitionHarness {
  static class HeaderView { HEADER_CONSTANTS }
  NAV_CONSTANTS
  static final int MODE_BACKWARD=1, MODE_FORWARD=2, MODE_REBASE=4, MODE_FADE=8, MODE_ARG_SAVE_FIRST=16;
  static final int HARD_TRANSITION_DURATION=400, SLOW_HARD_TRANSITION_DURATION=500, FINISH_NAVIGATION=1;
  static final boolean USE_ASYNC_IN_STEP_2=false;
  static class TdApi {static class MessageTopicForum {}}
  static class View {static final int LAYER_TYPE_NONE=0;}
  static class ViewController<T> {
    Object account=new Object();boolean popup,fast,fade,async=true,preview,force,scheduledOnly;
    Object thread,topic; Runnable scheduled;int ready,focus,destroy;
    Object tdlib(){return account;}boolean usePopupMode(){return popup;}
    boolean forceFastAnimation(){return fast;}boolean forceFadeMode(){return fade;}
    boolean needAsynchronousAnimation(){return async;}
    long getAsynchronousAnimationTimeout(boolean f){return 500;}
    long getStartDelay(boolean f){return 0;}
    void executeAnimationReadyListeners(){ready++;}
    void scheduleAnimation(Runnable r,long timeout){scheduled=r;}
    Runnable getScheduledAnimation(){return scheduled;}void resetScheduledAnimation(){scheduled=null;}
    void destroy(){destroy++;}View getValue(){return new View();}
  }
  static class MessagesController extends ViewController<Object> {
    boolean inPreviewMode(){return preview;}boolean isInForceTouchMode(){return force;}
    boolean areScheduledOnly(){return scheduledOnly;}Object getMessageThread(){return thread;}
    Object getMessageTopicId(){return topic;}
  }
  static class ForumTopicsController extends ViewController<Object>{}
  static class MoexTwoPane {
    boolean isActive=true,destroyed;NavigationController navigation;ViewController<?> root;
    boolean isHiddenRoot(ViewController<?> c){return c==root;}
    PANE
  }
  static class Activity {MoexTwoPane panes;MoexTwoPane moexTwoPane(){return panes;}}
  static class UI {static Activity getContext(Activity a){return a;}}
  static class Settings {static Settings instance(){return new Settings();}boolean needReduceMotion(){return false;}}
  static class PredictiveGesture {static final int NONE=0;}
  static class Config {static boolean DEBUG_NAV_ANIM;}
  static class Views {static boolean HARDWARE_LAYER_ENABLED;}
  static class Animator {}
  static class AnimatorListenerAdapter {public void onAnimationEnd(Animator a){}}
  static class ValueAnimator extends Animator {
    static int created;AnimatorListenerAdapter listener;ValueAnimator(){created++;}
    void addUpdateListener(java.util.function.Consumer<ValueAnimator> c){}
    void setDuration(long t){}void setInterpolator(Object o){}void setStartDelay(long t){}
    void addListener(AnimatorListenerAdapter a){listener=a;}
  }
  static class AnimatorUtils {
    static final Object DECELERATE_INTERPOLATOR=null,NAVIGATION_INTERPOLATOR=null;
    static ValueAnimator simpleValueAnimator(){return new ValueAnimator();}
    static float getFraction(ValueAnimator a){return 0;}static void startAnimator(View v,ValueAnimator a){a.listener.onAnimationEnd(a);}
  }
  static class Stack {
    ViewController<?> previous,current;ViewController<?> getPrevious(){return previous;}
    ViewController<?> getCurrent(){return current;}
  }
  static class Header {float factor=-1;void setTranslation(float f){factor=f;}void applyPreview(ViewController<?> c){}}
  static class NavigationController {
    Activity context=new Activity();Stack stack=new Stack();Header headerView=new Header();
    boolean isAttachedToWindow=true,isDestroyed,animatorRunning;int direction,completed,popped,rebased;
    Processor processor=new Processor();
    class Processor {
      void setNextAsCurrent(){completed++;stack.current.focus++;}
      void rebaseStack(ViewController<?> c,boolean first){rebased++;setNextAsCurrent();}
    }
    Stack getStack(){return stack;}void hideContextualPopups(){}
    void prepareFactorAnimation(ViewController<?> l,ViewController<?> r,boolean f,int d,int p){direction=d;}
    void setFactor(float f){}void removeFadeView(){}void completeNextLayout(){}
    void setLayerType(int t,ViewController<?> l,ViewController<?> r){}void updateHackyViews(){}
    void finishTransaction(int mode){popped++;stack.current.destroy();stack.current=stack.previous;stack.current.focus++;}
    NAV
  }
  static int checks;
  static void check(boolean x,String why){checks++;if(!x)throw new AssertionError(why);}
  static NavigationController nav(ViewController<?> from,ViewController<?> to){
    NavigationController n=new NavigationController();MoexTwoPane p=new MoexTwoPane();p.navigation=n;p.root=from;n.context.panes=p;
    to.account=from.account;n.stack.previous=from;n.stack.current=to;return n;
  }
  public static void main(String[] args){
    ViewController<?> root=new ViewController<>();ForumTopicsController list=new ForumTopicsController();
    NavigationController n=nav(root,list);n.navigate(list,MODE_FORWARD);
    check(list.scheduled==null,"wide content still waits for history");
    check(ValueAnimator.created==0,"wide content still creates timed animator");
    check(n.completed==1&&list.ready==1&&list.focus==1,"forward completion/focus");
    check(n.direction==TRANSLATION_NONE,"wide content must not slide or dim");
    check(n.headerView.factor==0,"header Back/menu reveal must finish without animation frames");
    MessagesController chat=new MessagesController();chat.topic=new TdApi.MessageTopicForum();
    n=nav(list,chat);n.context.panes.root=root;n.navigate(chat,MODE_FORWARD);
    check(n.completed==1&&chat.scheduled==null&&ValueAnimator.created==0,"Topic entry must not wait, as an ordinary chat");
    check(n.direction==TRANSLATION_NONE&&chat.focus==1,"Topic entry must switch immediately and focus once");
    n.navigate(list,MODE_BACKWARD);
    check(n.popped==1&&chat.destroy==1&&n.stack.current==list,"Back preserves list and destroys only topic");
    check(list.focus==2&&ValueAnimator.created==0,"Back is immediate and returns focus once");
    check(n.headerView.factor==1,"Back header state must finish");
    n=nav(root,new MessagesController());n.navigate(n.stack.current,MODE_REBASE|MODE_ARG_SAVE_FIRST);
    check(n.rebased==1,"replacing right content retains root rebase lifecycle");
    MoexTwoPane p=n.context.panes;MessagesController normal=(MessagesController)n.stack.current;
    check(p.switchesContentImmediately(n,root,normal,true),"ordinary chat parity");
    p.isActive=false;check(!p.switchesContentImmediately(n,root,normal,true),"single pane excluded");p.isActive=true;
    check(!p.switchesContentImmediately(new NavigationController(),root,normal,true),"left/other navigation excluded");
    p.destroyed=true;check(!p.switchesContentImmediately(n,root,normal,true),"destroyed panes excluded");p.destroyed=false;
    normal.account=new Object();check(!p.switchesContentImmediately(n,root,normal,true),"account switch excluded");normal.account=root.account;
    check(!p.switchesContentImmediately(n,normal,new ViewController<>(),true),"profile/editor excluded");
    normal.preview=true;check(!p.switchesContentImmediately(n,root,normal,true),"preview excluded");normal.preview=false;
    normal.force=true;check(!p.switchesContentImmediately(n,root,normal,true),"force touch excluded");normal.force=false;
    normal.scheduledOnly=true;check(!p.switchesContentImmediately(n,root,normal,true),"scheduled excluded");normal.scheduledOnly=false;
    normal.thread=new Object();check(!p.switchesContentImmediately(n,root,normal,true),"comment thread excluded");normal.thread=null;
    normal.topic=new Object();check(!p.switchesContentImmediately(n,root,normal,true),"non-forum topic excluded");normal.topic=null;
    n=nav(root,new MessagesController());n.context.panes.isActive=false;n.navigate(n.stack.current,MODE_FORWARD);
    check(n.stack.current.scheduled!=null,"narrow native readiness retained");
    n.stack.current.scheduled.run();check(ValueAnimator.created==1&&n.direction==TRANSLATION_HORIZONTAL,"narrow native animation retained");
    n=nav(root,new MessagesController());n.stack.current.fast=true;n.navigate(n.stack.current,MODE_FORWARD);
    check(n.stack.current.scheduled!=null,"fast preview retains readiness");
    n=nav(root,new MessagesController());n.stack.current.popup=true;n.navigate(n.stack.current,MODE_FORWARD);
    check(n.stack.current.scheduled!=null,"popup flow retained");
    System.out.println(checks+" production transition checks passed");
  }
}
'''.replace('HEADER_CONSTANTS', header_constants).replace('NAV_CONSTANTS', nav_constants).replace('PANE', (method(pane, 'public boolean switchesContentImmediately (') + method(pane, 'private boolean isPaneContent (')).replace('moe.kirao.mgx.topics.', '')).replace('\n    NAV\n', '\n' + methods + '\n')
        run_java({'PaneTransitionHarness.java': harness}, 'PaneTransitionHarness')

    def test_production_navigation_and_lifecycle(self):
        self.run_navigation()

    def test_waiting_topic_entry_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_navigation(old_topic_wait=True)
        self.assertEqual(caught.exception.cmd[0], 'java')

    def test_old_readiness_gate_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_navigation(old_gate=True)
        self.assertEqual(caught.exception.cmd[0], 'java')

    def test_old_timed_animation_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_navigation(old_animator=True)
        self.assertEqual(caught.exception.cmd[0], 'java')


if __name__ == '__main__':
    unittest.main()
