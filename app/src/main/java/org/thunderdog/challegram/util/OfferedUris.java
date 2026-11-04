/*
 * This file is a part of moegramX.
 * Licensed under the GNU General Public License, version 3 or later.
 */
package org.thunderdog.challegram.util;

import android.net.Uri;

import androidx.annotation.Nullable;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * This app's own content URIs that it just handed to other apps on the user's request (share sheet,
 * "open with"). Choosing this app there sends them back through the external share entry, which otherwise
 * refuses this app's providers. In memory only, bounded and short-lived.
 */
public final class OfferedUris {
  private OfferedUris () { }

  static final long TTL_NANOS = 15L * 60L * 1_000_000_000L;
  static final int MAX_URIS = 256;

  private static final LinkedHashMap<String, Long> offered = new LinkedHashMap<>();

  private static String key (Uri uri) {
    return uri.normalizeScheme().toString();
  }

  public static void remember (@Nullable Uri uri) {
    if (uri == null || !"content".equals(uri.normalizeScheme().getScheme())) {
      return;
    }
    remember(uri, System.nanoTime());
  }

  static synchronized void remember (Uri uri, long now) {
    String key = key(uri);
    offered.remove(key);
    offered.put(key, now);
    trim(now);
  }

  public static boolean wasOffered (@Nullable Uri uri) {
    return uri != null && wasOffered(uri, System.nanoTime());
  }

  static synchronized boolean wasOffered (Uri uri, long now) {
    trim(now);
    return offered.containsKey(key(uri));
  }

  private static void trim (long now) {
    Iterator<Map.Entry<String, Long>> iterator = offered.entrySet().iterator();
    while (iterator.hasNext()) {
      Map.Entry<String, Long> entry = iterator.next();
      if (offered.size() > MAX_URIS || now - entry.getValue() > TTL_NANOS) {
        iterator.remove();
      } else {
        break; // Insertion order: the rest are newer.
      }
    }
  }
}
