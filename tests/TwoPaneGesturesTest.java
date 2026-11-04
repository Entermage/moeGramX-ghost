import androidx.activity.BackEventCompat;
import moe.kirao.mgx.layout.MoexTwoPane;
import moe.kirao.mgx.layout.MoexTwoPaneGestures;
import org.thunderdog.challegram.BaseActivity;
import org.thunderdog.challegram.core.Lang;
import org.thunderdog.challegram.navigation.BackPressMode;
import org.thunderdog.challegram.navigation.DrawerController;
import org.thunderdog.challegram.navigation.NavigationController;
import org.thunderdog.challegram.ui.MainController;

/** Behavioral contract for the production router; Android/navigation objects are state doubles. */
public final class TwoPaneGesturesTest {
  private static int checks;

  private static void check (boolean condition, String description) {
    checks++;
    if (!condition) {
      throw new AssertionError(description);
    }
  }

  public static void main (String[] args) {
    final int leftEdge = BackEventCompat.EDGE_LEFT, rightEdge = BackEventCompat.EDGE_RIGHT;
    check(MoexTwoPaneGestures.listNavigation(null) == null, "No Activity has no list navigation");
    BaseActivity activity = new BaseActivity();
    activity.nav = new NavigationController();
    activity.drawer = new DrawerController();
    activity.pane = new MoexTwoPane();
    activity.pane.main = new MainController();
    NavigationController list = new NavigationController();
    activity.pane.main.nav = list;

    check(MoexTwoPaneGestures.listNavigation(activity) == null,
      "A narrow window must not route to its retained, hidden list pane");
    activity.pane.active = true;
    check(MoexTwoPaneGestures.listNavigation(activity) == list,
      "A wide window exposes its separate list navigation");
    list.destroyed = true;
    check(MoexTwoPaneGestures.listNavigation(activity) == null,
      "Destroyed list navigation must not receive gestures");
    list.destroyed = false;
    activity.pane.main.nav = activity.nav;
    check(MoexTwoPaneGestures.listNavigation(activity) == null,
      "The primary stack is not a separate list pane");
    activity.pane.main.nav = list;

    check(MoexTwoPaneGestures.backTargetForEdge(activity, leftEdge) == null,
      "The list root has no navigation transition to animate");
    list.size = 2; // An archive/folder is open over the list; the right pane is still a placeholder.
    check(MoexTwoPaneGestures.backTargetForEdge(activity, leftEdge) == list,
      "LTR list-edge Back animates the archive back into the list");
    check(MoexTwoPaneGestures.backTargetForEdge(activity, rightEdge) == list,
      "With an empty right pane, right-edge prediction must match committed Back on the left");
    activity.nav.size = 2; // A chat now occupies the right pane.
    check(MoexTwoPaneGestures.backTargetForEdge(activity, rightEdge) == null,
      "With a chat open, right-edge Back keeps the primary chat navigation");
    check(MoexTwoPaneGestures.backTargetForEdge(activity, leftEdge) == list,
      "With a chat open, left-edge Back still targets the list's archive");

    list.animating = true;
    check(MoexTwoPaneGestures.backTargetForEdge(activity, leftEdge) == null,
      "A list transition already in progress cannot start another predictive transition");
    list.animating = false;
    list.mode = BackPressMode.CUSTOM_ACTION_PERFORMED;
    check(MoexTwoPaneGestures.backTargetForEdge(activity, leftEdge) == null,
      "Search or selection must close without predicting a stack pop");
    list.mode = BackPressMode.NAVIGATE_BACK_IN_STACK;

    Lang.RTL = true;
    check(MoexTwoPaneGestures.backTargetForEdge(activity, rightEdge) == list,
      "RTL reverses which screen edge belongs to the list");
    check(MoexTwoPaneGestures.backTargetForEdge(activity, leftEdge) == null,
      "RTL chat-edge Back retains the primary chat navigation");
    activity.nav.size = 1;
    check(MoexTwoPaneGestures.backTargetForEdge(activity, leftEdge) == list,
      "RTL placeholder also permits either edge to return from the visible archive");

    activity.drawer.visible = true;
    check(MoexTwoPaneGestures.closesDrawerFirst(activity),
      "A drawer above the list closes before either pane navigates");
    check(MoexTwoPaneGestures.backTargetForEdge(activity, rightEdge) == null,
      "An open drawer prevents an archive predictive transition");
    activity.pane.active = false;
    check(!MoexTwoPaneGestures.closesDrawerFirst(activity),
      "Narrow windows retain the original single-pane drawer handling");
    check(MoexTwoPaneGestures.backTargetForEdge(activity, rightEdge) == null,
      "Narrow windows never animate the retained list stack");
    check(!MoexTwoPaneGestures.closesDrawerFirst(null),
      "No Activity has no pane-specific drawer priority");

    System.out.println("Two-pane Back routing: " + checks + " production checks passed (JVM state doubles)");
  }
}
