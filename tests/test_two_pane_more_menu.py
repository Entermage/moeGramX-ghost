"""Run production drop-down width/margin methods; Android display is checked separately."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/src/main/java/org/thunderdog/challegram/navigation/MenuMoreWrap.java"

class MoreMenuTest(unittest.TestCase):
    def test_menu_stays_inside_source_pane_with_anchor_offsets(self):
        methods = "\n".join(block(SOURCE, x) for x in ("public int getItemsWidth (", "public void onApplyMarginInsets ("))
        harness = r'''import java.util.*;
public class MoreMenuHarness {
 static class View { Object tag; int visibility; Object getTag(){return tag;} int getVisibility(){return visibility;} static int GONE=8; }
 static class Rect {int left,top,right,bottom;}
 static class FrameLayout {static class LayoutParams{int l,t,r,b;}}
 static class Screen {static int dp(float v){return Math.round(v);} static int currentWidth(){return 1600;}}
 static class Views {static void setMargins(FrameLayout.LayoutParams p,int l,int t,int r,int b){p.l=l;p.t=t;p.r=r;p.b=b;}}
 static class Bounds {int available=400,l=0,r=1200;void update(){} int getLeftInset(){return l;} int getRightInset(){return r;}int getAvailableWidth(int full){return available;}}
 static class Menu {static int PADDING=8;boolean reserveTranslationWidth=true;Bounds popupPaneBounds;List<View> children=new ArrayList<>();float translation;int getMinimumWidth(){return 196;}int getChildCount(){return children.size();}View getChildAt(int i){return children.get(i);}float getTranslationX(){return translation;}
 /* METHODS */
 }
 static void check(boolean c,String m){if(!c)throw new AssertionError(m);}
 public static void main(String[] args){
  Menu m=new Menu();View v=new View();v.tag=800;m.children.add(v);check(m.getItemsWidth()==816,"unscoped menu retains original width");
  m.popupPaneBounds=new Bounds();check(m.getItemsWidth()==400,"long item clamps to left pane");
  m.translation=46;check(m.getItemsWidth()==354,"header anchor inset stays inside pane");
  m.translation=-98;check(m.getItemsWidth()==302,"button index inset stays inside pane");
  Rect legacy=new Rect();legacy.top=12;legacy.bottom=28;FrameLayout.LayoutParams p=new FrameLayout.LayoutParams();m.onApplyMarginInsets(null,p,legacy,new Rect(),new Rect());check(p.l==0&&p.r==1200&&p.t==12&&p.b==28,"left menu anchored within pane and preserves vertical system insets");
  m.popupPaneBounds.l=1200;m.popupPaneBounds.r=0;m.onApplyMarginInsets(null,p,legacy,new Rect(),new Rect());check(p.l==1200&&p.r==0,"mirrored pane margins");
  m.popupPaneBounds.available=1600;m.popupPaneBounds.l=0;m.translation=0;check(m.getItemsWidth()==816,"single pane restores natural width");
  m.popupPaneBounds=null;m.onApplyMarginInsets(null,p,legacy,new Rect(),new Rect());check(p.l==0&&p.r==0&&p.t==12&&p.b==28,"unscoped margins unchanged");
  m.popupPaneBounds=new Bounds();m.reserveTranslationWidth=false;m.translation=-1200;
  check(m.getItemsWidth()==400,"view-anchored menu never collapses when moved across screen coordinates");
  System.out.println("More menu: 9 production geometry checks passed");
 }
}'''.replace("/* METHODS */",methods)
        with tempfile.TemporaryDirectory(prefix="moex-more-menu-") as d:
            path=Path(d)/"MoreMenuHarness.java";path.write_text(harness)
            subprocess.run(["javac","-d",d,str(path)],check=True)
            subprocess.run(["java","-cp",d,"MoreMenuHarness"],check=True)

if __name__ == "__main__": unittest.main()
