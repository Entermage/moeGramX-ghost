import unittest
import test_history_preview as base
SRC = base.SRC

class ScrollIdentityTest(unittest.TestCase):
    run_java = base.HistoryPreviewTest.run_java
    def test_replacement_measurement_cannot_scroll_old_container(self):
        source=(SRC/'component/chat/MessagesManager.java').read_text()
        start=source.index('  public void onMessageHeightChanged (')
        prefix=source[start:source.index('    final long playingRoundVideoId',start)]
        code='''public class Harness {
          static class View {} interface MessageProvider {TGMessage getMessage();}
          static class Row extends View implements MessageProvider {TGMessage value; public TGMessage getMessage(){return value;}}
          static class TGMessage {long getChatId(){return 10;}long getId(){return 20;}}
          View bound;int effects;View findMessageView(long c,long id){return bound;}
        '''+prefix+''' effects++; }
          public static void main(String[] args){Harness h=new Harness();Row row=new Row();TGMessage old=new TGMessage(),replacement=new TGMessage();row.value=old;h.bound=row;
            h.onMessageHeightChanged(replacement,0,951);if(h.effects!=0)throw new AssertionError("replacement measured against old row");
            h.onMessageHeightChanged(old,50,70);if(h.effects!=1)throw new AssertionError("live resize suppressed");
            h.bound=null;h.onMessageHeightChanged(old,50,70);if(h.effects!=1)throw new AssertionError("detached resize");}}
        '''
        r=self.run_java({'Harness.java':code});self.assertEqual(r.returncode,0,r.stderr)
        negative=code.replace('if (!(boundView instanceof MessageProvider) || ((MessageProvider) boundView).getMessage() != source) return;','')
        r=self.run_java({'Harness.java':negative});self.assertNotEqual(r.returncode,0);self.assertIn('replacement measured',r.stderr)

    def test_queued_scroll_compensation_expires_with_its_container(self):
        sources={
          'org/thunderdog/challegram/util/ScrollJumpCompensator.java':(SRC/'util/ScrollJumpCompensator.java').read_text(),
          'androidx/annotation/Nullable.java':'package androidx.annotation; public @interface Nullable {}',
          'android/view/View.java':'package android.view; public class View {public final ViewTreeObserver observer=new ViewTreeObserver();public ViewTreeObserver getViewTreeObserver(){return observer;}}',
          'android/view/ViewTreeObserver.java':'''package android.view; public class ViewTreeObserver {public interface OnGlobalLayoutListener {void onGlobalLayout();}public int active;
            public void addOnGlobalLayoutListener(OnGlobalLayoutListener l){active++;}public void removeOnGlobalLayoutListener(OnGlobalLayoutListener l){active--;}public boolean isAlive(){return true;}}''',
          'androidx/recyclerview/widget/RecyclerView.java':'''package androidx.recyclerview.widget;public class RecyclerView extends android.view.View {public int scroll;public void scrollBy(int x,int y){scroll+=y;}}''',
          'Harness.java':'''import org.thunderdog.challegram.util.ScrollJumpCompensator;import androidx.recyclerview.widget.RecyclerView;public class Harness {
            public static void main(String[] args){RecyclerView r=new RecyclerView();boolean[] alive={true};ScrollJumpCompensator old=new ScrollJumpCompensator(r,r,-951);
            old.setValidityCheck(()->alive[0]);old.add();alive[0]=false;old.onGlobalLayout();if(r.scroll!=0||r.observer.active!=0)throw new AssertionError("stale compensation");
            ScrollJumpCompensator live=new ScrollJumpCompensator(r,r,20);live.setValidityCheck(()->true);live.add();live.onGlobalLayout();if(r.scroll!=20||r.observer.active!=0)throw new AssertionError("live compensation");}}
          '''}
        r=self.run_java(sources);self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
