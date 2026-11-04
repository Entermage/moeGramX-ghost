"""Execute production sheet geometry and reaction-width methods with view doubles.

Android rendering, nested menus and touch routing are verified separately by ADB.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "app/src/main/java/org/thunderdog/challegram"
BASE = JAVA / "ui/BottomSheetViewController.java"
REACTIONS = JAVA / "ui/MessageOptionsPagerController.java"


def source_for(broken=None):
    methods = "\n".join(block(BASE, signature) for signature in (
        "public @Nullable ViewController<?> getOptionsSourceController (",
        "protected final int getPopupContentWidth (",
        "protected final boolean isOutsideSourcePane (",
        "protected final float popupToContentY (",
        "public boolean shouldTouchOutside (",
        "public void onApplyMarginInsets (",
        "protected void onLayout (boolean changed",
    ))
    reaction_touch = block(REACTIONS, "public boolean shouldTouchOutside (").replace("shouldTouchOutside", "reactionOutside")
    picker = block(REACTIONS, "public static float getReactionsPickerRightHiddenWidth (")
    if broken == "width":
        picker = picker.replace("contentWidth -", "Screen.currentWidth() -")
    if broken == "resize":
        methods = methods.replace("height != oldHeight || width != oldWidth", "height != oldHeight")
    if broken == "touch":
        methods = methods.replace("isOutsideSourcePane(x) || ", "")
        reaction_touch = reaction_touch.replace("isOutsideSourcePane(x) || ", "")
    return r'''
import java.util.*;
public class SheetHarness {
 @interface Nullable {}
 static class Rect {int left,top,right,bottom; Rect(int l,int t,int r,int b){left=l;top=t;right=r;bottom=b;}}
 static class FrameLayout {static class LayoutParams{int l,t,r,b;}}
 static class Views {static void setMargins(FrameLayout.LayoutParams p,int l,int t,int r,int b){p.l=l;p.t=t;p.r=r;p.b=b;}}
 static class Screen {static int dp(float n){return Math.round(n*1.5f);} static int currentWidth(){return 1600;}}
 static class HeaderView {static int getSize(boolean b){return 84;}}
 static class State {int getRightViewsWidth(){return 150;}}
 static class ReactionsPickerController {static float RECYCLER_VIEW_LEFT_RIGHT_PADDING=9.5f;}
 static class EmojiLayoutRecyclerController {static int calculateSpanCount(int w,int n,int size){return Math.max(n,w/size);}}
 static class View {int left=653,right=1600,width=947,height=1200;float y=70;int getLeft(){return left;}int getRight(){return right;}float getY(){return y;}int getMeasuredWidth(){return width;}}
 static class Bounds {int left=653,right,available=947;boolean isConstrained(){return left>0||right>0;}void update(){}int getLeftInset(){return left;}int getRightInset(){return right;}int getAvailableWidth(int w){return Math.min(w,available);}}
 static class Context {View root=new View();View getRootView(){root.width=1600;return root;}}
 static class ViewController<T> {ViewController<?> owner=this;public ViewController<?> getOptionsSourceController(){return owner;}protected void onLayout(boolean c,int l,int t,int r,int b){}}
 static class Sheet extends ViewController<Object> {
  ViewController<?> popupSourceController;
  Bounds popupPaneBounds=new Bounds(); View wrapView=new View(),headerView=new View();
  boolean hasPopupContentBounds;Rect popupContentBounds=new Rect(30,40,330,480);
  int oldHeight=-1,oldWidth=-1,height=1200,width=947,invalidations,pages;float headerTranslationY=350,currentPositionOffset;int currentMediaPosition;
  boolean destroyed,attached=true,keyboardGuard;
  Context context(){return new Context();}int getHeaderHeight(boolean b){return 84;}float getPickerTop(){return 350;}
  int getTargetHeight(){return height;}int getMeasuredWidth(){return width;}boolean isDestroyed(){return destroyed;}boolean isAttachedToWindow(){return attached;}
  void post(Runnable r){r.run();}void invalidateAllItemDecorations(){invalidations++;}boolean isDisallowKeyboardHideOnPageScrolled(){return keyboardGuard;}
  void setDisallowKeyboardHideOnPageScrolled(boolean b){keyboardGuard=b;}void onPageScrolled(int a,float b,int c){pages++;}
  /* METHODS */
  /* REACTION_TOUCH */
 }
 /* PICKER */
 static void check(boolean v,String m){if(!v)throw new AssertionError(m);}
 public static void main(String[] args){
  Sheet s=new Sheet();
  switch(args[0]){
   case "margins": {
    Rect legacy=new Rect(12,70,20,36);FrameLayout.LayoutParams p=new FrameLayout.LayoutParams();
    s.onApplyMarginInsets(null,p,legacy,legacy,legacy);check(p.l==653&&p.r==20&&p.t==70&&p.b==36,"right pane + original vertical insets");
    s.popupPaneBounds.left=0;s.popupPaneBounds.right=965;s.onApplyMarginInsets(null,p,legacy,legacy,legacy);check(p.l==12&&p.r==965,"left pane");
    s.popupPaneBounds.left=0;s.popupPaneBounds.right=0;s.onApplyMarginInsets(null,p,legacy,legacy,legacy);check(p.l==12&&p.r==20,"single pane restore");
    s.popupPaneBounds=null;s.onApplyMarginInsets(null,p,legacy,legacy,legacy);check(p.l==12&&p.r==20&&p.t==70&&p.b==36,"independent full-screen flow");break;
   }
   case "ownership": {
    ViewController<?> pane=new ViewController<>(),nested=new ViewController<>();nested.owner=pane;s.popupSourceController=nested;
    check(s.getOptionsSourceController()==pane,"nested options follow source pane");s.popupSourceController=null;check(s.getOptionsSourceController()==s,"unowned flow stays independent");
    check(s.getPopupContentWidth()==947,"measured content width");s.wrapView.width=0;check(s.getPopupContentWidth()==947,"first-layout pane estimate");s.popupPaneBounds=null;check(s.getPopupContentWidth()==1600,"unowned estimate");break;
   }
   case "touch": {
    check(s.shouldTouchOutside(300,900)&&s.reactionOutside(300,900),"left-column tap must be outside right sheet");
    check(!s.shouldTouchOutside(653,900)&&!s.reactionOutside(1599,900),"in-pane content remains interactive");
    check(s.shouldTouchOutside(1600,900),"right edge exclusive");check(s.shouldTouchOutside(800,300)&&s.reactionOutside(800,300),"above header uses content-local y");
    check(!s.shouldTouchOutside(800,340),"below header boundary");
    s.popupPaneBounds.left=0;check(!s.shouldTouchOutside(300,900),"folding restores full-width touch");
    s.hasPopupContentBounds=true;check(!s.shouldTouchOutside(100,200)&&s.shouldTouchOutside(400,200),"emoji status custom rectangle unchanged");break;
   }
   case "resize": {
    s.onLayout(true,0,0,947,1200);check(s.invalidations==1&&s.pages==1,"initial layout");
    s.onLayout(false,0,0,947,1200);check(s.invalidations==1,"stable geometry does not repeat refresh");
    s.width=750;s.onLayout(true,0,0,750,1200);check(s.invalidations==2&&s.pages==2,"width-only fold refreshes text and picker");
    s.width=947;s.onLayout(true,0,0,947,1200);check(s.invalidations==3,"unfold refresh");check(!s.keyboardGuard,"keyboard suppression restored");
    s.destroyed=true;s.width=600;s.onLayout(true,0,0,600,1200);check(s.invalidations==3,"destroyed sheet ignores deferred layout");break;
   }
   case "picker": {
    State state=new State();for(int w:new int[]{947,750,635,1600}){
     float result=getReactionsPickerRightHiddenWidth(state,w);int usable=w-Screen.dp(19);float cell=(float)usable/Math.max(9,usable/Screen.dp(38));
     float expected=(float)Math.ceil((150-Screen.dp(12))/cell)*cell+Screen.dp(9.5f)+Screen.dp(1);
     check(Math.abs(expected-result)<.001,"reaction controls aligned to actual grid width "+w);
    }check(Float.isFinite(getReactionsPickerRightHiddenWidth(state,0)),"safe before first measurement");break;
   }
   default: throw new AssertionError(args[0]);
  }
  System.out.println(args[0]+": production sheet checks passed");
 }
}
'''.replace("/* METHODS */", methods).replace("/* REACTION_TOUCH */", reaction_touch).replace("/* PICKER */", picker)


def compile_harness(directory, source):
    path = Path(directory) / "SheetHarness.java"
    path.write_text(source)
    subprocess.run(["javac", "-d", directory, str(path)], check=True)


class BottomSheetPaneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moex-sheet-")
        compile_harness(cls.temp.name, source_for())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_geometry_ownership_resize_and_touch(self):
        for case in ("margins", "ownership", "touch", "resize", "picker"):
            with self.subTest(case=case):
                subprocess.run(["java", "-cp", self.temp.name, "SheetHarness", case], check=True)

    def test_negative_controls_detect_old_behavior(self):
        for defect, case in (("width", "picker"), ("resize", "resize"), ("touch", "touch")):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory(prefix="moex-sheet-old-") as directory:
                compile_harness(directory, source_for(defect))
                result = subprocess.run(["java", "-cp", directory, "SheetHarness", case], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("AssertionError", result.stderr)


if __name__ == "__main__":
    unittest.main()
