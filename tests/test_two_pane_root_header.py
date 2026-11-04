"""Run the production header fade-out and direct title setup for the two-pane root on fold."""
from pathlib import Path
import subprocess
import unittest
from test_preview_filter import run_java

HEADER = Path(__file__).resolve().parents[1] / 'app/src/main/java/org/thunderdog/challegram/navigation/HeaderView.java'


def block(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


class RootHeaderTest(unittest.TestCase):
    def run_header(self, drop=()):
        header = HEADER.read_text()
        fade = block(header, '    if (useBackFade) {', '    if (useFloatSwitch == 2) {')
        set_title = header[header.index('  public void setTitle (ViewController<?> item) {'):]
        menu = block(set_title, '    if (item.getMenuId() != menu.getId()) {', '    View v = item.getCustomHeaderCell();')
        back = block(set_title, '    if (item.getBackButton() != BackHeaderButton.TYPE_NONE) {', '    if (item.getCustomHeaderCell() != null) {')
        for line in drop:
            self.assertIn(line, menu + back)
            menu, back = menu.replace(line, ''), back.replace(line, '')
        harness = r'''
import java.util.ArrayList;
public class RootHeaderHarness {
  static class View {
    static final int VISIBLE = 0, GONE = 8;
    float alpha = 1f, x, y; int visibility = VISIBLE;
    void setAlpha (float a) { alpha = a; }
    void setTranslationX (float v) { x = v; }
    void setTranslationY (float v) { y = v; }
    float getTranslationX () { return x; }
    void setVisibility (int v) { visibility = v; }
  }
  static class BackHeaderButton extends View {
    static final int TYPE_NONE = 1, TYPE_MENU = 2, TYPE_BACK = 3, TYPE_CLOSE = 4;
    float factor;
    static float toButtonFactor (int type) { return type == TYPE_BACK ? 1f : type == TYPE_CLOSE ? 2f : 0f; }
    void setButtonFactor (int type) { if (type != TYPE_NONE) factor = toButtonFactor(type); }
    void setFactor (float f) { factor = f; }
    void setBackgroundResource (int res) { }
    void setColor (int color) { }
  }
  static class LayoutParams { int width = 56; }
  static class Child extends View { LayoutParams getLayoutParams () { return new LayoutParams(); } }
  static class LinearLayout extends View {
    int id; final ArrayList<Child> children = new ArrayList<>();
    int getId () { return id; }
    void setId (int id) { this.id = id; }
    void removeAllViews () { children.clear(); }
    int getChildCount () { return children.size(); }
    Child getChildAt (int i) { return children.get(i); }
  }
  static class Size { static int getHeaderPortraitSize () { return 56; } }
  static class Theme { static int getColor (int id) { return id; } }
  interface Menu { void fillMenuItems (int id, RootHeaderHarness header, LinearLayout menu); }
  static class ViewController<T> implements Menu {
    final int back, menuId; final float fillY;
    ViewController (int back, int menuId, float fillY) { this.back = back; this.menuId = menuId; this.fillY = fillY; }
    int getBackButton () { return back; }
    int getMenuId () { return menuId; }
    int getBackButtonResource () { return 0; }
    int getHeaderIconColorId () { return 0; }
    int getHeaderIconColor () { return 0; }
    // TranslationControllerV2 offsets the back button while its menu is filled.
    public void fillMenuItems (int id, RootHeaderHarness header, LinearLayout menu) {
      menu.children.add(new Child());
      if (fillY != 0f) header.backButton.setTranslationY(fillY);
    }
  }

  static final int MODE_VERTICAL = 2;
  final BackHeaderButton backButton = new BackHeaderButton();
  final LinearLayout menu = new LinearLayout();
  View title = new View(), preview = new View(), textTitle = new View();
  boolean useBackFade, backFade; int translationMode;
  float fromBackButtonFactor, toBackButtonFactor;
  int getEffectiveTopOffset () { return 24; }
  int getCurrentHeaderOffset () { return 0; }
  void updateTextMargins (View title, ViewController<?> item, int width, int offset) { }

  /** Production frame of the header transition, limited to the back button. */
  void fade (float raptor) {
@@FADE@@
  }

  /** Production direct title setup, limited to the menu and the back button. */
  void setTitleButtons (ViewController<?> item) {
@@MENU@@
@@BACK@@
  }

  static void check (boolean ok, String reason) { if (!ok) throw new AssertionError(reason); }

  public static void main (String[] args) {
    for (float titleX : new float[] {0f, 640f}) {
      RootHeaderHarness h = new RootHeaderHarness();
      // Wide: the right pane's chat is closed back to its hidden root (no back button, no menu).
      h.menu.setId(7); h.menu.children.add(new Child());
      h.backButton.setButtonFactor(BackHeaderButton.TYPE_BACK);
      h.title.setTranslationX(titleX);
      h.useBackFade = true; h.backFade = false;
      h.fromBackButtonFactor = h.toBackButtonFactor = 1f;
      h.fade(1f);
      h.menu.setAlpha(0f); // the closed chat's menu fades out in the same frame
      h.backButton.setVisibility(View.GONE); h.menu.setVisibility(View.GONE); // clearPreview
      check(h.backButton.alpha == 0f && h.backButton.x == titleX, "fixture is not the faded-out button");

      // Fold: the same root now owns the menu button and the main menu.
      h.setTitleButtons(new ViewController<Void>(BackHeaderButton.TYPE_MENU, 9, 0f));
      check(h.backButton.visibility == View.VISIBLE && h.backButton.factor == 0f, "menu button not restored");
      check(h.backButton.alpha == 1f, "menu button stays transparent after fold");
      check(h.backButton.x == 0f, "menu button stays displaced after fold");
      check(h.menu.visibility == View.VISIBLE && h.menu.alpha == 1f, "header actions stay transparent after fold");
    }

    // A controller that offsets its back button while filling its menu keeps that offset.
    RootHeaderHarness h = new RootHeaderHarness();
    h.backButton.setTranslationY(-80f);
    h.setTitleButtons(new ViewController<Void>(BackHeaderButton.TYPE_BACK, 5, 7.5f));
    check(h.backButton.y == 7.5f && h.backButton.alpha == 1f, "fillMenuItems back button offset was reset");

    // Hiding still hides: the next animated transition sets its own start alpha.
    h.setTitleButtons(new ViewController<Void>(BackHeaderButton.TYPE_NONE, 0, 0f));
    check(h.backButton.visibility == View.GONE && h.menu.visibility == View.GONE, "hidden root shows buttons");
    System.out.println("two-pane root header checks passed");
  }
}
'''.replace('@@FADE@@', fade).replace('@@MENU@@', menu).replace('@@BACK@@', back)
        run_java({'RootHeaderHarness.java': harness}, 'RootHeaderHarness')

    def test_production_fold_restores_root_buttons(self):
        self.run_header()

    def test_transparent_menu_button_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_header(drop=('      backButton.setAlpha(1f);\n',))
        self.assertEqual(caught.exception.cmd[0], 'java')

    def test_displaced_menu_button_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_header(drop=('      backButton.setTranslationX(0f);\n',))
        self.assertEqual(caught.exception.cmd[0], 'java')

    def test_transparent_header_actions_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_header(drop=('        menu.setAlpha(1f); // may still hold the faded-out buttons of an earlier transition\n',))
        self.assertEqual(caught.exception.cmd[0], 'java')


if __name__ == '__main__':
    unittest.main()
