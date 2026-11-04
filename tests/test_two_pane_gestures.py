"""Compile the real two-pane Back router against minimal navigation state doubles.

The checks cover pane ownership, LTR/RTL edges, placeholder fallback and drawer
priority. No production routing code is copied into the harness. These JVM
checks do not verify Android input dispatch, predictive animation or rendering;
the APK still needs emulator/device validation.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/src/main/java/moe/kirao/mgx/layout/MoexTwoPaneGestures.java'
HARNESS = ROOT / 'tests/TwoPaneGesturesTest.java'

# Doubles expose state only. The production class makes every routing decision.
STUBS = {
    'androidx/annotation/Nullable.java': '''
package androidx.annotation;
public @interface Nullable { }
''',
    'androidx/activity/BackEventCompat.java': '''
package androidx.activity;
public class BackEventCompat {
  public static final int EDGE_LEFT = 0, EDGE_RIGHT = 1;
}
''',
    'org/thunderdog/challegram/core/Lang.java': '''
package org.thunderdog.challegram.core;
public class Lang {
  public static boolean RTL;
  public static boolean rtl () { return RTL; }
}
''',
    'org/thunderdog/challegram/navigation/BackPressMode.java': '''
package org.thunderdog.challegram.navigation;
public @interface BackPressMode {
  int SYSTEM_ACTION_REQUIRED = 0, NAVIGATE_BACK_IN_STACK = 1, CUSTOM_ACTION_PERFORMED = 2;
}
''',
    'org/thunderdog/challegram/navigation/NavigationController.java': '''
package org.thunderdog.challegram.navigation;
public class NavigationController {
  public boolean destroyed, animating;
  public int size = 1, mode = BackPressMode.NAVIGATE_BACK_IN_STACK;
  public boolean isDestroyed () { return destroyed; }
  public boolean isAnimating () { return animating; }
  public int getStackSize () { return size; }
  public int performOnBackPressed (boolean fromTop, boolean commit) {
    if (fromTop || commit) {
      throw new AssertionError("Choosing a predictive target must only query Back availability");
    }
    return mode;
  }
}
''',
    'org/thunderdog/challegram/navigation/DrawerController.java': '''
package org.thunderdog.challegram.navigation;
public class DrawerController {
  public boolean visible;
  public boolean isVisible () { return visible; }
}
''',
    'org/thunderdog/challegram/ui/MainController.java': '''
package org.thunderdog.challegram.ui;
import org.thunderdog.challegram.navigation.NavigationController;
public class MainController {
  public NavigationController nav;
  public NavigationController navigationController () { return nav; }
}
''',
    'moe/kirao/mgx/layout/MoexTwoPane.java': '''
package moe.kirao.mgx.layout;
import org.thunderdog.challegram.ui.MainController;
public class MoexTwoPane {
  public boolean active;
  public MainController main;
  public MainController leftMain () { return active ? main : null; }
  public boolean isActive () { return active; }
}
''',
    'org/thunderdog/challegram/BaseActivity.java': '''
package org.thunderdog.challegram;
import moe.kirao.mgx.layout.MoexTwoPane;
import org.thunderdog.challegram.navigation.DrawerController;
import org.thunderdog.challegram.navigation.NavigationController;
public class BaseActivity {
  public NavigationController nav;
  public DrawerController drawer;
  public MoexTwoPane pane;
  public NavigationController navigation () { return nav; }
  public DrawerController getDrawer () { return drawer; }
  public MoexTwoPane moexTwoPane () { return pane; }
}
''',
}


class TwoPaneGesturesTest(unittest.TestCase):
    def test_production_back_target_routing(self):
        with tempfile.TemporaryDirectory(prefix='two-pane-gestures-') as directory:
            temporary = Path(directory)
            sources = []
            for relative, text in STUBS.items():
                source = temporary / relative
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(text, encoding='utf-8')
                sources.append(str(source))
            classes = temporary / 'classes'
            subprocess.run([
                'javac', '-encoding', 'UTF-8', '-d', str(classes),
                str(SOURCE), str(HARNESS), *sources,
            ], check=True)
            subprocess.run(['java', '-cp', str(classes), 'TwoPaneGesturesTest'], check=True)


if __name__ == '__main__':
    unittest.main()
