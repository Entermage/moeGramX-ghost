"""Exercise real emoji section scroll methods with measured recycler geometry.

JVM doubles record animation scroll deltas; Android drawing and IME behavior are
verified separately in the emulator. No client or TDLib service is constructed.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT=Path(__file__).resolve().parents[1]
JAVA=ROOT/"app/src/main/java/org/thunderdog/challegram"
CONTROLLER=JAVA/"ui/EmojiStatusListController.java"
ADAPTER=JAVA/"component/emoji/MediaStickersAdapter.java"


def source_for(broken=None):
    current=block(CONTROLLER,"private int getStickersScrollY (")
    target=block(CONTROLLER,"private void scrollToStickerSet (")
    adapter="\n".join(block(ADAPTER,s) for s in (
        "public int measureScrollTop (int position, int spanCount, int sectionIndex, ArrayList<TGStickerSetInfo> sections, @Nullable RecyclerView recyclerView, boolean haveRecentsTitle)",
        "public int measureScrollTop (int position, int spanCount, int sectionIndex, ArrayList<TGStickerSetInfo> sections, @Nullable RecyclerView recyclerView, boolean haveRecentsTitle, boolean useRecyclerWidthForTrending)",
        "public static class LayoutParams",
    ))
    if broken=="current": current=current.replace("stickersView, false, true", "null, false")
    if broken=="target": target=target.replace("stickersView, false, true", "null, false")
    if broken=="trending": adapter=adapter.replace("recyclerWidth > 0 && useRecyclerWidthForTrending", "false")
    return TEMPLATE.replace("/* CURRENT */",current).replace("/* TARGET */",target).replace("/* ADAPTER */",adapter)


TEMPLATE=r"""
import java.util.*;
public class EmojiStatusScrollHarness {
  @interface Nullable {}
  static class Screen {static int width=1600,height=1200;static int dp(float n){return Math.round(n*1.5f);}static int currentWidth(){return width;}static int smallestSide(){return Math.min(width,height);}}
  static class EmojiLayout {
    static final int STICKERS_INSTALLED_CONTROLLER_ID=1;
    static int getHeaderSize(){return Screen.dp(47);}static int getHeaderPadding(){return Screen.dp(6);}
    boolean ignoring;int section;
    void setIgnoreMovement(boolean b){ignoring=b;}
    void setCurrentStickerSectionByPosition(int id,int s,boolean a,boolean b){section=s;}
  }
  static class Build {static class VERSION {static final int SDK_INT=35;}static class VERSION_CODES{static final int LOLLIPOP=21;}}
  static class AnimatorUtils {static final Object DECELERATE_INTERPOLATOR=new Object();}
  static class FactorAnimator {
    interface Target {void onFactorChanged(int id,float factor,float fraction,FactorAnimator a);void onFactorChangeFinished(int id,float factor,FactorAnimator a);}
    Target target;boolean cancelled;
    FactorAnimator(int id,Target t,Object interpolation,int time){target=t;}
    void cancel(){cancelled=true;}
    void animateTo(float v){for(float f:new float[]{.2f,.55f,1f})target.onFactorChanged(0,f,f,this);target.onFactorChangeFinished(0,1f,this);}
  }
  static class View {int top;int getTop(){return top;}}
  static class LinearLayoutManager {
    int first,top,offsetPosition=-1,offset;int findFirstVisibleItemPosition(){return first;}
    View findViewByPosition(int i){View v=new View();v.top=top;return v;}
    void scrollToPositionWithOffset(int p,int o){offsetPosition=p;offset=o;}
  }
  static class RecyclerView {
    int width=450,left=0,right=0,scrolled;boolean disabled;LinearLayoutManager manager=new LinearLayoutManager();
    int getMeasuredWidth(){return width;}int getPaddingLeft(){return left;}int getPaddingRight(){return right;}
    LinearLayoutManager getLayoutManager(){return manager;}
    void stopScroll(){scrolled=0;}void setScrollDisabled(boolean b){disabled=b;}void scrollBy(int x,int y){scrolled+=y;}
  }
  static class TGStickerSetInfo {
    int start;boolean trending;TGStickerSetInfo(int s,boolean t){start=s;trending=t;}
    boolean isTrending(){return trending;}boolean isSystem(){return false;}boolean isDefaultEmoji(){return false;}
    boolean isFavorite(){return false;}boolean isRecent(){return false;}boolean isFakeClassicEmoji(){return false;}boolean isEmoji(){return true;}
    int getSize(){return 16;}long getId(){return start;}
  }
  static class Adapter {
    LayoutParams layoutParams;
    /* ADAPTER */
  }
  static class Controller {
    int spanCount=8,currentSection;RecyclerView stickersView=new RecyclerView();Adapter stickersAdapter=new Adapter();
    ArrayList<TGStickerSetInfo> stickerSets=new ArrayList<>();EmojiLayout arguments=new EmojiLayout();FactorAnimator lastScrollAnimator;
    static final int SCROLLBY_SECTION_LIMIT=8;boolean ignoreRequests;
    Controller(boolean firstTrending){stickerSets.add(new TGStickerSetInfo(1,firstTrending));stickerSets.add(new TGStickerSetInfo(18,false));}
    int indexOfStickerSetByAdapterPosition(int p){return p>=0&&p<35?(p<18?0:1):-1;}
    int getStickerSetSection(){return currentSection;}EmojiLayout getArguments(){return arguments;}
    void setIgnoreRequests(boolean b,long id){ignoreRequests=b;}
    /* CURRENT */
    /* TARGET */
  }
  static int checks;
  static void equal(int expected,int actual,String message){checks++;if(expected!=actual)throw new AssertionError(message+" expected="+expected+" actual="+actual);}
  static void check(boolean b,String message){checks++;if(!b)throw new AssertionError(message);}
  static int headerHeight(boolean trending){return trending?Screen.dp(52):Screen.dp(27)+Screen.dp(5);}
  static int barHeight(){return EmojiLayout.getHeaderSize()+EmojiLayout.getHeaderPadding();}
  static void scrollCases(){
    for(boolean trending:new boolean[]{false,true})for(int width:new int[]{450,750,1600})for(int padding:new int[]{0,15}) {
      Controller c=new Controller(trending);c.stickersView.width=width;c.stickersView.left=padding;c.stickersView.right=padding;
      c.spanCount=width==1600?10:8;
      int rowHeight=(width-padding*2)/c.spanCount,header=headerHeight(trending);
      c.scrollToStickerSet(18,true);
      equal(header+2*rowHeight,c.stickersView.scrolled,"animated group target must use physical row heights");
      check(!c.stickersView.disabled&&!c.ignoreRequests&&!c.arguments.ignoring,"animation restores scroll and movement after completion");
      c.stickersView.manager.first=10;c.stickersView.manager.top=-11;
      equal(barHeight()+header+rowHeight+11,c.getStickersScrollY(),"current scroll origin must use physical row heights");
      c.scrollToStickerSet(18,true);
      equal(rowHeight-barHeight()-11,c.stickersView.scrolled,"current and target offsets share the same geometry");
      c.scrollToStickerSet(18,false);
      equal(18,c.stickersView.manager.offsetPosition,"nonanimated path retains exact target position");
      equal(barHeight(),c.stickersView.manager.offset,"nonanimated group remains below group bar");
    }
    Controller forced=new Controller(true);forced.stickersAdapter.layoutParams=new Adapter.LayoutParams(-1,-1,-1,-1,32);
    forced.scrollToStickerSet(18,true);equal(headerHeight(true)+64,forced.stickersView.scrolled,"explicit forced sticker height still wins");
  }
  static void legacyCase(){
    Controller c=new Controller(true);
    int old=c.stickersAdapter.measureScrollTop(18,8,1,c.stickerSets,c.stickersView,false);
    equal(barHeight()+headerHeight(true)+2*(Screen.smallestSide()/8),old,"existing six-argument callers preserve trending fallback");
    int measured=c.stickersAdapter.measureScrollTop(18,8,1,c.stickerSets,c.stickersView,false,true);
    equal(barHeight()+headerHeight(true)+2*(450/8),measured,"emoji opt-in overrides trending fallback with measured width");
    c.stickersView.width=0;
    equal(old,c.stickersAdapter.measureScrollTop(18,8,1,c.stickerSets,c.stickersView,false,true),"unmeasured recycler falls back safely");
  }
  public static void main(String[] args){if(args[0].equals("scroll"))scrollCases();else legacyCase();System.out.println(args[0]+": "+checks+" production checks passed");}
}
"""


def compile_harness(directory,broken=None):
    source=Path(directory)/"EmojiStatusScrollHarness.java"
    source.write_text(source_for(broken),encoding="utf-8")
    subprocess.run(["javac","-d",directory,str(source)],check=True)


class EmojiStatusScrollTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="emoji-status-scroll-")
        compile_harness(cls.temp.name)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def run_case(self,case):
        subprocess.run(["java","-cp",self.temp.name,"EmojiStatusScrollHarness",case],check=True,timeout=15)

    def test_measured_current_and_target_offsets_include_first_trending(self): self.run_case("scroll")
    def test_existing_adapter_callers_preserve_their_geometry(self): self.run_case("legacy")

    def test_negative_controls_detect_screen_based_row_height(self):
        for broken,message in (("current","current scroll origin"),("target","animated group target"),("trending","animated group target")):
            with self.subTest(broken=broken),tempfile.TemporaryDirectory(prefix="emoji-status-scroll-broken-") as directory:
                compile_harness(directory,broken)
                result=subprocess.run(["java","-cp",directory,"EmojiStatusScrollHarness","scroll"],text=True,capture_output=True,timeout=15)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(message,result.stderr)


if __name__=="__main__": unittest.main()
