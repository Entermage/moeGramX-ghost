package org.thunderdog.challegram;

public final class Log {
  private Log () { }

  public static void w (String message, Throwable throwable) {
    // Deliberately quiet in the standalone test harness.
  }
}
