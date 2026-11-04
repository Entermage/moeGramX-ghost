"""Long FLOOD_WAIT timers must release a closed list without affecting another list."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_forum_scope import method

ROOT = Path(__file__).resolve().parents[1]

HARNESS = '''
import java.util.*;
public class RetryHarness {
  static class android {static class os {static class SystemClock {static long uptimeMillis(){return 0;}}}}
  static class Handler {
    static class Job {Runnable run;Object token;Job(Runnable r,Object t){run=r;token=t;}}
    List<Job> jobs=new ArrayList<>();
    void postAtTime(Runnable r,Object token,long at){jobs.add(new Job(r,token));}
    void removeCallbacks(Runnable r){jobs.removeIf(j->j.run==r);}
    void removeCallbacksAndMessages(Object token){jobs.removeIf(j->j.token==token);}
  }
  static class Listeners {
    void unsubscribeFromChatUpdates(long chat,Object owner){}
    void unsubscribeFromMessageUpdates(long chat,Object owner){}
  }
  static class Tdlib {Handler h=new Handler();Handler ui(){return h;}Listeners listeners(){return new Listeners();}}
  static class ForumRequests {static void cancel(Tdlib t,Object owner){}}
  Tdlib tdlib;boolean isDestroyed;long chatId;Object retryToken=new Object();Runnable refreshTask=()->{};
  List<Object> pendingRefresh=new ArrayList<>(),updatesWhileLoading=new ArrayList<>(),infosWhileLoading=new ArrayList<>(),fetchedWhileLoading=new ArrayList<>(),listeners=new ArrayList<>();
  RetryHarness(Tdlib t){tdlib=t;}
  METHODS
  static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
  public static void main(String[] args){
    Tdlib t=new Tdlib();int[] calls={0};RetryHarness survivor=new RetryHarness(t);
    survivor.postRetry(()->calls[0]++,86400000);
    for(int i=0;i<100;i++){
      RetryHarness closed=new RetryHarness(t);
      closed.postRetry(()->{throw new AssertionError("closed list ran");},86400000);
      closed.postRetry(()->{throw new AssertionError("closed list ran");},5000);
      closed.performDestroy();closed.performDestroy();
      closed.postRetry(()->{throw new AssertionError("late callback scheduled");},1000);
      check(t.h.jobs.size()==1,"closed list retained retry timer");
    }
    t.h.jobs.get(0).run.run();check(calls[0]==1,"another list keeps its retry");
    survivor.performDestroy();check(t.h.jobs.isEmpty(),"all timers released");
    System.out.println("retry lifecycle checks passed");
  }
}
'''


class ForumRetryLifecycleTest(unittest.TestCase):
    def run_harness(self, negative=False):
        source = (ROOT / 'app/src/main/java/moe/kirao/mgx/topics/ForumTopicList.java').read_text()
        bodies = method(source, 'private void postRetry (') + '\n' + method(source, 'public void performDestroy ()')
        if negative:
            bodies = bodies.replace('tdlib.ui().removeCallbacksAndMessages(retryToken);', '')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'RetryHarness.java'
            path.write_text(HARNESS.replace('METHODS', bodies))
            subprocess.run(['javac', str(path)], check=True, capture_output=True, text=True)
            return subprocess.run(['java', '-cp', tmp, 'RetryHarness'], capture_output=True, text=True)

    def test_production_long_wait_cleanup(self):
        result = self.run_harness()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_negative_retained_timer(self):
        result = self.run_harness(True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('retained retry timer', result.stderr)


if __name__ == '__main__':
    unittest.main()
