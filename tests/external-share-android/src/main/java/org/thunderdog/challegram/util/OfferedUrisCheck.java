package org.thunderdog.challegram.util;

import android.net.Uri;

/** Lifetime and size bounds of the production OfferedUris registry, on the real android.net.Uri. */
public final class OfferedUrisCheck {
  private OfferedUrisCheck () { }

  private static void check (boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }

  public static void run () {
    long now = System.nanoTime(); // the same monotonic clock as production entries
    Uri first = Uri.parse("content://com.ayx.mgx.provider/internal_0_photos/1.jpg");
    OfferedUris.remember(first, now);
    check(OfferedUris.wasOffered(Uri.parse("CONTENT://com.ayx.mgx.provider/internal_0_photos/1.jpg"), now), "scheme is normalized");
    check(OfferedUris.wasOffered(first, now + OfferedUris.TTL_NANOS), "offer lasts for its lifetime");
    check(!OfferedUris.wasOffered(first, now + OfferedUris.TTL_NANOS + 1), "offer expires");
    for (int i = 0; i <= OfferedUris.MAX_URIS; i++) {
      OfferedUris.remember(Uri.parse("content://com.ayx.mgx.provider/internal_0_photos/n" + i + ".jpg"), now);
    }
    check(!OfferedUris.wasOffered(Uri.parse("content://com.ayx.mgx.provider/internal_0_photos/n0.jpg"), now), "registry is bounded");
    check(OfferedUris.wasOffered(Uri.parse("content://com.ayx.mgx.provider/internal_0_photos/n" + OfferedUris.MAX_URIS + ".jpg"), now), "newest kept");
    OfferedUris.remember(null);
    OfferedUris.remember(Uri.parse("file:///storage/emulated/0/Download/a.pdf"));
    check(!OfferedUris.wasOffered(Uri.parse("file:///storage/emulated/0/Download/a.pdf")), "only content URIs are offered");
    System.out.println("OfferedUris bounds passed");
  }
}
