"""Execute folder-icon content measurement using Android geometry doubles.

The real PopupWindow, RecyclerView rendering and folder interactions need the
separate emulator test. The negative control restores the old full-screen width.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/src/main/java/org/thunderdog/challegram/ui/ChatFolderIconSelector.java"


def source_for(broken=False):
    grid = block(SOURCE, "private final class IconGridLayout")
    if broken:
        grid = grid.replace("MeasureSpec.getSize(widthMeasureSpec)", "Screen.currentWidth()")
    methods = "\n".join(block(SOURCE, signature) for signature in (
        "private void updateGridWidth (", "private int computeSpanCount (", "public void show (",
    ))
    return TEMPLATE.replace("/* GRID */", grid).replace("/* METHODS */", methods)


TEMPLATE = r"""
import java.util.function.Consumer;
public class FolderIconGridHarness {
  static class Context {}
  static class Rect {int left, top, right, bottom;}
  static class View {}
  static class FrameLayoutFix extends View {
    static class LayoutParams {int leftMargin, topMargin, rightMargin, bottomMargin;}
    static class MeasureSpec {static int getSize(int value) {return value;}}
    int measuredWidth;
    FrameLayoutFix(Context context) {}
    protected void onAttachedToWindow() {}
    protected void onDetachedFromWindow() {}
    protected void onMeasure(int width, int height) {measuredWidth=width;}
  }
  static class RootFrameLayout {
    interface MarginModifier {void onApplyMarginInsets(View child, FrameLayoutFix.LayoutParams params, Rect legacy, Rect insets, Rect withoutIme);}
  }
  static class ViewController<T> {int paneWidth=668;}
  static class PopupPaneBounds {
    interface Provider {PopupPaneBounds getPopupPaneBounds();}
    final ViewController<?> source; boolean attached;
    PopupPaneBounds(View view, ViewController<?> source) {this.source=source;}
    void attach() {attached=true;}
    void detach() {attached=false;}
    int getAvailableWidth(int width) {return source.paneWidth>0?source.paneWidth:width;}
    void applyInsets(FrameLayoutFix.LayoutParams p, Rect insets) {p.leftMargin=insets.left;p.rightMargin=insets.right;p.topMargin=0;p.bottomMargin=0;}
  }
  static class Screen {static int dp(float n) {return Math.round(n*1.5f);} static int currentWidth(){return 1600;}}
  static class LayoutManager {
    int span=3, changes;
    int getItemCount() {return 37;}
    int getSpanCount() {return span;}
    void setSpanCount(int n) {span=n;changes++;}
  }
  static class PopupLayout {
    int height;View content;
    PopupLayout(Context c) {}
    void init(boolean b) {}
    void setShowListener(Consumer<PopupLayout> c) {}
    void setDismissListener(Consumer<PopupLayout> c) {}
    void setHideKeyboard() {}
    void setNeedRootInsets() {}
    void showSimplePopupView(View v,int h) {content=v;height=h;}
  }
  static class Delegate {void onShow(){} void onDismiss(){}}
  static class Controller {
    final Context context=new Context(); final ViewController<?> owner=new ViewController<>();
    final LayoutManager layoutManager=new LayoutManager();final Delegate delegate=new Delegate();
    final IconGridLayout popupView=new IconGridLayout();PopupLayout popupLayout;
    /* GRID */
    /* METHODS */
  }
  static void check(boolean b,String message) {if(!b)throw new AssertionError(message);}
  static void measured() {
    Controller c=new Controller();
    int[][] cases={{668,7},{450,5},{750,8},{1600,19},{390,4},{168,3}};
    for(int[] pair:cases){
      c.popupView.onMeasure(pair[0],1200);
      check(c.layoutManager.span==pair[1],"grid must use measured pane width");
      int changes=c.layoutManager.changes;
      c.popupView.onMeasure(pair[0],1200);
      check(c.layoutManager.changes==changes,"unchanged measure must not request a new span layout");
      check(c.popupView.measuredWidth==pair[0],"content retains real measure spec");
    }
    c.popupView.onMeasure(0,1200);
    check(c.layoutManager.span==3,"unmeasured content must not clear valid spans");
  }
  static void showAndInsets() {
    Controller c=new Controller();c.show();
    check(c.layoutManager.span==7,"first show uses source-pane estimate");
    check(c.popupLayout.height==581,"initial reveal estimate follows source rows");
    check(c.popupLayout.content==c.popupView,"scoped grid is actual popup content");
    FrameLayoutFix.LayoutParams p=new FrameLayoutFix.LayoutParams();Rect legacy=new Rect(),insets=new Rect();
    legacy.top=6;legacy.bottom=36;insets.left=12;insets.right=18;
    c.popupView.onApplyMarginInsets(c.popupView,p,legacy,insets,insets);
    check(p.topMargin==6&&p.bottomMargin==36,"system vertical insets survive pane constraints");
    check(p.leftMargin==12&&p.rightMargin==18,"horizontal insets reach pane helper");
    c.popupView.onAttachedToWindow();check(c.popupView.getPopupPaneBounds().attached,"attached grid watches source");
    c.popupView.onDetachedFromWindow();check(!c.popupView.getPopupPaneBounds().attached,"detached grid stops watching source");
  }
  public static void main(String[] args) {if(args[0].equals("measure"))measured();else showAndInsets();}
}
"""


class FolderIconGridTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="folder-icon-grid-")
        cls.compile(cls.temp.name, source_for())

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    @staticmethod
    def compile(directory, source):
        p=Path(directory)/"FolderIconGridHarness.java"
        p.write_text(source)
        subprocess.run(["javac","-d",directory,str(p)],check=True)

    def run_case(self,case):
        subprocess.run(["java","-cp",self.temp.name,"FolderIconGridHarness",case],check=True,timeout=15)

    def test_grid_remeasures_with_content_width(self): self.run_case("measure")
    def test_first_show_and_system_insets_follow_source(self): self.run_case("show")
    def test_negative_control_reproduces_screen_width_grid(self):
        with tempfile.TemporaryDirectory(prefix="folder-icon-old-") as directory:
            self.compile(directory, source_for(broken=True))
            p=subprocess.run(["java","-cp",directory,"FolderIconGridHarness","measure"],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn("grid must use measured pane width",p.stderr)


if __name__=="__main__": unittest.main()
