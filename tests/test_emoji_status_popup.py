"""Production-method geometry checks; actual Android popup rendering needs UI E2E.

These methods are extracted from the current Java sources. View doubles expose
window coordinates, insets and measured sizes without contacting TDLib.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "app/src/main/java/org/thunderdog/challegram/ui"
PAGE = UI / "EmojiStatusSelectorEmojiPage.java"
BOTTOM = UI / "BottomSheetViewController.java"
GRID = UI / "EmojiStatusListController.java"


def source_for(broken=None):
    wrapper = "\n".join(block(PAGE, s) for s in (
        "public void setDrawerAnchor (", "private boolean isCompactPopup (",
        "protected boolean getPopupContentBounds (", "protected int getTargetHeight (",
        "protected int getHeaderTopOffset (", "protected float getContentClipTop (",
        "protected void setHeaderPosition (", "protected int getContentOffset (",
        "protected int getHeaderHeight (",
    ))
    page = block(PAGE, "public void setHeaderPosition (")
    base = "\n".join(block(BOTTOM, s) for s in (
        "protected int getHeaderTopOffset (", "protected final int getHeaderHeight (",
        "protected void setHeaderPosition (", "protected float getContentClipTop (",
        "protected boolean getPopupContentBounds (", "public boolean shouldTouchOutside (",
        "private void updateHeaderTopOffset (", "protected final boolean isOutsideSourcePane (", "protected final float popupToContentY (",
    ))
    grid = "\n".join(block(GRID, s) for s in (
        "public void checkSpanCount (", "private static int calculateSpanCount (",
    ))
    if broken == "clip":
        wrapper = wrapper.replace("return headerTranslationY + getHeaderHeight();",
                                  "return headerTranslationY + getHeaderTopOffset();")
    if broken == "offset":
        page = page.replace("parent.getHeaderTopOffset()", "Screen.getStatusBarHeight()")
    if broken == "ime":
        wrapper = wrapper.replace("bottomInset > root.getSystemInsetsWithoutIme().bottom", "false")
    if broken == "double_ime":
        wrapper = wrapper.replace("visibleBottom = Math.min(visibleBottom,", "visibleBottom = Math.min(visibleBottom - bottomInset,")
    if broken == "grid":
        grid = grid.replace("width > 0 ? width : Screen.currentWidth()", "Screen.currentWidth()")
    result = TEMPLATE
    for marker, text in (("BASE", base), ("WRAPPER", wrapper), ("PAGE", page), ("GRID", grid)):
        result = result.replace("/* " + marker + " */", text)
    return result.replace("moe.kirao.mgx.layout.MoexTwoPane", "MoexTwoPane").replace("org.thunderdog.challegram.widget.RootFrameLayout", "RootFrameLayout")


TEMPLATE = r"""
public class EmojiStatusPopupHarness {
  @interface NonNull {} @interface Nullable {}
  static class Screen {
    static float density=1.5f; static int status=136, width=1600, height=1200;
    static int dp(float value){return Math.round(value*density);}
    static int getStatusBarHeight(){return status;}
    static int currentWidth(){return width;} static int currentHeight(){return height;}
  }
  static class HeaderView {static int getTopOffset(){return Screen.status;}}
  static class Lang {static boolean rtl; static boolean rtl(){return rtl;}}
  static class Rect {
    int left,top,right,bottom;
    Rect(){} Rect(int l,int t,int r,int b){set(l,t,r,b);}
    void set(int l,int t,int r,int b){left=l;top=t;right=r;bottom=b;}
    int width(){return right-left;} int height(){return bottom-top;}
  }
  static class ViewGroup {
    static class LayoutParams {static final int MATCH_PARENT=-1;int height,width,topMargin;}
  }
  static class RelativeLayout {static class LayoutParams extends ViewGroup.LayoutParams {}}
  static class FrameLayoutFix {
    static ViewGroup.LayoutParams newParams(int w,int h){ViewGroup.LayoutParams p=new ViewGroup.LayoutParams();p.width=w;p.height=h;return p;}
  }
  static class View {
    static final int VISIBLE=0,GONE=8;
    int windowX,windowY,width,height=1200,visibility,children; float translationY;
    ViewGroup.LayoutParams params=new RelativeLayout.LayoutParams();
    View(){} View(int x,int y){windowX=x;windowY=y;}
    void getLocationInWindow(int[] out){out[0]=windowX;out[1]=windowY;}
    ViewGroup.LayoutParams getLayoutParams(){return params;}
    void setLayoutParams(ViewGroup.LayoutParams p){params=p;}
    void setVisibility(int v){visibility=v;}
    void setTranslationY(float y){translationY=y;} void invalidate(){}
    int getLeft(){return windowX;} int getRight(){return windowX+width;} float getY(){return windowY+translationY;}
    void addView(View v){children++;} int getMeasuredWidth(){return width;} int getMeasuredHeight(){return height;}
  }
  static class LickView extends View {
    float factor; LickView(Context c){} void setFactor(float f){factor=f;}
    void setHeaderBackground(int c){}
  }
  static class MoexTwoPane {boolean active=true; boolean isActive(){return active;}}
  static class RootFrameLayout extends View {Rect systemInsets=new Rect(),withoutIme=new Rect();Rect getSystemInsets(){return systemInsets;}Rect getSystemInsetsWithoutIme(){return withoutIme;}}
  static class Context {MoexTwoPane panes=new MoexTwoPane();RootFrameLayout root=new RootFrameLayout();MoexTwoPane moexTwoPane(){return panes;}RootFrameLayout getRootView(){return root;}}
  static class Bounds {boolean isConstrained(){return false;}}
  static class Base {
    Bounds popupPaneBounds;
    Context ctx=new Context(); Context context(){return ctx;}
    float headerTranslationY,headerBackgroundFactor;
    View headerView=new View(),fixView=new View(),contentView=new View(),wrapView=new View(),pagerInFrameLayoutFix=new View();
    LickView lickView; int currentHeaderTopOffset=-1,lickViewColor;boolean hasLickViewColor;
    Rect popupContentBounds=new Rect(); boolean hasPopupContentBounds;
    protected int getHeaderHeight(){return Screen.dp(56);} protected int getContentOffset(){return 0;}
    protected int getTargetHeight(){return Screen.height;}
    void addThemeInvalidateListener(View v){} void onUpdateLickViewFactor(float f){}
    void setHeaderBackgroundFactor(float f){headerBackgroundFactor=f;}
    void syncInsets(){updateHeaderTopOffset();}
    /* BASE */
  }
  static class EmojiLayout {float headerOffset;void setHeaderOffset(float y){headerOffset=y;}}
  static class Page {
    Wrapper parent;View foregroundEmojiLayout=new View();EmojiLayout emojiCustomListLayout=new EmojiLayout();
    Page(Wrapper p){parent=p;}
    /* PAGE */
  }
  static class Wrapper extends Base {
    View drawerAnchor;int drawerAnchorX,drawerAnchorY,compactHeight;Page fragment=new Page(this);
    /* WRAPPER */
  }
  static class GridLayoutManager {int count,updates;void setSpanCount(int n){count=n;updates++;}}
  static class RecyclerView extends View {GridLayoutManager layout=new GridLayoutManager();Object getLayoutManager(){return layout;}}
  static class Grid {
    int spanCount;RecyclerView stickersView;
    /* GRID */
  }
  static int checks;
  static void check(boolean condition,String message){checks++;if(!condition)throw new AssertionError(message);}
  static void equal(float expected,float actual,String message){check(Math.abs(expected-actual)<.001f,message+" expected="+expected+" actual="+actual);}
  static void reset(){Screen.density=1.5f;Screen.status=136;Screen.width=1600;Screen.height=1200;Lang.rtl=false;}
  static Wrapper create(){Wrapper w=new Wrapper();w.setDrawerAnchor(new View(100,180),200,80);return w;}
  static void headerCase(){
    for(float density:new float[]{1f,1.5f,3f}) {
      Screen.density=density;
      for(int status:new int[]{0,Screen.dp(24),Screen.dp(91)}) {
        Screen.status=status;Wrapper w=create();
        for(boolean compact:new boolean[]{false,true,false,true}) {
          w.ctx.panes.active=compact;w.syncInsets();
          for(float requested:new float[]{-50f,0f,Screen.dp(250)}) {
            w.setHeaderPosition(requested);
            float groupTop=w.pagerInFrameLayoutFix.params.topMargin+w.fragment.emojiCustomListLayout.headerOffset;
            float titleBottom=w.headerTranslationY+w.getHeaderHeight();
            equal(titleBottom,groupTop,"group strip must start at actual title bottom");
            equal(w.fragment.emojiCustomListLayout.headerOffset,w.fragment.foregroundEmojiLayout.translationY,"search overlay shares group local coordinates");
            int groupHeight=Screen.dp(47);
            float visible=Math.max(0,groupHeight-Math.max(0,w.getContentClipTop()-groupTop));
            equal(groupHeight,visible,"group strip must remain fully visible above large top inset");
            check(Float.isFinite(w.headerBackgroundFactor),"header background must not become NaN when leaving sheet");
            if(w.lickView!=null)check(Float.isFinite(w.lickView.factor),"lick factor must remain finite");
          }
          equal(w.getHeaderHeight()+w.getHeaderTopOffset(),w.pagerInFrameLayoutFix.params.topMargin,"current inset margin");
          if(w.lickView!=null)equal(w.getHeaderTopOffset(),w.lickView.params.height,"lick view follows zero/nonzero offset");
        }
      }
    }
  }
  static void boundsCase(){
    reset();Wrapper w=create();w.drawerAnchor.windowX=500;View popup=new View(45,30);Rect available=new Rect(31,10,1571,1160),out=new Rect();
    check(w.getPopupContentBounds(popup,available,out),"drawer wide popup constrains bounds");
    equal(450,out.width(),"wide popup has fixed 300dp width");equal(660,out.height(),"wide popup has 440dp height");
    equal(229,out.left,"anchor maps window x to popup-local x");equal(242,out.top,"anchor maps window y to popup-local y");
    int initialLeft=out.left;int initialTop=out.top;
    popup.windowX+=210;popup.windowY+=95;w.drawerAnchor.windowX+=210;w.drawerAnchor.windowY+=95;
    w.getPopupContentBounds(popup,available,out);equal(initialLeft,out.left,"common window translation cannot move local anchor");equal(initialTop,out.top,"common y translation cannot move local anchor");
    w.drawerAnchor.windowX=1300;popup.windowX=45;Lang.rtl=true;w.getPopupContentBounds(popup,available,out);
    equal(1109,out.left,"RTL opens toward drawer and clamps to safe edge");equal(450,out.width(),"RTL retains same fixed width");
    for(Rect bounds:new Rect[]{new Rect(0,0,1600,1200),new Rect(18,22,380,600),new Rect(7,150,430,450)}) {
      for(boolean rtl:new boolean[]{false,true})for(int coordinate:new int[]{-400,200,4000}) {
        Lang.rtl=rtl;w.drawerAnchor.windowX=coordinate;w.drawerAnchor.windowY=coordinate;
        check(w.getPopupContentBounds(popup,bounds,out),"nonempty safe area produces bounds");
        check(out.left>=bounds.left&&out.right<=bounds.right&&out.top>=bounds.top&&out.bottom<=bounds.bottom,"popup clamps inside local available area");
        check(out.width()<=Screen.dp(300)&&out.height()<=Screen.dp(440),"compact size never grows with pane divider");
        w.hasPopupContentBounds=true;w.popupContentBounds=out;
        check(!w.shouldTouchOutside(out.left+.5f,out.top+.5f),"inside popup remains interactive");
        check(w.shouldTouchOutside(out.left-1,out.top),"left outside dismiss area");
        check(w.shouldTouchOutside(out.right,out.top),"right exclusive boundary");
        check(w.shouldTouchOutside(out.left,out.top-1),"above dismiss area");
        check(w.shouldTouchOutside(out.left,out.bottom),"bottom exclusive boundary");
      }
    }
    w.ctx.panes.active=false;check(!w.getPopupContentBounds(popup,available,out),"narrow screen keeps default full-width sheet");
    w.ctx.panes.active=true;w.drawerAnchor=null;check(!w.getPopupContentBounds(popup,available,out),"settings entry does not opt into floating bounds");
    w.setDrawerAnchor(new View(),0,0);check(!w.getPopupContentBounds(popup,new Rect(0,0,0,300),out),"zero-width layout defers bounds");
    Base base=new Base();check(!base.getPopupContentBounds(popup,available,out),"other BottomSheet subclasses retain default bounds");
  }
  static void imeCase(){
    reset();Wrapper w=create();View popup=new View(0,40);Rect full=new Rect(0,0,1600,1160),out=new Rect();
    w.ctx.root.windowY=20;w.ctx.root.height=1200;w.ctx.root.systemInsets.bottom=500;w.ctx.root.withoutIme.bottom=24;
    check(w.getPopupContentBounds(popup,full,out),"IME bounds resolved");
    equal(668,out.bottom,"popup must stop above raw window IME boundary plus gap");
    equal(520,out.height(),"IME shrinks compact height to visible area");
    Rect alreadyInset=new Rect(0,0,1600,680),second=new Rect();w.getPopupContentBounds(popup,alreadyInset,second);
    equal(out.top,second.top,"already-applied IME margin cannot be subtracted twice");equal(out.bottom,second.bottom,"same raw boundary with existing inset margin");
    Rect smaller=new Rect(0,0,1600,600);w.getPopupContentBounds(popup,smaller,second);
    equal(588,second.bottom,"smaller parent available area wins over window boundary");
    w.ctx.root.systemInsets.bottom=24;w.getPopupContentBounds(popup,full,out);
    equal(660,out.height(),"dismissing IME restores 440dp height");
  }
  static void gridCase(){
    reset();Grid g=new Grid();g.checkSpanCount();equal(10,g.spanCount,"unmeasured grid retains screen fallback");
    g.stickersView=new RecyclerView();g.stickersView.width=450;g.checkSpanCount();
    equal(8,g.spanCount,"compact grid uses actual measured 300dp width");equal(8,g.stickersView.layout.count,"layout manager receives compact columns");
    int updates=g.stickersView.layout.updates;g.checkSpanCount();equal(updates,g.stickersView.layout.updates,"unchanged width does not request new spans");
    g.stickersView.width=1600;g.checkSpanCount();equal(10,g.spanCount,"expanding grid recalculates columns");
    g.stickersView.width=450;g.checkSpanCount();equal(8,g.spanCount,"reopening compact returns to eight columns");
  }
  public static void main(String[] args){reset();if(args[0].equals("header"))headerCase();else if(args[0].equals("bounds"))boundsCase();else if(args[0].equals("grid"))gridCase();else if(args[0].equals("ime"))imeCase();else throw new AssertionError("unknown case");System.out.println(args[0]+": "+checks+" production checks passed");}
}
"""


def compile_harness(directory, broken=None):
    source = Path(directory) / "EmojiStatusPopupHarness.java"
    source.write_text(source_for(broken), encoding="utf-8")
    subprocess.run(["javac", "-d", directory, str(source)], check=True)


class EmojiStatusPopupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="emoji-status-popup-")
        compile_harness(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, case):
        subprocess.run(["java", "-cp", self.temp.name, "EmojiStatusPopupHarness", case], check=True, timeout=15)

    def test_group_strip_and_local_header_offset_survive_mode_changes(self): self.run_case("header")
    def test_compact_bounds_rtl_insets_and_default_full_width(self): self.run_case("bounds")
    def test_grid_uses_actual_width_and_updates_only_on_span_change(self): self.run_case("grid")
    def test_ime_boundary_is_applied_once_and_restores_height(self): self.run_case("ime")

    def test_negative_controls_detect_previous_clip_offset_and_screen_width(self):
        for broken,case,message in (("clip","header","fully visible"),("offset","header","actual title bottom"),("grid","grid","actual measured"),("ime","ime","raw window IME boundary"),("double_ime","ime","raw window IME boundary")):
            with self.subTest(broken=broken),tempfile.TemporaryDirectory(prefix="emoji-status-broken-") as directory:
                compile_harness(directory, broken)
                result=subprocess.run(["java","-cp",directory,"EmojiStatusPopupHarness",case],text=True,capture_output=True,timeout=15)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(message,result.stderr)


if __name__ == "__main__":
    unittest.main()
