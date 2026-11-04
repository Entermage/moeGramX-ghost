package org.thunderdog.challegram.telegram;

import androidx.annotation.Nullable;

import org.drinkless.tdlib.TdApi;

import java.util.ArrayList;
import java.util.List;

/** Transport double: requests are recorded and answered by the test, UI work is queued. */
public class Tdlib {
  public interface ResultHandler<T extends TdApi.Object> {
    void onResult (T result, @Nullable TdApi.Error error);
  }

  public static final class Sent {
    public final TdApi.Function<?> function;
    final ResultHandler<TdApi.Object> handler;
    boolean answered;
    Sent (TdApi.Function<?> function, ResultHandler<TdApi.Object> handler) { this.function = function; this.handler = handler; }
    public void answer (TdApi.Object result, TdApi.Error error) {
      if (answered) throw new AssertionError("TDLib answers a request once");
      answered = true;
      handler.onResult(result, error);
    }
  }

  public final class Ui {
    final List<Runnable> queue = new ArrayList<>();
    final List<Runnable> delayed = new ArrayList<>();
    public boolean post (Runnable r) { queue.add(r); return true; }
    public boolean postDelayed (Runnable r, long delay) { delayed.add(r); return true; }
    public void removeCallbacks (Runnable r) { delayed.remove(r); queue.remove(r); }
    public void flush () { while (!queue.isEmpty()) queue.remove(0).run(); }
    public void runDelayed () { List<Runnable> copy = new ArrayList<>(delayed); delayed.clear(); for (Runnable r : copy) r.run(); flush(); }
  }

  public final class Listeners {
    public final List<CleanupStartupDelegate> delegates = new ArrayList<>();
    public void addCleanupListener (CleanupStartupDelegate delegate) { delegates.add(delegate); }
    /** What Tdlib.updateAuthState does on AuthorizationStateClosed, on the TDLib thread. */
    public void performRestart () { for (CleanupStartupDelegate d : delegates) d.onPerformRestart(); }
  }

  private final int id;
  private final Ui ui = new Ui();
  private final Listeners listeners = new Listeners();
  public final List<Sent> sent = new ArrayList<>();

  public Tdlib (int id) { this.id = id; }
  public int id () { return id; }
  public Ui ui () { return ui; }
  public Listeners listeners () { return listeners; }

  @SuppressWarnings("unchecked")
  public <T extends TdApi.Object> void send (TdApi.Function<T> function, ResultHandler<T> handler) {
    sent.add(new Sent(function, (ResultHandler<TdApi.Object>) (ResultHandler<?>) handler));
  }

  public List<Sent> unanswered () {
    List<Sent> list = new ArrayList<>();
    for (Sent s : sent) if (!s.answered) list.add(s);
    return list;
  }
}
