"""Production PiP layout/settling and actual forceFactor callback regressions.

Android input, video rendering and physical folding require device validation.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / 'app/src/main/java/org/thunderdog/challegram/mediaview/MediaViewController.java'
ROUND = ROOT / 'app/src/main/java/org/thunderdog/challegram/player/RoundVideoController.java'
ANIMATOR = ROOT / 'vkryl/android/src/main/java/me/vkryl/android/animator/FactorAnimator.java'


def inside(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class VideoPipPositionTest(unittest.TestCase):
    def harness(self, variant='fixed'):
        methods = '\n'.join(block(MEDIA, signature) for signature in (
            'private void checkPipLayoutSize (int width, int height)',
            'private void updatePipLayout (int viewWidth, int viewHeight, boolean byLayout, boolean allowControlsHide)',
            'private void preparePipMovement ()',
            'private static float calculatePipPosition (int offset, int full, float pipFactor, float position)',
            'private void normalizePipPosition (float velocityX, float velocityY, boolean allowHide)',
            'private void applyPipPosition ()',
            'private void setPipPositionFactor (float factor)',
            'private void movePip (float dx, float dy, int viewWidth, int viewHeight)',
        ))
        if variant == 'legacy-rect-reset':
            start = methods.index('    if (pipPositionAnimator != null) {\n      pipPositionAnimator.cancel();\n    }', methods.index('private void normalizePipPosition'))
            end = methods.index('\n\n    fromPipAddX', start)
            methods = methods[:start] + '''    if (pipPositionAnimator == null) {
      pipPositionAnimator = new FactorAnimator(ANIMATOR_PIP_POSITION, this, AnimatorUtils.DECELERATE_INTERPOLATOR, 180);
    } else {
      pipPositionAnimator.forceFactor(0f);
    }''' + methods[end:]
        if variant == 'legacy-resize':
            methods = methods.replace('    checkPipLayoutSize(viewWidth, viewHeight);', '')
        round_source = ROUND.read_text().split('private static class InterceptPipLayout', 1)[1]
        round_methods = '\n'.join(inside(round_source, signature) for signature in (
            'private void animateGravity (int gravity, float velocity)',
            'public void onFactorChanged (int id, float factor, float fraction, FactorAnimator callee)',
            'public void onFactorChangeFinished (int id, float finalFactor, FactorAnimator callee)',
        ))
        if variant == 'legacy-round-reset':
            start = round_methods.index('      if (positionAnimator != null)')
            end = round_methods.index('\n\n      this.fromX', start)
            round_methods = round_methods[:start] + '''      if (positionAnimator == null) {
        positionAnimator = new FactorAnimator(0, this, AnimatorUtils.DECELERATE_INTERPOLATOR, 180l, 0f);
      } else {
        positionAnimator.forceFactor(0f);
      }''' + round_methods[end:]
        factor = '\n'.join(block(ANIMATOR, signature) for signature in (
            'private boolean setFactor (float factor, float fraction)',
            'public void forceFactor (float factor)',
        ))
        return r"""
public class PipPositionHarness {
  static class Screen {
    static int dp(float x) { return Math.round(x*1.5f); }
    static int getTouchSlopBig() { return 16; }
  }
  static class HeaderView { static int getSize(boolean x) { return 84; } }
  static class Build {
    static class VERSION { static int SDK_INT=35; }
    static class VERSION_CODES { static int LOLLIPOP=21; }
  }
  static class AnimatorUtils { static final Object DECELERATE_INTERPOLATOR=null; }
  static class FrameLayoutFix {
    static class LayoutParams { int width,height,gravity,leftMargin=12,rightMargin=12,topMargin=110,bottomMargin=12; }
  }
  static class ViewGroup {
    int w=1600,h=1200;
    int getMeasuredWidth() { return w; }
    int getMeasuredHeight() { return h; }
  }
  static class View extends ViewGroup {
    static final int GONE=8,VISIBLE=0;
    float tx,ty,sx=1,sy=1,alpha=1;
    int visibility=VISIBLE,left,top,layoutRequests;
    Object parent;
    final FrameLayoutFix.LayoutParams params=new FrameLayoutFix.LayoutParams();
    void setScaleX(float x) { sx=x; }
    void setScaleY(float x) { sy=x; }
    void setTranslationX(float x) { tx=x; }
    void setTranslationY(float x) { ty=x; }
    float getTranslationX() { return tx; }
    float getTranslationY() { return ty; }
    int getLeft() { return left; }
    int getTop() { return top; }
    Object getParent() { return parent; }
    void invalidateOutline() { }
    void setAlpha(float x) { alpha=x; }
    int getVisibility() { return visibility; }
    void setVisibility(int x) { visibility=x; }
    Object getLayoutParams() { return params; }
    void setLayoutParams(Object p) { layoutRequests++; }
  }
  static class CircleFrameLayout extends View { }
  static class Item { int getWidth() { return 1920; } int getHeight() { return 1080; } }
  interface Target {
    void onFactorChanged(int id,float factor,float fraction,FactorAnimator animator);
    void onFactorChangeFinished(int id,float factor,FactorAnimator animator);
  }
  static class FactorAnimator {
    final int id; final Target target;
    float factor; boolean isAnimating;
    FactorAnimator(int id,Target target,Object interpolator,long duration) { this(id,target,interpolator,duration,0); }
    FactorAnimator(int id,Target target,Object interpolator,long duration,float factor) { this.id=id;this.target=target;this.factor=factor; }
    boolean isAnimating() { return isAnimating; }
    boolean cancel() { boolean old=isAnimating;isAnimating=false;return old; }
    void animateTo(float target) { isAnimating=true; }
    void tick(float f) {
      if(!isAnimating)return;
      setFactor(f,f);
      if(f==1) { isAnimating=false;target.onFactorChangeFinished(id,f,this); }
    }
    __FACTOR__
  }
  static class Controller implements Target {
    static final int ANIMATOR_PIP_POSITION=11;
    final View mediaView=new View(),pipControlsWrap=new View();
    final Item pipItem=new Item();
    int pipWidth,pipHeight,pipLayoutWidth,pipLayoutHeight,saves;
    float pipX,pipY,pipFactor=1,pipXFactor=1,pipYFactor=-1;
    float pipStartX,pipStartY,pipAddX,pipAddY,fromPipAddX,fromPipAddY,toPipAddX,toPipAddY,toPipXFactor,toPipYFactor;
    boolean isPipUp,listenCatchPip,hidden;
    FactorAnimator pipPositionAnimator;
    void setPipHidden(boolean hidden,boolean left) { this.hidden=hidden; }
    void animatePipUpFactor(boolean up) { }
    void savePipFactors() { saves++; }
    public void onFactorChanged(int id,float factor,float fraction,FactorAnimator a) { setPipPositionFactor(factor); }
    public void onFactorChangeFinished(int id,float factor,FactorAnimator a) { applyPipPosition(); }
    __METHODS__
    void layout() { updatePipLayout(mediaView.w,mediaView.h,false,false); }
    void resize(int w,int h) { mediaView.w=w;mediaView.h=h;updatePipLayout(w,h,true,true); }
    void drag(float dx,float dy) { preparePipMovement();movePip(dx,dy,mediaView.w,mediaView.h); }
  }
  static class RoundContext {
    final CircleFrameLayout pipPlayerView=new CircleFrameLayout();
    int applied;
    RoundContext() { pipPlayerView.parent=new ViewGroup();pipPlayerView.left=1400;pipPlayerView.top=110; }
    void applyPipGravity(int gravity) { applied++;pipPlayerView.tx=0;pipPlayerView.ty=0; }
  }
  static int getPlayerPipSize() { return 150; }
  static boolean isRightGravity(int gravity) { return (gravity&1)!=0; }
  static boolean isBottomGravity(int gravity) { return (gravity&2)!=0; }
  static class Round implements Target {
    final RoundContext context=new RoundContext();
    FactorAnimator positionAnimator;
    float fromX,fromY,toX,toY; int toGravity;
    void setPlayerTranslate(float x,float y) { context.pipPlayerView.tx=x;context.pipPlayerView.ty=y; }
    __ROUND__
  }
  static int checks;
  static void check(boolean ok,String reason) { checks++;if(!ok)throw new AssertionError(reason); }
  static void equal(float a,float b,String reason) { check(Math.abs(a-b)<.01f,reason+" actual="+a+" expected="+b); }
  static Controller fixture() { Controller c=new Controller();c.layout();return c; }
  static void sameDock(Controller c,String reason) {
    Controller dock=fixture();dock.pipXFactor=c.pipXFactor;dock.pipYFactor=c.pipYFactor;
    dock.resize(c.mediaView.w,c.mediaView.h);
    equal(c.mediaView.tx,dock.mediaView.tx,reason+" X");
    equal(c.mediaView.ty,dock.mediaView.ty,reason+" Y");
  }
  public static void main(String[] args) {
    if(args.length==0 || args[0].equals("repeat")) {
      Controller c=fixture();
      c.drag(-200,75);float before=c.mediaView.tx;c.normalizePipPosition(0,0,false);
      equal(c.mediaView.tx,before,"First release keeps actual drag origin");
      c.pipPositionAnimator.tick(1);sameDock(c,"First completion uses dock factors");
      c.drag(-1000,100);before=c.mediaView.tx;c.normalizePipPosition(0,0,false);
      equal(c.mediaView.tx,before,"Second release must not replay previous drag");
      c.pipPositionAnimator.tick(.5f);c.pipPositionAnimator.tick(1);sameDock(c,"Second completion immediately redraws dock");
      c.drag(900,-400);before=c.mediaView.tx;c.normalizePipPosition(0,0,false);
      equal(c.mediaView.tx,before,"Third release keeps its own origin");
      c.pipPositionAnimator.tick(1);sameDock(c,"Third completion redraws dock");
    }
    if(args.length==0 || args[0].equals("resize")) {
      Controller c=fixture();c.drag(-1000,100);c.normalizePipPosition(0,0,false);
      FactorAnimator old=c.pipPositionAnimator;old.tick(.4f);
      float targetX=c.toPipXFactor,targetY=c.toPipYFactor;
      c.resize(900,1800);
      check(!old.isAnimating(),"Resize must cancel old pixel animator");
      equal(c.pipXFactor,targetX,"Resize keeps intended horizontal dock");
      equal(c.pipYFactor,targetY,"Resize keeps intended vertical dock");
      sameDock(c,"Resize computes fresh dock immediately");
      float after=c.mediaView.tx;old.tick(1);equal(c.mediaView.tx,after,"Cancelled animator cannot overwrite resized coordinates");
      int requests=c.pipControlsWrap.layoutRequests;c.resize(900,1800);
      check(c.pipControlsWrap.layoutRequests==requests,"Same-size measure does not schedule another controls layout");
      c.isPipUp=true;c.listenCatchPip=true;c.drag(100,150);c.resize(1600,1200);
      check(!c.isPipUp && !c.listenCatchPip && c.pipAddX==0 && c.pipAddY==0,
        "Resize discards drag coordinates from the old window");
      sameDock(c,"Resize during drag restores stable dock");
      c.pipXFactor=2;c.layout();c.resize(900,1600);
      equal(c.pipXFactor,2,"Intentionally hidden edge factor survives resize");sameDock(c,"Hidden edge uses new window");
    }
    if(args.length==0 || args[0].equals("round")) {
      Round r=new Round();r.context.pipPlayerView.tx=-200;r.animateGravity(1,-1);r.positionAnimator.tick(1);
      r.context.pipPlayerView.tx=-500;r.context.pipPlayerView.ty=100;
      int applied=r.context.applied;r.animateGravity(0,-1);
      equal(r.context.pipPlayerView.tx,-500,"Round second release must not replay old callbacks");
      equal(r.fromX,-500,"Round new animation captures actual dragged position");
      check(r.context.applied==applied,"Round reset must not prematurely apply gravity");
      r.positionAnimator.tick(1);check(r.context.applied==applied+1,"Round target applies once on actual completion");
    }
    System.out.println("PiP position: "+checks+" production checks passed");
  }
}
""".replace('__METHODS__', methods).replace('__ROUND__', round_methods).replace('__FACTOR__', factor)

    def run_variant(self, variant, scenario=None):
        with tempfile.TemporaryDirectory(prefix='video-pip-') as directory:
            source = Path(directory) / 'PipPositionHarness.java'
            source.write_text(self.harness(variant), encoding='utf-8')
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', directory, str(source)], check=True)
            return subprocess.run(['java','-cp',directory,'PipPositionHarness'] + ([scenario] if scenario else []),
                                  text=True, capture_output=True)

    def test_production_drag_resize_and_round_settling(self):
        result=self.run_variant('fixed')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        print(result.stdout.strip())

    def test_old_animator_reset_reproduces_repeat_drag_jump(self):
        result=self.run_variant('legacy-rect-reset','repeat')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Second release must not replay previous drag',result.stderr)

    def test_old_resize_leaves_stale_pixel_target_running(self):
        result=self.run_variant('legacy-resize','resize')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Resize must cancel old pixel animator',result.stderr)

    def test_round_old_reset_replays_old_callbacks(self):
        result=self.run_variant('legacy-round-reset','round')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Round second release must not replay old callbacks',result.stderr)


if __name__ == '__main__': unittest.main()
