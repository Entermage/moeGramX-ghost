"""Production header visibility/offset regression; real playback still needs Android."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_chat_navigation import block

ROOT = Path(__file__).resolve().parents[1]
NAV = ROOT / 'app/src/main/java/org/thunderdog/challegram/navigation/NavigationController.java'
FILLING = ROOT / 'app/src/main/java/org/thunderdog/challegram/navigation/HeaderFilling.java'
PANE = ROOT / 'app/src/main/java/moe/kirao/mgx/layout/MoexTwoPane.java'


class TwoPanePlayerTest(unittest.TestCase):
    def harness(self):
        navigation = '\n'.join(block(NAV, x) for x in (
            'public NavigationController (Context context)',
            'public NavigationController (Context context, boolean ownsGlobalOngoingBar)',
            'public boolean ownsGlobalOngoingBar ()',
        ))
        methods = '\n'.join(block(FILLING, x) for x in (
            'private boolean canBuildSection (int section)',
            'private void setShowOngoingSection (int section, boolean isShowing, boolean needRebuild, boolean force)',
            'private void buildSection (int section)',
            'private void showHideAnimated (boolean show, boolean force)',
            'private void setShowFactor (float playerFactor)',
            'public int getPlayerOffset ()',
            'private boolean hasVisibleOngoingBar ()',
            'public void layout ()',
        ))
        return r"""
public class PanePlayerHarness {
  static class Context { }
  static class NavigationProcessor { NavigationProcessor(NavigationController n) { } }
  static class NavigationController {
    final Context context;
    final boolean ownsGlobalOngoingBar;
    NavigationProcessor processor;
    float offset;
    __NAVIGATION__
    ViewController<?> getCurrentStackItem() { return null; }
    void applyPlayerOffset(float factor, float offset) { this.offset = offset; }
  }
  static class ViewController<T> { boolean usePopupMode() { return false; } }
  static class HeaderView {
    static int getPlayerSize() { return 36; }
    Object getContext() { return null; }
  }
  static class Round { void checkLayout() { } }
  static class UI {
    static UI getContext(Object x) { return new UI(); }
    Round getRoundVideoController() { return new Round(); }
  }
  static class AnimatorUtils { static final Object DECELERATE_INTERPOLATOR = null; }
  static class FactorAnimator {
    FactorAnimator(int id, Object target, Object interpolator, long time, float factor) { }
    void animateTo(float value) { }
    void forceFactor(float value) { }
  }
  static class BitwiseUtils {
    static boolean hasFlag(int value, int flag) { return (value & flag) != 0; }
    static int setFlag(int value, int flag, boolean enabled) { return enabled ? value | flag : value & ~flag; }
  }
  static class Filling {
    static final int SECTION_BIRTHDAY=1, SECTION_AUDIO=2, SECTION_CALL=4, ANIMATOR_SHOW_ID=0;
    final NavigationController navigationController;
    final boolean ongoingBarEnabled;
    final HeaderView headerView = new HeaderView();
    float showFactor, hideFactor, dropShadowAlpha=1;
    int ongoingSections, lastBarType, builtAudio, builtCall, builtBirthday;
    boolean showOngoingBar;
    FactorAnimator barShowAnimator;
    Filling(NavigationController navigationController) {
      this.navigationController = navigationController;
      this.ongoingBarEnabled = navigationController == null || navigationController.ownsGlobalOngoingBar();
    }
    void buildAudio() { builtAudio++; }
    void buildCall() { builtCall++; }
    void buildBirthday() { builtBirthday++; }
    void invalidate() { }
    void invalidateOngoingBar() { }
    void layoutOngoingBar() { }
    __METHODS__
  }
  static int checks;
  static void check(boolean ok, String message) {
    checks++; if(!ok) throw new AssertionError(message);
  }
  static int visible(Filling a, Filling b) {
    return (a.hasVisibleOngoingBar()?1:0)+(b.hasVisibleOngoingBar()?1:0);
  }
  public static void main(String[] args) {
    NavigationController primary = new NavigationController(new Context());
    NavigationController auxiliary = new NavigationController(new Context(), args.length != 0);
    Filling right = new Filling(primary), left = new Filling(auxiliary);
    right.setShowOngoingSection(Filling.SECTION_AUDIO,true,true,true);
    left.setShowOngoingSection(Filling.SECTION_AUDIO,true,true,true);
    check(visible(right,left)==1,"Exactly one global media bar must be visible");
    check(right.getPlayerOffset()==36 && primary.offset==36,"Primary media bar reserves its actual height");
    check(left.getPlayerOffset()==0 && auxiliary.offset==0 && left.ongoingSections==0,
      "Auxiliary bar must not leave duplicate header height or sections");
    left.setShowOngoingSection(Filling.SECTION_CALL,true,true,true);
    left.setShowOngoingSection(Filling.SECTION_BIRTHDAY,true,true,true);
    check(visible(right,left)==1 && left.builtCall==0 && left.builtBirthday==0,
      "Global call and birthday updates cannot create an auxiliary bar");
    right.setShowOngoingSection(Filling.SECTION_CALL,true,true,true);
    check(right.lastBarType==Filling.SECTION_CALL && right.builtCall==1,
      "Primary call priority is retained over audio");
    right.setShowOngoingSection(Filling.SECTION_CALL,false,true,true);
    check(right.showOngoingBar && primary.offset==36,"Ending call reveals the existing audio bar");
    right.setShowOngoingSection(Filling.SECTION_AUDIO,false,true,true);
    check(visible(right,left)==0 && primary.offset==0 && auxiliary.offset==0,
      "Stopping playback releases both drawing and reserved height");
    right.setShowOngoingSection(Filling.SECTION_AUDIO,true,true,false);
    check(right.showOngoingBar && primary.offset==36,"Primary continues to own playback after a narrow layout transition");
    Filling recreatedLeft = new Filling(new NavigationController(new Context(),false));
    recreatedLeft.setShowOngoingSection(Filling.SECTION_AUDIO,true,true,true);
    check(visible(right,recreatedLeft)==1,"A recreated auxiliary pane cannot duplicate current playback");
    System.out.println("Two-pane media bar: "+checks+" production checks passed");
  }
}
""".replace('__NAVIGATION__', navigation).replace('__METHODS__', methods)

    def test_production_visibility_and_offset_with_legacy_negative_control(self):
        with tempfile.TemporaryDirectory(prefix='pane-player-') as directory:
            source = Path(directory) / 'PanePlayerHarness.java'
            source.write_text(self.harness(), encoding='utf-8')
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', directory, str(source)], check=True)
            subprocess.run(['java', '-cp', directory, 'PanePlayerHarness'], check=True)
            old = subprocess.run(['java', '-cp', directory, 'PanePlayerHarness', 'legacy-both-own'],
                                 text=True, capture_output=True)
            self.assertNotEqual(old.returncode, 0)
            self.assertIn('Exactly one global media bar', old.stderr)

    def test_registration_and_placeholder_layer_wiring(self):
        source = FILLING.read_text()
        subscriptions = block(FILLING, 'if (navigationController != null && ongoingBarEnabled)')
        self.assertIn('addTrackChangeListener(this)', subscriptions)
        self.assertIn('initCallListeners()', subscriptions)
        self.assertEqual(source.count('addTrackChangeListener(this)'), 1)
        self.assertIn('leftNavigation = new NavigationController(context, false)', PANE.read_text())
        activate = block(PANE, 'private void activate (Tdlib tdlib)')
        self.assertIn('navigation.addViewUnderHeader(placeholder)', activate)
        self.assertNotIn('container.addView(placeholder', activate)
        self.assertIn('placeholder.layout(0, 0, chatPaneWidth, height)', block(PANE, 'public void onLayout (ViewGroup parent)'))
        self.assertIn('Views.removeFromParent(placeholder)', block(PANE, 'private void detachLeft ()'))


if __name__ == '__main__':
    unittest.main()
